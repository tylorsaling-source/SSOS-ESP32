# Host tools

The `host/` directory contains release helpers, model utilities, benchmark
generators, and earlier research prototypes. The presence of a source file does
not mean its command set is implemented by the current firmware.

## Current release paths

- `flash_ssos.py` and `run_esptool.py` support the guided flashing scripts.
- `basic_surv_9d.py` loads the bundled adapter artifact, projects one correctly
  ordered 48-value observation to nine values, and can call V2 `MINFER` over a
  serial port. The required public 48-field contract is not yet included, so do
  not invent input ordering.
- `cdc-pty.c`, `usb_bl_reset.c`, `usb_app_reset.c`, and `ssos_cmd.c` support the
  native-USB Termux workflow documented by the release scripts.
- `ssos_dump.c` retrieves `ID` and the current `DUMP` output through the Termux
  USB file descriptor.
- `gen_fc9.cpp` and `gen_fc9.py` are build/benchmark generators.

## Research and compatibility warning

`ssos_host.c` is an earlier spatial-host prototype. It contains commands such
as `PUT`, `MOVE`, `QUERY`, `NEIGHBORS`, `ROUTE`, and `SEND usb|wifi|ble` that are
not implemented by the current `ssos.packet.v1` firmware.

`ssos_model.c` is also a legacy research prototype. It writes named four-class
rows with ten integers, which is incompatible with V2's required eight numeric
row IDs and nine signed-Q10 values per row. It is not the V2 installer.

Both files are retained as research source and are excluded from the default
Termux build. Set `SSOS_BUILD_LEGACY=1` only when intentionally compiling them
for source study; the resulting programs are not supported current clients.

Use the command surface in [the protocol reference](../docs/PROTOCOL.md) as the
authority for current firmware integrations.
