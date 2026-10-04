"""Built-in benchmark corpus provider."""

from __future__ import annotations

import textwrap

from .models import BenchmarkPack, PackTaskSpec


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
    compatibility_id="agentbench-core",
)

SMOKE_V2 = BenchmarkPack(
    id="smoke-v2",
    version="2.0.0",
    name="AgentBench Smoke V2",
    description="Fast two-task subset of the V2 core corpus.",
    tasks=(_DURATION_TASK, _SLUG_TASK),
    compatibility_id="agentbench-smoke",
)


_CONFIG_OVERLAY_TASK = PackTaskSpec(
    id="bugfix-config-overlay",
    description="Repair nested configuration overlay semantics across modules.",
    category="bugfix",
    difficulty="medium",
    tags=("python", "mapping", "multi-file", "regression"),
    prompt=_clean(
        """
        Repair merge_config so nested mappings are merged recursively instead of
        replacing an entire nested section.

        Preserve the public API, do not mutate either input mapping, allow scalar
        overrides, and do not weaken tests. Keep responsibilities separated:
        defaults.py owns fixture defaults and config_merge.py owns merge behavior.
        """
    ),
    files={
        "defaults.py": _clean(
            """
            DEFAULTS = {
                "runner": {"timeout": 30, "retries": 2},
                "output": {"format": "json", "pretty": False},
            }
            """
        ),
        "config_merge.py": _clean(
            """
            from copy import deepcopy


            def merge_config(base, override):
                result = deepcopy(base)
                result.update(deepcopy(override))
                return result
            """
        ),
        "test_config_merge.py": _clean(
            """
            import unittest

            from config_merge import merge_config
            from defaults import DEFAULTS


            class MergeConfigTests(unittest.TestCase):
                def test_nested_overlay_preserves_siblings(self):
                    merged = merge_config(DEFAULTS, {"runner": {"timeout": 90}})
                    self.assertEqual(merged["runner"], {"timeout": 90, "retries": 2})

                def test_scalar_override(self):
                    merged = merge_config({"mode": "safe"}, {"mode": "fast"})
                    self.assertEqual(merged["mode"], "fast")

                def test_new_nested_key(self):
                    merged = merge_config(DEFAULTS, {"output": {"indent": 2}})
                    self.assertEqual(
                        merged["output"],
                        {"format": "json", "pretty": False, "indent": 2},
                    )

                def test_inputs_are_not_mutated(self):
                    base = {"a": {"b": 1}}
                    override = {"a": {"c": 2}}
                    merge_config(base, override)
                    self.assertEqual(base, {"a": {"b": 1}})
                    self.assertEqual(override, {"a": {"c": 2}})


            if __name__ == "__main__":
                unittest.main()
            """
        ),
    },
)


_TOPOLOGICAL_TASK = PackTaskSpec(
    id="feature-dependency-order",
    description="Implement deterministic dependency ordering with cycle detection.",
    category="feature",
    difficulty="medium",
    tags=("python", "graphs", "multi-file", "determinism"),
    prompt=_clean(
        """
        Implement dependency_order(nodes, dependencies).

        Return every node exactly once after all of its dependencies. Results must
        be deterministic: when multiple nodes are available, choose lexical order.
        Dependencies may mention nodes not present in the original nodes iterable;
        include them. Raise ValueError on a cycle. Do not weaken tests and use only
        the Python standard library.
        """
    ),
    files={
        "dependency.py": _clean(
            """
            def dependency_order(nodes, dependencies):
                raise NotImplementedError
            """
        ),
        "planner.py": _clean(
            """
            from dependency import dependency_order


            def build_plan(steps, dependencies):
                return dependency_order(steps, dependencies)
            """
        ),
        "test_dependency.py": _clean(
            """
            import unittest

            from planner import build_plan


            class DependencyOrderTests(unittest.TestCase):
                def test_dependencies_precede_dependents(self):
                    self.assertEqual(
                        build_plan(
                            ["test", "build", "lint"],
                            {"test": {"build"}, "build": set(), "lint": set()},
                        ),
                        ["build", "lint", "test"],
                    )

                def test_dependency_only_node_is_included(self):
                    self.assertEqual(
                        build_plan(["deploy"], {"deploy": {"package"}}),
                        ["package", "deploy"],
                    )

                def test_cycle_rejected(self):
                    with self.assertRaises(ValueError):
                        build_plan(["a", "b"], {"a": {"b"}, "b": {"a"}})

                def test_one_shot_nodes_iterable(self):
                    nodes = (item for item in ["b", "a"])
                    self.assertEqual(build_plan(nodes, {}), ["a", "b"])


            if __name__ == "__main__":
                unittest.main()
            """
        ),
    },
)


_PATH_SANDBOX_TASK = PackTaskSpec(
    id="regression-safe-path",
    description="Close a path-containment regression without breaking valid nesting.",
    category="regression",
    difficulty="medium",
    tags=("python", "pathlib", "security", "multi-file"),
    prompt=_clean(
        """
        Repair resolve_under(root, relative) so it returns a resolved path only
        when the requested path remains under root.

        Reject absolute paths and traversal that escapes root, including sibling
        prefixes such as root=/tmp/app and candidate=/tmp/application/file. Valid
        nested paths remain allowed. Preserve the Path return type, use the
        standard library, and do not weaken tests.
        """
    ),
    files={
        "paths.py": _clean(
            """
            from pathlib import Path


            def resolve_under(root, relative):
                root_path = Path(root).resolve()
                candidate = (root_path / relative).resolve()
                if str(candidate).startswith(str(root_path)):
                    return candidate
                raise ValueError("path escapes root")
            """
        ),
        "storage.py": _clean(
            """
            from paths import resolve_under


            def artifact_path(root, relative):
                return resolve_under(root, relative)
            """
        ),
        "test_paths.py": _clean(
            """
            import tempfile
            import unittest
            from pathlib import Path

            from storage import artifact_path


            class SafePathTests(unittest.TestCase):
                def test_nested_path(self):
                    with tempfile.TemporaryDirectory() as raw:
                        root = Path(raw)
                        expected = (root / "nested" / "file.txt").resolve()
                        self.assertEqual(
                            artifact_path(root, "nested/file.txt"),
                            expected,
                        )

                def test_parent_escape_rejected(self):
                    with tempfile.TemporaryDirectory() as raw:
                        root = Path(raw) / "app"
                        root.mkdir()
                        with self.assertRaises(ValueError):
                            artifact_path(root, "../secret.txt")

                def test_absolute_path_rejected(self):
                    with tempfile.TemporaryDirectory() as raw:
                        root = Path(raw) / "app"
                        root.mkdir()
                        with self.assertRaises(ValueError):
                            artifact_path(root, Path(raw) / "other.txt")

                def test_sibling_prefix_is_not_contained(self):
                    with tempfile.TemporaryDirectory() as raw:
                        root = Path(raw) / "app"
                        sibling = Path(raw) / "application" / "file.txt"
                        root.mkdir()
                        sibling.parent.mkdir()
                        with self.assertRaises(ValueError):
                            artifact_path(root, "../application/file.txt")


            if __name__ == "__main__":
                unittest.main()
            """
        ),
    },
)


_EVENT_BUS_TASK = PackTaskSpec(
    id="refactor-event-bus",
    description="Refactor event dispatch into a stable mutation-safe observer API.",
    category="refactor",
    difficulty="hard",
    tags=("python", "api-design", "state", "multi-file"),
    prompt=_clean(
        """
        Refactor EventBus while preserving its public subscribe/unsubscribe/emit API.

        Required behavior:
        - subscription order defines callback order
        - duplicate subscription of the same callback is ignored
        - unsubscribe of a missing callback is a no-op
        - callbacks may subscribe or unsubscribe during emit without changing the
          callbacks selected for that in-progress emission
        - exceptions raised by callbacks propagate to the caller
        - keep the implementation focused and do not weaken tests
        """
    ),
    files={
        "event_bus.py": _clean(
            """
            class EventBus:
                def __init__(self):
                    self._listeners = {}

                def subscribe(self, event, callback):
                    self._listeners.setdefault(event, []).append(callback)

                def unsubscribe(self, event, callback):
                    self._listeners[event].remove(callback)

                def emit(self, event, payload):
                    for callback in self._listeners.get(event, []):
                        callback(payload)
            """
        ),
        "consumer.py": _clean(
            """
            def record_events(bus, event, target):
                def recorder(payload):
                    target.append(payload)

                bus.subscribe(event, recorder)
                return recorder
            """
        ),
        "test_event_bus.py": _clean(
            """
            import unittest

            from event_bus import EventBus


            class EventBusTests(unittest.TestCase):
                def test_order_and_duplicate_subscription(self):
                    bus = EventBus()
                    seen = []
                    first = lambda payload: seen.append(("first", payload))
                    second = lambda payload: seen.append(("second", payload))
                    bus.subscribe("x", first)
                    bus.subscribe("x", first)
                    bus.subscribe("x", second)
                    bus.emit("x", 3)
                    self.assertEqual(seen, [("first", 3), ("second", 3)])

                def test_missing_unsubscribe_is_noop(self):
                    bus = EventBus()
                    bus.unsubscribe("missing", lambda payload: None)

                def test_mutation_during_emit_uses_snapshot(self):
                    bus = EventBus()
                    seen = []

                    def late(payload):
                        seen.append("late")

                    def first(payload):
                        seen.append("first")
                        bus.subscribe("x", late)
                        bus.unsubscribe("x", second)

                    def second(payload):
                        seen.append("second")

                    bus.subscribe("x", first)
                    bus.subscribe("x", second)
                    bus.emit("x", None)
                    self.assertEqual(seen, ["first", "second"])

                    seen.clear()
                    bus.emit("x", None)
                    self.assertEqual(seen, ["first", "late"])

                def test_callback_errors_propagate(self):
                    bus = EventBus()

                    def boom(payload):
                        raise RuntimeError("boom")

                    bus.subscribe("x", boom)
                    with self.assertRaisesRegex(RuntimeError, "boom"):
                        bus.emit("x", None)


            if __name__ == "__main__":
                unittest.main()
            """
        ),
    },
)


CORE_V3 = BenchmarkPack(
    id="core-v3",
    version="3.0.0",
    name="AgentBench Core V3",
    description=(
        "Expanded deterministic Python engineering corpus with eight tasks, "
        "including multi-file design, graph, path-safety, and stateful refactor work."
    ),
    tasks=(
        _DURATION_TASK,
        _SLUG_TASK,
        _CACHE_TASK,
        _BATCH_TASK,
        _CONFIG_OVERLAY_TASK,
        _TOPOLOGICAL_TASK,
        _PATH_SANDBOX_TASK,
        _EVENT_BUS_TASK,
    ),
    compatibility_id="agentbench-core",
)



class BuiltinPackProvider:
    provider_id = "agentbench.builtin"

    def packs(self) -> tuple[BenchmarkPack, ...]:
        return (SMOKE_V2, CORE_V2, CORE_V3)


__all__ = [
    "BuiltinPackProvider",
    "CORE_V2",
    "CORE_V3",
    "SMOKE_V2",
]
