# ANT BMS for SolarOS Playground

Standalone Python monitor for up to two ANT Bluetooth BMS devices. It requires
SolarOS v4.11 or later, plus the standard Python, BLE, and graphics packages.

Install with `playground install antbms sd`, then run `playground run antbms`
from a display shell. The first launch opens Setup and scans nearby BLE
devices. Use Up/Down to select a result and Enter to assign and connect the
next BMS slot. After assigning both, press `C` to verify both connections and
open the dashboards. Their address, address type, and name are saved at
`/.solar/ant-bms.json` for later launches, preserving configurations from the
earlier `ant-bms` development package.

Controls:

- Left/Right: Summary, BMS 1 cells, BMS 2 cells, temperatures/health, Setup,
  after at least one BMS connection succeeds.
- Summary Up/Down: Overview, Power (large current/power), Energy (large SOC,
  capacity, and time remaining).
- Touch targets: swipe left/right for pages; swipe up/down on Summary for its
  three layouts. Keyboard controls remain available.
- Setup: Up/Down select, Enter assign, `R` scan, `C` connect, `X` clear.
- Escape: disconnect both BMSes and exit.

The summary refreshes at 1 Hz, showing aggregate SOC, pack voltage, individual
BMS voltage, a charge/draw gauge, and estimated time to empty or full. The app
uses SolarOS semantic colors for its interface and keeps literal color confined
to non-text gauge and cell-indicator fills, so monochrome targets retain
legible text. BLE notification polling remains active between UI refreshes, so
ANT frames are assembled without a one-second gap.
