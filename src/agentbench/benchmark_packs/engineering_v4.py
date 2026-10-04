"""Additional deterministic engineering tasks for the V4 benchmark corpus."""

from __future__ import annotations

import textwrap

from ..resources import TaskRequirements
from .models import PackTaskSpec


def _clean(value: str) -> str:
    return textwrap.dedent(value).lstrip("\n").rstrip() + "\n"


PYTHON_REQUIREMENTS = TaskRequirements(
    min_cpu_count=1,
    min_memory_mb=64,
    supported_platforms=("linux", "darwin", "windows"),
    required_commands=("python",),
)


_BOUNDED_RETRY_TASK = PackTaskSpec(
    id="feature-bounded-retry",
    description=(
        "Implement a bounded retry helper with explicit attempt accounting and "
        "deterministic backoff callbacks."
    ),
    category="feature",
    difficulty="medium",
    tags=("python", "reliability", "api-contract", "multi-file"),
    requirements=PYTHON_REQUIREMENTS,
    prompt=_clean(
        """
        Implement retry_call() according to the public contract in the tests.

        Requirements:
        - attempts means total attempts, not retries-after-first-attempt
        - attempts must be >= 1
        - retry only the exception types supplied through retry_on
        - invoke sleep_fn(delay) only between attempts
        - delay is base_delay * attempt_number for the failure that just occurred
        - propagate the final retryable exception unchanged
        - propagate non-retryable exceptions immediately
        - keep RetryPolicy immutable and do not weaken tests
        """
    ),
    files={
        "policy.py": _clean(
            """
            from dataclasses import dataclass


            @dataclass(frozen=True)
            class RetryPolicy:
                attempts: int = 3
                base_delay: float = 0.1

                def __post_init__(self):
                    if self.attempts < 1:
                        raise ValueError("attempts must be >= 1")
                    if self.base_delay < 0:
                        raise ValueError("base_delay must be >= 0")
            """
        ),
        "retrying.py": _clean(
            """
            from policy import RetryPolicy


            def retry_call(
                operation,
                *,
                policy=RetryPolicy(),
                retry_on=(Exception,),
                sleep_fn=lambda delay: None,
            ):
                return operation()
            """
        ),
        "test_retrying.py": _clean(
            """
            import unittest

            from policy import RetryPolicy
            from retrying import retry_call


            class RetryTests(unittest.TestCase):
                def test_succeeds_after_retry_and_records_delay(self):
                    calls = []
                    sleeps = []

                    def operation():
                        calls.append("call")
                        if len(calls) < 3:
                            raise ValueError("temporary")
                        return 42

                    result = retry_call(
                        operation,
                        policy=RetryPolicy(attempts=3, base_delay=0.25),
                        retry_on=(ValueError,),
                        sleep_fn=sleeps.append,
                    )
                    self.assertEqual(result, 42)
                    self.assertEqual(len(calls), 3)
                    self.assertEqual(sleeps, [0.25, 0.5])

                def test_final_exception_is_propagated(self):
                    marker = ValueError("still broken")

                    def operation():
                        raise marker

                    with self.assertRaises(ValueError) as caught:
                        retry_call(
                            operation,
                            policy=RetryPolicy(attempts=2, base_delay=0),
                            retry_on=(ValueError,),
                        )
                    self.assertIs(caught.exception, marker)

                def test_non_retryable_exception_is_immediate(self):
                    calls = []

                    def operation():
                        calls.append(1)
                        raise TypeError("permanent")

                    with self.assertRaises(TypeError):
                        retry_call(
                            operation,
                            policy=RetryPolicy(attempts=5),
                            retry_on=(ValueError,),
                        )
                    self.assertEqual(calls, [1])

                def test_one_attempt_never_sleeps(self):
                    sleeps = []
                    with self.assertRaises(ValueError):
                        retry_call(
                            lambda: (_ for _ in ()).throw(ValueError("x")),
                            policy=RetryPolicy(attempts=1),
                            retry_on=(ValueError,),
                            sleep_fn=sleeps.append,
                        )
                    self.assertEqual(sleeps, [])


            if __name__ == "__main__":
                unittest.main()
            """
        ),
    },
)


_JSONL_TASK = PackTaskSpec(
    id="bugfix-jsonl-reader",
    description=(
        "Repair a streaming JSONL reader so blank lines, Unicode, and malformed "
        "record diagnostics have deterministic semantics."
    ),
    category="bugfix",
    difficulty="medium",
    tags=("python", "json", "streaming", "diagnostics"),
    requirements=PYTHON_REQUIREMENTS,
    prompt=_clean(
        """
        Repair iter_jsonl() without changing its public signature.

        Contract:
        - consume the input lazily line by line
        - ignore blank/whitespace-only lines
        - preserve Unicode values
        - every nonblank record must decode to a JSON object
        - malformed JSON raises ValueError containing the 1-based source line
        - non-object JSON raises ValueError containing the 1-based source line
        - do not silently skip malformed records or weaken tests
        """
    ),
    files={
        "jsonl_reader.py": _clean(
            """
            import json


            def iter_jsonl(lines):
                for line in lines:
                    if not line:
                        continue
                    yield json.loads(line)
            """
        ),
        "test_jsonl_reader.py": _clean(
            """
            import unittest

            from jsonl_reader import iter_jsonl


            class JsonlReaderTests(unittest.TestCase):
                def test_blank_lines_are_ignored(self):
                    rows = list(iter_jsonl(['{"id": 1}\n', "   \n", '{"id": 2}\n']))
                    self.assertEqual(rows, [{"id": 1}, {"id": 2}])

                def test_unicode_is_preserved(self):
                    rows = list(iter_jsonl(['{"name": "東京"}\n']))
                    self.assertEqual(rows[0]["name"], "東京")

                def test_malformed_json_has_source_line(self):
                    with self.assertRaisesRegex(ValueError, "line 3"):
                        list(iter_jsonl(['{"ok": true}\n', "\n", "{broken}\n"]))

                def test_non_object_record_has_source_line(self):
                    with self.assertRaisesRegex(ValueError, "line 2"):
                        list(iter_jsonl(['{"ok": true}\n', "[1, 2]\n"]))

                def test_is_lazy(self):
                    consumed = []

                    def source():
                        consumed.append(1)
                        yield '{"id": 1}\n'
                        consumed.append(2)
                        yield '{"id": 2}\n'

                    rows = iter_jsonl(source())
                    self.assertEqual(consumed, [])
                    self.assertEqual(next(rows), {"id": 1})
                    self.assertEqual(consumed, [1])


            if __name__ == "__main__":
                unittest.main()
            """
        ),
    },
)


_PLUGIN_REGISTRY_TASK = PackTaskSpec(
    id="refactor-plugin-registry",
    description=(
        "Refactor a plugin registry around explicit duplicate, lazy-construction, "
        "and unknown-plugin contracts."
    ),
    category="refactor",
    difficulty="hard",
    tags=("python", "plugins", "architecture", "dependency-inversion"),
    requirements=PYTHON_REQUIREMENTS,
    prompt=_clean(
        """
        Refactor PluginRegistry while preserving its public class name.

        Required behavior:
        - register(name, factory) validates a non-empty normalized name
        - duplicate registrations are rejected
        - factories are not called during registration
        - create(name, config) calls the registered factory exactly once
        - create passes an independent shallow copy of config to the factory
        - unknown names raise KeyError with available names in deterministic order
        - names() returns a sorted tuple
        - do not introduce global registry state or weaken tests
        """
    ),
    files={
        "registry.py": _clean(
            """
            class PluginRegistry:
                def __init__(self):
                    self._plugins = {}

                def register(self, name, factory):
                    self._plugins[name] = factory
                    factory({})

                def create(self, name, config):
                    return self._plugins[name](config)

                def names(self):
                    return tuple(self._plugins)
            """
        ),
        "test_registry.py": _clean(
            """
            import unittest

            from registry import PluginRegistry


            class RegistryTests(unittest.TestCase):
                def test_registration_is_lazy(self):
                    calls = []
                    registry = PluginRegistry()
                    registry.register("alpha", lambda config: calls.append(config))
                    self.assertEqual(calls, [])

                def test_duplicate_registration_is_rejected(self):
                    registry = PluginRegistry()
                    registry.register("alpha", lambda config: config)
                    with self.assertRaises(ValueError):
                        registry.register("alpha", lambda config: config)

                def test_create_copies_config_and_calls_once(self):
                    seen = []
                    registry = PluginRegistry()

                    def factory(config):
                        seen.append(config)
                        config["mutated"] = True
                        return "instance"

                    registry.register("alpha", factory)
                    original = {"value": 3}
                    self.assertEqual(registry.create("alpha", original), "instance")
                    self.assertEqual(original, {"value": 3})
                    self.assertEqual(len(seen), 1)

                def test_unknown_error_lists_available_names(self):
                    registry = PluginRegistry()
                    registry.register("beta", lambda config: config)
                    registry.register("alpha", lambda config: config)
                    with self.assertRaisesRegex(KeyError, "alpha.*beta"):
                        registry.create("missing", {})

                def test_names_are_sorted(self):
                    registry = PluginRegistry()
                    registry.register("beta", lambda config: config)
                    registry.register("alpha", lambda config: config)
                    self.assertEqual(registry.names(), ("alpha", "beta"))

                def test_blank_name_is_rejected(self):
                    with self.assertRaises(ValueError):
                        PluginRegistry().register("   ", lambda config: config)


            if __name__ == "__main__":
                unittest.main()
            """
        ),
    },
)


_ATOMIC_CONFIG_TASK = PackTaskSpec(
    id="regression-atomic-config-store",
    description=(
        "Fix transactional configuration updates so failed validation cannot leave "
        "partial state behind."
    ),
    category="regression",
    difficulty="hard",
    tags=("python", "state", "transactions", "multi-file", "validation"),
    requirements=PYTHON_REQUIREMENTS,
    prompt=_clean(
        """
        Repair ConfigStore.update() so updates are atomic.

        Contract:
        - merge the proposed patch onto a copy of current state
        - validate the complete candidate before committing it
        - if validation raises, preserve the original state exactly
        - snapshot() returns an independent copy
        - nested dictionaries must not alias caller-owned values
        - successful updates replace nested sections using normal dict update
          semantics; recursive merging is not required
        - preserve the Validator interface and do not weaken tests
        """
    ),
    files={
        "validator.py": _clean(
            """
            class Validator:
                def validate(self, values):
                    workers = values.get("workers", 1)
                    mode = values.get("mode", "safe")
                    if workers < 1:
                        raise ValueError("workers must be >= 1")
                    if mode not in {"safe", "fast"}:
                        raise ValueError("unsupported mode")
            """
        ),
        "config_store.py": _clean(
            """
            from copy import deepcopy


            class ConfigStore:
                def __init__(self, initial, validator):
                    self._values = deepcopy(initial)
                    self._validator = validator
                    self._validator.validate(self._values)

                def update(self, patch):
                    self._values.update(patch)
                    self._validator.validate(self._values)

                def snapshot(self):
                    return self._values
            """
        ),
        "test_config_store.py": _clean(
            """
            import unittest

            from config_store import ConfigStore
            from validator import Validator


            class ConfigStoreTests(unittest.TestCase):
                def test_failed_update_rolls_back(self):
                    store = ConfigStore({"workers": 2, "mode": "safe"}, Validator())
                    with self.assertRaises(ValueError):
                        store.update({"workers": 0, "mode": "fast"})
                    self.assertEqual(
                        store.snapshot(),
                        {"workers": 2, "mode": "safe"},
                    )

                def test_successful_update_commits(self):
                    store = ConfigStore({"workers": 2, "mode": "safe"}, Validator())
                    store.update({"workers": 4})
                    self.assertEqual(store.snapshot()["workers"], 4)

                def test_snapshot_is_independent(self):
                    store = ConfigStore({"nested": {"enabled": True}}, Validator())
                    snapshot = store.snapshot()
                    snapshot["nested"]["enabled"] = False
                    self.assertTrue(store.snapshot()["nested"]["enabled"])

                def test_patch_does_not_alias_caller(self):
                    store = ConfigStore({"workers": 1}, Validator())
                    patch = {"nested": {"value": 1}}
                    store.update(patch)
                    patch["nested"]["value"] = 99
                    self.assertEqual(store.snapshot()["nested"]["value"], 1)

                def test_invalid_mode_rolls_back_other_fields(self):
                    store = ConfigStore({"workers": 1, "mode": "safe"}, Validator())
                    with self.assertRaises(ValueError):
                        store.update({"workers": 8, "mode": "turbo"})
                    self.assertEqual(
                        store.snapshot(),
                        {"workers": 1, "mode": "safe"},
                    )


            if __name__ == "__main__":
                unittest.main()
            """
        ),
    },
)


ENGINEERING_V4_EXTRA_TASKS = (
    _BOUNDED_RETRY_TASK,
    _JSONL_TASK,
    _PLUGIN_REGISTRY_TASK,
    _ATOMIC_CONFIG_TASK,
)


__all__ = ["ENGINEERING_V4_EXTRA_TASKS", "PYTHON_REQUIREMENTS"]
