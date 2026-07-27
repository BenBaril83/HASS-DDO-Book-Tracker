# DDO Library Book Tracker

Keep track of every book you (and your family) have checked out from the
**Dollard-des-Ormeaux public library**, and when each one is due — from the
command line, or surfaced in **Home Assistant** with reminders.

The DDO library runs Infor's *Iguana* web OPAC at `webopac.ddo.qc.ca`. There
is no public API, so this tool signs in the same way the website does and
reads the same JSON endpoints its own JavaScript uses.

## The key idea: one login covers all your cards

DDO family cards can be **linked**. When cards are linked, logging in with a
single card lets you read the loans on every linked card too. So even though
you have 4 accounts, you normally only need **one** barcode + PIN configured —
the tracker fetches your card, then "switches" into each linked card and reads
its loans as well.

(If any of your cards are *not* linked to each other, you can also list several
logins in the config — see below.)

## What you get

- A clean list of every book on loan across all accounts, sorted by due date.
- Per-book **days until due**, and overdue / due-soon flags.
- Machine-readable JSON for automation.
- A ready-made Home Assistant sensor, dashboard card, and morning reminder.

```
Account          Title                            Author                     Due         When
---------------  -------------------------------  -------------------------  ----------  -----
Bob              Charlie Brown, here we go again  Schulz, Charles M.         2026-07-30  in 3d
Bob              The yellow house mystery         Warner, Gertrude Chandler  2026-07-30  in 3d
Alice (primary)  Judy Moody                       McDonald, Megan            2026-08-04  in 8d
Alice (primary)  Take the plunge                  Green, John Patrick        2026-08-04  in 8d

4 item(s) across 2 account(s) · 0 overdue · 2 due within 3 days
```

## Install

```bash
git clone <this-repo>
cd HASS-DDO-Book-Tracker
python3 -m venv .venv && source .venv/bin/activate
pip install -e .          # or: pip install -r requirements.txt
```

## Configure

Copy the example config and fill in your card details:

```bash
cp config.example.yaml config.yaml
$EDITOR config.yaml
```

```yaml
accounts:
  - barcode: "00000000000000"   # the number on your library card
    pin: "1234"                 # your account PIN
    include_linked: true        # also read cards linked to this one
    institution: ""             # DDO uses "QMBDO"; "" also works
```

`config.yaml` is git-ignored so your credentials are never committed.

Prefer environment variables (e.g. for a single account)?

```bash
export DDO_BARCODE=00000000000000
export DDO_PIN=1234
```

## Use it

```bash
python3 -m ddo_tracker list      # pretty table (default)
python3 -m ddo_tracker json      # machine-readable JSON
python3 -m ddo_tracker list -c /path/to/config.yaml
```

If you installed with `pip install -e .`, the `ddo-tracker` command works too:

```bash
ddo-tracker list
```

### JSON shape

```jsonc
{
  "generated_at": "2026-07-27",
  "total_items": 4,
  "overdue_count": 0,
  "due_soon_count": 2,
  "next_due_date": "2026-07-30",
  "accounts": [ { "name": "...", "is_primary": true, "item_count": 2, "loans": [ ... ] } ],
  "items": [
    {
      "title": "Judy Moody",
      "author": "McDonald, Megan",
      "due_date": "2026-08-04",
      "days_until_due": 8,
      "is_overdue": false,
      "account_name": "...",
      "isbn": "9780763606855",
      ...
    }
  ]
}
```

## Home Assistant

The `homeassistant/` folder has everything to surface this in HA:

| File | What it is |
|------|------------|
| `run.sh` | Wrapper the sensor calls — sets `DDO_CONFIG` and prints the JSON. Edit the paths inside. |
| `command_line_sensor.yaml` | A `command_line` sensor (`sensor.ddo_library_books`) whose state is the number of books out and whose attributes carry the full data. |
| `dashboard_card.yaml` | A Markdown card listing all books by due date. |
| `automations.yaml` | A 9 a.m. reminder that pings you when anything is due within 3 days or overdue. |

Quick start:

1. Put this project on your HA host (e.g. `/config/ddo/HASS-DDO-Book-Tracker`)
   and your credentials at `/config/ddo/config.yaml`.
2. Edit the paths at the top of `homeassistant/run.sh`, and `chmod +x` it.
3. Add the sensor to `configuration.yaml`:
   ```yaml
   command_line: !include homeassistant/command_line_sensor.yaml
   ```
   `command_line` is a YAML-only integration, so **restart** Home Assistant
   (a reload won't pick it up).
4. Add the dashboard card and (optionally) the reminder automation.

## How it works (reverse-engineered API)

All calls go to `Rest.Server.cls?sessionId=<token>&method=<method>` with a
JSON body `{"request": {...}}`:

| Method | Purpose |
|--------|---------|
| `user/credentials` | Log in with `user` (barcode) + `password` (PIN); returns the body session token. |
| `user/summary` | Counts + the borrower's display name. |
| `user/linkedaccounts` | The owner id and every linked card. |
| `user/switchuser` | Make a linked card the "active" account. |
| `user/loans` | The active account's current loans (title, author, due date, …). |

The flow is: load the page to get a session cookie and URL token → `credentials`
to authenticate → read the primary card's `loans` → `switchuser` into each
linked card and read its `loans` → switch back to the owner.

### A note on reliability

This rides on an undocumented, JavaScript-driven surface, so the **login /
session handshake** was reconstructed from a captured browser session rather
than from documentation, and DDO could change it at any time. The **parsing**
of the loan data (the part most likely to matter day to day) is covered by
tests that run against real captured API responses. If a library-side change
breaks login, the failure is loud (a clear auth error), and the fix is
localized to `ddo_tracker/client.py`.

## Development

```bash
pip install -e ".[dev]"
python3 -m pytest -q
```

Tests use sanitized copies of real API responses in `tests/fixtures/` — no
personal data is committed.
