"""Exact base-3 packing used by the ESP32 ParetoQ shard format."""

from __future__ import annotations

from collections.abc import Iterable

TRITS_PER_BYTE = 5
TRIT_TO_DIGIT = {-1: 0, 0: 1, 1: 2}
DIGIT_TO_TRIT = (-1, 0, 1)


def pack_trits(values: Iterable[int]) -> tuple[bytes, int]:
    trits = list(values)
    out = bytearray()
    for offset in range(0, len(trits), TRITS_PER_BYTE):
        chunk = trits[offset : offset + TRITS_PER_BYTE]
        encoded = 0
        factor = 1
        for value in chunk:
            try:
                digit = TRIT_TO_DIGIT[int(value)]
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"invalid trit at index {offset + len(chunk) - 1}: {value!r}") from exc
            encoded += digit * factor
            factor *= 3
        out.append(encoded)
    return bytes(out), len(trits)


def unpack_trits(payload: bytes, count: int) -> list[int]:
    if count < 0:
        raise ValueError("count must be nonnegative")
    required = (count + TRITS_PER_BYTE - 1) // TRITS_PER_BYTE
    if len(payload) != required:
        raise ValueError(f"payload has {len(payload)} bytes; expected {required}")
    values: list[int] = []
    for encoded in payload:
        if encoded >= 3**TRITS_PER_BYTE:
            raise ValueError(f"invalid packed byte {encoded}; maximum is 242")
        remaining = encoded
        for _ in range(TRITS_PER_BYTE):
            values.append(DIGIT_TO_TRIT[remaining % 3])
            remaining //= 3
    return values[:count]
