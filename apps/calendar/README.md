# Calendar for SolarOS

Calendar is an offline-first graphical calendar designed for keyboard-driven
SolarOS devices. It keeps events locally and expands recurring rules only for
the date range currently on screen, keeping memory use bounded.

## Features

- Agenda view covering today and the next 30 days
- Graphical month grid with per-day event counts
- Single-day event lists and detailed event reading
- Timed and all-day events
- Location and notes fields
- Multiple named calendars with independent visibility
- Clearly exposed creation of additional local calendars
- Downloadable ICS URL subscriptions with per-calendar and sync-all refresh
- Transactional subscription refresh: failed downloads and malformed files keep
  the previously downloaded events intact
- Search across titles, locations, and notes
- Per-event reminders while Calendar is running
- Daily, weekday, weekly, monthly, and yearly recurrence
- Weekly selection of multiple weekdays
- Monthly numbered-day, Nth-weekday, and last-weekday rules
- Optional recurrence ending dates
- Skip one occurrence without deleting its recurring series
- Duplicate, edit, or delete events and recurring series
- 12- or 24-hour time display
- Sunday- or Monday-first month layout
- Four date formats
- ICS import and export
- JSON backup export
- Interrupted-save recovery and bounded validation of saved data

## Installation and launch

Copy this directory to `/apps/calendar` and add the included `alias` line to
`/.shell/alias`, or install the application through Playground. Launch it with:

```text
calendar
```

An ICS file can be imported directly from the shell using SolarOS's canonical
file argument:

```text
calendar --file /Downloads/events.ics
```

Additional calendars are managed through **Settings > Calendars and
subscriptions**. The first two entries create a local calendar or add an ICS
calendar from an `http://`, `https://`, or `webcal://` URL. Open a subscribed
calendar there and choose **Sync now** to refresh only that calendar, or use
**Sync all URL calendars** from Settings.

Subscribed calendars are read-only because their contents are replaced during
refresh. An event from a subscription can be duplicated into a local calendar
before editing it. Downloads are streamed to a temporary file and capped at 1
MB; the application parses the completed file before replacing any existing
events.

## Controls

### Agenda

- `Up` / `Down`: select an occurrence
- `Enter`: open the selected event
- `A`: add an event
- `M`: open the month view
- `/`: search
- `S`: settings
- `Esc`: exit

### Month

- Arrow keys: move by one day or one week
- `[` / `]` or `Page Up` / `Page Down`: previous or next month
- `Enter`: open the selected day's events
- `A`: add an event on the selected date
- `T`: return to today
- `Esc`: return to Agenda

### Event details

- `E`: edit the event or recurring series
- `D`: duplicate the event
- `S`: skip this occurrence of a recurring event
- `X`: delete this occurrence or the entire event
- `Esc`: return

## Storage and exports

Calendar stores its state beside the application in `calendar.json`. Saves are
written through a temporary file, with recovery from an interrupted save or
backup when possible.

Exports are written to `/Downloads`:

- `calendar-YYYY-MM-DD.ics`
- `calendar-YYYY-MM-DD.json`

The ICS reader handles common `VEVENT` fields, unfolded lines, all-day and timed
events, `RRULE`, and `EXDATE`. Imported UIDs are used to skip duplicates.
New local events use the configured SolarOS user and hostname as the UID origin,
for example `e2-20260912T100300@heyvictorfrost.mosscap`. Exports include the
required UTC `DTSTAMP` property.

## Current limitations

- Reminders appear only while Calendar is open. Event reminder data is stored in
  a form suitable for later SolarOS scheduler integration.
- ICS timezone identifiers and UTC markers are currently interpreted as local
  wall-clock time. Import calendars already exported in the device's timezone.
- The importer supports the recurrence forms offered by this app. Complex
  combinations involving `COUNT`, multiple `BYSETPOS` values, or detached
  recurrence overrides are not preserved fully.
- URL calendars refresh only when requested; there is no background sync.
- Authenticated calendar URLs and CalDAV write synchronization are not
  currently supported.

## Requirements

Calendar requires SolarOS 4.8.4 or newer, the Python runtime, writable storage,
a ready graphics display, keyboard input, and Wi-Fi for URL calendars. Existing
local and previously synchronized events remain usable offline.
