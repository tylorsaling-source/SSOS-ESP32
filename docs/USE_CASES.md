# What you can build with SSOS now

SSOS is useful when an ESP32-S3 should own a small amount of structured state
or a tiny final decision layer while a phone, laptop, Pi, or other host handles
the larger application.

## 1. Portable controller or configuration state

Store up to 32 compact records that describe device modes, thresholds, routing
labels, controller metadata, or short opaque payloads. Each record has an ID,
nine signed integer coordinates, a semantic role, metadata fields, and a body.

The host can read by ID or coordinate, force an immediate bank save, and export
it with `DUMP`. The runtime also has an adaptive background flush. The emitted
`PKT` lines can be replayed on compatible SSOS firmware. This is useful for
versioned controller snapshots and moving small state between boards without
designing a separate binary file format.

This is not arbitrary file storage: there are 32 slots and each body stores at
most 63 characters.

## 2. Replaceable tiny scoring or action head

V2 supports exactly one 9-input/8-output linear head:

```text
8 scores = 8x9 weight matrix @ 9 caller-supplied floats
```

The 72 weights are encoded as eight signed-Q10 packet bodies. After compatible
V2 firmware has been installed, a host can replace those packets, call `MLOAD`,
test with `MINFER`, and call `SAVE` without reflashing firmware.

Possible experiments include eight-way action scoring, compact state
classification, or a learned final layer fed by features from a larger host
model. The board returns raw scores. Activation, probability conversion,
thresholding, and action selection remain the host application's responsibility.

## 3. Split host/MCU inference

A more capable host can reduce a larger observation to nine values and send
those values to the ESP32. The ESP32 owns the final packet-carried head, making
the last linear calculation independently of the host's stored copy.

The bundled `basic_surv` artifact demonstrates that architecture: an external
48-to-8 projection produces eight latent values, a constant ninth input acts as
bias, and the ESP head produces eight skill scores. Its reports describe
simulation and teacher-agreement results. The public repository does not yet
contain the ordered 48-field source contract, so the example is currently an
architecture and artifact demonstration rather than a complete public training
recipe.

## 4. Packet-runtime and tiny-kernel experiments

The firmware contains a separate experimental 9-D runtime driven by packet-bank
fullness, timing, request hits, faults, and related controller state. Its
adaptive flush threshold directly controls background persistence; other
reported values such as burst, rest, and scale remain internal to the heuristic
or observational in the current firmware. `TENSOR` exposes the values, and
`BENCH` runs the included kernel measurements.

This makes the project useful for studying low-overhead 9-D math and the cost of
a fused 9-to-8 operation on the tested ESP32-S3. Benchmark ratios apply only to
the exact equal-work kernels named in the raw traces.

## Current boundaries

The public implementation does not currently provide:

- Wi-Fi, BLE, LoRa, mesh, or MCP transport;
- distributed memory across several boards;
- sensors or automatic feature extraction;
- dynamic model shapes or arbitrary neural-network layers;
- on-device training of the V2 application head;
- cryptographic integrity or permission enforcement;
- autonomous real-world survival behavior; or
- a general-purpose operating system.

Those can be proposed as future integrations, but they should not be described
as features of the current release.
