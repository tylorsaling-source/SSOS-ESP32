#!/usr/bin/env sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
IMAGE_DIR="$ROOT/images/flash"

command -v sha256sum >/dev/null 2>&1 || {
  echo "verify: sha256sum is required" >&2
  exit 2
}

cd "$IMAGE_DIR"
sha256sum -c SHA256SUMS
