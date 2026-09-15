# V2.0.1 — Reliable save on reused boards

V2.0.0 could pass live inference while `SAVE` failed because retained settings
occupied its NVS storage. Flashing the app did not clear that region.

V2.0.1 makes the Windows proof workflow initialize the release's 20 KiB NVS
region after flashing and verification, with a clear notice before confirmation.
Flash-only Windows, Linux/macOS, and Termux installers expose the same explicit
option. `-KeepSettings` opts out in the proof workflow. Nothing automatically
erases storage during ordinary inference or `SAVE`.

The firmware identifies itself as 2.0.1 and points failed saves to the install
workflow. The packet format, 72-coefficient Q10 layout, and 9-to-8 head math are
unchanged. Images are rebuilt with Arduino-ESP32 3.3.5 and PSRAM disabled.

Physical validation and its exact limits are recorded in
[the V2.0.1 run report](validation/v2-hardware/RUN-v2.0.1-20260914.md).
The extracted ZIP's stock Windows command passed on controlled dirty storage
and on a clean-enough repeat: 72 coefficients, 48/48 matching scores per run,
`OK saved`, and boot count 1 to 2 without resending rows. Maximum absolute
error was 0.000000468750000149 against a 0.00002 tolerance. All four image
regions passed digest verification in each run.
The [V2.0.0 run](validation/v2-hardware/RUN-20260914.md) remains historical:
it needed a manual NVS initialization, which this release incorporates into
the standard workflow.

The proof covers hardware reset, not USB power-unplug endurance or every
possible damaged/encrypted storage state. No model architecture, training,
Quark/ParetoQ, or multi-board payload is part of this update.
