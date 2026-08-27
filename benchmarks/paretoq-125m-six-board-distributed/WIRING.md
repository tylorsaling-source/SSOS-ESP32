# Six-board SPI ring wiring

The accepted ring order is:

```text
COM4 -> COM7 -> COM8 -> COM9 -> COM11 -> COM22 -> COM4
```

Every arrow connects the upstream board's outgoing pins to the downstream
board's incoming pins:

| Signal | Upstream outgoing | Downstream incoming |
|---|---:|---:|
| SCK | GPIO2 normally; GPIO6 on COM7 and COM11 | GPIO9 |
| MOSI | GPIO42 | GPIO10 |
| MISO | GPIO41 | GPIO11 |
| CS | GPIO40 | GPIO12 |
| READY | GPIO39 | GPIO13 |
| Ground | GND | GND |

Exact accepted edges:

| Edge | SCK | MOSI | MISO | CS | READY |
|---|---|---|---|---|---|
| COM4 -> COM7 | 2 -> 9 | 42 -> 10 | 41 -> 11 | 40 -> 12 | 39 -> 13 |
| COM7 -> COM8 | 6 -> 9 | 42 -> 10 | 41 -> 11 | 40 -> 12 | 39 -> 13 |
| COM8 -> COM9 | 2 -> 9 | 42 -> 10 | 41 -> 11 | 40 -> 12 | 39 -> 13 |
| COM9 -> COM11 | 2 -> 9 | 42 -> 10 | 41 -> 11 | 40 -> 12 | 39 -> 13 |
| COM11 -> COM22 | 6 -> 9 | 42 -> 10 | 41 -> 11 | 40 -> 12 | 39 -> 13 |
| COM22 -> COM4 | 2 -> 9 | 42 -> 10 | 41 -> 11 | 40 -> 12 | 39 -> 13 |

Use short wires, connect all grounds, and power each board by USB. Do not join
the boards' 5 V or 3.3 V rails. Disconnect power before changing wiring.

COM labels are evidence from the tested Windows host. The prebuilt firmware
selects roles by MAC address, not by COM number. COM3 is not part of this system.
