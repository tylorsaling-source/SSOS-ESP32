# SSOS ESP32 release guide

## V4.0.1: independent cluster lineage

V4.0.1 adds `cluster-345-fresh`, a separately initialized training lineage for
the same 549,984-parameter split architecture. It owns independent model
weights, AdamW state, RNG state, training schedule and checkpoint history.

Its first durable checkpoint is step 5,000 after 5,120,000 presented tokens
(9.309362 tokens per parameter). Training loss at the checkpoint was 3.468667
and held-out loss was 3.488711. The checkpoint records no parent checkpoint,
confirming that it was initialized independently rather than copied from the
original lineage.

The release includes the exact 6,652,561-byte checkpoint, its SHA-256 identity,
cluster manifest, deterministic language samples and machine-readable result.
Both lineages retain the same parameter split, tokenizer/corpus contract and
9-D transaction format, allowing direct comparison without sharing learned
state.

## V4.0.0: reproducible split-language training and first checkpoint

V4 publishes the first reproducible checkpoint for a custom
549,984-parameter causal-language model with separately owned master and worker
stages. The package contains the exact checkpoint, tokenizer, architecture,
curriculum builders, resumable trainer, 9-D transaction contract and a
deterministic continuous-versus-split update gate.

The first checkpoint reached 54,998,528 presented tokens, or 100.00023 tokens
per parameter. Its best recorded held-out loss was 2.991671 at step 105,000;
the final step-107,419 evaluation was 2.995222. The checkpoint retains master
and worker weights, AdamW state, RNG state, tokenizer/corpus identity and the
training schedule.

The master owns embeddings and layers 0-1 (274,944 parameters). The worker owns
layers 2-3, final normalization and the language head (275,040 parameters).
The split-equivalence gate verifies identical loss, gradients and updated
weights for one continuous update and one detached-boundary update.

See the complete [V4 training package](benchmarks/ssos-550k-language-training/README.md).

## V1.0.0: packet-controller baseline

V1 is the frozen, hardware-tested baseline for the stated ESP32-S3-WROOM-1U
N16R8 board. It provides:

- a 32-slot `ssos.packet.v1` bank;
- lookup and replacement by ID or nine signed integer coordinates;
- short opaque bodies and semantic role metadata;
- immediate `SAVE`/`LOAD` persistence plus the runtime's adaptive background
  packet flush;
- `DUMP` packet-state export and replay; and
- the internal adaptive 9-D runtime and benchmark suite.

V1 is model-agnostic. Its benchmark and host-model source files do not mean an
application model is installed or executed by V1.

## V2.0.0: packet-backed model bridge

V2 preserves the V1 packet bank and adds one fixed 9-input/8-output linear
execution head:

1. Eight ordinary packets named `model:w:0` through `model:w:7` hold signed-Q10
   weight rows.
2. `MLOAD` validates the rows and reconstructs a volatile 72-float cache.
3. `MINFER` computes eight raw dot-product scores from nine caller-supplied
   floats.
4. `SAVE` persists the weight packets; reboot or `LOAD` reconstructs the cache.

The packet records remain authoritative. The cache is not a second persistent
model store. V2 is compiled and host/artifact-validated but has not been
physically flashed in the published validation record.

## V3.0.1: Quark interleaved language pipelines

V3 packages the physically tested Quark-v2-0.5M master/worker implementation
as one complete release for two ESP32-S3-WROOM-1U N16R8 boards:

1. The master executes model layers 0-1.
2. A 40 MHz SPI link transfers the intermediate representation.
3. The worker executes layers 2-3 and next-token selection.
4. Two independent autoregressive contexts alternate so master and worker
   computation overlap.

The release contains the pinned 465,504-parameter Q8 group-8 model, exact
physically tested master and worker images, source, wiring, Windows and POSIX
build/flash scripts, baseline evidence, result capture, and a fail-closed
verifier.

The accepted five-run gate produced 240/240 expected tokens at a median
44.730763 aggregate tokens/second. That is 2.421880x the 18.469438 tok/s
one-board baseline and 2.438279x the 18.345216 tok/s original sequential-pair
median. The measurement is the aggregate decode throughput of two independent
interleaved contexts.

V3 runs as a dedicated multi-board application with role-specific firmware.
Flashing V3 writes the current application on every selected board. Preserve
any existing firmware and learned state before installing it.

See the complete [V3 package guide](benchmarks/quark-v2-0.5m-pair-pipeline/README.md).

V3.0.1 adds an optional one-master/two-worker extension. It duplicates the
accepted two-context schedule across two independent SPI lanes and four model
contexts with separate KV-cache state. Each lane carries stream and sequence
identity, retains its own retry frame, and validates response checksums before
advancing. The accepted physical run was exact at 96/96 tokens and measured
87.927387 aggregate tok/s. The release adds three role-specific applications,
two-lane wiring, prebuilt images, cross-platform build/flash helpers, and
machine-readable results while preserving the original two-board topology.

## Choosing safely

Use V1 for the physically tested packet-state baseline. Choose V2 only when the
fixed linear model head is needed and its published validation status is
acceptable. Choose V3 when two supported boards—or the documented optional
three-board topology—should run the packaged Quark language model together.
None of the releases provides networking, sensors,
on-device application-model training, arbitrary neural-network execution, or
security enforcement.

See [README.md](README.md), [docs/PROTOCOL.md](docs/PROTOCOL.md), and
[docs/FLASHING.md](docs/FLASHING.md).
