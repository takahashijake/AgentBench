# Adding a New Benchmark

Define immutable `BenchmarkPack` and `PackTaskSpec` values through a `BenchmarkPackProvider`. Providers describe corpus content; `PackMaterializer` owns Git/filesystem creation.

Third-party packages can register providers through the `agentbench.pack_providers` entry-point group.
