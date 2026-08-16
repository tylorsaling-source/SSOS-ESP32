# SSOS packet protocol and limits

The current firmware exposes a newline-delimited text console at 115200 baud
over native USB serial. Commands and responses use `ssos.packet.v1`.

## Packet record

```text
PKT id=<id> d=<d0,d1,d2,d3,d4,d5,d6,d7,d8> role=<role> [hash=<text>] [perm=<text>] [body=<text>]
```

Current storage limits:

| Field | Limit or behavior |
| --- | --- |
| Bank | 32 records |
| `id` | 39 stored characters plus terminator |
| `d` | Nine stored signed 16-bit integers; send all nine for portable records |
| `role` | `note`, `document`, `executable`, `runtime`, `boot`, `payload`, `archive`, or `firmware` |
| `hash` | Up to 16 characters; when omitted, firmware stores 32-bit FNV-1a of the body as eight hex digits |
| `perm` | Up to 19 stored characters; defaults to `open` |
| `body` | 63 stored characters plus terminator; because it consumes the rest of the line, it must be the last field and may contain spaces |
| Input line | 239 characters plus terminator |

`hash` is non-cryptographic metadata. `perm` is metadata only and is not checked
when commands run. Neither is a security control.

The comma parser accepts one through nine coordinate values and zero-fills
omitted trailing dimensions; the `grid://...` coordinate form printed by the
firmware is also accepted. Public integrations should send all nine values so
the record meaning is explicit. The current parser uses `atoi`: malformed
components become zero, out-of-range values are cast to signed 16-bit integers,
and values beyond the ninth are ignored rather than rejected. Validate and
range-check coordinates on the host.

## Replacement behavior

When a `PKT` command arrives, firmware searches in this order:

1. existing record with the same ID;
2. existing record with the same nine coordinates; or
3. the first unused slot.

The selected slot is replaced in full. If no matching or unused slot exists,
the command fails. Choose unique IDs and coordinates when records must coexist.

## Read, delete, and inspect

```text
GET id=demo:mode
GET d=1,0,0,0,0,0,0,0,0
DEL id=demo:mode
STATS
DUMP
```

`DUMP` prints the current packet records as `PKT` lines between an `OK dump`
header and `OK end`. Those lines are a replayable packet-state snapshot. They
do not contain the firmware image, runtime RAM, or an automatic flashing step.

## Persistence

`PKT`, `DEL`, and `CLEAR` change the live RAM bank first. `SAVE` forces an
immediate persistence attempt:

```text
SAVE
LOAD
```

`SAVE` writes the full packet bank and associated counters to the ESP32
Preferences/NVS namespace. The internal runtime also triggers a background save
when its adaptive received-packet flush threshold is reached. `LOAD` replaces
RAM state from the stored bank.

Do not depend on the background threshold for a durability boundary: a recent
change can be lost if power fails before the next successful flush. Send `SAVE`
and confirm `OK saved` before disconnecting power or reporting a transaction as
durable. `DEL` and `CLEAR` do not increment the received-packet flush counter, so
they especially require explicit `SAVE` when the deletion must persist.

On boot, firmware loads the saved bank when one exists; otherwise it creates
the seed controller records. In V2, a successful load also attempts to rebuild
the model cache from `model:w:0` through `model:w:7`.

## Three separate 9-D representations

- Packet `d=` values are host-supplied signed integer address metadata.
- The internal runtime tensor is a board-derived float vector describing
  controller operation.
- `MINFER x=` is a caller-supplied float vector for the separate V2 model head.

They share a dimension count but not storage, values, or automatic data flow.

## V2 model packets

V2 reserves the IDs `model:w:0` through `model:w:7` for nine-value signed-Q10
rows. All eight valid records are required:

```text
PKT id=model:w:0 d=... role=payload body=q0,q1,q2,q3,q4,q5,q6,q7,q8
...
PKT id=model:w:7 d=... role=payload body=q0,q1,q2,q3,q4,q5,q6,q7,q8
MLOAD
MINFER x=x0,x1,x2,x3,x4,x5,x6,x7,x8
SAVE
```

`MLOAD` decodes each integer as `q / 1024.0` into a volatile 72-float cache.
`MINFER` returns eight raw dot-product outputs. There is no activation, softmax,
argmax, or separate bias. A caller may reserve one input as a constant bias
value if its external training pipeline uses the same convention.

Changing or deleting any model packet invalidates the volatile cache until a
successful `MLOAD`. `SAVE` persists the packets, not a separate cache.

## Current console surface

```text
ID DUMP PKT GET DEL STATS SAVE LOAD CLEAR
TENSOR TSET TRESET
MODEL MLOAD MINFER MCLEAR
BENCH HELP
```

Some source files under `host/` are research prototypes from earlier protocol
experiments. In particular, commands such as `PUT`, `MOVE`, `QUERY`,
`NEIGHBORS`, `ROUTE`, or `SEND usb|wifi|ble` are not implemented by the current
firmware and must not be treated as public protocol support.
