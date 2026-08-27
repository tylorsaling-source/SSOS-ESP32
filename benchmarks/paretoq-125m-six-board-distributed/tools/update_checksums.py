#!/usr/bin/env python3
"""Regenerate the deterministic package checksum inventory."""

from __future__ import annotations

import hashlib
from pathlib import Path


def digest(path: Path) -> str:
    if path.suffix.lower() != ".bin":
        return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


root = Path(__file__).resolve().parents[1]
paths = sorted(
    (path for path in root.rglob("*")
     if path.is_file()
     and path.name != "SHA256SUMS"
     and not {"__pycache__", ".pytest_cache"}.intersection(path.parts)),
    key=lambda path: path.relative_to(root).as_posix(),
)
(root / "SHA256SUMS").write_text(
    "".join(f"{digest(path)}  {path.relative_to(root).as_posix()}\n" for path in paths),
    encoding="utf-8",
)
