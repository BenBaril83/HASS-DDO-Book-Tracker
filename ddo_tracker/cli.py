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

from .calendar import build_ics
from .client import DDOLibraryClient, DDOLibraryError
from .config import Config, ConfigError, load_config
from .digest import render_html, render_text, send_email
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
        choices=["list", "json", "calendar", "digest"],
        nargs="?",
        default="list",
        help=(
            "'list' prints a table; 'json' prints machine-readable output; "
            "'calendar' writes/prints an .ics feed of due dates; "
            "'digest' renders an email digest (add --send to email it)."
        ),
    )
    parser.add_argument(
        "-c",
        "--config",
        help="Path to a YAML config file (default: config.yaml or env vars).",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="For 'calendar': write the .ics here instead of stdout "
        "(defaults to the calendar.output_path in config).",
    )
    parser.add_argument(
        "--send",
        action="store_true",
        help="For 'digest': actually send the email via the configured SMTP.",
    )
    parser.add_argument(
        "--html",
        action="store_true",
        help="For 'digest': print HTML instead of plain text.",
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
    elif args.command == "calendar":
        return _do_calendar(accounts, config, args)
    elif args.command == "digest":
        return _do_digest(accounts, config, args)
    else:
        print(format_table(accounts))
    return 0


def _do_calendar(accounts: list[Account], config: Config, args) -> int:
    ics = build_ics(
        accounts,
        reminder_days_before=config.calendar.reminder_days_before,
        calendar_name=config.calendar.calendar_name,
    )
    output = args.output or config.calendar.output_path
    if output in (None, "-"):
        print(ics)
    else:
        with open(output, "w", encoding="utf-8", newline="") as handle:
            handle.write(ics)
        print(f"Wrote {output}", file=sys.stderr)
    return 0


def _do_digest(accounts: list[Account], config: Config, args) -> int:
    if args.send:
        if config.email is None:
            print(
                "Configuration error: no 'email' section in config to send with.",
                file=sys.stderr,
            )
            return 2
        try:
            send_email(accounts, config.email)
        except Exception as exc:  # noqa: BLE001 - surface any SMTP error cleanly
            print(f"Failed to send digest: {exc}", file=sys.stderr)
            return 1
        print(
            f"Digest sent to {', '.join(config.email.recipients)}", file=sys.stderr
        )
        return 0
    print(render_html(accounts) if args.html else render_text(accounts))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
