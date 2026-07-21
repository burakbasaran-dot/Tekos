"""Helpers for parsing environment variables (testable without full Django settings load)."""

from __future__ import annotations

import os


def env_flag(name: str, default: str = "False") -> bool:
    """Return True when env var equals true/1/yes (case-insensitive)."""
    return os.getenv(name, default).strip().lower() in ("true", "1", "yes")


def parse_csv_env(name: str, default: str = "") -> list[str]:
    """Split a comma-separated env var into stripped non-empty items."""
    return [
        part.strip()
        for part in os.getenv(name, default).split(",")
        if part.strip()
    ]
