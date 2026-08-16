# Contributing to SSOS ESP32

SSOS prefers collaboration through change requests and pull requests. Small,
reviewable changes with direct evidence are easier to merge and reproduce.

## Before writing code

- Search existing issues and pull requests.
- Open a change request before changing packet formats, persistence, flashing,
  model representation, or benchmark methodology.
- Never post credentials, Wi-Fi details, private packets, or full device IDs.
- Keep V1 compatibility claims separate from V2 features.

## Development flow

1. Fork the repository.
2. Create a branch such as `feature/short-name` or `fix/short-name`.
3. Make one focused change.
4. Run the checks that apply to your change.
5. Update documentation and release notes when behavior changes.
6. Open a pull request and complete every section of the template.

## Required evidence

Documentation-only changes need link and command review. Firmware changes need
a successful build with the exact FQBN and must state whether hardware was
flashed. Flashing-script changes must demonstrate validate-only behavior before
any write test. Benchmark changes must preserve raw traces and identify:

- board/module and relevant build configuration;
- compiler/core version and optimization level;
- clock rate, sample count, warm/cold treatment, and timer source;
- whether compared kernels use the same inputs, weights, math, and MAC count;
- median/tail behavior where available, not only the best sample.

Do not describe compilation, simulation, or artifact validation as a physical
hardware test. Do not quote an unequal-model comparison as a speedup.

## Compatibility and safety

- Preserve `ssos.packet.v1` unless a reviewed proposal explicitly versions it.
- Never silently alter flash offsets, partition layout, DTR/RTS behavior, or
  destructive console commands.
- New board support must not reuse the N16R8 binaries.
- Generated binaries must include an updated manifest and SHA-256 checksums.
- A model integration should use ordinary packets or clearly document why a
  new storage authority is required.

## Review and acceptance

The automated moderator checks structure and routes labels; it does not approve
or merge code. Maintainers evaluate compatibility, safety, evidence, scope, and
licensing. Review may request a smaller change or independent reproduction.

By contributing, you agree that your contribution is licensed under the
repository's Apache-2.0 license and that you have the right to submit it.
