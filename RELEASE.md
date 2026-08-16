# SSOS ESP32 V1

V1 is the frozen, model-agnostic packet-controller release that was flashed
and verified on an ESP32-S3-WROOM-1U N16R8 through Windows. The user separately
validated the Termux path.

Its product is the `ssos.packet.v1` bank: 32 persistent records with 9-D
coordinates, IDs, generations, roles, permissions, hashes, and opaque bodies;
`DUMP`/`PKT` provide the replaceable-controller tape.

The included model-related host demo and TFLM `hello_world` binary exist only
to demonstrate opaque payload use and benchmark labeling. V1 does not install
an application model or interpret packet bodies as a fixed model contract.

V1 contains no `MODEL`, `MLOAD`, or `MINFER` execution bridge. That additive
packet-backed bridge belongs only to the separately distributed V2 release.
