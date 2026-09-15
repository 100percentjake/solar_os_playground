# Hacker News

A small, read-only Hacker News client designed for the T-Deck display. It uses
the official Hacker News API and concentrates on discussion threads rather than
trying to launch external story pages.

## Controls

### Story list

- Up/Down or PgUp/PgDn: move through stories
- Enter/Right: open the selected discussion
- `f`: switch between Top, Best, New, Ask, and Show feeds
- `r`: refresh the current feed
- Esc/Left/`q`: exit

### Comment thread

- Up/Down: move one comment
- PgUp/PgDn: move by a screenful
- Enter/Right/Space: expand or collapse replies
- Home/End: first or last visible comment
- `r`: reload the discussion
- Esc/Left/`q`: return to the story list

External story URLs are shown as domains in the list, but the app deliberately
does not attempt to open them in the SolarOS browser.

The first level of comments is loaded when a discussion opens. Replies are
downloaded only when their parent is expanded, keeping network traffic and
memory use reasonable on the ESP32.
