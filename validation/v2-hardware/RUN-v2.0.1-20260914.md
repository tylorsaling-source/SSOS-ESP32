# V2.0.1 physical release validation — 2026-09-14

Validation in progress. This report is not a physical PASS claim until the
rebuilt V2.0.1 images complete both release gates below.

## Required gates

- Controlled reused-storage gate: synthetic legacy NVS reproduces `ERR save
  failed` under V2.0.0, then the stock V2.0.1 Windows proof initializes settings
  as part of installation and passes all 48 output/save/reset checks.
- Clean-enough gate: run the same stock workflow with a normal SSOS settings
  bank and require the same 48 output/save/reset checks.

COM20 identifies as ESP32-S3 QFN56 revision v0.2, native USB Serial/JTAG,
16 MB quad flash and 8 MB embedded PSRAM. The release disables PSRAM. Module
printing has not been visually inspected; the hardware record uses device
reported chip/memory/interface values. No prior firmware backup or dump was
made. COM3 is protected.

The [synthetic fixture](dirty-settings/README.md) fills NVS with an 11,000-byte
legacy blob. On V2.0.0 at 23:41:02Z, all 24 inference values matched but `SAVE`
returned `ERR save failed`. The old storage condition from issue #15 is unknown;
this controlled fixture reproduces the observed failure symptom.

No USB power removal or endurance result is claimed. The required persistence
test uses a real hardware reset and verifies that saved model rows reload
without resending them.
