# SSOS ESP32 V2

V2 preserves the V1 `ssos.packet.v1` bank, 9-D addressing, opaque packet
bodies, `DUMP` replacement tape, persistence, and fused OS matcher.

Its additive feature is a packet-backed model execution bridge:

1. Eight ordinary packets named `model:w:0` through `model:w:7` hold signed
   Q10 weight rows in their opaque bodies.
2. `MLOAD` validates those eight packets and reconstructs a volatile contiguous
   72-float execution cache.
3. `MINFER` executes a supplied 9-D tensor through that cache.
4. Reboot or `LOAD` reconstructs the cache from the saved packet bank.

The packets remain authoritative. The execution matrix is not an independent
model store and is never written to NVS separately.

The separately distributed V1 release is the frozen, hardware-tested,
model-agnostic packet-controller baseline. V2 has passed compilation and host
artifact validation but has not been flashed to physical hardware.
