# DDO Library Book Tracker

Keep track of every book you (and your family) have checked out from the
**Dollard-des-Ormeaux public library**, and when each one is due — from the
command line, or surfaced in **Home Assistant** with reminders.

The DDO library runs Infor's *Iguana* web OPAC at `webopac.ddo.qc.ca`. There
is no public API, so this tool signs in the same way the website does and
reads the same JSON endpoints its own JavaScript uses.

## The key idea: one login covers all your cards

DDO family cards can be **linked**. When cards are linked, logging in with a
single card lets you read the loans on every linked card too. So you normally
only need **one** barcode + PIN configured — the tracker fetches your card,
then "switches" into each linked card and reads its loans as well.

### Which linked cards can be read

The library only lets you *view* linked cards where you have that permission —
typically **dependent** cards (e.g. your children). A **peer** link (e.g. a
spouse's card) shows up as linked, but the library won't let you read it
through your login; the tracker detects this, **skips that card with a logged
warning, and keeps going** — it never fails because of one unreadable card.

To also track a peer's books, just add *their* card as its own login:

- **CLI:** list a second account in `config.yaml` (see below).
- **Home Assistant:** add the integration a second time with that card's
  barcode + PIN.

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
python3 -m ddo_tracker calendar  # write/print an .ics feed of due dates
python3 -m ddo_tracker digest    # render an email digest (--send to email it)
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

## Calendar & email

Two optional ways to be reminded, both configured in `config.yaml` (see the
`calendar:` and `email:` sections in `config.example.yaml`):

- **Google Calendar** — `python -m ddo_tracker calendar -o due.ics` writes an
  iCalendar feed with an all-day event (and reminder) per book. Subscribe to it
  from Google Calendar (**Other calendars → From URL**); no Google API
  credentials needed. Events use stable UIDs, so refreshing the feed updates
  existing entries and drops returned books.
- **Email digest** — `python -m ddo_tracker digest` prints a grouped
  (overdue / due-soon / later) summary; add `--send` to email it. Defaults
  target Gmail SMTP — use a [Gmail App Password](https://myaccount.google.com/apppasswords).

Scheduling both from Home Assistant is covered in
[`homeassistant/calendar_and_digest.md`](homeassistant/calendar_and_digest.md).

## Home Assistant — HACS custom integration (recommended)

The `custom_components/ddo_book_tracker/` folder is a full Home Assistant
integration: add your card once in the UI and get sensors with no YAML.

**Install via HACS**

1. HACS → ⋮ → **Custom repositories** → add `https://github.com/BenBaril83/HASS-DDO-Book-Tracker`, category **Integration**.
2. Install **DDO Library Book Tracker**, then **restart** Home Assistant.
3. **Settings → Devices & Services → Add Integration → DDO Library Book Tracker**, and enter one card's barcode + PIN. Linked family cards are picked up automatically.

**Or install manually:** copy `custom_components/ddo_book_tracker/` into your HA
`config/custom_components/` and restart.

**Entities created** (grouped under one "DDO Library" device):

- One sensor **per account** — state = books on loan; attributes include a
  `books` list (title, author, due date, days until due), `next_due_date`, and
  a `reservations` list (holds — queue position or "ready for pickup").
- **Total on loan**, **Overdue**, **Next due date**, **Reserved** (total holds),
  and **Ready for pickup** (holds waiting on the shelf) summary sensors.

Refresh interval and whether to include linked accounts are adjustable under
the integration's **Configure** (options) button.

**Multiple logins:** you can add the integration more than once — one entry per
card you have credentials for. Use this to cover a peer (e.g. spouse) card that
can't be read through your own login. Each entry is keyed by borrower ID, so
adding the same card twice is prevented.

**Dashboards** (both auto-discover the per-account sensors — no entity IDs to
fill in; add via **Edit dashboard → Add card → Manual**):

- [`homeassistant/dashboard_by_card.yaml`](homeassistant/dashboard_by_card.yaml)
  — a plain **Markdown** card listing every book grouped by card and sorted by
  due date, with overdue/due-soon flags and a totals header. No extra installs.
- [`homeassistant/dashboard_fancy.yaml`](homeassistant/dashboard_fancy.yaml)
  — a **cover-tile "bookshelf"** grouped by family member with color-coded due
  badges. Covers come from Open Library by ISBN (gradient fallback otherwise).
  Requires the HACS **Frontend** card `button-card` (`custom:button-card`).

**Notifications:** [`homeassistant/automation_hold_ready.yaml`](homeassistant/automation_hold_ready.yaml)
sends a push when a hold becomes ready for pickup (off the **Ready for pickup**
sensor), listing the title(s), whose card, and where to collect them. See also
`homeassistant/automations.yaml` for a due-soon reminder.

> Maintainer note: HACS shows the integration best once the repo has a
> description + topics and at least one **GitHub release/tag**. CI
> (`hassfest` + the HACS action) validates the integration on every push.

## Home Assistant — command_line sensor (no-install alternative)

If you'd rather not install a custom component, the `homeassistant/` folder
drives the same data through a `command_line` sensor:

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

This rides on an undocumented, JavaScript-driven surface, so DDO could change
it at any time. The **session bootstrap**, the **login request** (endpoint,
fields, and values — including `serviceProfile: "Iguana"`), the **switchuser**
call, and the **loan parsing** are all verified against real captured sessions
and covered by tests. If a library-side change ever
breaks login, the failure is loud (a clear auth error) and the fix is localized
to `ddo_tracker/client.py`.

## Development

```bash
pip install -e ".[dev]"
python3 -m pytest -q
```

Tests use sanitized copies of real API responses in `tests/fixtures/` — no
personal data is committed.
