"""Built-in deterministic benchmark packs for AgentBench V2."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
import subprocess
import textwrap
from typing import Any, Iterable

import yaml


_PACK_COMMIT_ENV = {
    "GIT_AUTHOR_NAME": "AgentBench Fixtures",
    "GIT_AUTHOR_EMAIL": "fixtures@agentbench.local",
    "GIT_COMMITTER_NAME": "AgentBench Fixtures",
    "GIT_COMMITTER_EMAIL": "fixtures@agentbench.local",
    "GIT_AUTHOR_DATE": "2026-01-01T00:00:00+00:00",
    "GIT_COMMITTER_DATE": "2026-01-01T00:00:00+00:00",
}
_RESOURCE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


@dataclass(frozen=True)
class PackTaskSpec:
    id: str
    description: str
    category: str
    difficulty: str
    tags: tuple[str, ...]
    prompt: str
    files: dict[str, str]


@dataclass(frozen=True)
class BenchmarkPack:
    id: str
    version: str
    name: str
    description: str
    tasks: tuple[PackTaskSpec, ...]


def _clean(value: str) -> str:
    return textwrap.dedent(value).lstrip("\n").rstrip() + "\n"


_DURATION_TASK = PackTaskSpec(
    id="bugfix-duration-parser",
    description="Repair a unit-conversion regression in a small duration parser.",
    category="bugfix",
    difficulty="easy",
    tags=("python", "parsing", "regression"),
    prompt=_clean(
        """
        Fix the duration parser so every existing test passes.

        The public behavior is intentionally small: parse_duration accepts a
        numeric value followed by ms, s, or m and returns seconds as a float.
        Preserve the API, reject unsupported input, and do not weaken the tests.
        Keep the change focused.
        """
    ),
    files={
        "duration.py": _clean(
            """
            import re


            _DURATION_RE = re.compile(r"^\\s*(\\d+(?:\\.\\d+)?)\\s*(ms|s|m)\\s*$")


            def parse_duration(value: str) -> float:
                match = _DURATION_RE.match(value)
                if not match:
                    raise ValueError(f"invalid duration: {value!r}")
                amount = float(match.group(1))
                unit = match.group(2)
                factors = {"ms": 1.0, "s": 1.0, "m": 60.0}
                return amount * factors[unit]
            """
        ),
        "test_duration.py": _clean(
            """
            import unittest

            from duration import parse_duration


            class DurationTests(unittest.TestCase):
                def test_seconds(self):
                    self.assertEqual(parse_duration("12s"), 12.0)

                def test_minutes(self):
                    self.assertEqual(parse_duration("1.5m"), 90.0)

                def test_milliseconds(self):
                    self.assertAlmostEqual(parse_duration("250ms"), 0.25)

                def test_whitespace(self):
                    self.assertAlmostEqual(parse_duration(" 500 ms "), 0.5)

                def test_invalid_unit(self):
                    with self.assertRaises(ValueError):
                        parse_duration("2h")


            if __name__ == "__main__":
                unittest.main()
            """
        ),
        "README.md": _clean(
            """
            # Duration fixture

            A deliberately small parser regression used by AgentBench core-v2.
            Run with python -m unittest -q.
            """
        ),
    },
)


_SLUG_TASK = PackTaskSpec(
    id="feature-slug-normalizer",
    description="Implement a deterministic text-to-slug normalization contract.",
    category="feature",
    difficulty="medium",
    tags=("python", "strings", "api-contract"),
    prompt=_clean(
        """
        Complete slugify() according to the contract encoded by the tests.

        Requirements:
        - lowercase ASCII text
        - runs of non-alphanumeric characters become one hyphen
        - no leading or trailing hyphen
        - empty/no-alphanumeric input returns an empty string
        - preserve the public function name and signature
        - use only the Python standard library
        - do not weaken or remove tests
        """
    ),
    files={
        "slug.py": _clean(
            """
            def slugify(text: str) -> str:
                return text.lower().replace(" ", "-")
            """
        ),
        "test_slug.py": _clean(
            """
            import unittest

            from slug import slugify


            class SlugifyTests(unittest.TestCase):
                def test_basic(self):
                    self.assertEqual(slugify("AgentBench V2"), "agentbench-v2")

                def test_punctuation_and_spacing(self):
                    self.assertEqual(
                        slugify("  Reliable, repeatable   agents!  "),
                        "reliable-repeatable-agents",
                    )

                def test_collapses_existing_separators(self):
                    self.assertEqual(slugify("one---two___three"), "one-two-three")

                def test_edges(self):
                    self.assertEqual(slugify("---Hello---"), "hello")

                def test_empty_semantics(self):
                    self.assertEqual(slugify("___ !!!"), "")


            if __name__ == "__main__":
                unittest.main()
            """
        ),
    },
)


_CACHE_TASK = PackTaskSpec(
    id="regression-ttl-cache",
    description="Fix boundary expiration semantics in an injectable-clock TTL cache.",
    category="regression",
    difficulty="medium",
    tags=("python", "state", "time", "edge-case"),
    prompt=_clean(
        """
        Repair TTLCache.get() so expiration semantics are correct at the exact
        deadline and stale entries are removed.

        An item is valid strictly before its expiration timestamp and expired at
        or after that timestamp. Keep the injectable clock design, preserve the
        public API, and do not weaken tests.
        """
    ),
    files={
        "ttl_cache.py": _clean(
            """
            class TTLCache:
                def __init__(self, clock):
                    self._clock = clock
                    self._items = {}

                def set(self, key, value, ttl_seconds):
                    if ttl_seconds < 0:
                        raise ValueError("ttl_seconds must be non-negative")
                    self._items[key] = (value, self._clock() + ttl_seconds)

                def get(self, key, default=None):
                    if key not in self._items:
                        return default
                    value, expires_at = self._items[key]
                    if self._clock() > expires_at:
                        del self._items[key]
                        return default
                    return value

                def __len__(self):
                    return len(self._items)
            """
        ),
        "test_ttl_cache.py": _clean(
            """
            import unittest

            from ttl_cache import TTLCache


            class FakeClock:
                def __init__(self):
                    self.now = 100.0

                def __call__(self):
                    return self.now


            class TTLCacheTests(unittest.TestCase):
                def setUp(self):
                    self.clock = FakeClock()
                    self.cache = TTLCache(self.clock)

                def test_before_deadline(self):
                    self.cache.set("k", "v", 5)
                    self.clock.now = 104.999
                    self.assertEqual(self.cache.get("k"), "v")

                def test_exact_deadline_is_expired(self):
                    self.cache.set("k", "v", 5)
                    self.clock.now = 105.0
                    self.assertIsNone(self.cache.get("k"))
                    self.assertEqual(len(self.cache), 0)

                def test_zero_ttl_is_immediately_expired(self):
                    self.cache.set("k", "v", 0)
                    self.assertEqual(self.cache.get("k", "missing"), "missing")

                def test_missing_default(self):
                    self.assertEqual(self.cache.get("missing", 7), 7)

                def test_negative_ttl_rejected(self):
                    with self.assertRaises(ValueError):
                        self.cache.set("k", "v", -1)


            if __name__ == "__main__":
                unittest.main()
            """
        ),
    },
)


_BATCH_TASK = PackTaskSpec(
    id="refactor-lazy-batching",
    description="Refactor eager batching into a lazy one-pass iterator.",
    category="refactor",
    difficulty="medium",
    tags=("python", "iterators", "memory", "refactor"),
    prompt=_clean(
        """
        Refactor chunked(iterable, size) into a lazy one-pass iterator.

        Contract:
        - yield tuples of at most size elements
        - preserve input order
        - work with one-shot iterators
        - do not eagerly consume the full input
        - raise ValueError for size <= 0 before consuming the iterable
        - use only the Python standard library
        - preserve the public function name/signature and do not weaken tests
        """
    ),
    files={
        "batch.py": _clean(
            """
            def chunked(iterable, size):
                items = list(iterable)
                return [
                    tuple(items[index:index + size])
                    for index in range(0, len(items), size)
                ]
            """
        ),
        "test_batch.py": _clean(
            """
            import unittest

            from batch import chunked


            class BatchTests(unittest.TestCase):
                def test_groups(self):
                    self.assertEqual(
                        list(chunked(range(5), 2)),
                        [(0, 1), (2, 3), (4,)],
                    )

                def test_returns_iterator(self):
                    result = chunked([1, 2, 3], 2)
                    self.assertIs(iter(result), result)

                def test_one_shot_source(self):
                    source = (value for value in range(4))
                    self.assertEqual(list(chunked(source, 3)), [(0, 1, 2), (3,)])

                def test_is_lazy(self):
                    consumed = []

                    def source():
                        for value in range(5):
                            consumed.append(value)
                            yield value

                    result = chunked(source(), 2)
                    self.assertEqual(consumed, [])
                    self.assertEqual(next(result), (0, 1))
                    self.assertEqual(consumed, [0, 1])

                def test_invalid_size_does_not_consume(self):
                    consumed = []

                    def source():
                        consumed.append("started")
                        yield 1

                    with self.assertRaises(ValueError):
                        chunked(source(), 0)
                    self.assertEqual(consumed, [])


            if __name__ == "__main__":
                unittest.main()
            """
        ),
    },
)


CORE_V2 = BenchmarkPack(
    id="core-v2",
    version="2.0.0",
    name="AgentBench Core V2",
    description=(
        "Portable deterministic Python software-engineering tasks spanning "
        "bugfix, feature, regression, and refactor work."
    ),
    tasks=(_DURATION_TASK, _SLUG_TASK, _CACHE_TASK, _BATCH_TASK),
)

SMOKE_V2 = BenchmarkPack(
    id="smoke-v2",
    version="2.0.0",
    name="AgentBench Smoke V2",
    description="Fast two-task subset of the V2 core corpus.",
    tasks=(_DURATION_TASK, _SLUG_TASK),
)

_PACKS = {pack.id: pack for pack in (CORE_V2, SMOKE_V2)}


def list_packs() -> list[dict[str, Any]]:
    return [
        {
            "id": pack.id,
            "version": pack.version,
            "name": pack.name,
            "description": pack.description,
            "task_count": len(pack.tasks),
            "tasks": [
                {
                    "id": task.id,
                    "category": task.category,
                    "difficulty": task.difficulty,
                    "tags": list(task.tags),
                }
                for task in pack.tasks
            ],
        }
        for pack in _PACKS.values()
    ]


def get_pack(pack_id: str) -> BenchmarkPack:
    try:
        return _PACKS[pack_id]
    except KeyError as exc:
        raise ValueError(
            f"Unknown benchmark pack {pack_id!r}; available: {', '.join(_PACKS)}"
        ) from exc


def parse_agent_spec(value: str) -> dict[str, str]:
    """Parse CLI syntax '<id>=<command template>' for generated manifests."""

    if "=" not in value:
        raise ValueError("Agent must use '<id>=<command template>' syntax")
    agent_id, command = value.split("=", 1)
    agent_id = agent_id.strip()
    command = command.strip()
    if not _RESOURCE_ID_RE.fullmatch(agent_id):
        raise ValueError(f"Invalid agent ID: {agent_id!r}")
    if not command:
        raise ValueError("Agent command template must not be empty")
    if "{prompt}" not in command:
        raise ValueError("Agent command template must contain {prompt}")
    return {
        "id": agent_id,
        "description": f"Agent supplied when materializing benchmark pack: {agent_id}",
        "command_template": command,
    }


def _run_git(cwd: Path, *args: str, env: dict[str, str] | None = None) -> str:
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
        env=merged_env,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise ValueError(f"Git command failed ({' '.join(args)}): {detail}")
    return result.stdout.strip()


def _materialize_repository(root: Path, task: PackTaskSpec) -> str:
    root.mkdir(parents=True, exist_ok=False)
    _run_git(root, "init", "-q")
    _run_git(root, "config", "core.autocrlf", "false")
    _run_git(root, "config", "core.filemode", "false")

    for relative_path, contents in sorted(task.files.items()):
        target = root / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(contents, encoding="utf-8", newline="\n")

    _run_git(root, "add", "-A")
    _run_git(
        root,
        "commit",
        "-q",
        "-m",
        f"AgentBench {task.id} fixture",
        env=_PACK_COMMIT_ENV,
    )
    return _run_git(root, "rev-parse", "HEAD").lower()


def materialize_pack(
    pack_id: str,
    output_dir: str | Path,
    *,
    agents: Iterable[dict[str, str]],
    repetitions: int = 5,
) -> dict[str, Any]:
    """Create deterministic local Git fixtures and a runnable suite manifest."""

    pack = get_pack(pack_id)
    destination = Path(output_dir).expanduser().resolve()
    if destination.exists() and any(destination.iterdir()):
        raise ValueError(f"Output directory is not empty: {destination}")
    destination.mkdir(parents=True, exist_ok=True)

    normalized_agents = list(agents)
    if not normalized_agents:
        raise ValueError("At least one agent is required to materialize a benchmark pack")
    ids = [agent["id"] for agent in normalized_agents]
    if len(ids) != len(set(ids)):
        raise ValueError("Agent IDs must be unique")
    if repetitions < 1 or repetitions > 100:
        raise ValueError("repetitions must be between 1 and 100")

    repo_root = destination / "repositories"
    repo_root.mkdir()
    tasks: list[dict[str, Any]] = []
    commits: dict[str, str] = {}

    for task in pack.tasks:
        repository = repo_root / task.id
        commit = _materialize_repository(repository, task)
        commits[task.id] = commit
        tasks.append(
            {
                "id": task.id,
                "description": task.description,
                "repository_path": f"repositories/{task.id}",
                "base_commit": commit,
                "agent_prompt": task.prompt,
                "test_command": "python -m unittest -q",
                "timeout": 600,
                "category": task.category,
                "difficulty": task.difficulty,
                "tags": list(task.tags),
            }
        )

    manifest = {
        "schema_version": 2,
        "id": f"agentbench-{pack.id}",
        "name": pack.name,
        "description": pack.description,
        "benchmark_pack": {
            "id": pack.id,
            "version": pack.version,
            "description": pack.description,
        },
        "agents": normalized_agents,
        "tasks": tasks,
        "experiment": {
            "tasks": [task.id for task in pack.tasks],
            "agents": ids,
            "repetitions": repetitions,
            "stop_on_error": False,
        },
    }
    manifest_path = destination / "suite.yaml"
    manifest_path.write_text(
        yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
        newline="\n",
    )

    return {
        "pack_id": pack.id,
        "pack_version": pack.version,
        "output_directory": str(destination),
        "manifest_path": str(manifest_path),
        "task_count": len(pack.tasks),
        "agent_count": len(normalized_agents),
        "repetitions": repetitions,
        "planned_runs": len(pack.tasks) * len(normalized_agents) * repetitions,
        "commits": commits,
    }


__all__ = [
    "BenchmarkPack",
    "CORE_V2",
    "PackTaskSpec",
    "SMOKE_V2",
    "get_pack",
    "list_packs",
    "materialize_pack",
    "parse_agent_spec",
]
