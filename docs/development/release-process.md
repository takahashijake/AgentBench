# Release Process

AgentBench uses semantic package versions and does not publish automatically from CI.

Before tagging a release:

1. update user-facing version metadata and the changelog;
2. run `make qa`;
3. confirm the GitHub CI workflow is green;
4. create a signed/annotated `vX.Y.Z` tag;
5. let the release workflow build and validate wheel/sdist artifacts;
6. inspect the uploaded workflow artifacts before any manual publication.

The release workflow intentionally stops at validated artifacts. Publishing to a package index or creating a public release remains an explicit maintainer decision.
