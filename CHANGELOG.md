# Changelog

All notable changes to this project are documented here. This project adheres
to [Semantic Versioning](https://semver.org/).

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
