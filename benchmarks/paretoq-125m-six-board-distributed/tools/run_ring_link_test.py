#!/usr/bin/env python3
"""Run one six-board SPI ring lap without loading model PSRAM payloads."""

from __future__ import annotations

import json
import time

from run_physical_benchmark import PORTS, dump_ring_status, open_port, wait_line


def main() -> None:
    connections = {}
    try:
        for port in PORTS:
            connection = open_port(port)
            connections[port] = connection
            connection.reset_input_buffer()
            connection.write(b"INFO\n")
            wait_line(connection, "INFO ", 10)
        for port in PORTS[1:]:
            connections[port].write(b"STARTLINK\n")
            wait_line(connections[port], "OK STARTLINK", 10)
        connections["COM4"].write(b"STARTLINK\n")
        wait_line(connections["COM4"], "OK STARTLINK", 10)
        time.sleep(2)
        # A node that restarts during peripheral bring-up reports bus=0. Repair
        # that transient once before injecting the authoritative packet.
        for port in PORTS:
            connection = connections[port]
            connection.reset_input_buffer()
            connection.write(b"INFO\n")
            status = wait_line(connection, "INFO ", 5)
            print(json.dumps({"port": port, "pre_link_status": status}), flush=True)
            if " bus=0 " in f" {status} ":
                connection.write(b"STARTLINK\n")
                wait_line(connection, "OK STARTLINK", 10)
        time.sleep(1)
        master = connections["COM4"]
        master.write(b"LINKTEST\n")
        result = wait_line(master, "LINKTEST ", 30)
        print(result, flush=True)
        dump_ring_status(connections)
        fields = dict(item.split("=", 1) for item in result.split()[1:])
        if fields.get("pass") != "1" or fields.get("spi_errors") != "0":
            raise SystemExit(1)
        print(json.dumps({"ring_link_test": "pass", "ports": PORTS}), flush=True)
    finally:
        for connection in connections.values():
            connection.dtr = False
            connection.rts = False
            connection.close()


if __name__ == "__main__":
    main()
