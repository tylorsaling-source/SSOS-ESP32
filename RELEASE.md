# SSOS ESP32 release guide

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

## Choosing safely

Use V1 for the physically tested packet-state baseline. Choose V2 only when the
fixed linear model head is needed and its published validation status is
acceptable. Neither release provides networking, sensors, on-device application
model training, arbitrary neural-network execution, or security enforcement.

See [README.md](README.md), [docs/PROTOCOL.md](docs/PROTOCOL.md), and
[docs/FLASHING.md](docs/FLASHING.md).
