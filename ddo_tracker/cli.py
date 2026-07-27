"""Command-line interface for the DDO book tracker.

Usage::

    python -m ddo_tracker list            # pretty table of all books
    python -m ddo_tracker json            # machine-readable JSON (for HA)
    python -m ddo_tracker list -c my.yaml # explicit config file
"""

from __future__ import annotations

import argparse
import json
import sys

from .client import DDOLibraryClient, DDOLibraryError
from .config import Config, ConfigError, load_config
from .models import Account
from .report import build_summary, format_table


def gather_accounts(config: Config) -> list[Account]:
    """Log in to every configured account and collect their loans."""
    accounts: list[Account] = []
    seen: set[str] = set()
    for account_cfg in config.accounts:
        client = DDOLibraryClient(
            barcode=account_cfg.barcode,
            pin=account_cfg.pin,
            institution=account_cfg.institution,
        )
        client.login()
        for account in client.fetch_all_accounts(
            include_linked=account_cfg.include_linked
        ):
            # De-duplicate: linked accounts can appear via multiple logins.
            key = account.account_id or account.name
            if key in seen:
                continue
            seen.add(key)
            accounts.append(account)
    return accounts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ddo_tracker",
        description="Track books checked out from the DDO library.",
    )
    parser.add_argument(
        "command",
        choices=["list", "json"],
        nargs="?",
        default="list",
        help="'list' prints a table; 'json' prints machine-readable output.",
    )
    parser.add_argument(
        "-c",
        "--config",
        help="Path to a YAML config file (default: config.yaml or env vars).",
    )
    args = parser.parse_args(argv)

    try:
        config = load_config(args.config)
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    try:
        accounts = gather_accounts(config)
    except DDOLibraryError as exc:
        print(f"Library error: {exc}", file=sys.stderr)
        return 1

    if args.command == "json":
        print(json.dumps(build_summary(accounts), indent=2, ensure_ascii=False))
    else:
        print(format_table(accounts))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
