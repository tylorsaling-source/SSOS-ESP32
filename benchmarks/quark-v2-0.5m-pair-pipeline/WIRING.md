# Wiring and power safety

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
