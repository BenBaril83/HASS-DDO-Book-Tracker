# Calendar feed & email digest in Home Assistant

Two optional extras on top of the `sensor.ddo_library_books` sensor.

## 1. Due dates in Google Calendar (via an .ics feed)

The tracker can write an iCalendar file that Google Calendar subscribes to — no
Google API credentials needed.

1. Have HA regenerate the feed a few times a day. Add a `shell_command` and an
   automation (or a cron job on the host):

   ```yaml
   # configuration.yaml
   shell_command:
     ddo_calendar: "/config/ddo/run.sh calendar -o /config/www/ddo_due_dates.ics"
   ```

   > `run.sh` already sets `DDO_CONFIG` and the project dir; it forwards any
   > extra arguments to the CLI. Writing into `/config/www/` exposes the file
   > at `https://<your-ha>/local/ddo_due_dates.ics`.

   ```yaml
   # automations.yaml — refresh 3x/day
   - alias: "Refresh library calendar feed"
     id: ddo_refresh_calendar
     mode: single
     triggers:
       - trigger: time
         at: ["07:00:00", "13:00:00", "19:00:00"]
     actions:
       - action: shell_command.ddo_calendar
   ```

2. In Google Calendar: **Other calendars → + → From URL**, and paste the
   public URL of `ddo_due_dates.ics`. Google refreshes subscribed URLs
   periodically. (If your HA isn't public, host the file anywhere reachable,
   or use HA's own **Local Calendar** and import the file.)

Prefer to keep it entirely local? HA's **Local Calendar** integration can
import the same `.ics`.

## 2. Emailed digest

If you configured the `email:` section in `config.yaml`, the CLI can send the
digest directly:

```yaml
# configuration.yaml
shell_command:
  ddo_digest: "/config/ddo/run.sh digest --send"
```

```yaml
# automations.yaml — Monday & Thursday at 08:00
- alias: "Library email digest"
  id: ddo_email_digest
  mode: single
  triggers:
    - trigger: time
      at: "08:00:00"
  conditions:
    - condition: time
      weekday: [mon, thu]
  actions:
    - action: shell_command.ddo_digest
```

Alternatively, skip SMTP and let Home Assistant send it through an existing
notify/email service, using the sensor attributes to build the body — see
`automations.yaml` for the templating pattern.

> `shell_command` is a YAML-only integration: **restart** Home Assistant after
> adding it (a reload won't register new shell commands).
