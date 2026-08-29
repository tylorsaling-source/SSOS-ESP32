# basic_surv ESP4 9-D adapter

This is a compact communication/inference adapter for the separate SSOS model
head. It does not replace the full `basic_surv` policy and it does not use the
OS packet-scheduling tensor as survival input.

This directory demonstrates the architecture and preserves validated artifacts.
The exact field order, normalization formulas, proposal order, projection, and
output meanings are now included in the
[48-field observation contract](OBSERVATION_CONTRACT.md). The host adapter also
accepts a name-keyed observation and fails clearly on missing or unknown fields.

The sender computes:

```text
latent8 = tanh(observation48 @ projection_weight.T + projection_bias)
tensor9 = [latent8[0], ..., latent8[7], 1.0]
```

ESP4 executes `head_weight @ tensor9` in the 9-to-8 model head. Output indices
map to the eight skill names in `ssos_head_rows.json`.

Artifacts:

- `basic_surv_esp4_ssos_9d.npz`: projection and head weights.
- `ssos_head_rows.json`: the 72 signed head weights accepted by the installer.
- `training_report.json`: provenance, hashes, held-out metrics, and rollout gate.

The selected 464-parameter adapter was trained from 28,000 sequential
decisions of the accepted Pi5 node-distilled teacher. It reached 96.55% teacher
agreement on 6,000 separate decisions and completed 30/30 unseen rollouts with
a 1.0 safe-action rate. Those are simulation results, not physical-world or
on-device training claims.

V2 stores the eight head rows as signed Q10 bodies in ordinary
`ssos.packet.v1` records. The independently rerun Q10 gate preserved the same
96.55% agreement and 30/30 rollouts; maximum float-weight error was 0.0004882,
and the largest row body was 45 bytes against the 63-byte packet-body limit.
See `q10_validation_report.json`.

From the repository root, install the head after compatible firmware is already
present:

```powershell
.\scripts\install-model-windows.ps1 -Port COM4
```

This writes eight ordinary `model:w:0..7` packets, reconstructs the volatile
execution matrix with `MLOAD`, persists the packet bank with `SAVE`, and
verifies one known inference vector. It does not invoke `esptool` and does not
flash.

To form a 9-D message from one ordered 48-field observation and optionally ask
the board to execute it:

```text
python host/basic_surv_9d.py observation.json
python host/basic_surv_9d.py observation.json --port COM4
```

NumPy is required for projection. Serial execution additionally requires
PySerial. Prefer the name-keyed input described in the contract; if an array is
used, do not invent or reorder its 48 values.

The recorded agreement and rollout values are external simulation results, not
physical-world survival capability, on-device training, or autonomous behavior.
