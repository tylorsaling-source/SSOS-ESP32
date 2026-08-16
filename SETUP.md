# Setup

Start with the platform instructions in [README.md](README.md):

- Windows: `scripts\flash-windows.cmd`
- Android/Termux: `scripts/flash-termux.sh`
- Linux/macOS: `scripts/flash-posix.sh`

Detailed safety, troubleshooting, and recovery instructions are in
[docs/FLASHING.md](docs/FLASHING.md).

The supplied binaries are only for the tested ESP32-S3-WROOM-1U N16R8 board
with 16 MB flash. Do not enable OPI PSRAM. Never leave DTR asserted; DTR drives
GPIO0/BOOT on the tested board.
