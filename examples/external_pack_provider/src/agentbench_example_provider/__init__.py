"""Example third-party AgentBench benchmark provider.

This package intentionally lives outside the AgentBench source package.
AgentBench discovers it only through the packaging entry point declared here.
"""

from agentbench.benchmark_packs import BenchmarkPack, PackTaskSpec


_TASK = PackTaskSpec(
    id="external-safe-divide",
    description="Repair a small externally provided arithmetic API.",
    category="bugfix",
    difficulty="easy",
    tags=("external-provider", "python"),
    prompt=(
        "Implement safe_divide(a, b). Return None when b is zero; otherwise "
        "return a / b. Do not weaken the tests."
    ),
    files={
        "math_api.py": (
            "def safe_divide(a, b):\n"
            "    raise NotImplementedError\n"
        ),
        "test_math_api.py": (
            "import unittest\n"
            "from math_api import safe_divide\n\n"
            "class SafeDivideTests(unittest.TestCase):\n"
            "    def test_regular_division(self):\n"
            "        self.assertEqual(safe_divide(9, 3), 3)\n\n"
            "    def test_zero_divisor(self):\n"
            "        self.assertIsNone(safe_divide(9, 0))\n\n"
            "if __name__ == '__main__':\n"
            "    unittest.main()\n"
        ),
    },
)


class Provider:
    provider_id = "agentbench.example.external"

    def packs(self):
        return (
            BenchmarkPack(
                id="example-external-v1",
                version="1.0.0",
                name="AgentBench External Provider Example",
                description=(
                    "A separately packaged corpus proving entry-point discovery."
                ),
                tasks=(_TASK,),
                compatibility_id="example-external",
            ),
        )


__all__ = ["Provider"]
