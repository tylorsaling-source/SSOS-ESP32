# V2.0.1 physical release validation — September 14, 2026 local

**PASS on both required storage conditions using the extracted ZIP's stock
Windows command.** Each run installed 72 signed-Q10 coefficients, matched all
48 scores, received `OK saved`, and reconstructed the head after a real
hardware reset without resending model rows. The passing runs occurred on
September 15 UTC (September 14 in America/New_York).

## Results and direct evidence

| Starting condition | Harness start UTC | Settings initialized | Result | Boot count |
| --- | --- | --- | --- | --- |
| Synthetic legacy NVS under V2.0.0 | Sep 14 23:41:02 | No | 24/24 scores; `SAVE` failed | 1; reset gate not reached |
| Same dirty NVS under V2.0.1 with `-KeepSettings` | Sep 15 00:01:25 | No | 24/24 scores; `SAVE` failed with new recovery hint | 1; reset gate not reached |
| Same board, stock V2.0.1 default | Sep 15 00:01:48 | Yes, once | **48/48, SAVE/reset PASS** | **1 → 2** |
| Normal SSOS NVS left by the passing run; default repeated | Sep 15 00:02:18 | Yes, once | **48/48, SAVE/reset PASS** | **1 → 2** |

- Dirty recovery: [JSON](results/v2.0.1-20260914/dirty-default/v2-physical-20260915T000148Z.json),
  [serial trace](results/v2.0.1-20260914/dirty-default/v2-physical-20260915T000148Z.txt),
  [flash/initialization log](results/v2.0.1-20260914/dirty-default/v2-flash-20260915T000136212Z.txt),
  [complete output](results/v2.0.1-20260914/dirty-default-workflow.txt).
- Clean-enough repeat: [JSON](results/v2.0.1-20260914/clean-default/v2-physical-20260915T000218Z.json),
  [serial trace](results/v2.0.1-20260914/clean-default/v2-physical-20260915T000218Z.txt),
  [flash/initialization log](results/v2.0.1-20260914/clean-default/v2-flash-20260915T000206638Z.txt),
  [complete output](results/v2.0.1-20260914/clean-default-workflow.txt).
- Preserved failures: [V2.0.0 JSON](results/v2.0.1-20260914/old-release-dirty-baseline/v2-physical-20260914T234102Z.json)
  and [trace](results/v2.0.1-20260914/old-release-dirty-baseline/v2-physical-20260914T234102Z.txt);
  [V2.0.1 KeepSettings JSON](results/v2.0.1-20260914/new-release-keep-settings-failure/v2-physical-20260915T000125Z.json)
  and [trace](results/v2.0.1-20260914/new-release-keep-settings-failure/v2-physical-20260915T000125Z.txt).

The [independent dirty audit](results/v2.0.1-20260914/dirty-default-independent-audit.json)
and [clean audit](results/v2.0.1-20260914/clean-default-independent-audit.json)
recomputed the dot products using exact rational Q10 coefficients, matched all
six serial responses to JSON, checked source/fixture/image hashes, and verified
the reset boundary. Maximum absolute error in each run was
`4.6875000014878765e-7`, below the `2e-5` tolerance. All six argmax results matched.
Both flash logs contain four digest matches and exactly one completed
`SETTINGS_INITIALIZED offset=0x9000 length=0x5000` marker after verification.

## Reproduction and storage conditions

The tested staging ZIP came from immutable source commit
`8f3cf47453ba2f6c72e0d7d3cdbd92b52fab6861` and was extracted outside the Git
checkout. Its [package audit](results/v2.0.1-20260914/tested-package-verification.json)
records SHA-256 `e540384b2689dc40ec1c9ee92f5491926abc21cce2a98ac5aa38b5f8cfe406e5`
and 87 verified internal hashes. Later evidence/documentation commits change
the final ZIP identity. Each physical record also binds the exact firmware,
fixture, and four installation/validation scripts by SHA-256. The final release
has its own checksum file and `PACKAGE.json` source commit.

From the extracted root, the failing control and two passing gates used:

```powershell
.\scripts\validate-v2-windows.cmd -Port COM20 -Yes -KeepSettings -OutputDirectory <control-results>
.\scripts\validate-v2-windows.cmd -Port COM20 -Yes -OutputDirectory <dirty-results>
.\scripts\validate-v2-windows.cmd -Port COM20 -Yes -OutputDirectory <clean-results>
```

`-Yes` accepted the already authorized, displayed flash/initialization action.
No manual erase command occurred between the failing V2.0.1 control and its
passing default recovery. No manual packet commands were needed.

The [synthetic fixture](dirty-settings/README.md) is valid 20 KiB NVS containing
an 11,000-byte legacy blob of ASCII `L`, with no user data. The
[setup log](results/v2.0.1-20260914/dirty-fixture-write.txt) records writing only
that image at `0x9000`. V2.0.0 passed inference but failed SAVE. The board was
[held in the ROM bootloader](results/v2.0.1-20260914/rom-hold-after-baseline.txt)
while the new firmware was built. V2.0.1 with settings preserved reproduced
the failure; its default installation fixed it. The second pass started with
the normal SSOS bank left by the first pass. The original storage condition
behind issue #15 was not inspected; this fixture reproduces its observed
failure symptom, not the user's previous contents.

## Hardware, build, and artifact identity

One board on COM20 reported ESP32-S3 QFN56 revision v0.2, native USB
Serial/JTAG 303A:1001, 16 MB quad flash, 8 MB embedded AP_3v3 PSRAM, and a
40 MHz crystal. Module printing was not visually inspected. The evidence's
`target` field states the harness configuration; these device-reported values
are the verified hardware facts. PSRAM is disabled in the release. COM3 was
refused by host checks and never used.

The [toolchain record](results/v2.0.1-20260914/toolchain-versions.txt) confirms
Arduino CLI 1.5.1 and Arduino-ESP32 3.3.5. The
[successful build log](results/v2.0.1-20260914/build.txt) records
app3M_fat9M_16MB, USBMode=hwcdc,
CDCOnBoot=cdc, UploadMode=default, FlashMode=qio, FlashSize=16M, and
PSRAM=disabled. The application binary is 380,704 bytes. The pinned core
supplied boot_app0; the build produced the app, bootloader, and partition image.
Partitions and boot_app0 remain byte-identical to V2.0.0. Writes used DIO,
80 MHz, 16 MB, and the same four offsets.

| Image | SHA-256 |
| --- | --- |
| Application | `6ab6fa74130ee02f82377f137465a039c11a3874f50ec899709b8f8b43229f94` |
| Bootloader | `d9263d09dd8c95efe3761bd53613848f3a7f05824720f71c8a44b8cdfec788e3` |
| Partitions | `ace02503447d0f470692e65fa76002f2d77a92dc81cd3813d8aa66718d716da9` |
| boot_app0 | `f94c5d786a7a8fab06ac5d10e33bf37711a6697636dc037559ea19cc410a17f0` |

[BUILD.json](../../images/flash/BUILD.json) records normalized source hashes
and all image identities. Fixture LF SHA-256 is
`3014a17b72bff5004b628b1f75aae319109e63d082f4759d7c293b7a81bfc560`.
The V2.0.0 control used the equivalent historical CRLF fixture with SHA-256
`723a5d6eb2289bb5233eadf3fc0024cd7df62e6e4b48cbce125da1c43d94c924`.

## Host checks, preserved failures, and publication

[Host checks](results/v2.0.1-20260914/host-checks.json) passed 11 unit tests,
Windows dry-run and COM3 refusals, both shell syntax checks, POSIX/Termux
dry-runs and COM3 refusals, and whitespace validation. POSIX/Termux checks ran
under Git Bash on Windows; physical Linux, macOS, and Android were not tested.
Physical runs used Windows PowerShell 5.1, Python 3.14, Esptool 5.3.1 and PySerial.

Two earlier host failures are retained. The capture process initially inherited
PowerShell 7 module paths into Windows PowerShell 5.1
([log](results/v2.0.1-20260914/host-checks-initial-failure.txt)); the first ZIP
then exposed Python quoting in the stock `.cmd` workflow
([log](results/v2.0.1-20260914/launcher-pyserial-failure.txt)). The capture
environment was corrected and the release wrapper was fixed before the
physical V2.0.1 runs above. Both host failures stopped before device access.

The [publication manifest](results/v2.0.1-20260914/SHA256-MANIFEST.json) records
original log hashes and every published evidence-file hash. Publication copies
redact full device identifiers and private host paths, normalize LF, and add
JSON provenance metadata. A JSON flash-log hash refers to its original log;
the manifest separately identifies the normalized public copy. Raw logs were
retained locally. Numeric results, failures, reset events, and initialization
markers were preserved.

No previous firmware or packet contents were copied, backed up, or dumped.
This is a one-board hard-reset persistence test, not USB power-unplug endurance
or a guarantee for every damaged/encrypted storage state. No Quark/ParetoQ,
training, multi-board, packet-format, or 9-to-8 model-math change is included.
