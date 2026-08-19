# SSOS benchmarks

Benchmarks are isolated implementations with release-specific firmware and
validation records. The Quark package below is the authoritative implementation
payload for V3.0.1; the core SSOS V1/V2 packet firmware remains independently
versioned.

## Reproducible packages

### [Quark-v2-0.5M interleaved pipelines](quark-v2-0.5m-pair-pipeline/README.md)

**Official release:** SSOS ESP32 V3.0.1

Use two ESP32-S3-WROOM-1U N16R8 boards to run one pretrained 465,504-parameter
English text model with two independent contexts. The package includes exact
prebuilt firmware, source, wiring, Windows/POSIX scripts, the premade model,
original baselines, physical results, and a fail-closed verifier.

Accepted result: 240/240 expected tokens across five runs at a median 44.730763
aggregate tokens/second across two independent contexts.

The same package includes an optional three-board, two-lane extension. Its
accepted physical gate produced 96/96 expected tokens at 87.927387 aggregate
tok/s across four independent contexts. V3.0.1 adds independent lane state,
stream/sequence validation, checksum recovery, role-specific firmware, and
Windows/POSIX build and flash workflows for the trio.
