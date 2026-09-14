# Contacts for SolarOS

Contacts is an offline graphical personal address book for SolarOS. It is
separate from SolarOS's built-in provider-neutral `contacts` service, which is
intended for gateway and MeshCore identities rather than ordinary personal
contact information.

## Features

- Alphabetical contact list
- Search across every stored field
- Multiple phone numbers per person
- Multiple email addresses per person
- Multiple labeled handles, such as Bluesky, Mastodon, Matrix, or amateur radio
- Postal or physical address
- Website
- Free-form notes
- Editing and deletion
- Duplicate phone number, email, and handle suppression
- Field and record size limits chosen for predictable MicroPython memory use
- Atomic saves with interrupted-save recovery and a retained previous copy
- Validation and repair of malformed or partially invalid saved data

## Installation and launch

Copy this directory to `/apps/addressbook` and add the included `alias` line to
`/.shell/alias`, or install it through Playground. Launch it with:

```text
addressbook
```

The name `addressbook` is intentional. SolarOS's native `contacts` application
has command precedence and manages trusted or discovered messaging endpoints.
Using a separate command prevents the two applications from colliding.

## Controls

### Contact list

- `Up` / `Down`: select a contact
- `Page Up` / `Page Down`: move by one screen
- `Enter` / `Right`: open the selected contact
- `A`: add a contact
- `/`: search names, contact details, addresses, and notes
- `C`: clear the current search
- `Esc`: exit

### Contact details

- `Up` / `Down`: scroll by one line
- `Page Up` / `Page Down`: scroll by one screen
- `E`: edit the contact
- `D` or `Delete`: delete the contact after confirmation
- `Esc` / `Left`: return to the list

### Editors

- `Up` / `Down`: select a field or list item
- `Enter`: edit or choose
- `S`: save a new or edited contact from any field
- `Backspace`: remove the last character in a text field
- `Esc`: cancel; unsaved contact edits require confirmation before they are
  discarded

Adding a contact opens this editor directly with Name selected. There is no
separate name prompt or second page of save and cancel menu entries.

Phone numbers and email addresses are deliberately stored as entered rather
than being rejected by strict format rules. This allows extensions,
international dialing forms, unusual local addresses, and future protocols.
Handles consist of a user-chosen service or label and a value.

## Storage

Contacts stores data in `/.addressbook/contacts.json`, outside the installed
application directory so a Playground update cannot replace it. Writes first
go to `contacts.json.tmp`; the previous valid file is retained as
`contacts.json.bak`. On startup the app checks the primary, temporary, and
backup copies in that order and recovers a usable interrupted save. Existing
data from the earlier `/apps/addressbook/contacts.json` location is migrated
automatically after the updated app starts successfully.

The current version supports up to 256 contacts. Each contact may contain up to
8 phone numbers, 8 email addresses, and 12 handles. Names and individual values
are bounded, addresses may contain 500 characters, and notes may contain 1,200
characters. These are memory-safety limits rather than file-system limits: the
app parses its JSON store in memory on an ESP32.

## Current limitations

- Data is local to this application and is not synchronized into SolarOS's
  native messaging-identity contact service.
- There is currently no CardDAV synchronization, vCard import/export, or
  automatic website/phone launching.
- The keyboard text API enters printable ASCII. Existing Unicode data remains
  valid when read from JSON, but cannot be typed directly on current devices.
- Displays smaller than 160 by 112 pixels receive an explanatory compatibility
  screen instead of a clipped interface.
