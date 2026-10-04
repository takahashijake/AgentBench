from agentbench.usage import detect_agent_family, extract_usage_metadata


def test_structured_usage_extracts_nested_json_and_cumulative_maximums():
    stdout = "\n".join(
        [
            '{"type":"start","usage":{"input_tokens":10,"output_tokens":4}}',
            '{"type":"finish","usage":{"prompt_tokens":12,"completion_tokens":7,"total_tokens":19,"cached_input_tokens":3},"cost_usd":0.02}',
        ]
    )

    usage = extract_usage_metadata(stdout)

    assert usage["source"] == "structured_json_output"
    assert usage["structured_events_scanned"] == 2
    assert usage["prompt_tokens"] == 12
    assert usage["completion_tokens"] == 7
    assert usage["total_tokens"] == 19
    assert usage["cached_input_tokens"] == 3
    assert usage["cost_usd"] == 0.02


def test_usage_parser_ignores_unstructured_prose_numbers():
    usage = extract_usage_metadata(
        "prompt_tokens=999 and total_tokens=1000 but this is prose"
    )

    assert usage["source"] is None
    assert usage["prompt_tokens"] is None
    assert usage["total_tokens"] is None


def test_agent_family_detection_is_conservative():
    assert detect_agent_family("codex exec {prompt}") == "codex"
    assert detect_agent_family("/usr/local/bin/qwen -p {prompt}") == "qwen"
    assert detect_agent_family("claude --print {prompt}") == "claude"
    assert detect_agent_family("gemini -p {prompt}") == "gemini"
    assert detect_agent_family("python runner.py {prompt}") == "shell"
