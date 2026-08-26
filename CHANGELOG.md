# Changelog

All notable changes to this project are documented here. This project adheres
to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Fixed
- **Fancy "bookshelf" dashboard no longer splits by card or double-counts.**
  DDO's owner card reports the whole family's loans as an aggregate while each
  linked child card repeats its own subset, so the old one-section-per-card
  layout showed every book twice and doubled the totals (e.g. "42 out" for 21
  books). The dashboard now renders a single combined shelf, collapsing the
  aggregate + child copy of a checkout into one tile (preferring the child's
  name for the small "who has it" label) and sorting everything by due date.

### Added
- **Reading history, ratings & person assignment (recommendations groundwork).**
  The client reads each account's loan history (`user/loanhistory`). The
  integration keeps a **persistent catalogue** (HA storage) of every book seen
  in loans/history — deduped by ISBN/title so books stay ratable after return —
  and adds `rate_book` / `assign_book` services (1–5 stars per person; record
  who actually read a book, independent of whose card borrowed it). New
  **Reading history** and **Books to rate** sensors, a rating helpers/scripts
  package, and a catalogue dashboard. Pure catalogue logic lives in
  `ddo_tracker/catalog.py` with unit tests.

- **Reservations / holds.** The client now reads each account's reservations
  (`user/reservations`); the integration exposes them on the per-account sensor
  (`reservations` list with queue position or "ready for pickup" + pickup
  location), plus **Reserved** and **Ready for pickup** summary sensors. Both
  dashboards gained a "Holds" section.

## [0.1.0] - 2026-07-27

First release.

### Added
- **Core library & CLI** (`ddo_tracker`) for the Dollard-des-Ormeaux Iguana
  OPAC: login, linked-account aggregation, and current loans with due dates.
  Commands: `list`, `json`, `calendar`, `digest`.
- **iCalendar feed** of due dates (subscribe from Google Calendar, no API
  credentials needed).
- **Email digest** (text + HTML) grouped by urgency, with Gmail-compatible SMTP.
- **Home Assistant HACS integration** (`custom_components/ddo_book_tracker`):
  config flow, `DataUpdateCoordinator`, and one sensor per account plus Total
  on loan / Overdue / Next due date. Options flow for refresh interval.
- **Home Assistant `command_line` alternative** (sensor, dashboard card,
  reminder automation) for those who prefer no custom component.
- Tests against sanitized copies of real captured API responses; CI runs
  `hassfest`, the HACS action, and a pytest matrix (3.11 / 3.12).

### Notes on behaviour
- One login reads every linked card you have permission to view (typically
  dependent/children cards). A **peer** link (e.g. a spouse's card) that the
  library won't let you view through your login is **skipped with a logged
  warning** rather than failing setup — add that card as its own login to
  track it.
- The session bootstrap, login, `switchuser`, and loan parsing are all verified
  against real captured browser sessions.
