"""ANT BMS monitor for SolarOS Playground.

Requires SolarOS v4.11 or later for solaros.ble.scan and solaros.ble.gatt.
Use Left/Right to change pages; touch targets also support swipe navigation.
"""

import json
import os

import solaros
from solaros import gfx
from solaros import input as device_input


APP_NAME = "ANT BMS"
CONFIG_PATH = "/.solar/ant-bms.json"
SERVICE_UUID = "ffe0"
CHARACTERISTIC_UUID = "ffe1"
MAX_FRAME = 192
POLL_INTERVAL_MS = 500
REDRAW_INTERVAL_MS = 1000
LOW_SOC_PERCENT = 20.0

PAGE_SUMMARY = 0
PAGE_BMS1 = 1
PAGE_BMS2 = 2
PAGE_TEMPS = 3
PAGE_SETUP = 4
PAGE_COUNT = 5

LAYOUT_OVERVIEW = 0
LAYOUT_POWER = 1
LAYOUT_ENERGY = 2
LAYOUT_COUNT = 3


def has_touch_pointer():
    """Return True only when a ready absolute-pointer source is present."""
    try:
        for source in device_input.sources():
            capabilities = source.get("capabilities", 0)
            if (source.get("ready") and
                    capabilities & device_input.CAP_POINTER_ABSOLUTE):
                return True
    except Exception:
        pass
    return False


def now_ms():
    return solaros.time.uptime_ms()


def crc16(data):
    value = 0xffff
    for byte in data:
        value ^= byte
        for _ in range(8):
            if value & 1:
                value = (value >> 1) ^ 0xa001
            else:
                value >>= 1
    return value


def u16(data, offset):
    return data[offset] | (data[offset + 1] << 8)


def i16(data, offset):
    value = u16(data, offset)
    return value - 65536 if value >= 32768 else value


def u32(data, offset):
    return u16(data, offset) | (u16(data, offset + 2) << 16)


def i32(data, offset):
    value = u32(data, offset)
    return value - 4294967296 if value >= 2147483648 else value


def uuid_has(uuid, short_uuid):
    return short_uuid in uuid.lower().replace("0x", "").replace("-", "")


def new_reading():
    return {
        "valid": False,
        "cells": [],
        "temps": [],
        "voltage": 0.0,
        "current": 0.0,
        "power": 0.0,
        "soc": 0.0,
        "soh": 0.0,
        "capacity_total": 0.0,
        "capacity_remaining": 0.0,
        "runtime": 0,
        "min_cell": 0.0,
        "max_cell": 0.0,
        "avg_cell": 0.0,
        "delta_cell": 0.0,
        "charge_mos": 0,
        "discharge_mos": 0,
        "balancer": 0,
        "frames": 0,
        "crc_errors": 0,
    }


def new_module(label):
    return {
        "label": label,
        "address": "",
        "addr_type": 0,
        "name": "",
        "peer": None,
        "handle": 0,
        "buffer": bytearray(),
        "connected": False,
        "last_request": 0,
        "last_error": "not configured",
        "reading": new_reading(),
    }


def load_config(modules):
    try:
        with open(CONFIG_PATH, "r") as handle:
            config = json.load(handle)
        entries = config.get("modules", [])
        for index in range(min(2, len(entries))):
            entry = entries[index]
            modules[index]["address"] = entry.get("address", "")
            modules[index]["addr_type"] = int(entry.get("addr_type", 0))
            modules[index]["name"] = entry.get("name", "")
        return bool(modules[0]["address"])
    except Exception:
        return False


def save_config(modules):
    try:
        try:
            os.mkdir("/.solar")
        except OSError:
            pass
        entries = []
        for module in modules:
            if module["address"]:
                entries.append({
                    "address": module["address"],
                    "addr_type": module["addr_type"],
                    "name": module["name"],
                })
        with open(CONFIG_PATH, "w") as handle:
            handle.write(json.dumps({"version": 1, "modules": entries}))
        return True
    except Exception:
        return False


def status_request():
    frame = bytearray((0x7e, 0xa1, 0x01, 0x00, 0x00, 0xbe, 0, 0, 0xaa, 0x55))
    checksum = crc16(frame[1:6])
    frame[6] = checksum & 0xff
    frame[7] = checksum >> 8
    return frame


def parse_status(module, frame):
    if len(frame) < 110 or frame[2] != 0x11 or len(frame) != 6 + frame[5] + 4:
        return False
    cell_count = min(frame[9], 32)
    temp_count = min(frame[8], 4)
    offset = cell_count * 2
    try:
        cells = [u16(frame, 34 + index * 2) * 0.001 for index in range(cell_count)]
        temps = [i16(frame, 34 + offset + index * 2) for index in range(temp_count)]
        offset += temp_count * 2
        if len(temps) < 6 and 35 + offset < len(frame):
            temps.append(i16(frame, 34 + offset))
        if len(temps) < 6 and 37 + offset < len(frame):
            temps.append(i16(frame, 36 + offset))
        if 110 + offset >= len(frame):
            return False
        previous = module["reading"]
        module["reading"] = {
            "valid": True,
            "cells": cells,
            "temps": temps,
            "voltage": u16(frame, 38 + offset) * 0.01,
            "current": i16(frame, 40 + offset) * 0.1,
            "soc": u16(frame, 42 + offset),
            "soh": u16(frame, 44 + offset),
            "charge_mos": frame[46 + offset],
            "discharge_mos": frame[47 + offset],
            "balancer": frame[48 + offset],
            "capacity_total": u32(frame, 50 + offset) * 0.000001,
            "capacity_remaining": u32(frame, 54 + offset) * 0.000001,
            "power": i32(frame, 62 + offset),
            "runtime": u32(frame, 66 + offset),
            "max_cell": u16(frame, 74 + offset) * 0.001,
            "min_cell": u16(frame, 78 + offset) * 0.001,
            "delta_cell": u16(frame, 82 + offset) * 0.001,
            "avg_cell": u16(frame, 84 + offset) * 0.001,
            "frames": previous["frames"] + 1,
            "crc_errors": previous["crc_errors"],
        }
        module["last_error"] = "live"
        return True
    except (IndexError, ValueError):
        return False


def feed_frame(module, data):
    if len(data) >= 2 and data[0] == 0x7e and data[1] == 0xa1:
        module["buffer"] = bytearray()
    if len(module["buffer"]) + len(data) > MAX_FRAME:
        module["buffer"] = bytearray()
        module["last_error"] = "frame too large"
        return
    module["buffer"].extend(data)
    buffer = module["buffer"]
    if len(buffer) < 10 or buffer[-2:] != b"\xaa\x55":
        return
    frame_length = 6 + buffer[5] + 4
    if frame_length <= len(buffer):
        frame = buffer[:frame_length]
        expected = u16(frame, frame_length - 4)
        if crc16(frame[1:frame_length - 4]) == expected:
            parse_status(module, frame)
        else:
            module["reading"]["crc_errors"] += 1
            module["last_error"] = "CRC error"
    module["buffer"] = bytearray()


def find_ant_handle(peer):
    for service in solaros.ble.gatt.services(peer):
        if not uuid_has(service["uuid"], SERVICE_UUID):
            continue
        for characteristic in solaros.ble.gatt.characteristics(peer, service["index"]):
            if uuid_has(characteristic["uuid"], CHARACTERISTIC_UUID):
                return characteristic["handle"]
    return 0


def connect_module(module):
    if not module["address"]:
        return False
    disconnect_module(module)
    try:
        module["last_error"] = "connecting"
        peer = solaros.ble.gatt.connect(module["address"], module["addr_type"], 12000)
        handle = find_ant_handle(peer)
        if not handle:
            solaros.ble.gatt.disconnect(peer)
            module["last_error"] = "FFE0/FFE1 not found"
            return False
        solaros.ble.gatt.configure_queue(peer, 32)
        solaros.ble.gatt.subscribe(peer, handle)
        module["peer"] = peer
        module["handle"] = handle
        module["connected"] = True
        module["last_request"] = 0
        module["last_error"] = "connected"
        return True
    except OSError as error:
        module["last_error"] = "connect " + str(error)
        return False


def disconnect_module(module):
    if module["peer"] is not None:
        try:
            solaros.ble.gatt.disconnect(module["peer"])
        except OSError:
            pass
    module["peer"] = None
    module["handle"] = 0
    module["connected"] = False
    module["buffer"] = bytearray()


def poll_modules(modules, current_time):
    for module in modules:
        if not module["connected"]:
            continue
        if current_time - module["last_request"] >= POLL_INTERVAL_MS:
            try:
                solaros.ble.gatt.write(module["peer"], module["handle"], status_request(), False, 1000)
                module["last_request"] = current_time
            except OSError as error:
                module["last_error"] = "write " + str(error)
                disconnect_module(module)
                continue
        while True:
            try:
                event = solaros.ble.gatt.poll(module["peer"])
            except OSError as error:
                module["last_error"] = "poll " + str(error)
                disconnect_module(module)
                break
            if event is None:
                break
            if event["handle"] == module["handle"]:
                feed_frame(module, event["data"])


def scan_devices():
    try:
        return solaros.ble.scan()
    except OSError:
        return []


def foreground_for_soc(soc):
    if soc <= LOW_SOC_PERCENT:
        return gfx.rgb(175, 0, 0)
    if soc <= 40:
        return gfx.rgb(180, 100, 0)
    return gfx.rgb(0, 105, 65)


def background_for_soc(soc):
    if soc <= LOW_SOC_PERCENT:
        return gfx.rgb(255, 219, 219)
    return gfx.rgb(244, 248, 252)


def aggregate(modules):
    readings = [module["reading"] for module in modules if module["reading"]["valid"]]
    if not readings:
        return {"valid": False, "soc": 0.0, "voltage": 0.0, "current": 0.0,
                "remaining": 0.0, "capacity": 0.0}
    remaining = sum(item["capacity_remaining"] for item in readings)
    capacity = sum(item["capacity_total"] for item in readings)
    soc = remaining * 100.0 / capacity if capacity > 0.01 else sum(item["soc"] for item in readings) / len(readings)
    return {"valid": True, "soc": soc,
            "voltage": sum(item["voltage"] for item in readings),
            "current": sum(item["current"] for item in readings),
            "remaining": remaining, "capacity": capacity}


def text(x, y, value, font=None, color=None):
    if font is not None:
        gfx.font(font)
    if color is not None:
        gfx.color(color)
    gfx.text(int(x), int(y), str(value))


def draw_header(width, page, status, soc):
    color = foreground_for_soc(soc)
    gfx.color(color)
    gfx.fill_rect(0, 0, width, 27)
    text(8, 20, APP_NAME, gfx.FONT_BOLD_16, gfx.WHITE)
    names = ("SUMMARY", "BMS 1", "BMS 2", "TEMPS", "SETUP")
    text(width - 72, 19, names[page], gfx.FONT_SMALL, gfx.WHITE)
    text(8, 43, status[:44], gfx.FONT_SMALL, gfx.DARK)


def draw_gauge(x, y, width, height, value, maximum, color):
    gfx.color(gfx.DARK)
    gfx.rect(x, y, width, height)
    fill = int((width - 4) * min(max(value, 0.0), maximum) / maximum) if maximum > 0 else 0
    if fill:
        gfx.color(color)
        gfx.fill_rect(x + 2, y + 2, fill, height - 4)


def format_runtime(seconds):
    if seconds <= 0:
        return "--"
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    return "%dh %02dm" % (hours, minutes)


def draw_summary(width, height, modules, layout, touch_enabled):
    total = aggregate(modules)
    soc = total["soc"]
    layout_names = ("OVERVIEW", "POWER", "ENERGY")
    controls = "Swipe: pages/layouts" if touch_enabled else "Up/Down: layouts"
    draw_header(width, PAGE_SUMMARY,
                "%s  |  %s  |  %s" % (layout_names[layout], controls, "S setup"), soc)
    if not total["valid"]:
        text(12, height // 2 - 6, "Waiting for ANT BMS data...", gfx.FONT_BOLD_16, gfx.DARK)
        text(12, height // 2 + 18, "Use Setup to scan and choose BMS 1 and BMS 2.", gfx.FONT_SMALL, gfx.DARK)
        return

    margin = max(8, width // 40)
    primary = foreground_for_soc(soc)
    draw = max(0.0, total["current"])
    runtime = int(total["remaining"] * 3600 / draw) if draw >= 0.1 else 0
    power = total["voltage"] * total["current"]

    if layout == LAYOUT_POWER:
        text(margin, 76, "LIVE POWER", gfx.FONT_BOLD_16, gfx.DARK)
        text(margin, 121, "%.1f A" % total["current"], gfx.FONT_BOLD_20, gfx.rgb(35, 105, 190))
        amp_max = max(10.0, draw * 1.25)
        draw_gauge(margin, 134, width - margin * 2, 24, draw, amp_max, gfx.rgb(35, 105, 190))
        text(margin, 188, "%.0f W" % power, gfx.FONT_BOLD_20, gfx.BLACK)
        text(margin, 213, "PACK  %.2f V     SOC  %.0f%%" % (total["voltage"], soc), gfx.FONT_BOLD_14, primary)
        text(margin, min(height - 7, 236), "EST. TO 0  %s" % format_runtime(runtime), gfx.FONT_BOLD_14, primary)
        return

    if layout == LAYOUT_ENERGY:
        text(margin, 76, "AVAILABLE ENERGY", gfx.FONT_BOLD_16, gfx.DARK)
        text(margin, 126, "%.0f%%" % soc, gfx.FONT_BOLD_20, primary)
        draw_gauge(margin, 140, width - margin * 2, 24, soc, 100.0, primary)
        text(margin, 188, "%.1f / %.1f Ah" % (total["remaining"], total["capacity"]), gfx.FONT_BOLD_16, gfx.BLACK)
        text(margin, 215, "EST. TO 0  %s" % format_runtime(runtime), gfx.FONT_BOLD_16, primary)
        text(margin, min(height - 7, 236), "PACK  %.2f V   DRAW  %.1f A" % (total["voltage"], total["current"]), gfx.FONT_SMALL, gfx.DARK)
        return

    text(margin, 85, "SOC", gfx.FONT_BOLD_16, gfx.DARK)
    text(margin, 126, "%.0f%%" % soc, gfx.FONT_BOLD_20, primary)
    draw_gauge(margin + 85, 91, width - margin - 95, 24, soc, 100.0, primary)

    y = 151
    text(margin, y, "PACK  %.2f V" % total["voltage"], gfx.FONT_BOLD_14, gfx.BLACK)
    bms1 = modules[0]["reading"]
    bms2 = modules[1]["reading"]
    text(margin, y + 21, "BMS 1  %s" % ("%.2f V" % bms1["voltage"] if bms1["valid"] else "--"), gfx.FONT_SMALL, gfx.DARK)
    text(width // 2, y + 21, "BMS 2  %s" % ("%.2f V" % bms2["voltage"] if bms2["valid"] else "--"), gfx.FONT_SMALL, gfx.DARK)

    amp_max = max(10.0, draw * 1.25)
    text(margin, y + 45, "DRAW  %.1f A" % total["current"], gfx.FONT_BOLD_14, gfx.BLACK)
    draw_gauge(margin + 112, y + 32, width - margin - 122, 18, draw, amp_max, gfx.rgb(35, 105, 190))
    text(margin, y + 72, "EST. TO 0  %s" % format_runtime(runtime), gfx.FONT_BOLD_14, primary)


def draw_cells(width, height, module, page):
    reading = module["reading"]
    soc = aggregate([module])["soc"] if reading["valid"] else 100.0
    draw_header(width, page, "%s: %s" % (module["label"], module["last_error"]), soc)
    if not reading["valid"]:
        text(12, height // 2, "No %s cell data yet." % module["label"], gfx.FONT_BOLD_16, gfx.DARK)
        return
    cells = reading["cells"]
    columns = 4 if width >= 240 else 2
    rows = max(1, (len(cells) + columns - 1) // columns)
    top = 55
    cell_width = width // columns
    cell_height = max(19, min(31, (height - top - 8) // rows))
    span = max(reading["max_cell"] - reading["min_cell"], 0.001)
    for index, voltage in enumerate(cells):
        column = index % columns
        row = index // columns
        x = column * cell_width + 5
        y = top + row * cell_height
        normalized = (voltage - reading["min_cell"]) / span
        color = gfx.rgb(0, 110, 65)
        if voltage == reading["min_cell"] or voltage == reading["max_cell"]:
            color = gfx.rgb(185, 35, 25)
        elif normalized < 0.2 or normalized > 0.8:
            color = gfx.rgb(185, 115, 0)
        gfx.color(color)
        gfx.fill_rect(x, y, cell_width - 9, cell_height - 3)
        text(x + 3, y + cell_height - 7, "C%02d %.3f" % (index + 1, voltage), gfx.FONT_SMALL, gfx.WHITE)
    text(8, height - 4, "min %.3f  max %.3f  delta %.3f" %
         (reading["min_cell"], reading["max_cell"], reading["delta_cell"]), gfx.FONT_SMALL, gfx.DARK)


def draw_temps(width, height, modules):
    total = aggregate(modules)
    draw_header(width, PAGE_TEMPS, "Temperature and BMS health", total["soc"])
    y = 62
    for module in modules:
        reading = module["reading"]
        text(10, y, "%s  %s" % (module["label"], module["name"] or module["address"] or "not configured"), gfx.FONT_BOLD_14, gfx.BLACK)
        y += 20
        if not reading["valid"]:
            text(18, y, module["last_error"], gfx.FONT_SMALL, gfx.DARK)
            y += 30
            continue
        temps = "  ".join("T%d %dC" % (index + 1, value) for index, value in enumerate(reading["temps"])) or "No temperatures"
        text(18, y, temps, gfx.FONT_SMALL, gfx.DARK)
        y += 17
        health = "SOH %.0f%%  MOS C:%s D:%s  Bal:%s  Frames:%d CRC:%d" % (
            reading["soh"], "on" if reading["charge_mos"] else "off",
            "on" if reading["discharge_mos"] else "off", "on" if reading["balancer"] else "off",
            reading["frames"], reading["crc_errors"])
        text(18, y, health, gfx.FONT_SMALL, gfx.DARK)
        y += 38


def device_label(device):
    return (device.get("name") or "unnamed") + "  " + device["address"]


def draw_setup(width, height, devices, selected, modules, message):
    draw_header(width, PAGE_SETUP, message, aggregate(modules)["soc"])
    text(8, 61, "Enter assigns next BMS   R scans   C connects   X clears", gfx.FONT_SMALL, gfx.DARK)
    for index, module in enumerate(modules):
        detail = module["name"] or module["address"] or "not selected"
        text(8, 82 + index * 18, "%s: %s" % (module["label"], detail), gfx.FONT_SMALL, gfx.BLACK)
    top = 124
    visible = max(1, (height - top - 8) // 18)
    first = max(0, selected - visible + 1)
    for row, device in enumerate(devices[first:first + visible]):
        index = first + row
        color = gfx.rgb(20, 80, 150) if index == selected else gfx.DARK
        if index == selected:
            gfx.color(gfx.rgb(210, 230, 255))
            gfx.fill_rect(4, top + row * 18 - 13, width - 8, 17)
        text(8, top + row * 18, device_label(device)[:42], gfx.FONT_SMALL, color)


def draw(page, modules, devices, selected, message, layout, touch_enabled):
    width, height = gfx.size()
    total = aggregate(modules)
    gfx.clear(background_for_soc(total["soc"]))
    if page == PAGE_SUMMARY:
        draw_summary(width, height, modules, layout, touch_enabled)
    elif page == PAGE_BMS1:
        draw_cells(width, height, modules[0], page)
    elif page == PAGE_BMS2:
        draw_cells(width, height, modules[1], page)
    elif page == PAGE_TEMPS:
        draw_temps(width, height, modules)
    else:
        draw_setup(width, height, devices, selected, modules, message)
    gfx.present()


def select_device(modules, device):
    for module in modules:
        if not module["address"]:
            module["address"] = device["address"]
            module["addr_type"] = device["addr_type"]
            module["name"] = device.get("name", "")
            return module["label"] + " selected"
    return "Both BMS slots are already selected; X clears them"


def handle_touch(starts, event_list, page, layout, width, height):
    """Interpret absolute-pointer swipes without consuming keyboard input."""
    changed = False
    for event in event_list:
        if (event.get("type") != "pointer" or
                event.get("mode") != device_input.MODE_ABSOLUTE):
            continue
        pointer = event.get("pointer_id", 0)
        action = event.get("action")
        if action == device_input.ACTION_PRESS:
            starts[pointer] = (event.get("x", 0), event.get("y", 0))
        elif action == device_input.ACTION_RELEASE:
            start = starts.pop(pointer, None)
            if start is None:
                continue
            dx = event.get("x", 0) - start[0]
            dy = event.get("y", 0) - start[1]
            if max(abs(dx), abs(dy)) < max(24, min(width, height) // 8):
                continue
            if abs(dx) > abs(dy):
                page = (page + (1 if dx < 0 else -1)) % PAGE_COUNT
            elif page == PAGE_SUMMARY:
                layout = (layout + (1 if dy < 0 else -1)) % LAYOUT_COUNT
            else:
                page = (page + (1 if dy < 0 else -1)) % PAGE_COUNT
            changed = True
    return page, layout, changed


def main():
    modules = [new_module("BMS 1"), new_module("BMS 2")]
    configured = load_config(modules)
    page = PAGE_SUMMARY if configured else PAGE_SETUP
    devices = []
    selected = 0
    message = "Ready"
    last_draw = 0
    layout = LAYOUT_OVERVIEW
    touch_enabled = has_touch_pointer()
    touch_starts = {}
    gfx.begin()
    try:
        if configured:
            for module in modules:
                if module["address"]:
                    connect_module(module)
            message = "Connecting saved BMS modules"
        else:
            message = "Scanning for BLE devices..."
            draw(page, modules, devices, selected, message, layout, touch_enabled)
            devices = scan_devices()
            message = "%d devices found" % len(devices)

        while not solaros.should_exit():
            current_time = now_ms()
            poll_modules(modules, current_time)
            key = gfx.getch(80)
            width, height = gfx.size()
            touch_events = []
            while len(touch_events) < 16:
                event = device_input.read(0)
                if event is None:
                    break
                touch_events.append(event)
            page, layout, touch_changed = handle_touch(
                touch_starts, touch_events, page, layout, width, height)
            if key == gfx.KEY_ESCAPE:
                break
            if key == gfx.KEY_LEFT:
                page = (page - 1) % PAGE_COUNT
            elif key == gfx.KEY_RIGHT:
                page = (page + 1) % PAGE_COUNT
            elif page == PAGE_SETUP:
                if key in (ord("r"), ord("R")):
                    message = "Scanning for BLE devices..."
                    draw(page, modules, devices, selected, message, layout, touch_enabled)
                    devices = scan_devices()
                    selected = min(selected, max(0, len(devices) - 1))
                    message = "%d devices found" % len(devices)
                elif key in (ord("x"), ord("X")):
                    for module in modules:
                        disconnect_module(module)
                        module["address"] = ""
                        module["name"] = ""
                        module["reading"] = new_reading()
                        module["last_error"] = "not configured"
                    save_config(modules)
                    message = "BMS selection cleared"
                elif key in (ord("c"), ord("C")):
                    for module in modules:
                        if module["address"]:
                            connect_module(module)
                    message = "Connecting selected BMS modules"
                elif key in (10, 13) and devices:  # SolarOS canonical Enter is LF.
                    message = select_device(modules, devices[selected])
                    if modules[0]["address"] and modules[1]["address"]:
                        if save_config(modules):
                            message += "; saved. Press C to connect"
                        else:
                            message += "; save failed"
                elif key == gfx.KEY_UP and devices:
                    selected = max(0, selected - 1)
                elif key == gfx.KEY_DOWN and devices:
                    selected = min(len(devices) - 1, selected + 1)
            elif key == gfx.KEY_UP:
                layout = (layout - 1) % LAYOUT_COUNT if page == PAGE_SUMMARY else (page - 1) % PAGE_COUNT
            elif key == gfx.KEY_DOWN:
                layout = (layout + 1) % LAYOUT_COUNT if page == PAGE_SUMMARY else (page + 1) % PAGE_COUNT

            if touch_changed or current_time - last_draw >= REDRAW_INTERVAL_MS:
                draw(page, modules, devices, selected, message, layout, touch_enabled)
                last_draw = current_time
    finally:
        for module in modules:
            disconnect_module(module)
        gfx.end()


main()
