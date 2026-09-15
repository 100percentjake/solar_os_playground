# Hacker News

A small, read-only Hacker News client designed for the T-Deck display. It uses
the official Hacker News API and concentrates on discussion threads rather than
trying to launch external story pages.

## Controls

### Story list

- Up/Down: scroll one rendered line
- PgUp/PgDn: jump to the previous or next story
- Enter/Right: open the selected discussion
- `f`: switch between Top, Best, New, Ask, and Show feeds
- `r`: refresh the current feed
- Esc/Left/`q`: exit

### Comment thread

- Up/Down: scroll one rendered line
- PgUp/PgDn: jump to the previous or next comment
- Enter/Right/Space: expand or collapse replies
- Home/End: first or last visible comment
- `r`: reload the discussion
- Esc/Left/`q`: return to the story list

External story URLs are shown as domains in the list, but the app deliberately
does not attempt to open them in the SolarOS browser.

The first level of comments is loaded when a discussion opens. Replies are
downloaded only when their parent is expanded, keeping network traffic and
memory use reasonable on the ESP32.

Stories and replies appear as soon as each request finishes. A progress bar on
the bottom row remains visible while a batch is loading.

Large JSON integers such as Unix timestamps are retained as strings so API
responses remain compatible with SolarOS's small-int-only MicroPython build.
