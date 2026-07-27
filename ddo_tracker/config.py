"""Configuration loading for the DDO book tracker.

Credentials can come from either a YAML config file or environment variables.
Because DDO family cards are usually *linked*, a single login can read every
account. But you can also list multiple independent logins here in case some
of your cards are not linked to one another.

YAML format (see config.example.yaml)::

    accounts:
      - barcode: "0000..."
        pin: "1234"
        include_linked: true   # also read accounts linked to this one
        institution: ""        # optional, defaults to ""

Environment variables (single-account fallback)::

    DDO_BARCODE=0000...
    DDO_PIN=1234
    DDO_INSTITUTION=            # optional
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml


@dataclass
class AccountConfig:
    barcode: str
    pin: str
    institution: str = ""
    include_linked: bool = True

    def __post_init__(self) -> None:
        self.barcode = str(self.barcode).strip()
        self.pin = str(self.pin).strip()


@dataclass
class Config:
    accounts: list[AccountConfig]


class ConfigError(Exception):
    """Raised when no usable credentials can be found."""


def load_config(path: Optional[str] = None) -> Config:
    """Load configuration from ``path`` (YAML) or environment variables.

    Resolution order:
      1. explicit ``path`` argument
      2. ``DDO_CONFIG`` environment variable
      3. ``config.yaml`` in the current working directory
      4. ``DDO_BARCODE`` / ``DDO_PIN`` environment variables
    """
    candidate = path or os.environ.get("DDO_CONFIG")
    if not candidate and Path("config.yaml").is_file():
        candidate = "config.yaml"

    if candidate:
        return _load_yaml(Path(candidate))
    return _load_env()


def _load_yaml(path: Path) -> Config:
    if not path.is_file():
        raise ConfigError(f"Config file not found: {path}")
    data = yaml.safe_load(path.read_text()) or {}
    raw_accounts = data.get("accounts")
    if not raw_accounts:
        raise ConfigError(f"No 'accounts' listed in {path}")
    accounts = []
    for entry in raw_accounts:
        if not entry.get("barcode") or not entry.get("pin"):
            raise ConfigError(
                f"Each account needs a 'barcode' and 'pin' (in {path})"
            )
        accounts.append(
            AccountConfig(
                barcode=entry["barcode"],
                pin=entry["pin"],
                institution=entry.get("institution", ""),
                include_linked=entry.get("include_linked", True),
            )
        )
    return Config(accounts=accounts)


def _load_env() -> Config:
    barcode = os.environ.get("DDO_BARCODE")
    pin = os.environ.get("DDO_PIN")
    if not barcode or not pin:
        raise ConfigError(
            "No config file found and DDO_BARCODE / DDO_PIN are not set. "
            "Create a config.yaml (see config.example.yaml) or set the "
            "environment variables."
        )
    return Config(
        accounts=[
            AccountConfig(
                barcode=barcode,
                pin=pin,
                institution=os.environ.get("DDO_INSTITUTION", ""),
                include_linked=_env_bool("DDO_INCLUDE_LINKED", True),
            )
        ]
    )


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")
