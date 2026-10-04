#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import textwrap
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_MODEL = "qwen3-coder-next-local"
DEFAULT_BASE_URL = "http://127.0.0.1:8080/v1"

RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["continue", "complete", "blocked"]},
        "summary": {"type": "string"},
        "tests": {"type": "string"},
        "next_objective": {"type": "string"},
        "known_issues": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["status", "summary", "tests", "next_objective", "known_issues"],
    "additionalProperties": False,
}


def run(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=cwd, text=True, capture_output=True)


def git(repo: Path, *args: str) -> str:
    p = run(["git", *args], repo)
    if p.returncode != 0:
        return f"<git {' '.join(args)} failed>\n{p.stderr.strip()}"
    return p.stdout.strip()


def repo_fingerprint(repo: Path) -> str:
    payload = "\n".join([
        git(repo, "rev-parse", "HEAD"),
        git(repo, "status", "--porcelain=v1", "-uall"),
        git(repo, "diff", "--binary"),
        git(repo, "diff", "--cached", "--binary"),
    ])
    return hashlib.sha256(payload.encode("utf-8", errors="replace")).hexdigest()


def check_server(base_url: str, api_key: str) -> tuple[bool, str]:
    req = urllib.request.Request(
        base_url.rstrip("/") + "/models",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            return True, f"HTTP {response.status}"
    except Exception as exc:
        return False, str(exc)


def extract_structured_result(stdout: str) -> dict[str, Any] | None:
    try:
        events = json.loads(stdout)
    except json.JSONDecodeError:
        return None
    if not isinstance(events, list):
        return None
    for event in reversed(events):
        if not isinstance(event, dict) or event.get("type") != "result":
            continue
        structured = event.get("structured_result")
        if isinstance(structured, dict):
            return structured
        raw = event.get("result")
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                pass
    return None


def make_prompt(index: int, total: int, overall_goal: str, previous: dict[str, Any] | None) -> str:
    previous_text = (
        json.dumps(previous, indent=2, ensure_ascii=False)[-7000:]
        if previous
        else "No previous session. Establish the current repository state yourself."
    )
    return textwrap.dedent(f"""
        You are fresh coding-agent session {index} of at most {total}.

        You are working directly in the current Git repository. The repository on disk is
        authoritative. A previous agent may have left uncommitted changes. Preserve correct
        existing work and inspect it before editing.

        OVERALL GOAL
        ============
        {overall_goal.strip()}

        PREVIOUS SESSION HANDOFF
        ========================
        {previous_text}

        SESSION PROTOCOL
        ================
        1. Start by selectively inspecting git status --short, git diff --stat,
           git log -5 --oneline, and files relevant to the current objective.
        2. Do not dump the whole repository into context.
        3. Implement the highest-value unfinished bounded slice that advances the goal.
        4. Build on correct uncommitted changes from earlier sessions.
        5. Run relevant tests and validation after editing.
        6. Fix regressions you introduce when feasible in this session.
        7. Do NOT commit, push, reset, force-checkout, or discard unrelated work.
        8. Prefer concrete implementation over speculative future architecture.
        9. Report status=complete only when the overall goal is genuinely finished and validated.
        10. Otherwise report status=continue and ONE concise next_objective.
        11. Use status=blocked only for a real external blocker another fresh session cannot solve.

        Keep the final handoff compact. The next session will inspect the repository again.
    """).strip()


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="Run multiple fresh Qwen Code sessions sequentially.")
    ap.add_argument("--repo", type=Path, default=Path.cwd())
    ap.add_argument("--goal", type=Path, required=True)
    ap.add_argument("--sessions", type=int, default=6)
    ap.add_argument("--qwen", default="qwen")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--base-url", default=DEFAULT_BASE_URL)
    ap.add_argument("--api-key", default="local")
    ap.add_argument("--auth-type", default="openai")
    ap.add_argument("--max-wall-time", default="45m")
    ap.add_argument("--max-tool-calls", type=int, default=120)
    ap.add_argument("--max-session-turns", type=int, default=80)
    ap.add_argument("--continue-on-blocked", action="store_true")
    args = ap.parse_args()

    repo = args.repo.resolve()
    goal_path = args.goal.resolve()
    if args.sessions < 1:
        ap.error("--sessions must be >= 1")
    if not repo.is_dir() or not (repo / ".git").exists():
        ap.error(f"Not a Git repository: {repo}")
    if not goal_path.is_file():
        ap.error(f"Goal file does not exist: {goal_path}")
    if shutil.which(args.qwen) is None:
        ap.error(f"Qwen executable not found on PATH: {args.qwen}")

    overall_goal = goal_path.read_text(encoding="utf-8").strip()
    if not overall_goal:
        ap.error("Goal file is empty")

    ok, message = check_server(args.base_url, args.api_key)
    if not ok:
        print(f"ERROR: local model server did not answer at {args.base_url}: {message}", file=sys.stderr)
        print("Start llama-server first, then rerun this pipeline.", file=sys.stderr)
        return 2

    git_dir_raw = git(repo, "rev-parse", "--git-dir")
    git_dir = Path(git_dir_raw)
    if not git_dir.is_absolute():
        git_dir = (repo / git_dir).resolve()
    state_root = git_dir / "qwen_pipeline"
    state_root.mkdir(parents=True, exist_ok=True)
    latest_state = state_root / "latest_handoff.json"
    previous: dict[str, Any] | None = None
    if latest_state.exists():
        try:
            previous = json.loads(latest_state.read_text(encoding="utf-8"))
        except Exception:
            previous = None

    print(f"Repository: {repo}")
    print(f"Goal:       {goal_path}")
    print(f"Sessions:   {args.sessions}")
    print(f"Server:     {args.base_url} ({message})")
    print(f"Model:      {args.model}")
    print("Mode:       fresh Qwen process each stage / YOLO / no commit or push\n")

    schema_json = json.dumps(RESULT_SCHEMA, separators=(",", ":"))

    for index in range(1, args.sessions + 1):
        session_dir = state_root / f"session_{index:02d}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        session_dir.mkdir(parents=True, exist_ok=False)
        before = repo_fingerprint(repo)
        prompt = make_prompt(index, args.sessions, overall_goal, previous)
        write_text(session_dir / "prompt.md", prompt)
        write_text(session_dir / "git-before.txt", "\n\n".join([
            "HEAD\n" + git(repo, "rev-parse", "HEAD"),
            "STATUS\n" + git(repo, "status", "--short"),
            "DIFF STAT\n" + git(repo, "diff", "--stat"),
        ]))

        cmd = [
            args.qwen,
            "--prompt", prompt,
            "--approval-mode", "yolo",
            "--auth-type", args.auth_type,
            "--model", args.model,
            "--openai-api-key", args.api_key,
            "--openai-base-url", args.base_url,
            "--output-format", "json",
            "--max-wall-time", args.max_wall_time,
            "--max-tool-calls", str(args.max_tool_calls),
            "--max-session-turns", str(args.max_session_turns),
            "--json-schema", schema_json,
        ]

        print(f"=== Session {index}/{args.sessions} ===")
        started = time.monotonic()
        try:
            proc = subprocess.run(cmd, cwd=repo, text=True, capture_output=True)
        except KeyboardInterrupt:
            print("\nInterrupted by user.")
            return 130
        elapsed = time.monotonic() - started

        write_text(session_dir / "qwen-output.json", proc.stdout)
        write_text(session_dir / "qwen-stderr.log", proc.stderr)

        result = extract_structured_result(proc.stdout)
        if result is None:
            result = {
                "status": "continue",
                "summary": f"Session ended without structured handoff; Qwen exit code={proc.returncode}.",
                "tests": "Unknown; inspect session logs and repository state.",
                "next_objective": "Inspect current repository state and continue the unfinished implementation.",
                "known_issues": ["Previous session emitted no structured completion record."],
            }

        changed = before != repo_fingerprint(repo)
        result["_pipeline"] = {
            "session_index": index,
            "qwen_exit_code": proc.returncode,
            "elapsed_seconds": round(elapsed, 2),
            "repository_changed": changed,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        }

        payload = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
        write_text(session_dir / "handoff.json", payload)
        write_text(latest_state, payload)
        write_text(session_dir / "git-after.txt", "\n\n".join([
            "HEAD\n" + git(repo, "rev-parse", "HEAD"),
            "STATUS\n" + git(repo, "status", "--short"),
            "DIFF STAT\n" + git(repo, "diff", "--stat"),
        ]))

        previous = result
        print(f"Exit code:   {proc.returncode}")
        print(f"Elapsed:     {elapsed:.1f}s")
        print(f"Repo changed:{' yes' if changed else ' no'}")
        print(f"Status:      {result.get('status')}")
        if result.get("summary"):
            print("Summary:     " + str(result["summary"]).replace("\n", " ")[:500])
        if result.get("next_objective"):
            print("Next:        " + str(result["next_objective"]).replace("\n", " ")[:500])
        print(f"Artifacts:   {session_dir}\n")

        if result.get("status") == "complete":
            print("Pipeline reports the overall goal is complete.")
            return 0
        if result.get("status") == "blocked" and not args.continue_on_blocked:
            print("Pipeline stopped because Qwen reported an external blocker.")
            return 3

    print(f"Reached configured session limit ({args.sessions}). Review {latest_state} and rerun if needed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
