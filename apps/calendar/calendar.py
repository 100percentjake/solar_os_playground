"""Keyboard-first graphical calendar for SolarOS."""

import gc
import json
import sys

import solaros
from solaros import gfx

from calendar_core import (MAX_EVENTS, WEEKDAYS, add_calendar, add_days,
                           add_event, add_minutes, calendar_visible, clean_notes,
                           clean_text, date_key, date_parts, days_in_month,
                           date_to_ordinal, default_state, delete_calendar, delete_event,
                           due_reminders, events_on, find_event,
                           format_date, format_time, import_ics, make_date,
                           mark_reminded, month_shift, normalize_repeat,
                           normalize_state, occurrence_counts,
                           occurrences_between, repeat_label,
                           pad2, replace_calendar_events, search_events,
                           set_uid_origin, skip_occurrence, timestamp,
                           valid_date, valid_time, weekday_for, write_ics)


def app_directory():
    path = sys.argv[0] if sys.argv else "calendar.py"
    if not path or "/" not in path:
        try:
            path = __file__
        except NameError:
            path = "calendar.py"
    separator = path.rfind("/")
    if separator < 0:
        return "."
    return path[:separator] if separator > 0 else "/"


APP_DIR = app_directory()
STATE_PATH = APP_DIR + "/calendar.json"
BACKUP_PATH = STATE_PATH + ".bak"
EXPORT_DIR = "/Downloads"
SYNC_TEMP = APP_DIR + "/calendar-sync.ics.tmp"
MAX_ICS_DOWNLOAD = 1048576
KEY_ENTER = 13
KEY_LF = 10
KEY_BACKSPACE = 8
KEY_DELETE = 127
KEY_PAGE_UP = getattr(gfx, "KEY_PAGE_UP", -1001)
KEY_PAGE_DOWN = getattr(gfx, "KEY_PAGE_DOWN", -1002)
HEADER_H = 43
FOOTER_H = 25
ROW_H = 42
LOAD_NOTICE = ""


def clip(value, count):
    value = clean_text(value)
    if len(value) <= count:
        return value
    if count < 2:
        return value[:count]
    return value[:count - 1] + "~"


def now_value():
    try:
        value = solaros.time.datetime()
        if isinstance(value, dict):
            return value
    except Exception:
        pass
    return {"year": 2000, "month": 1, "day": 1, "hour": 0, "minute": 0,
            "second": 0, "weekday": 0, "clock_integrity": False}


def utc_now_value():
    try:
        value = solaros.time.utc_datetime()
        if isinstance(value, dict):
            return value
    except Exception:
        pass
    return now_value()


def device_uid_origin():
    try:
        user = solaros.identity.user()
        host = solaros.identity.hostname()
        if isinstance(user, str) and user and isinstance(host, str) and host:
            return user + "." + host
    except Exception:
        pass
    return "solaros.local"


def load_state():
    global LOAD_NOTICE
    found_invalid = False
    for path in (STATE_PATH, STATE_PATH + ".tmp", BACKUP_PATH):
        try:
            with open(path, "r") as source:
                raw = json.load(source)
            if not isinstance(raw, dict):
                found_invalid = True
                continue
            state = normalize_state(raw)
            if path != STATE_PATH:
                try:
                    solaros.storage.remove(STATE_PATH)
                except OSError:
                    pass
                try:
                    solaros.storage.rename(path, STATE_PATH)
                    LOAD_NOTICE = "Recovered calendar data from an interrupted save."
                except OSError:
                    pass
            return state
        except OSError:
            continue
        except Exception:
            found_invalid = True
    if found_invalid:
        LOAD_NOTICE = "Calendar data was damaged and no usable backup was found. The damaged files were left in place."
    return default_state()


def save_state(state):
    temporary = STATE_PATH + ".tmp"
    with open(temporary, "w") as output:
        json.dump(state, output)
        output.flush()
    try:
        solaros.storage.remove(BACKUP_PATH)
    except OSError:
        pass
    had_primary = True
    try:
        solaros.storage.rename(STATE_PATH, BACKUP_PATH)
    except OSError:
        had_primary = False
    try:
        solaros.storage.rename(temporary, STATE_PATH)
    except Exception:
        if had_primary:
            try:
                solaros.storage.rename(BACKUP_PATH, STATE_PATH)
            except OSError:
                pass
        raise
    if had_primary:
        try:
            solaros.storage.remove(BACKUP_PATH)
        except OSError:
            pass
    gc.collect()


def ensure_directory(path):
    try:
        solaros.storage.mkdir(path)
    except OSError:
        pass


def wait_key():
    while not solaros.should_exit():
        key = gfx.getch(250)
        if key is not None:
            return key
    return gfx.KEY_ESCAPE


def draw_header(width, title, subtitle=""):
    gfx.color(gfx.BLACK)
    gfx.fill_rect(0, 0, width, HEADER_H)
    gfx.color(gfx.WHITE)
    gfx.font(gfx.FONT_BOLD_16)
    gfx.text(10, 19, clip(title, max(1, (width - 20) // 8)))
    if subtitle:
        gfx.font(gfx.FONT_MONO_12)
        gfx.text(10, 36, clip(subtitle, max(1, (width - 20) // 6)))


def draw_footer(width, height, text):
    y = height - FOOTER_H
    gfx.color(gfx.BLACK)
    gfx.fill_rect(0, y, width, FOOTER_H)
    gfx.color(gfx.WHITE)
    gfx.font(gfx.FONT_MONO_12)
    gfx.text(7, y + 17, clip(text, max(1, (width - 14) // 6)))


def wrap_text(value, columns, max_lines=20):
    value = value.replace("\r", "") if isinstance(value, str) else ""
    lines = []
    for paragraph in value.split("\n"):
        words = paragraph.split()
        line = ""
        if not words:
            lines.append("")
        for word in words:
            while len(word) > columns:
                if line:
                    lines.append(line)
                    line = ""
                lines.append(word[:columns])
                word = word[columns:]
            trial = word if not line else line + " " + word
            if len(trial) > columns:
                if line:
                    lines.append(line)
                line = word
            else:
                line = trial
        if line:
            lines.append(line)
        if len(lines) >= max_lines:
            break
    return lines[:max_lines]


def draw_message(width, height, title, text, footer="Press any key"):
    gfx.clear(gfx.WHITE)
    draw_header(width, title)
    gfx.color(gfx.BLACK)
    gfx.font(gfx.FONT_MONO_14)
    columns = max(10, (width - 24) // 7)
    y = HEADER_H + 27
    visible = max(1, (height - HEADER_H - FOOTER_H - 10) // 20)
    for line in wrap_text(text, columns, visible):
        gfx.text(12, y, line)
        y += 20
    draw_footer(width, height, footer)
    gfx.refresh()


def message(width, height, title, text):
    draw_message(width, height, title, text)
    wait_key()


def confirm(width, height, title, text):
    draw_message(width, height, title, text, "Y confirm   any other key cancels")
    return wait_key() in (ord("y"), ord("Y"))


def persist(width, height, state):
    try:
        save_state(state)
        return True
    except Exception as error:
        message(width, height, "Could not save",
                "This change is only in memory and will be lost when the app closes. " + str(error))
        return False


def edit_text(width, height, title, label, initial="", limit=120, multiline=False):
    if multiline:
        value = clean_notes(initial)[:limit]
    else:
        value = clean_text(initial)[:limit]
    while not solaros.should_exit():
        gfx.clear(gfx.WHITE)
        draw_header(width, title, clip(label, 32) + "  {}/{}".format(len(value), limit))
        gfx.color(gfx.BLACK)
        gfx.font(gfx.FONT_MONO_16)
        columns = max(8, (width - 24) // 8)
        shown = value.replace("\n", " ") + "_"
        lines = []
        while shown:
            lines.append(shown[:columns])
            shown = shown[columns:]
        y = HEADER_H + 31
        visible = max(1, (height - HEADER_H - FOOTER_H - 10) // 23)
        for line in lines[-visible:]:
            gfx.text(12, y, line)
            y += 23
        footer = "Maximum length reached" if len(value) >= limit else "Enter save   Esc cancel   Backspace delete"
        draw_footer(width, height, footer)
        gfx.refresh()
        key = wait_key()
        if key == gfx.KEY_ESCAPE:
            return None
        if key in (KEY_ENTER, KEY_LF):
            return value.strip()
        if key in (KEY_BACKSPACE, KEY_DELETE):
            value = value[:-1]
        elif isinstance(key, int) and 32 <= key <= 126 and len(value) < limit:
            value += chr(key)
    return None


def choose(width, height, title, options, selected=0, footer="Enter choose   Esc cancel"):
    if not options:
        return None
    if selected < 0 or selected >= len(options):
        selected = 0
    while not solaros.should_exit():
        gfx.clear(gfx.WHITE)
        draw_header(width, title)
        row_h = 31
        visible = max(1, (height - HEADER_H - FOOTER_H) // row_h)
        start = (selected // visible) * visible
        for row, option in enumerate(options[start:start + visible]):
            index = start + row
            y = HEADER_H + row * row_h
            if index == selected:
                gfx.color(gfx.BLACK)
                gfx.fill_rect(4, y + 2, width - 8, row_h - 3)
                gfx.color(gfx.WHITE)
            else:
                gfx.color(gfx.BLACK)
            gfx.font(gfx.FONT_MONO_14)
            gfx.text(11, y + 21, clip(option, max(4, (width - 22) // 7)))
        page = "{}/{}".format(selected + 1, len(options))
        gfx.color(gfx.WHITE)
        gfx.font(gfx.FONT_MONO_12)
        gfx.text(width - 8 - len(page) * 6, 19, page)
        draw_footer(width, height, footer)
        gfx.refresh()
        key = wait_key()
        if key == gfx.KEY_ESCAPE or key in (ord("q"), ord("Q")):
            return None
        if key in (gfx.KEY_UP, ord("k")):
            selected = (selected - 1) % len(options)
        elif key in (gfx.KEY_DOWN, ord("j")):
            selected = (selected + 1) % len(options)
        elif key in (KEY_ENTER, KEY_LF, gfx.KEY_RIGHT):
            return selected
    return None


def number_picker(width, height, title, label, value, low, high, step=1):
    value = max(low, min(high, int(value)))
    while not solaros.should_exit():
        gfx.clear(gfx.WHITE)
        draw_header(width, title, label)
        shown = str(value)
        gfx.color(gfx.BLACK)
        gfx.font(gfx.FONT_BOLD_20)
        gfx.text((width - len(shown) * 10) // 2, HEADER_H + 82, shown)
        gfx.font(gfx.FONT_MONO_14)
        gfx.text(20, HEADER_H + 125, "Up/Right increases")
        gfx.text(20, HEADER_H + 148, "Down/Left decreases")
        draw_footer(width, height, "Enter save   Esc cancel")
        gfx.refresh()
        key = wait_key()
        if key == gfx.KEY_ESCAPE:
            return None
        if key in (gfx.KEY_LEFT, gfx.KEY_DOWN, ord("j")):
            value -= step
            if value < low:
                value = high
        elif key in (gfx.KEY_RIGHT, gfx.KEY_UP, ord("k")):
            value += step
            if value > high:
                value = low
        elif key in (KEY_ENTER, KEY_LF):
            return value
    return None


def time_picker(width, height, title, value):
    value = valid_time(value, "09:00")
    total = int(value[:2]) * 60 + int(value[3:5])
    while not solaros.should_exit():
        gfx.clear(gfx.WHITE)
        draw_header(width, title, "Up/Down 5 min   Left/Right 1 hour")
        shown = pad2(total // 60) + ":" + pad2(total % 60)
        gfx.color(gfx.BLACK)
        gfx.font(gfx.FONT_BOLD_20)
        gfx.text((width - len(shown) * 10) // 2, HEADER_H + 85, shown)
        draw_footer(width, height, "Enter save   Esc cancel")
        gfx.refresh()
        key = wait_key()
        if key == gfx.KEY_ESCAPE:
            return None
        if key == gfx.KEY_UP:
            total = (total + 5) % 1440
        elif key == gfx.KEY_DOWN:
            total = (total - 5) % 1440
        elif key == gfx.KEY_RIGHT:
            total = (total + 60) % 1440
        elif key == gfx.KEY_LEFT:
            total = (total - 60) % 1440
        elif key in (KEY_ENTER, KEY_LF):
            return pad2(total // 60) + ":" + pad2(total % 60)
    return None


def date_picker(width, height, title, value):
    selected = valid_date(value, date_key(now_value()))
    while not solaros.should_exit():
        gfx.clear(gfx.WHITE)
        year, month, day = date_parts(selected)
        draw_header(width, title, WEEKDAYS[weekday_for(selected)] + "  " + selected)
        gfx.color(gfx.BLACK)
        gfx.font(gfx.FONT_BOLD_20)
        heading = "{} {}".format(calendar_month_name(month), year)
        gfx.text((width - len(heading) * 10) // 2, HEADER_H + 42, heading)
        gfx.font(gfx.FONT_BOLD_20)
        shown = str(day)
        gfx.rect(width // 2 - 35, HEADER_H + 65, 70, 62)
        gfx.text((width - len(shown) * 10) // 2, HEADER_H + 105, shown)
        gfx.font(gfx.FONT_MONO_14)
        gfx.text(40, HEADER_H + 157, "Left/Right: day")
        gfx.text(40, HEADER_H + 179, "Up/Down: week")
        gfx.text(40, HEADER_H + 201, "[/]: month   T: today")
        draw_footer(width, height, "Enter choose   Esc cancel")
        gfx.refresh()
        key = wait_key()
        if key == gfx.KEY_ESCAPE:
            return None
        if key == gfx.KEY_LEFT:
            selected = add_days(selected, -1)
        elif key == gfx.KEY_RIGHT:
            selected = add_days(selected, 1)
        elif key == gfx.KEY_UP:
            selected = add_days(selected, -7)
        elif key == gfx.KEY_DOWN:
            selected = add_days(selected, 7)
        elif key in (ord("["), KEY_PAGE_UP):
            selected = month_shift(selected, -1)
        elif key in (ord("]"), KEY_PAGE_DOWN):
            selected = month_shift(selected, 1)
        elif key in (ord("t"), ord("T")):
            selected = date_key(now_value())
        elif key in (KEY_ENTER, KEY_LF):
            return selected
    return None


def calendar_month_name(month):
    return ("January", "February", "March", "April", "May", "June", "July",
            "August", "September", "October", "November", "December")[month - 1]


def calendar_name(state, ident):
    for item in state["calendars"]:
        if item.get("id") == ident:
            return item.get("name", "Calendar")
    return "Calendar"


def calendar_is_subscribed(state, ident):
    for item in state["calendars"]:
        if item.get("id") == ident:
            return bool(item.get("source_url"))
    return False


def choose_calendar(width, height, state, current="", writable_only=False):
    calendars = []
    for item in state["calendars"]:
        if not writable_only or not item.get("source_url"):
            calendars.append(item)
    if not calendars:
        message(width, height, "No local calendar", "Add a local calendar before creating or importing events.")
        return None
    options = [item.get("name", "Calendar") for item in calendars]
    selected = 0
    for index, item in enumerate(calendars):
        if item.get("id") == current:
            selected = index
            break
    result = choose(width, height, "Choose calendar", options, selected)
    return None if result is None else calendars[result]["id"]


def weekday_selector(width, height, initial):
    selected_days = []
    if isinstance(initial, list):
        for day in initial:
            if isinstance(day, int) and 0 <= day <= 6 and day not in selected_days:
                selected_days.append(day)
    cursor = 0
    while not solaros.should_exit():
        gfx.clear(gfx.WHITE)
        draw_header(width, "Weekly repeat", "Space toggles; S saves")
        row_h = 31
        for row, name in enumerate(("Sunday", "Monday", "Tuesday", "Wednesday",
                                    "Thursday", "Friday", "Saturday")):
            y = HEADER_H + row * row_h
            if row == cursor:
                gfx.color(gfx.BLACK)
                gfx.fill_rect(4, y + 2, width - 8, row_h - 3)
                gfx.color(gfx.WHITE)
            else:
                gfx.color(gfx.BLACK)
            gfx.font(gfx.FONT_MONO_14)
            gfx.text(12, y + 21, ("[x] " if row in selected_days else "[ ] ") + name)
        draw_footer(width, height, "Space toggle   S save   Esc cancel")
        gfx.refresh()
        key = wait_key()
        if key == gfx.KEY_ESCAPE:
            return None
        if key == gfx.KEY_UP:
            cursor = (cursor - 1) % 7
        elif key == gfx.KEY_DOWN:
            cursor = (cursor + 1) % 7
        elif key in (ord(" "), KEY_ENTER, KEY_LF):
            if cursor in selected_days:
                selected_days.remove(cursor)
            else:
                selected_days.append(cursor)
                selected_days.sort()
        elif key in (ord("s"), ord("S")):
            if selected_days:
                return selected_days
            message(width, height, "Weekly repeat", "Select at least one day.")
    return None


def monthly_rule(width, height, start_date, current):
    current = current if isinstance(current, dict) else {}
    mode = 1 if current.get("monthly_mode") == "nth_weekday" else 0
    result = choose(width, height, "Monthly repeat",
                    ["A numbered day", "The Nth weekday"], mode)
    if result is None:
        return None
    if result == 0:
        day = number_picker(width, height, "Monthly repeat", "Day of month",
                            current.get("month_day", date_parts(start_date)[2]), 1, 31)
        return None if day is None else {"monthly_mode": "day", "month_day": day}
    ordinals = (1, 2, 3, 4, -1)
    names = ["First", "Second", "Third", "Fourth", "Last"]
    old = current.get("ordinal", 1)
    index = ordinals.index(old) if old in ordinals else 0
    choice = choose(width, height, "Monthly repeat", names, index)
    if choice is None:
        return None
    old_day = current.get("weekday", weekday_for(start_date))
    day = choose(width, height, "Monthly repeat",
                 ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"],
                 old_day)
    if day is None:
        return None
    return {"monthly_mode": "nth_weekday", "ordinal": ordinals[choice], "weekday": day}


def recurrence_editor(width, height, start_date, current=None):
    current = current if isinstance(current, dict) else {}
    kinds = ("", "daily", "weekdays", "weekly", "monthly", "yearly")
    options = ["Does not repeat", "Daily", "Weekdays (Mon-Fri)",
               "Weekly (choose days)", "Monthly (custom rule)", "Yearly"]
    selected = kinds.index(current.get("kind")) if current.get("kind") in kinds else 0
    index = choose(width, height, "Repeat", options, selected)
    if index is None:
        return None
    kind = kinds[index]
    if not kind:
        return {}
    rule = {"kind": kind, "interval": current.get("interval", 1), "until": ""}
    if kind == "weekly":
        days = weekday_selector(width, height,
                                current.get("weekdays", [weekday_for(start_date)]))
        if days is None:
            return None
        rule["weekdays"] = days
    elif kind == "monthly":
        monthly = monthly_rule(width, height, start_date, current)
        if monthly is None:
            return None
        for name in monthly:
            rule[name] = monthly[name]
    ending = choose(width, height, "Repeat ending", ["Never", "On a date"],
                    1 if current.get("until") else 0)
    if ending is None:
        return None
    if ending == 1:
        until = date_picker(width, height, "Repeat until",
                            current.get("until") or month_shift(start_date, 6))
        if until is None:
            return None
        if until < start_date:
            message(width, height, "Invalid ending", "The ending date cannot be before the event starts.")
            return None
        rule["until"] = until
    return normalize_repeat(rule, start_date)


REMINDER_VALUES = (-1, 0, 5, 15, 30, 60, 1440)
REMINDER_NAMES = ("None", "At start", "5 minutes before", "15 minutes before",
                  "30 minutes before", "1 hour before", "1 day before")


def reminder_name(value):
    return REMINDER_NAMES[REMINDER_VALUES.index(value)] if value in REMINDER_VALUES else "None"


def choose_reminder(width, height, current):
    selected = REMINDER_VALUES.index(current) if current in REMINDER_VALUES else 0
    result = choose(width, height, "Reminder", list(REMINDER_NAMES), selected)
    return None if result is None else REMINDER_VALUES[result]


def event_fields_from(event):
    return {
        "title": event.get("title", ""), "calendar_id": event.get("calendar_id", ""),
        "start_date": event.get("start_date", ""), "start_time": event.get("start_time", ""),
        "end_date": event.get("end_date", ""), "end_time": event.get("end_time", ""),
        "all_day": event.get("all_day", False), "location": event.get("location", ""),
        "notes": event.get("notes", ""), "reminder": event.get("reminder", -1),
        "repeat": event.get("repeat", {}),
    }


def create_event_flow(width, height, state, initial_date=None, duplicate=None):
    if len(state["events"]) >= MAX_EVENTS:
        message(width, height, "Event limit", "This calendar already contains 1024 events. Export and remove older events first.")
        return None
    now = now_value()
    fields = event_fields_from(duplicate) if duplicate else {}
    fields["start_date"] = initial_date or fields.get("start_date") or date_key(now)
    title = edit_text(width, height, "New event", "Title", fields.get("title", ""))
    if not title:
        return None
    fields["title"] = title
    date = date_picker(width, height, "Event date", fields["start_date"])
    if date is None:
        return None
    fields["start_date"] = date
    fields["end_date"] = date
    kind = choose(width, height, "Event time", ["Timed event", "All-day event"],
                  1 if fields.get("all_day") else 0)
    if kind is None:
        return None
    fields["all_day"] = kind == 1
    if fields["all_day"]:
        fields["start_time"] = ""
        fields["end_time"] = ""
    else:
        initial_time = fields.get("start_time") or (pad2(now.get("hour", 9)) + ":" + pad2((now.get("minute", 0) // 5) * 5))
        start_time = time_picker(width, height, "Starts", initial_time)
        if start_time is None:
            return None
        end_date, end_time = add_minutes(date, start_time,
                                         state["settings"].get("default_duration", 60))
        fields["start_time"] = start_time
        fields["end_date"] = end_date
        fields["end_time"] = end_time
    calendar_id = choose_calendar(width, height, state, fields.get("calendar_id", ""), True)
    if calendar_id is None:
        return None
    fields["calendar_id"] = calendar_id
    reminder = choose_reminder(width, height,
                               fields.get("reminder", state["settings"].get("default_reminder", 15)))
    if reminder is None:
        return None
    fields["reminder"] = reminder
    repeat = recurrence_editor(width, height, date, fields.get("repeat"))
    if repeat is None:
        return None
    fields["repeat"] = repeat
    fields["utc_now"] = utc_now_value()
    more = choose(width, height, "Event details", ["Save now", "Add location and notes"])
    if more is None:
        return None
    if more == 1:
        location = edit_text(width, height, "Event details", "Location",
                             fields.get("location", ""), 120)
        if location is None:
            return None
        notes = edit_text(width, height, "Event details", "Notes",
                          fields.get("notes", ""), 800, True)
        if notes is None:
            return None
        fields["location"] = location
        fields["notes"] = notes
    item = add_event(state, fields, now)
    if item is not None and persist(width, height, state):
        return item
    return None


def edit_event_screen(width, height, state, event):
    selected = 0
    while not solaros.should_exit():
        time_text = "All day" if event.get("all_day") else event.get("start_time", "") + "-" + event.get("end_time", "")
        options = [
            "Title: " + event.get("title", ""),
            "Date: " + event.get("start_date", ""),
            "Time: " + time_text,
            "Calendar: " + calendar_name(state, event.get("calendar_id", "")),
            "Location: " + (event.get("location") or "None"),
            "Notes: " + (event.get("notes") or "None"),
            "Reminder: " + reminder_name(event.get("reminder", -1)),
            "Repeat: " + repeat_label(event.get("repeat")),
        ]
        choice = choose(width, height, "Edit event", options, selected)
        if choice is None:
            return
        selected = choice
        changed = False
        if choice == 0:
            value = edit_text(width, height, "Edit event", "Title", event.get("title", ""))
            if value:
                event["title"] = value
                changed = True
        elif choice == 1:
            value = date_picker(width, height, "Event date", event.get("start_date", ""))
            if value:
                event["start_date"] = value
                event["end_date"] = value
                event["repeat"] = normalize_repeat(event.get("repeat"), value)
                event["reminded"] = []
                changed = True
        elif choice == 2:
            mode = choose(width, height, "Event time", ["Timed event", "All-day event"],
                          1 if event.get("all_day") else 0)
            if mode is not None:
                event["all_day"] = mode == 1
                if event["all_day"]:
                    event["start_time"] = ""
                    event["end_time"] = ""
                    event["end_date"] = event.get("start_date", "")
                else:
                    start = time_picker(width, height, "Starts", event.get("start_time") or "09:00")
                    if start is None:
                        continue
                    end = time_picker(width, height, "Ends", event.get("end_time") or "10:00")
                    if end is None:
                        continue
                    event["start_time"] = start
                    event["end_time"] = end
                    event["end_date"] = (add_days(event.get("start_date", ""), 1)
                                         if end <= start else event.get("start_date", ""))
                event["reminded"] = []
                changed = True
        elif choice == 3:
            value = choose_calendar(width, height, state, event.get("calendar_id", ""), True)
            if value:
                event["calendar_id"] = value
                changed = True
        elif choice == 4:
            value = edit_text(width, height, "Edit event", "Location", event.get("location", ""), 120)
            if value is not None:
                event["location"] = value
                changed = True
        elif choice == 5:
            value = edit_text(width, height, "Edit event", "Notes", event.get("notes", ""), 800, True)
            if value is not None:
                event["notes"] = value
                changed = True
        elif choice == 6:
            value = choose_reminder(width, height, event.get("reminder", -1))
            if value is not None:
                event["reminder"] = value
                event["reminded"] = []
                changed = True
        elif choice == 7:
            value = recurrence_editor(width, height, event.get("start_date", ""), event.get("repeat"))
            if value is not None:
                event["repeat"] = value
                event["skip_dates"] = []
                event["reminded"] = []
                changed = True
        if changed:
            persist(width, height, state)


def event_time_label(event, settings):
    if event.get("all_day"):
        return "All day"
    style = settings.get("time_format", "12")
    start = format_time(event.get("start_time", ""), style)
    end = format_time(event.get("end_time", ""), style)
    return start + ("-" + end if end else "")


def event_detail(width, height, state, event, occurrence_date):
    while not solaros.should_exit():
        subscribed = calendar_is_subscribed(state, event.get("calendar_id", ""))
        gfx.clear(gfx.WHITE)
        draw_header(width, event.get("title", "Event"),
                    format_date(occurrence_date, state["settings"].get("date_format")) + "  " + event_time_label(event, state["settings"]))
        gfx.color(gfx.BLACK)
        gfx.font(gfx.FONT_MONO_14)
        lines = []
        lines.append("Calendar: " + calendar_name(state, event.get("calendar_id", "")))
        if event.get("location"):
            lines.append("Location: " + event["location"])
        if event.get("reminder", -1) >= 0:
            lines.append("Reminder: " + reminder_name(event["reminder"]))
        if event.get("repeat"):
            lines.append("Repeats: " + repeat_label(event["repeat"]))
        if event.get("notes"):
            lines.append("")
            lines.extend(wrap_text(event["notes"], max(10, (width - 24) // 7), 7))
        y = HEADER_H + 23
        visible = max(1, (height - HEADER_H - FOOTER_H - 5) // 19)
        flattened = []
        for line in lines:
            flattened.extend(wrap_text(line, max(10, (width - 24) // 7), 4) if line else [""])
        for line in flattened[:visible]:
            gfx.text(12, y, line)
            y += 19
        draw_footer(width, height, ("D copy to local  Esc back" if subscribed else
                                    "E edit  D duplicate  X delete  S skip  Esc back"))
        gfx.refresh()
        key = wait_key()
        if key in (gfx.KEY_ESCAPE, gfx.KEY_LEFT, ord("q"), ord("Q")):
            return False
        if key in (ord("e"), ord("E")) and not subscribed:
            edit_event_screen(width, height, state, event)
        elif key in (ord("d"), ord("D")):
            create_event_flow(width, height, state, occurrence_date, event)
        elif key in (ord("s"), ord("S")) and event.get("repeat") and not subscribed:
            if confirm(width, height, "Skip occurrence", "Skip only " + occurrence_date + "?"):
                skip_occurrence(event, occurrence_date)
                persist(width, height, state)
                return True
        elif key in (ord("x"), ord("X"), KEY_DELETE) and not subscribed:
            if event.get("repeat"):
                action = choose(width, height, "Delete recurring event",
                                ["Only this occurrence", "Entire series"])
                if action == 0:
                    skip_occurrence(event, occurrence_date)
                    persist(width, height, state)
                    return True
                if action != 1:
                    continue
            if confirm(width, height, "Delete event", event.get("title", "Event")):
                delete_event(state, event.get("id"))
                persist(width, height, state)
                return True
    return False


def draw_occurrence_row(width, y, occurrence, selected, state, show_date=True):
    date, event = occurrence
    if selected:
        gfx.color(gfx.BLACK)
        gfx.fill_rect(4, y + 2, width - 8, ROW_H - 3)
        foreground = gfx.WHITE
    else:
        gfx.color(gfx.WHITE)
        gfx.fill_rect(0, y, width, ROW_H)
        foreground = gfx.BLACK
        gfx.color(gfx.LIGHT)
        gfx.line(8, y + ROW_H - 1, width - 8, y + ROW_H - 1)
    date_width = 54 if show_date else 10
    gfx.color(foreground)
    gfx.font(gfx.FONT_MONO_12)
    if show_date:
        gfx.text(9, y + 18, clip(format_date(date, "mon_day"), 8))
        gfx.text(9, y + 34, WEEKDAYS[weekday_for(date)])
    title_x = date_width + 7
    gfx.font(gfx.FONT_BOLD_14)
    gfx.text(title_x, y + 19, clip(event.get("title", "Event"), max(5, (width - title_x - 9) // 7)))
    meta = event_time_label(event, state["settings"])
    if event.get("repeat"):
        meta += "  repeat"
    gfx.font(gfx.FONT_MONO_12)
    gfx.text(title_x, y + 35, clip(meta, max(5, (width - title_x - 9) // 6)))


def occurrence_list(width, height, state, title, start_date, end_date, show_date=True,
                    empty_text="Nothing scheduled."):
    selected = 0
    while not solaros.should_exit():
        items = occurrences_between(state, start_date, end_date)
        if selected >= len(items):
            selected = max(0, len(items) - 1)
        subtitle = start_date if start_date == end_date else start_date + " through " + end_date
        gfx.clear(gfx.WHITE)
        draw_header(width, title, subtitle)
        visible = max(1, (height - HEADER_H - FOOTER_H) // ROW_H)
        start = (selected // visible) * visible if items else 0
        for row, item in enumerate(items[start:start + visible]):
            draw_occurrence_row(width, HEADER_H + row * ROW_H, item,
                                start + row == selected, state, show_date)
        if not items:
            gfx.color(gfx.DARK)
            gfx.font(gfx.FONT_MONO_16)
            gfx.text(14, HEADER_H + 45, empty_text)
        draw_footer(width, height, "Enter open  A add  Esc back")
        gfx.refresh()
        key = wait_key()
        if key in (gfx.KEY_ESCAPE, gfx.KEY_LEFT, ord("q"), ord("Q")):
            return
        if key in (gfx.KEY_UP, ord("k")) and items:
            selected = (selected - 1) % len(items)
        elif key in (gfx.KEY_DOWN, ord("j")) and items:
            selected = (selected + 1) % len(items)
        elif key in (KEY_ENTER, KEY_LF, gfx.KEY_RIGHT) and items:
            event_detail(width, height, state, items[selected][1], items[selected][0])
        elif key in (ord("a"), ord("A")):
            create_event_flow(width, height, state, start_date)


def handle_reminders(width, height, state):
    reminders = due_reminders(state, now_value())
    if not reminders:
        return
    date, event = reminders[0]
    text = event_time_label(event, state["settings"]) + " on " + format_date(date, state["settings"].get("date_format"))
    if event.get("location"):
        text += " at " + event["location"]
    message(width, height, "Reminder: " + event.get("title", "Event"), text)
    mark_reminded(event, date)
    persist(width, height, state)


def agenda_screen(width, height, state):
    selected = 0
    while not solaros.should_exit():
        handle_reminders(width, height, state)
        now = now_value()
        today = date_key(now)
        items = occurrences_between(state, today, add_days(today, 30))
        if not state["settings"].get("show_past_today", True):
            current_time = pad2(now.get("hour", 0)) + ":" + pad2(now.get("minute", 0))
            items = [item for item in items if item[0] != today or item[1].get("all_day") or item[1].get("start_time", "") >= current_time]
        if selected >= len(items):
            selected = max(0, len(items) - 1)
        visible_calendars = 0
        for calendar in state["calendars"]:
            if calendar.get("visible", True):
                visible_calendars += 1
        subtitle = (format_date(today, state["settings"].get("date_format"))
                    if now.get("clock_integrity") is not False else "Clock not set")
        subtitle += "  |  {} calendar(s)".format(visible_calendars)
        gfx.clear(gfx.WHITE)
        draw_header(width, "Agenda", subtitle)
        visible = max(1, (height - HEADER_H - FOOTER_H) // ROW_H)
        start = (selected // visible) * visible if items else 0
        for row, item in enumerate(items[start:start + visible]):
            draw_occurrence_row(width, HEADER_H + row * ROW_H, item,
                                start + row == selected, state, True)
        if not items:
            gfx.color(gfx.DARK)
            gfx.font(gfx.FONT_MONO_16)
            gfx.text(14, HEADER_H + 43, "No upcoming events.")
            gfx.font(gfx.FONT_MONO_12)
            gfx.text(14, HEADER_H + 64, "Press A to add one.")
        draw_footer(width, height, "Enter open  A add  M month  / search  S settings")
        gfx.refresh()
        key = wait_key()
        if key in (gfx.KEY_ESCAPE, ord("q"), ord("Q")):
            return
        if key in (gfx.KEY_UP, ord("k")) and items:
            selected = (selected - 1) % len(items)
        elif key in (gfx.KEY_DOWN, ord("j")) and items:
            selected = (selected + 1) % len(items)
        elif key in (KEY_ENTER, KEY_LF, gfx.KEY_RIGHT) and items:
            event_detail(width, height, state, items[selected][1], items[selected][0])
        elif key in (ord("a"), ord("A")):
            create_event_flow(width, height, state, today)
        elif key in (ord("m"), ord("M")):
            month_screen(width, height, state, today)
        elif key == ord("/"):
            search_screen(width, height, state)
        elif key in (ord("s"), ord("S")):
            settings_screen(width, height, state)


def month_grid_start(selected, week_start):
    year, month, unused = date_parts(selected)
    first = make_date(year, month, 1)
    offset = (weekday_for(first) - week_start) % 7
    return add_days(first, -offset)


def draw_month(width, height, state, selected, counts=None):
    year, month, unused = date_parts(selected)
    week_start = state["settings"].get("week_start", 0)
    grid_start = month_grid_start(selected, week_start)
    if counts is None:
        counts = occurrence_counts(state, grid_start, add_days(grid_start, 41))
    gfx.clear(gfx.WHITE)
    draw_header(width, calendar_month_name(month) + " " + str(year),
                format_date(selected, state["settings"].get("date_format")))
    cell_w = width // 7
    grid_y = HEADER_H + 18
    grid_h = height - grid_y - FOOTER_H
    cell_h = max(25, grid_h // 6)
    gfx.font(gfx.FONT_MONO_12)
    for column in range(7):
        day = (column + week_start) % 7
        gfx.color(gfx.BLACK)
        gfx.text(column * cell_w + 4, HEADER_H + 14, WEEKDAYS[day][:2])
    date = grid_start
    for row in range(6):
        for column in range(7):
            x = column * cell_w
            y = grid_y + row * cell_h
            in_month = date_parts(date)[1] == month
            active = date == selected
            if active:
                gfx.color(gfx.BLACK)
                gfx.fill_rect(x + 1, y + 1, cell_w - 2, cell_h - 2)
                foreground = gfx.WHITE
            else:
                foreground = gfx.BLACK if in_month else gfx.DARK
                gfx.color(gfx.LIGHT)
                gfx.rect(x, y, cell_w, cell_h)
            gfx.color(foreground)
            gfx.font(gfx.FONT_BOLD_14 if active else gfx.FONT_MONO_14)
            gfx.text(x + 5, y + 17, str(date_parts(date)[2]))
            count = counts.get(date, 0)
            if count:
                marker = str(count) if count < 10 else "+"
                gfx.font(gfx.FONT_MONO_12)
                gfx.text(x + cell_w - 8, y + cell_h - 5, marker)
            date = add_days(date, 1)
    draw_footer(width, height, "Enter day  A add  T today  [/] month  Esc agenda")
    gfx.refresh()


def redraw_month_cell(width, height, state, date, selected, grid_start, month, counts):
    index = date_to_ordinal(date) - date_to_ordinal(grid_start)
    if index < 0 or index >= 42:
        return
    column = index % 7
    row = index // 7
    cell_w = width // 7
    grid_y = HEADER_H + 18
    grid_h = height - grid_y - FOOTER_H
    cell_h = max(25, grid_h // 6)
    x = column * cell_w
    y = grid_y + row * cell_h
    active = date == selected
    in_month = date_parts(date)[1] == month
    if active:
        gfx.color(gfx.BLACK)
        gfx.fill_rect(x + 1, y + 1, cell_w - 2, cell_h - 2)
        foreground = gfx.WHITE
    else:
        gfx.color(gfx.WHITE)
        gfx.fill_rect(x + 1, y + 1, cell_w - 2, cell_h - 2)
        gfx.color(gfx.LIGHT)
        gfx.rect(x, y, cell_w, cell_h)
        foreground = gfx.BLACK if in_month else gfx.DARK
    gfx.color(foreground)
    gfx.font(gfx.FONT_BOLD_14 if active else gfx.FONT_MONO_14)
    gfx.text(x + 5, y + 17, str(date_parts(date)[2]))
    count = counts.get(date, 0)
    if count:
        marker = str(count) if count < 10 else "+"
        gfx.font(gfx.FONT_MONO_12)
        gfx.text(x + cell_w - 8, y + cell_h - 5, marker)


def redraw_month_selection(width, height, state, old_date, selected, grid_start, counts):
    month = date_parts(selected)[1]
    redraw_month_cell(width, height, state, old_date, selected, grid_start, month, counts)
    redraw_month_cell(width, height, state, selected, selected, grid_start, month, counts)
    gfx.color(gfx.BLACK)
    gfx.fill_rect(0, 20, width, HEADER_H - 20)
    gfx.color(gfx.WHITE)
    gfx.font(gfx.FONT_MONO_12)
    gfx.text(10, 36, clip(format_date(selected, state["settings"].get("date_format")),
                          max(1, (width - 20) // 6)))
    gfx.refresh()


def month_screen(width, height, state, initial):
    selected = valid_date(initial, date_key(now_value()))
    cached_grid = ""
    cached_counts = {}
    dirty = True
    drawn_selected = ""
    while not solaros.should_exit():
        grid_start = month_grid_start(selected, state["settings"].get("week_start", 0))
        if dirty or grid_start != cached_grid:
            cached_grid = grid_start
            cached_counts = occurrence_counts(state, grid_start, add_days(grid_start, 41))
            dirty = False
            draw_month(width, height, state, selected, cached_counts)
        elif drawn_selected != selected:
            redraw_month_selection(width, height, state, drawn_selected, selected,
                                   grid_start, cached_counts)
        drawn_selected = selected
        key = wait_key()
        if key in (gfx.KEY_ESCAPE, ord("q"), ord("Q")):
            return
        if key == gfx.KEY_LEFT:
            selected = add_days(selected, -1)
        elif key == gfx.KEY_RIGHT:
            selected = add_days(selected, 1)
        elif key == gfx.KEY_UP:
            selected = add_days(selected, -7)
        elif key == gfx.KEY_DOWN:
            selected = add_days(selected, 7)
        elif key in (ord("["), KEY_PAGE_UP):
            selected = month_shift(selected, -1)
        elif key in (ord("]"), KEY_PAGE_DOWN):
            selected = month_shift(selected, 1)
        elif key in (ord("t"), ord("T")):
            selected = date_key(now_value())
        elif key in (ord("a"), ord("A")):
            create_event_flow(width, height, state, selected)
            dirty = True
        elif key in (KEY_ENTER, KEY_LF):
            occurrence_list(width, height, state, "Day", selected, selected, False)
            dirty = True


def search_screen(width, height, state):
    query = edit_text(width, height, "Search", "Title, location, or notes", "", 80)
    if not query:
        return
    selected = 0
    while not solaros.should_exit():
        events = search_events(state, query)
        options = []
        for event in events:
            options.append(event.get("start_date", "") + "  " + event.get("title", "Event"))
        if not options:
            message(width, height, "Search", "No events matched " + query)
            return
        choice = choose(width, height, "Search: " + query, options, selected,
                        "Enter open   Esc back")
        if choice is None:
            return
        selected = choice
        event = events[selected]
        event_detail(width, height, state, event, event.get("start_date", ""))


def normalize_ics_url(value):
    value = clean_text(value, "", 240)
    if value.lower().startswith("webcal://"):
        value = "https://" + value[9:]
    if not (value.lower().startswith("http://") or value.lower().startswith("https://")):
        return ""
    return value


def subscription_name(url):
    value = url.split("?", 1)[0].rstrip("/")
    value = value.rsplit("/", 1)[-1]
    if value.lower().endswith(".ics"):
        value = value[:-4]
    value = value.replace("%20", " ").replace("_", " ").replace("-", " ")
    return clean_text(value, "Subscribed calendar", 48)


def remove_file(path):
    try:
        solaros.storage.remove(path)
    except OSError:
        pass


def draw_sync_progress(width, height, name, received, total):
    gfx.clear(gfx.WHITE)
    draw_header(width, "Syncing calendar", clip(name, 40))
    gfx.color(gfx.BLACK)
    gfx.font(gfx.FONT_MONO_14)
    if total > 0:
        percent = min(100, (received * 100) // total)
        status = "Downloading: {}%  {}/{} KB".format(
            percent, received // 1024, total // 1024)
    else:
        status = "Downloading: {} KB".format(received // 1024)
    gfx.text(20, HEADER_H + 58, clip(status, max(8, (width - 40) // 7)))
    bar_x = 20
    bar_y = HEADER_H + 83
    bar_width = width - 40
    gfx.rect(bar_x, bar_y, bar_width, 20)
    if total > 0:
        filled = min(bar_width - 4, (received * (bar_width - 4)) // total)
    else:
        filled = min(bar_width - 4, (received // 1024) % max(1, bar_width - 4))
    if filled > 0:
        gfx.fill_rect(bar_x + 2, bar_y + 2, filled, 16)
    gfx.font(gfx.FONT_MONO_14)
    gfx.text(20, HEADER_H + 136, "Events remain available during errors.")
    draw_footer(width, height, "Esc cancel")
    gfx.refresh()


def download_ics_url(width, height, name, url, path):
    remove_file(path)
    handle = None
    received = 0
    total = -1
    status = 0
    complete = False
    next_redraw = 0
    try:
        handle = solaros.http.stream_open(
            "GET", url, None,
            {"Accept": "text/calendar, application/ics, text/plain"},
            20000, True)
        with open(path, "wb") as output:
            draw_sync_progress(width, height, name, 0, total)
            while not solaros.should_exit():
                key = gfx.getch(0)
                if key == gfx.KEY_ESCAPE:
                    raise RuntimeError("Sync cancelled")
                event = solaros.http.stream_read(handle, 500)
                if event is None:
                    continue
                kind = event.get("type")
                if kind == "response":
                    status = event.get("status_code", 0)
                    total = event.get("content_length", -1)
                    if status < 200 or status >= 300:
                        raise RuntimeError("Server returned HTTP " + str(status))
                    if total > MAX_ICS_DOWNLOAD:
                        raise RuntimeError("Calendar exceeds the 1 MB download limit")
                    draw_sync_progress(width, height, name, received, total)
                elif kind == "data":
                    chunk = event.get("data", b"")
                    received += len(chunk)
                    if received > MAX_ICS_DOWNLOAD:
                        raise RuntimeError("Calendar exceeds the 1 MB download limit")
                    output.write(chunk)
                    if received >= next_redraw:
                        draw_sync_progress(width, height, name, received, total)
                        next_redraw = received + 8192
                elif kind == "error":
                    raise RuntimeError(event.get("error_name", "HTTP stream error"))
                elif kind == "complete":
                    complete = True
                    break
            output.flush()
        if not complete or status < 200 or status >= 300:
            raise RuntimeError("Calendar download did not complete")
        draw_sync_progress(width, height, name, received, total)
        return received
    except Exception:
        remove_file(path)
        raise
    finally:
        if handle is not None:
            solaros.http.stream_close(handle)
        gc.collect()


def inspect_ics(path):
    began = False
    ended = False
    event_count = 0
    with open(path, "r") as source:
        for line in source:
            value = line.strip().upper()
            if value == "BEGIN:VCALENDAR":
                began = True
            elif value == "END:VCALENDAR":
                ended = True
            elif value == "BEGIN:VEVENT":
                event_count += 1
    if not began or not ended:
        raise RuntimeError("Downloaded file is not an ICS calendar")
    return event_count


def sync_calendar_path(state, calendar, path):
    source_events = inspect_ics(path)
    staging = default_state()
    staging["uid_origin"] = state.get("uid_origin", "solaros.local")
    with open(path, "r") as source:
        added, skipped = import_ics(source, staging, now_value(),
                                    staging["calendars"][0]["id"])
    if source_events and not added:
        raise RuntimeError("No valid events were found; the existing calendar was kept")
    replace_calendar_events(state, calendar.get("id"), staging["events"])
    calendar["last_sync"] = timestamp(now_value())
    gc.collect()
    return added, skipped


def sync_calendar(width, height, state, calendar, url=None):
    source_url = normalize_ics_url(url if url is not None else calendar.get("source_url", ""))
    if not source_url:
        raise RuntimeError("Enter a complete http:// or https:// calendar URL")
    download_ics_url(width, height, calendar.get("name", "Calendar"), source_url, SYNC_TEMP)
    try:
        result = sync_calendar_path(state, calendar, SYNC_TEMP)
        calendar["source_url"] = source_url
        return result
    finally:
        remove_file(SYNC_TEMP)


def add_local_calendar_flow(width, height, state):
    if len(state["calendars"]) >= 32:
        message(width, height, "Calendar limit", "Remove an existing calendar before adding another.")
        return None
    value = edit_text(width, height, "New local calendar", "Name", "", 48)
    if value:
        item = add_calendar(state, value)
        if item and persist(width, height, state):
            return item
    return None


def add_subscription_flow(width, height, state):
    if len(state["calendars"]) >= 32:
        message(width, height, "Calendar limit", "Remove an existing calendar before adding another.")
        return None
    entered = edit_text(width, height, "Calendar subscription", "ICS URL", "https://", 240)
    url = normalize_ics_url(entered)
    if not entered:
        return None
    if not url:
        message(width, height, "Invalid URL", "Use a complete http://, https://, or webcal:// URL.")
        return None
    name = edit_text(width, height, "Calendar subscription", "Calendar name",
                     subscription_name(url), 48)
    if not name:
        return None
    item = add_calendar(state, name, url)
    if item is None:
        return None
    try:
        added, skipped = sync_calendar(width, height, state, item)
        if not persist(width, height, state):
            return None
        message(width, height, "Subscription added",
                "Downloaded {} event(s); skipped {} invalid event(s). Refresh it any time from Calendars.".format(added, skipped))
        return item
    except Exception as error:
        delete_calendar(state, item.get("id"), True)
        message(width, height, "Subscription failed", str(error))
        return None


def calendars_screen(width, height, state):
    selected = 0
    while not solaros.should_exit():
        calendars = state["calendars"]
        labels = ["+ Add local calendar", "+ Add calendar from URL"]
        for item in calendars:
            kind = "URL " if item.get("source_url") else "LOCAL "
            labels.append(("[x] " if item.get("visible", True) else "[ ] ") +
                          kind + item.get("name", "Calendar"))
        choice = choose(width, height, "Calendars", labels, selected,
                        "Enter choose   Esc back")
        if choice is None:
            return
        selected = choice
        if choice == 0:
            item = add_local_calendar_flow(width, height, state)
            if item:
                selected = len(state["calendars"]) + 1
            continue
        if choice == 1:
            item = add_subscription_flow(width, height, state)
            if item:
                selected = len(state["calendars"]) + 1
            continue
        calendar_index = choice - 2
        if calendar_index < 0 or calendar_index >= len(calendars):
            selected = 0
            continue
        calendar = calendars[calendar_index]
        subscribed = bool(calendar.get("source_url"))
        actions = ["Show" if not calendar.get("visible", True) else "Hide", "Rename"]
        if subscribed:
            actions.extend(["Sync now", "Change subscription URL"])
        actions.append("Delete")
        key = choose(width, height, calendar.get("name", "Calendar"), actions)
        if key == 0:
            calendar["visible"] = not calendar.get("visible", True)
            persist(width, height, state)
        elif key == 1:
            value = edit_text(width, height, "Rename calendar", "Name",
                              calendar.get("name", ""), 48)
            if value:
                calendar["name"] = value
                persist(width, height, state)
        elif subscribed and key == 2:
            try:
                added, skipped = sync_calendar(width, height, state, calendar)
                if persist(width, height, state):
                    message(width, height, "Sync complete",
                            "Now contains {} event(s); skipped {} invalid event(s).".format(added, skipped))
            except Exception as error:
                message(width, height, "Sync failed", str(error))
        elif subscribed and key == 3:
            entered = edit_text(width, height, "Subscription URL", "ICS URL",
                                calendar.get("source_url", ""), 240)
            if entered:
                replacement = normalize_ics_url(entered)
                if not replacement:
                    message(width, height, "Invalid URL", "Use a complete http://, https://, or webcal:// URL.")
                else:
                    try:
                        added, skipped = sync_calendar(width, height, state, calendar, replacement)
                        if persist(width, height, state):
                            message(width, height, "URL changed",
                                    "Now contains {} event(s); skipped {} invalid event(s).".format(added, skipped))
                    except Exception as error:
                        message(width, height, "Sync failed", str(error))
        elif key == len(actions) - 1:
            local_count = len([item for item in calendars if not item.get("source_url")])
            if len(calendars) <= 1 or (not subscribed and local_count <= 1):
                message(width, height, "Cannot delete", "At least one local calendar must remain for new and imported events.")
            else:
                detail = ("Downloaded events will also be removed. Delete " if subscribed else
                          "Events will be moved to another calendar. Delete ")
                if confirm(width, height, "Delete calendar",
                           detail + calendar.get("name", "Calendar") + "?"):
                    delete_calendar(state, calendar.get("id"), subscribed)
                    persist(width, height, state)
                    selected = min(selected, len(state["calendars"]) + 1)


def write_export(state, kind):
    ensure_directory(EXPORT_DIR)
    now = now_value()
    today = date_key(now) if now.get("clock_integrity") is not False else "undated"
    extension = ".ics" if kind == "ics" else ".json"
    path = EXPORT_DIR + "/calendar-" + today + extension
    temporary = path + ".tmp"
    with open(temporary, "w") as output:
        if kind == "ics":
            write_ics(state, output)
        else:
            json.dump(state, output)
        output.flush()
    try:
        solaros.storage.remove(path)
    except OSError:
        pass
    solaros.storage.rename(temporary, path)
    return path


def import_ics_path(state, path, calendar_id=""):
    with open(path, "r") as source:
        return import_ics(source, state, now_value(), calendar_id)


def sync_all_subscriptions(width, height, state):
    subscriptions = [item for item in state["calendars"] if item.get("source_url")]
    if not subscriptions:
        message(width, height, "Sync calendars", "No URL calendars have been added yet.")
        return
    synced = 0
    failed = []
    for calendar in subscriptions:
        try:
            sync_calendar(width, height, state, calendar)
            if persist(width, height, state):
                synced += 1
        except Exception as error:
            failed.append(calendar.get("name", "Calendar") + ": " + str(error))
            if str(error) == "Sync cancelled":
                break
    text = "Synced {} of {} subscribed calendar(s).".format(synced, len(subscriptions))
    if failed:
        text += "\n" + "\n".join(failed[:3])
        if len(failed) > 3:
            text += "\nAnd {} more error(s).".format(len(failed) - 3)
    message(width, height, "Sync complete" if not failed else "Sync finished with errors", text)


def settings_screen(width, height, state):
    selected = 0
    while not solaros.should_exit():
        settings = state["settings"]
        options = [
            "Calendars and subscriptions",
            "Sync all URL calendars",
            "Date format: " + {"mon_day": "Sep 12", "ymd": "2026-09-12", "mdy": "09/12/2026", "dmy": "12/09/2026"}.get(settings.get("date_format"), "Sep 12"),
            "Time format: " + settings.get("time_format", "12") + " hour",
            "Week starts: " + ("Monday" if settings.get("week_start") == 1 else "Sunday"),
            "Past events today: " + ("shown" if settings.get("show_past_today", True) else "hidden"),
            "Default duration: " + str(settings.get("default_duration", 60)) + " minutes",
            "Default reminder: " + reminder_name(settings.get("default_reminder", 15)),
            "Import an ICS file from storage",
            "Export as ICS",
            "Back up as JSON",
        ]
        choice = choose(width, height, "Settings", options, selected)
        if choice is None:
            return
        selected = choice
        changed = False
        if choice == 0:
            calendars_screen(width, height, state)
        elif choice == 1:
            sync_all_subscriptions(width, height, state)
        elif choice == 2:
            values = ["Sep 12", "2026-09-12", "09/12/2026", "12/09/2026"]
            result = choose(width, height, "Date format", values)
            if result is not None:
                settings["date_format"] = ("mon_day", "ymd", "mdy", "dmy")[result]
                changed = True
        elif choice == 3:
            settings["time_format"] = "24" if settings.get("time_format") == "12" else "12"
            changed = True
        elif choice == 4:
            settings["week_start"] = 0 if settings.get("week_start") == 1 else 1
            changed = True
        elif choice == 5:
            settings["show_past_today"] = not settings.get("show_past_today", True)
            changed = True
        elif choice == 6:
            values = (15, 30, 45, 60, 90, 120)
            names = [str(value) + " minutes" for value in values]
            current = settings.get("default_duration", 60)
            index = values.index(current) if current in values else 3
            result = choose(width, height, "Default duration", names, index)
            if result is not None:
                settings["default_duration"] = values[result]
                changed = True
        elif choice == 7:
            result = choose_reminder(width, height, settings.get("default_reminder", 15))
            if result is not None:
                settings["default_reminder"] = result
                changed = True
        elif choice == 8:
            path = edit_text(width, height, "Import ICS", "File path", "/Downloads/", 200)
            if path:
                calendar_id = choose_calendar(width, height, state, "", True)
                if calendar_id:
                    try:
                        added, skipped = import_ics_path(state, path, calendar_id)
                        persist(width, height, state)
                        message(width, height, "Import complete", "Added {} event(s); skipped {} duplicate or invalid event(s).".format(added, skipped))
                    except Exception as error:
                        message(width, height, "Import failed", str(error))
        elif choice in (9, 10):
            try:
                path = write_export(state, "ics" if choice == 9 else "json")
                message(width, height, "Export complete", "Saved to " + path)
            except Exception as error:
                message(width, height, "Export failed", str(error))
        if changed:
            persist(width, height, state)


def command_file_argument():
    index = 1
    while index < len(sys.argv):
        if sys.argv[index] == "--file" and index + 1 < len(sys.argv):
            return sys.argv[index + 1]
        index += 1
    return ""


def main():
    state = load_state()
    if set_uid_origin(state, device_uid_origin(), utc_now_value()):
        try:
            save_state(state)
        except Exception:
            pass
    import_result = None
    import_error = ""
    path = command_file_argument()
    if path:
        try:
            import_result = import_ics_path(state, path)
            save_state(state)
        except Exception as error:
            import_error = str(error)
    gfx.begin()
    try:
        width, height = gfx.size()
        if LOAD_NOTICE:
            message(width, height, "Storage recovery", LOAD_NOTICE)
        if import_error:
            message(width, height, "Import failed", import_error)
        elif import_result is not None:
            message(width, height, "Import complete", "Added {} event(s); skipped {} duplicate or invalid event(s).".format(import_result[0], import_result[1]))
        agenda_screen(width, height, state)
    finally:
        gfx.end()


if __name__ == "__main__":
    main()
