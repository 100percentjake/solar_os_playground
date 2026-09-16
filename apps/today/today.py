"""Offline Today dashboard for SolarOS."""

import binascii
import gc
import hashlib
import json

import solaros
from solaros import gfx

from today_core import clean, date_key, recent_notes, today_events, today_tasks, unread_posts


TODO_PATH = "/apps/todo/todo.json"
CALENDAR_PATH = "/apps/calendar/calendar.json"
RSS_PATH = "/apps/rss/cache.json"
FLINT_CONFIG = "/.flint/config.json"
FLINT_INDEX = "/.flint/index.json"
FLINT_DEFAULT_ROOT = "/notes/vault"
STATUS_BAR_H = 16
APP_TOP = STATUS_BAR_H + 2
HEADER_H = 70
FOOTER_H = 25
ROW_H = 43
KEY_ENTER = 13
KEY_LF = 10


def load_json(path, fallback, maximum=262144):
    try:
        with open(path, "rb") as source:
            source.seek(0, 2)
            if source.tell() > maximum:
                return fallback
        # Let the JSON reader consume text directly. Keeping a bytes copy and a
        # decoded string alive together is unnecessarily expensive on-device.
        with open(path, "r") as source:
            return json.load(source)
    except Exception:
        return fallback


def flint_index_path():
    config = load_json(FLINT_CONFIG, {}, 8192)
    root = config.get("root", FLINT_DEFAULT_ROOT) if isinstance(config, dict) else FLINT_DEFAULT_ROOT
    if root == FLINT_DEFAULT_ROOT:
        return FLINT_INDEX
    try:
        digest = binascii.hexlify(hashlib.sha256(root.encode("utf-8")).digest())[:16].decode("ascii")
        return "/.flint/index-" + digest + ".json"
    except Exception:
        return FLINT_INDEX


def now_value():
    try:
        value = solaros.time.datetime()
        if isinstance(value, dict):
            return value
    except Exception:
        pass
    return {"year": 2000, "month": 1, "day": 1, "weekday": 6,
            "hour": 0, "minute": 0, "clock_integrity": False}


def service_status(name):
    """Read an optional SolarOS service without making it an app requirement."""
    try:
        service = getattr(solaros, name)
        value = service.status()
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def load_dashboard():
    now = now_value()
    today = date_key(now)
    battery = service_status("battery")
    wifi = service_status("wifi")
    tasks = today_tasks(load_json(TODO_PATH, {}), today)
    gc.collect()
    events = today_events(load_json(CALENDAR_PATH, {}), today)
    gc.collect()
    notes = recent_notes(load_json(flint_index_path(), {}))
    gc.collect()
    posts = unread_posts(load_json(RSS_PATH, {}))
    gc.collect()
    return {"now": now, "today": today, "battery": battery, "wifi": wifi,
            "tasks": tasks, "events": events, "notes": notes, "posts": posts}


def clip(value, count):
    value = clean(value)
    if len(value) <= count:
        return value
    return value[:max(1, count - 1)] + "~"


def wait_key():
    while not solaros.should_exit():
        key = gfx.getch(250)
        if key is not None:
            return key
    return gfx.KEY_ESCAPE


def clear_content(width, height):
    """Clear the dashboard below its compact faux status bar."""
    if height <= STATUS_BAR_H:
        return
    gfx.color(gfx.WHITE)
    gfx.fill_rect(0, STATUS_BAR_H, width, height - STATUS_BAR_H)


def draw_status_bar(width, data):
    """Draw the clock and basic radio/power state cleared by graphics mode."""
    now = data.get("now", {})
    battery = data.get("battery", {})
    wifi = data.get("wifi", {})
    try:
        hour = max(0, min(23, int(now.get("hour", 0))))
        minute = max(0, min(59, int(now.get("minute", 0))))
        clock = "{:02d}:{:02d}".format(hour, minute)
        if now.get("clock_integrity") is False:
            clock = "--:--"
    except Exception:
        clock = "--:--"
    percent = battery.get("percent")
    if not isinstance(percent, int) or isinstance(percent, bool):
        percent = None
    if percent is not None:
        percent = max(0, min(100, percent))

    gfx.color(gfx.BLACK)
    gfx.fill_rect(0, 0, width, STATUS_BAR_H)
    gfx.color(gfx.WHITE)
    try:
        gfx.icon(2, 0, "wifi", 16)
    except Exception:
        gfx.line(3, 11, 8, 5)
        gfx.line(8, 5, 13, 11)
    connected = bool(wifi.get("has_ip"))
    if not connected:
        gfx.line(2, 2, 15, 14)

    battery_x = 23
    gfx.rect(battery_x, 3, 19, 10)
    gfx.fill_rect(battery_x + 19, 6, 2, 4)
    if percent is not None and percent > 0:
        fill = max(1, (15 * percent) // 100)
        gfx.fill_rect(battery_x + 2, 5, fill, 6)
    if battery.get("charging_known") and battery.get("charging"):
        gfx.font(gfx.FONT_BOLD_12)
        gfx.text(46, 12, "+")

    gfx.font(gfx.FONT_MONO_12)
    if percent is not None:
        percent_text = str(percent) + "%"
        gfx.text(56, 12, percent_text)
    gfx.text(width - 6 - len(clock) * 6, 12, clock)


def draw_header(width, data, title="Today", subtitle=""):
    draw_status_bar(width, data)
    gfx.color(gfx.WHITE)
    gfx.fill_rect(0, APP_TOP, width, HEADER_H - APP_TOP)
    gfx.color(gfx.DARK)
    gfx.font(gfx.FONT_MONO_12)
    gfx.text(11, APP_TOP + 15, clip(subtitle or data["today"], max(4, (width - 22) // 6)))
    gfx.color(gfx.BLACK)
    gfx.font(gfx.FONT_BOLD_20)
    gfx.text(11, APP_TOP + 39, clip(title, max(4, (width - 22) // 10)))
    gfx.line(10, HEADER_H - 1, width - 10, HEADER_H - 1)


def draw_footer(width, height, text):
    y = height - FOOTER_H
    gfx.color(gfx.BLACK)
    gfx.fill_rect(0, y, width, FOOTER_H)
    gfx.color(gfx.WHITE)
    gfx.font(gfx.FONT_MONO_12)
    gfx.text(7, y + 17, clip(text, max(4, (width - 14) // 6)))


def wrap_text(value, columns, maximum=20):
    words = clean(value, "", 1200).split()
    lines = []
    line = ""
    for word in words:
        if len(line) + len(word) + (1 if line else 0) <= columns:
            line += (" " if line else "") + word
        else:
            if line:
                lines.append(line)
            while len(word) > columns and len(lines) < maximum:
                lines.append(word[:columns])
                word = word[columns:]
            line = word
        if len(lines) >= maximum:
            break
    if line and len(lines) < maximum:
        lines.append(line)
    return lines


def message(width, height, data, title, text):
    clear_content(width, height)
    draw_header(width, data, title)
    gfx.color(gfx.BLACK)
    gfx.font(gfx.FONT_MONO_14)
    y = HEADER_H + 23
    visible = max(1, (height - HEADER_H - FOOTER_H - 6) // 19)
    for line in wrap_text(text, max(10, (width - 24) // 7), visible):
        gfx.text(12, y, line)
        y += 19
    draw_footer(width, height, "Press any key to return")
    gfx.refresh()
    wait_key()


def home_rows(data):
    open_tasks = len([item for item in data["tasks"] if not item.get("completed")])
    next_event = data["events"][0] if data["events"] else None
    event_hint = "Your day is clear"
    if next_event:
        event_hint = ("All day" if next_event.get("all_day") else next_event.get("start_time", "")) + "  " + clean(next_event.get("title", "Event"))
    note_hint = clean(data["notes"][0].get("title", "")) if data["notes"] else "No recent notes"
    post_hint = clean(data["posts"][0].get("title", "")) if data["posts"] else "No unread posts"
    return [
        ("AGENDA", str(len(data["events"])), event_hint, "calendar"),
        ("TASKS", str(open_tasks), "open today", "task"),
        ("NOTES", str(len(data["notes"])), note_hint, "book"),
        ("FEEDS", str(len(data["posts"])), post_hint, "rss"),
    ]


def safe_icon(x, y, name, size=32):
    try:
        gfx.icon(x, y, name, size)
    except Exception:
        gfx.rect(x + 4, y + 4, size - 8, size - 8)


def home_geometry(width, height, index):
    gap = 6
    margin = 7
    body_bottom = height - FOOTER_H - 6
    card_width = (width - margin * 2 - gap) // 2
    card_height = (body_bottom - HEADER_H - gap) // 2
    column = index % 2
    row = index // 2
    return (margin + column * (card_width + gap),
            HEADER_H + row * (card_height + gap), card_width, card_height)


def draw_home_card(width, height, index, row, selected):
    x, y, card_width, card_height = home_geometry(width, height, index)
    gfx.color(gfx.WHITE)
    gfx.fill_rect(x, y, card_width, card_height)
    gfx.color(gfx.BLACK if selected else gfx.DARK)
    gfx.rect(x, y, card_width, card_height)
    if selected:
        gfx.rect(x + 1, y + 1, card_width - 2, card_height - 2)
        gfx.fill_rect(x + 1, y + 1, 4, card_height - 2)
    content_x = x + 52
    icon_y = y + max(8, (card_height - 32) // 2)
    gfx.color(gfx.BLACK)
    safe_icon(x + 13, icon_y, row[3], 32)
    gfx.color(gfx.DARK)
    gfx.font(gfx.FONT_MONO_12)
    gfx.text(content_x, y + 19, clip(row[0], max(4, (card_width - 60) // 6)))
    gfx.color(gfx.BLACK)
    gfx.font(gfx.FONT_BOLD_20)
    gfx.text(content_x, y + 43, clip(row[1], 6))
    gfx.font(gfx.FONT_MONO_12)
    gfx.text(content_x, y + 62, clip(row[2], max(4, (card_width - 60) // 6)))


def draw_home_header(width, data):
    draw_status_bar(width, data)
    months = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
              "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
    weekdays = ("Sunday", "Monday", "Tuesday", "Wednesday",
                "Thursday", "Friday", "Saturday")
    now = data["now"]
    try:
        month = months[max(1, min(12, int(now.get("month", 1)))) - 1]
        day = str(int(now.get("day", 1)))
        weekday = weekdays[max(0, min(6, int(now.get("weekday", 0))))]
        date_text = weekday + ", " + month + " " + day
    except Exception:
        date_text = data["today"]
    open_tasks = len([item for item in data["tasks"] if not item.get("completed")])
    events = len(data["events"])
    gfx.color(gfx.WHITE)
    gfx.fill_rect(0, APP_TOP, width, HEADER_H - APP_TOP)
    gfx.color(gfx.DARK)
    gfx.font(gfx.FONT_MONO_12)
    gfx.text(11, APP_TOP + 14, "TODAY")
    gfx.color(gfx.BLACK)
    gfx.font(gfx.FONT_BOLD_20)
    gfx.text(11, APP_TOP + 39, clip(date_text, max(8, (width - 115) // 10)))
    divider = width - 91
    gfx.line(divider, APP_TOP + 8, divider, HEADER_H - 8)
    gfx.font(gfx.FONT_BOLD_12)
    task_text = str(open_tasks) + " open"
    gfx.text(width - 8 - len(task_text) * 6, APP_TOP + 18, task_text)
    gfx.font(gfx.FONT_MONO_12)
    event_text = str(events) + (" event" if events == 1 else " events")
    gfx.text(width - 8 - len(event_text) * 6, APP_TOP + 38, event_text)


def draw_list_row(width, y, row, selected):
    gfx.color(gfx.WHITE)
    gfx.fill_rect(4, y + 1, width - 8, ROW_H - 2)
    gfx.color(gfx.LIGHT)
    gfx.line(10, y + ROW_H - 1, width - 10, y + ROW_H - 1)
    if selected:
        gfx.color(gfx.BLACK)
        gfx.rect(4, y + 1, width - 8, ROW_H - 2)
        gfx.fill_rect(5, y + 2, 4, ROW_H - 4)
    gfx.color(gfx.BLACK)
    gfx.font(gfx.FONT_BOLD_14)
    gfx.text(14, y + 18, clip(row[0], max(5, (width - 28) // 7)))
    gfx.font(gfx.FONT_MONO_12)
    gfx.text(14, y + 35, clip(row[1], max(5, (width - 28) // 6)))


def home_compact(width, height, data, rows):
    """Keep the app usable on SolarOS's short 384x168 display target."""
    selected = 0
    top = 55
    visible = max(1, (height - top - FOOTER_H) // ROW_H)
    while not solaros.should_exit():
        start = (selected // visible) * visible
        clear_content(width, height)
        draw_status_bar(width, data)
        gfx.color(gfx.DARK)
        gfx.font(gfx.FONT_MONO_12)
        gfx.text(10, APP_TOP + 14, "TODAY")
        gfx.color(gfx.BLACK)
        gfx.font(gfx.FONT_BOLD_16)
        gfx.text(10, APP_TOP + 34, data["today"])
        gfx.line(9, top - 1, width - 9, top - 1)
        for index in range(start, min(len(rows), start + visible)):
            label = rows[index][0] + "  " + rows[index][1]
            draw_list_row(width, top + (index - start) * ROW_H,
                          (label, rows[index][2]), index == selected)
        draw_footer(width, height, "Up/Down   Enter open   R refresh")
        gfx.refresh()
        key = wait_key()
        if key in (gfx.KEY_ESCAPE, ord("q"), ord("Q")):
            return None
        if key in (ord("r"), ord("R")):
            return "refresh"
        if key in (gfx.KEY_UP, ord("k")):
            selected = (selected - 1) % len(rows)
        elif key in (gfx.KEY_DOWN, ord("j")):
            selected = (selected + 1) % len(rows)
        elif key in (KEY_ENTER, KEY_LF, gfx.KEY_RIGHT):
            detail(width, height, data, selected)
    return None


def home(width, height, data):
    selected = 0
    previous = None
    rows = home_rows(data)
    if height < 240:
        return home_compact(width, height, data, rows)
    while not solaros.should_exit():
        if previous is None:
            clear_content(width, height)
            draw_home_header(width, data)
            draw_footer(width, height, "Arrows move   Enter open   R refresh")
            for index, row in enumerate(rows):
                draw_home_card(width, height, index, row, index == selected)
        else:
            draw_home_card(width, height, previous, rows[previous], False)
            draw_home_card(width, height, selected, rows[selected], True)
        gfx.refresh()
        previous = selected
        key = wait_key()
        if key in (gfx.KEY_ESCAPE, ord("q"), ord("Q")):
            return None
        if key in (ord("r"), ord("R")):
            return "refresh"
        if key in (gfx.KEY_UP, ord("k")):
            selected = (selected - 2) % len(rows)
        elif key in (gfx.KEY_DOWN, ord("j")):
            selected = (selected + 2) % len(rows)
        elif key in (gfx.KEY_LEFT, ord("h")):
            selected = selected - 1 if selected % 2 else selected + 1
        elif key in (gfx.KEY_RIGHT, ord("l")):
            selected = selected + 1 if selected % 2 == 0 else selected - 1
        elif key in (KEY_ENTER, KEY_LF, gfx.KEY_RIGHT):
            detail(width, height, data, selected)
            previous = None
            rows = home_rows(data)
    return None


def item_labels(data, section):
    labels = []
    if section == 0:
        for item in data["events"]:
            when = "All day" if item.get("all_day") else item.get("start_time", "")
            labels.append((clean(item.get("title", "Event")), when + ("  " + clean(item.get("location", "")) if item.get("location") else "")))
    elif section == 1:
        for item in data["tasks"]:
            labels.append((("[x] " if item.get("completed") else "[ ] ") + clean(item.get("title", "Task")),
                           "Recurring" if item.get("recurrence_id") else "General task"))
    elif section == 2:
        for item in data["notes"]:
            labels.append((clean(item.get("title", "Note")), clean(item.get("preview", item.get("path", "")))))
    elif section == 3:
        for item in data["posts"]:
            labels.append((clean(item.get("title", "Post")), clean(item.get("feed_title", ""))))
    return labels


def show_item(width, height, data, section, index):
    if section == 0:
        item = data["events"][index]
        when = "All day" if item.get("all_day") else item.get("start_time", "") + " to " + item.get("end_time", "")
        body = when
        if item.get("location"):
            body += "   Location: " + clean(item.get("location", ""))
        if item.get("notes"):
            body += "   " + clean(item.get("notes", ""), "", 700)
        message(width, height, data, clean(item.get("title", "Event")), body)
    elif section == 1:
        item = data["tasks"][index]
        state = "Completed today" if item.get("completed") else "Open"
        if item.get("recurrence_id"):
            state += ". Recurring task"
        if item.get("virtual"):
            state += ". It will be added to Todo List when Todo opens"
        message(width, height, data, clean(item.get("title", "Task")), state + ".")
    elif section == 2:
        item = data["notes"][index]
        body = clean(item.get("preview", "No preview available."), "No preview available.", 700)
        body += "   Path: " + clean(item.get("path", ""))
        message(width, height, data, clean(item.get("title", "Note")), body)
    elif section == 3:
        item = data["posts"][index]
        body = clean(item.get("summary", "No summary available."), "No summary available.", 700)
        if item.get("date"):
            body += "   Published: " + clean(item.get("date", ""))
        message(width, height, data, clean(item.get("title", "Post")),
                clean(item.get("feed_title", "")) + "   " + body)


def detail(width, height, data, section):
    titles = ("Agenda", "Tasks", "Recent notes", "Unread feeds")
    items = item_labels(data, section)
    selected = 0
    previous = None
    previous_start = None
    while not solaros.should_exit():
        visible = max(1, (height - HEADER_H - FOOTER_H) // ROW_H)
        start = (selected // visible) * visible if items else 0
        if previous_start != start or previous is None:
            clear_content(width, height)
            draw_header(width, data, titles[section], "{} item{}".format(len(items), "" if len(items) == 1 else "s"))
            draw_footer(width, height, "Enter details   Esc back")
            if not items:
                gfx.color(gfx.DARK)
                gfx.font(gfx.FONT_MONO_16)
                gfx.text(14, HEADER_H + 45, "Nothing here today.")
            for index in range(start, min(len(items), start + visible)):
                draw_list_row(width, HEADER_H + (index - start) * ROW_H, items[index], index == selected)
        else:
            if start <= previous < start + visible:
                draw_list_row(width, HEADER_H + (previous - start) * ROW_H, items[previous], False)
            draw_list_row(width, HEADER_H + (selected - start) * ROW_H, items[selected], True)
        gfx.refresh()
        previous = selected
        previous_start = start
        key = wait_key()
        if key in (gfx.KEY_ESCAPE, gfx.KEY_LEFT, ord("q"), ord("Q")):
            return
        if items and key in (gfx.KEY_UP, ord("k")):
            selected = (selected - 1) % len(items)
        elif items and key in (gfx.KEY_DOWN, ord("j")):
            selected = (selected + 1) % len(items)
        elif items and key in (KEY_ENTER, KEY_LF, gfx.KEY_RIGHT):
            show_item(width, height, data, section, selected)
            previous = None
            previous_start = None


def main():
    gfx.begin()
    try:
        width, height = gfx.size()
        while not solaros.should_exit():
            data = load_dashboard()
            action = home(width, height, data)
            del data
            gc.collect()
            if action != "refresh":
                break
    finally:
        gfx.end()


if __name__ == "__main__":
    main()
