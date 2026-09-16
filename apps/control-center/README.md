# Control Center

Control Center is a graphical status and service manager for SolarOS. It uses
the native Python APIs introduced by current SolarOS builds; it does not run or
parse shell commands.

## Features

- Identity, uptime, registered-app count, and job count overview.
- Full background-job list with state and summary.
- Confirmed start and stop actions for jobs. Jobs that require command-line
  arguments may refuse a default start and report the reason.
- Wi-Fi start/reconnect, station disconnect, and confirmed service stop.
- Storage status and capacity when the active MicroPython integer build can
  represent the volume's byte counts, plus block-device rescan and
  default-volume mounting.
- Battery voltage, charge state, external-power status, and environmental
  readings when the corresponding hardware services are present.
- Graceful handling of services unavailable in a particular firmware flavor.
- An icon-led instrument-panel layout with crisp selection outlines, compact
  page counters, and native SolarOS symbols for each main control area.
- Overview and Hardware readings use aligned, individually separated key/value
  rows rather than dense wrapped text.

Control Center deliberately does not unmount its own storage, erase saved Wi-Fi
profiles, or change the system identity. These operations are too disruptive
for a one-key dashboard action.

## Controls

- Up/Down or `j`/`k`: move through lists.
- Enter or Right: open or activate the selected item.
- Escape, Left, or `q`: go back or exit.
- Page Up/Page Down: move through long job lists.
- Destructive or connection-breaking actions require `y` confirmation.

## Requirements

Control Center requires a current SolarOS Python runtime with `solaros.jobs`,
`solaros.wifi`, `solaros.storage`, `solaros.identity`, `solaros.apps`, and the
graphical display API. Unsupported optional services are shown as unavailable
instead of preventing the app from opening.
