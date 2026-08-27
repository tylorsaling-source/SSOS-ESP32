# SSOS benchmarks

Benchmarks are isolated implementations with release-specific firmware and
validation records. The Quark package below is the authoritative implementation
payload for V3.0.1; the core SSOS V1/V2 packet firmware remains independently
versioned.

## Reproducible packages

### [ParetoQ 125M six-board distributed inference](paretoq-125m-six-board-distributed/README.md)

**Package version:** 1.0.0

Six ESP32-S3 N16R8 boards form one physical 40 MHz SPI ring: five boards hold
the 30 compute-layer/vocabulary shards and the sixth board is the transport
relay. The clean package contains source, exact prebuilt firmware, manifests,
wiring, fixed prompts, host oracle, full token outputs, physical captures, and
a fail-closed verifier. The gated Meta checkpoint and reconstructed weight
shards are deliberately excluded and can be regenerated at the pinned revision.

Accepted five-prompt result: FAST and REGULAR both produced 120/120 exact
tokens with zero SPI errors. FAST used 1.4959925x less total prompt-to-finish
time and delivered 1.479x the aggregate decode rate.

### [SSOS 550k cluster 3–4–5](ssos-550k-language-cluster-345/README.md)

**Official release:** SSOS ESP32 V4.0.1

A standalone fresh training lineage for the same 549,984-parameter split
architecture. It includes only the cluster 3–4–5 step-5,000 checkpoint and its
own identity, quality evidence, tokenizer, trainer and verification tools. The
V4.0.0 checkpoint remains in its separate package.

### [SSOS 550k split-language training](ssos-550k-language-training/README.md)

**Official release:** SSOS ESP32 V4.0.0

Reproduce and continue a custom 549,984-parameter causal-language model with
independently owned master and worker stages. The package includes the exact
step-107,419 checkpoint, tokenizer, deterministic curriculum builders,
resumable cumulative-token trainer, 9-D transaction protocol, quality evidence
and continuous-versus-split numerical gate.

First-checkpoint result: 54,998,528 presented tokens (100.00023
tokens/parameter), best held-out loss 2.991671 and exact one-step split
equivalence.

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
