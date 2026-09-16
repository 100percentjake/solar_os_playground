# Today Dashboard

Today Dashboard is a lightweight, offline daily overview for SolarOS. It reads
the data already maintained by Todo List, Calendar, Flint, and RSS Reader and
presents it in one 400 by 300 pixel screen.

## Features

- Today's visible calendar events, including recurring events.
- Open general tasks and tasks completed today.
- Due recurring tasks are shown even if Todo List has not yet been opened that
  day; Today does not modify Todo List's state.
- Recent Flint notes and unread cached RSS posts.
- A calm four-card home screen using SolarOS's native calendar, task, book, and
  RSS icons.
- A compact in-app status bar shows Wi-Fi state, battery level, charging state,
  and the current time while SolarOS graphics mode is active.
- Drill-down lists for every section.
- Manual refresh without repeatedly reading storage in the background.
- Read-only integration: source data remains owned by its original app.

Missing apps or damaged state files are treated as empty sources, so Today can
still open when only some companion apps are installed. Custom Flint vaults are
supported through Flint's saved configuration and per-vault index.

## Controls

- Arrow keys or `h`/`j`/`k`/`l`: move through the dashboard grid; Up/Down
  or `j`/`k` moves through detail lists.
- Enter: open a dashboard section. Enter or Right opens a selected detail item.
- Escape, Left, or `q`: go back or exit.
- `r`: reload all sources from storage.

## Data access

Today reads `/apps/todo/todo.json`, `/apps/calendar/calendar.json`,
`/apps/rss/cache.json`, and Flint's index under `/.flint`. It does not edit any
of these files and requires no network connection.
