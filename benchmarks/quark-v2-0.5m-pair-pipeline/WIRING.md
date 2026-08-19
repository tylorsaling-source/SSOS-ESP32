# Wiring and power safety

## Two-board pair

## Signal wiring

| Signal | Master pin | Worker pin |
|---|---:|---:|
| SPI clock | GPIO12 | GPIO12 |
| Master to worker | GPIO11 | GPIO11 |
| Worker to master | GPIO13 | GPIO13 |
| Chip select | GPIO10 | GPIO10 |
| Worker ready | GPIO9 | GPIO9 |
| Common reference | GND | GND |

Use short wires. Connect ground before the five signal wires.

## Power

Power each board through its own USB connection or a correctly sized external
supply. Do not connect 5 V, VBUS or 3.3 V between two independently powered
boards. Only the grounds are shared.

## Role identification

- Master idle LED: violet
- Worker idle LED: green
- Red LED: initialization, link or validation failure

## Startup order

1. Confirm wiring with both boards unpowered.
2. Power or connect the worker.
3. Power or connect the master.
4. Wait for the worker green and master violet idle colors.
5. Send `RUN` followed by a newline to the master at 115200 baud.

## Three-board dual-lane topology

The two workers use independent clocks, MOSI, MISO, chip-select and READY
signals. Do not combine either lane's MISO wires.

| Signal | Trio master | Worker 1 | Worker 2 |
|---|---:|---:|---:|
| Lane 1 SCK | GPIO12 | GPIO12 | — |
| Lane 1 MOSI | GPIO11 | GPIO11 | — |
| Lane 1 MISO | GPIO13 | GPIO13 | — |
| Lane 1 CS | GPIO10 | GPIO10 | — |
| Lane 1 READY | GPIO9 | GPIO9 | — |
| Lane 2 SCK | GPIO6 | — | GPIO12 |
| Lane 2 MOSI | GPIO7 | — | GPIO11 |
| Lane 2 MISO | GPIO15 | — | GPIO13 |
| Lane 2 CS | GPIO14 | — | GPIO10 |
| Lane 2 READY | GPIO8 | — | GPIO9 |
| Common reference | GND | GND | GND |

Power every board independently by USB and join grounds only. Flash/power both
workers first, wait for their green/orange idle colors, then start the violet
master. Keep all jumpers short; lane 2 is GPIO-matrix routed and the accepted
40 MHz result included one checksum retry.
