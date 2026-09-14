# copyparty Client

A full-screen graphical client for browsing a copyparty server from SolarOS.

## Features

- Browse remote folders using copyparty's JSON listing API.
- Navigate a pixel-based interface with clear file and folder rows, paging,
  progress bars, and layouts that adapt to the display size.
- Save and switch among up to 20 named server connections.
- Authenticate with either a password or `--usernames` username/password pair.
- Page through large directory listings from a disk-backed index.
- Download files directly to flash or SD storage in bounded HTTP ranges.
- Recursively download a remote folder.
- Preview folder contents and follow per-file and overall download progress.
- Choose the local destination for every download.
- Upload local files up to 64 KiB into the current remote folder.
- Create folders when the signed-in user has write permission.
- Refuse to overwrite an existing remote file.
- Prefill an upload path with the canonical Playground `--file PATH` option.

## Setup

Run `copyparty`, press `n` in the saved-server screen, and enter a connection
name and server URL. Include any volume or folder that should be the root of
the browser, for example:

```text
https://files.example.net/SolarOS/
```

Entering a bare hostname or IP address automatically selects copyparty's stock
port 3923. URLs that include `http://`, `https://`, or an explicit port are
preserved. For example, a stock LAN server can be entered as `192.168.1.20`,
which becomes `http://192.168.1.20:3923/`.

The username and password are optional. Leave the username blank for a normal
password-only copyparty server. If the server uses copyparty's `--usernames`
option, enter both fields; the client sends `PW: username:password` as required
by copyparty. Saved connections and credentials are stored as plain text in
`config.json` beside the installed script. Do not distribute that file in a
support bundle or copied installation. Configurations made by versions before
1.4 are migrated into the saved-server list automatically.
Malformed saved entries, control characters, and credentials containing HTTP
header delimiters are rejected rather than sent to a server.

SolarOS validates HTTPS certificates against its built-in certificate bundle.
Self-signed certificates are not supported by the HTTP client; use a
publicly trusted certificate or plain HTTP only on a trusted local network.
For safety, the client follows neither redirects nor links to a different
server origin.

## Controls

- Up/Down and Page Up/Page Down move through the remote listing.
- Enter opens a folder or downloads the selected file.
- `d` downloads the selected file or folder and asks for a local destination.
- `u` uploads a local file into the current remote folder.
- `m` creates a folder in the current remote folder.
- `r` refreshes the listing.
- `c` opens saved servers, where `n` adds, `e` edits, and `d` deletes a server.
- Escape or `q` goes to the parent folder, then exits from the configured root.

From the shell, an existing file can be prepared for upload with:

```text
copyparty --file /notes/todo.txt
```

SolarOS Playground Python cannot currently enumerate local directories, so
local paths are entered in a path editor rather than selected from a local
directory tree. Remote navigation is fully interactive.

## Limits

Directory listings are capped at 512 KiB, individual downloaded files at 64
MiB, recursive folder downloads at 256 files and 256 subdirectories, and
uploads at 64 KiB. Failed write operations report the HTTP status returned by
copyparty; read-only users can continue browsing and downloading normally.

Before a folder download begins, the client enumerates its contents into a
disk-backed plan. The download screen shows each file as pending, active with a
percentage, or complete, plus overall byte progress. If the plan is longer than
the display, it automatically follows the active file from page to page. The
plan is removed when the transfer finishes or fails, so large folder trees do
not remain in the MicroPython heap.

Downloads are written with an `.incomplete` suffix until the server confirms
the transfer completed. Interrupted files are preserved with that suffix for
inspection or removal and are never presented as completed downloads.
Replacing an existing single-file destination requires confirmation. Recursive
downloads stop before transfer if an existing file or a case-insensitive local
filename collision is found, preventing a folder from silently replacing local
content.
File data is pulled in 64 KiB HTTP ranges over one reused connection and each
range is written before the next is requested. The complete file is never held
in memory, and storage or display delays cannot overflow a background network
queue. Directory listings still use a bounded stream because their total size
is capped at 512 KiB.

The client requires SolarOS 4.8.4 or newer with Wi-Fi, Python, Playground, and
the HTTP client enabled.

## Release verification

Version 1.6.0 is tested against copyparty 1.20.23 with anonymous and
password-protected volumes, rejected logins, JSON directory listings,
byte-range downloads, and authenticated uploads. The test suite also covers
terminal-control sanitization, narrow-display clipping, malformed large
listings, incomplete transfers, path portability, header-injection rejection,
and local filename collision protection.
