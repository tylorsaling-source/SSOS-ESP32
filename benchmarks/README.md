# SSOS benchmarks

Benchmarks are isolated implementations. They do not silently change the
behavior or support claims of the core SSOS V1/V2 packet firmware. The Quark
package below is also the authoritative implementation payload for V3.0.1.

## Reproducible packages

### [Quark-v2-0.5M interleaved pipelines](quark-v2-0.5m-pair-pipeline/README.md)

**Official release:** SSOS ESP32 V3.0.1

Use two ESP32-S3-WROOM-1U N16R8 boards to run one pretrained 465,504-parameter
English text model with two independent contexts. The package includes exact
prebuilt firmware, source, wiring, Windows/POSIX scripts, the premade model,
original baselines, physical results, and a fail-closed verifier.

Accepted result: 240/240 expected tokens across five runs at a median 44.730763
aggregate tokens/second. Read the package's claim boundaries before comparing
it with single-stream inference.

The same package includes an optional three-board, two-lane extension. Its
accepted physical gate produced 96/96 expected tokens at 87.927387 aggregate
tok/s across four independent contexts. This is not a five-run stability claim
and it does not claim the unmet 90 tok/s target.
