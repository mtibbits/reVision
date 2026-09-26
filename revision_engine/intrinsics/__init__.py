"""Map SIMD intrinsic names to vendor documentation URLs."""

from __future__ import annotations

from functools import lru_cache
from importlib import resources

import yaml

_VENDORS = ("intel", "arm")


@lru_cache(maxsize=1)
def _table() -> dict[str, str]:
    table: dict[str, str] = {}
    for vendor in _VENDORS:
        text = resources.files(__package__).joinpath(f"{vendor}.yaml").read_text(encoding="utf-8")
        data = yaml.safe_load(text)
        pattern = data["url"]
        for name in data["names"]:
            table[name] = pattern.format(name=name)
    return table


def vendors() -> tuple[str, ...]:
    return _VENDORS


def lookup(name: str) -> str | None:
    if not name:
        return None
    return _table().get(name)
