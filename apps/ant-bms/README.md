# ANT BMS for SolarOS Playground

Standalone Python monitor for up to two ANT Bluetooth BMS devices. It requires
SolarOS v4.11 or later, plus the standard Python, BLE, and graphics packages.

Run `python ant_bms.py` from a display shell. The first launch opens Setup and
scans nearby BLE devices. Use Up/Down to select a result and Enter to assign
the next BMS slot. After assigning both, press `C` to connect; their address,
address type, and name are saved at `/.solar/ant-bms.json` for later launches.

Controls:

- Left/Right: Summary, BMS 1 cells, BMS 2 cells, temperatures/health, Setup.
- Summary Up/Down: Overview, Power (large current/power), Energy (large SOC,
  capacity, and time remaining).
- Touch targets: swipe left/right for pages; swipe up/down on Summary for its
  three layouts. Keyboard controls remain available.
- Setup: Up/Down select, Enter assign, `R` scan, `C` connect, `X` clear.
- Escape: disconnect both BMSes and exit.

The summary refreshes at 1 Hz, showing aggregate SOC, pack voltage, individual
BMS voltage, current/draw gauge, and estimated run time to zero. Low aggregate
SOC tints the whole interface red. BLE notification polling remains active
between UI refreshes, so ANT frames are assembled without a one-second gap.
