# Synthetic leftover-settings fixture

This fixture is intentionally unsuitable for normal SSOS use. It creates a
valid 20 KiB NVS partition containing an 11,000-byte legacy blob, leaving
insufficient room for the SSOS packet-bank save. It contains no user data.

Generation uses Espressif's `esp-idf-nvs-partition-gen` 0.3.0, format v2:

```sh
cd validation/v2-hardware/dirty-settings
python -m esp_idf_nvs_partition_gen generate fixture.csv dirty-nvs.bin 0x5000
```

`legacy-payload.bin` is exactly 11,000 ASCII `L` bytes. `dirty-nvs.bin` is exactly
20,480 bytes. The test wrote this synthetic image only at the V2 NVS offset
`0x9000`; it did not copy previous board contents. The subsequent default V2.0.1
installer must clear it as part of its announced install action.

Only use this fixture on an explicitly selected test board whose settings may
be discarded. It is not included in the normal flash image list and is never
written by the stock installer. The original Sep 14 storage condition was not
extracted; this is a controlled reproduction of the same save-failure symptom.
