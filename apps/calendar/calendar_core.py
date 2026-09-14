"""Portable data model for the SolarOS Calendar app.

The module intentionally uses only the small MicroPython language profile that
ships with SolarOS.  Dates are represented as ISO strings and recurrence rules
are expanded only for the range currently being viewed.
"""


STATE_VERSION = 2
MAX_TITLE = 120
MAX_LOCATION = 120
MAX_NOTES = 800
MAX_CALENDARS = 32
MAX_EVENTS = 1024
MAX_SOURCE_URL = 240
VALID_DATE_FORMATS = ("mon_day", "ymd", "mdy", "dmy")
VALID_REPEAT_KINDS = ("daily", "weekdays", "weekly", "monthly", "yearly")
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
WEEKDAYS = ("Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat")
ICS_WEEKDAYS = ("SU", "MO", "TU", "WE", "TH", "FR", "SA")


def clean_text(value, fallback="", limit=MAX_TITLE):
    if not isinstance(value, str):
        value = fallback
    value = " ".join(value.replace("\r", " ").replace("\n", " ").split())
    if len(value) > limit:
        value = value[:limit]
    return value or fallback


def clean_notes(value):
    if not isinstance(value, str):
        return ""
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    result = []
    for line in value.split("\n"):
        result.append(" ".join(line.split()))
    value = "\n".join(result).strip()
    return value[:MAX_NOTES]


def bounded_int(value, fallback, low, high):
    if not isinstance(value, int) or isinstance(value, bool):
        return fallback
    return max(low, min(high, value))


def pad2(value):
    value = str(int(value))
    return "0" + value if len(value) < 2 else value


def days_in_month(year, month):
    if month == 2:
        leap = (year % 4 == 0 and year % 100 != 0) or year % 400 == 0
        return 29 if leap else 28
    if month in (4, 6, 9, 11):
        return 30
    return 31


def make_date(year, month, day):
    return "{}-{}-{}".format(int(year), pad2(month), pad2(day))


def valid_date(value, fallback=""):
    if not isinstance(value, str) or len(value) < 10:
        return fallback
    sample = value[:10]
    if sample[4:5] != "-" or sample[7:8] != "-":
        return fallback
    for index, char in enumerate(sample):
        if index not in (4, 7) and not ("0" <= char <= "9"):
            return fallback
    try:
        year = int(sample[:4])
        month = int(sample[5:7])
        day = int(sample[8:10])
        if year < 1 or year > 9999 or month < 1 or month > 12:
            return fallback
        if day < 1 or day > days_in_month(year, month):
            return fallback
    except Exception:
        return fallback
    return sample


def valid_time(value, fallback=""):
    if not isinstance(value, str) or len(value) < 5:
        return fallback
    sample = value[:5]
    if sample[2:3] != ":":
        return fallback
    try:
        hour = int(sample[:2])
        minute = int(sample[3:5])
        if hour < 0 or hour > 23 or minute < 0 or minute > 59:
            return fallback
    except Exception:
        return fallback
    return pad2(hour) + ":" + pad2(minute)


def valid_stamp(value, fallback=""):
    if not isinstance(value, str):
        return fallback
    date = valid_date(value, "")
    if not date:
        return fallback
    if len(value) >= 16 and value[10:11] == "T":
        time = valid_time(value[11:16], "")
        if time:
            return date + "T" + time
    return date + "T00:00"


def date_key(now):
    try:
        return make_date(now.get("year", 2000), now.get("month", 1),
                         now.get("day", 1))
    except Exception:
        return "2000-01-01"


def timestamp(now):
    return date_key(now) + "T" + pad2(now.get("hour", 0)) + ":" + pad2(now.get("minute", 0))


def clean_uid_origin(value):
    value = value.lower() if isinstance(value, str) else ""
    result = ""
    for char in value[:80]:
        if ("a" <= char <= "z") or ("0" <= char <= "9") or char in ("-", "."):
            result += char
        elif char in ("_", "@", " ") and result and not result.endswith("-"):
            result += "-"
    result = result.strip("-.")
    return result or "solaros.local"


def uid_time(now):
    return (str(bounded_int(now.get("year"), 2000, 1, 9999)) +
            pad2(bounded_int(now.get("month"), 1, 1, 12)) +
            pad2(bounded_int(now.get("day"), 1, 1, 31)) + "T" +
            pad2(bounded_int(now.get("hour"), 0, 0, 23)) +
            pad2(bounded_int(now.get("minute"), 0, 0, 59)) +
            pad2(bounded_int(now.get("second"), 0, 0, 59)))


def uid_time_from_stamp(value):
    value = valid_stamp(value, "2000-01-01T00:00")
    return value[:4] + value[5:7] + value[8:10] + "T" + value[11:13] + value[14:16] + "00"


def valid_ics_stamp(value, fallback=""):
    if not isinstance(value, str) or len(value) != 16 or value[8:9] != "T" or value[-1:] != "Z":
        return fallback
    digits = value[:8] + value[9:15]
    for char in digits:
        if not ("0" <= char <= "9"):
            return fallback
    date, time = ics_date(value)
    return value if date and time else fallback


def make_uid(ident, now, origin):
    return ident + "-" + uid_time(now) + "@" + clean_uid_origin(origin)


def date_parts(value):
    value = valid_date(value, "2000-01-01")
    return int(value[:4]), int(value[5:7]), int(value[8:10])


def date_to_ordinal(value):
    """Return a compact Gregorian day number; 0001-01-01 is day 1."""
    year, month, day = date_parts(value)
    previous = year - 1
    total = previous * 365 + previous // 4 - previous // 100 + previous // 400
    for current in range(1, month):
        total += days_in_month(year, current)
    return total + day


def date_from_ordinal(ordinal):
    ordinal = max(1, int(ordinal))
    year = max(1, ordinal // 366)
    while date_to_ordinal(make_date(year + 1, 1, 1)) <= ordinal:
        year += 1
    while date_to_ordinal(make_date(year, 1, 1)) > ordinal:
        year -= 1
    remaining = ordinal - date_to_ordinal(make_date(year, 1, 1)) + 1
    month = 1
    while remaining > days_in_month(year, month):
        remaining -= days_in_month(year, month)
        month += 1
    return make_date(year, month, remaining)


def add_days(value, amount):
    return date_from_ordinal(date_to_ordinal(value) + int(amount))


def weekday_for(value):
    # Gregorian 0001-01-01 was Monday; SolarOS numbers Sunday as zero.
    return date_to_ordinal(value) % 7


def month_shift(value, amount):
    year, month, day = date_parts(value)
    index = year * 12 + month - 1 + int(amount)
    year = index // 12
    month = index % 12 + 1
    day = min(day, days_in_month(year, month))
    return make_date(year, month, day)


def time_minutes(value):
    value = valid_time(value, "00:00")
    return int(value[:2]) * 60 + int(value[3:5])


def add_minutes(date, time, amount):
    total = time_minutes(time) + int(amount)
    while total < 0:
        date = add_days(date, -1)
        total += 1440
    while total >= 1440:
        date = add_days(date, 1)
        total -= 1440
    return date, pad2(total // 60) + ":" + pad2(total % 60)


def format_date(value, style="mon_day"):
    value = valid_date(value, "")
    if not value:
        return ""
    year, month, day = date_parts(value)
    if style == "ymd":
        return value
    if style == "dmy":
        return pad2(day) + "/" + pad2(month) + "/" + str(year)
    if style == "mdy":
        return pad2(month) + "/" + pad2(day) + "/" + str(year)
    return MONTHS[month - 1] + " " + str(day)


def format_time(value, style="12"):
    value = valid_time(value, "")
    if not value:
        return ""
    hour = int(value[:2])
    minute = value[3:5]
    if style == "24":
        return value
    suffix = "am" if hour < 12 else "pm"
    shown = hour % 12
    if shown == 0:
        shown = 12
    return str(shown) + ":" + minute + suffix


def valid_id(value, prefix):
    if not isinstance(value, str) or len(value) < 2 or len(value) > 10 or value[0] != prefix:
        return False
    for char in value[1:]:
        if not ("0" <= char <= "9"):
            return False
    return True


def default_state():
    return {
        "version": STATE_VERSION,
        "next_id": 2,
        "uid_origin": "solaros.local",
        "settings": {
            "date_format": "mon_day",
            "time_format": "12",
            "week_start": 0,
            "default_duration": 60,
            "default_reminder": 15,
            "show_past_today": True,
        },
        "calendars": [{"id": "c1", "name": "Personal", "visible": True,
                       "source_url": "", "last_sync": ""}],
        "events": [],
    }


def new_id(state, prefix):
    value = bounded_int(state.get("next_id"), 1, 1, 99999999)
    used = {}
    for group_name in ("calendars", "events"):
        for item in state.get(group_name, []):
            if isinstance(item, dict):
                used[item.get("id", "")] = True
    for unused in range(len(used) + 2):
        ident = prefix + str(value)
        value = 1 if value >= 99999999 else value + 1
        if ident not in used:
            state["next_id"] = value
            return ident
    return prefix + "1"


def normalize_repeat(value, start_date):
    if not isinstance(value, dict) or value.get("kind") not in VALID_REPEAT_KINDS:
        return {}
    kind = value.get("kind")
    result = {
        "kind": kind,
        "interval": bounded_int(value.get("interval"), 1, 1, 99),
        "until": valid_date(value.get("until"), ""),
    }
    selected = []
    if isinstance(value.get("weekdays"), list):
        for day in value["weekdays"]:
            if isinstance(day, int) and not isinstance(day, bool) and 0 <= day <= 6 and day not in selected:
                selected.append(day)
    selected.sort()
    if kind == "weekly":
        result["weekdays"] = selected or [weekday_for(start_date)]
    if kind == "monthly":
        if value.get("monthly_mode") == "nth_weekday":
            result["monthly_mode"] = "nth_weekday"
            ordinal = value.get("ordinal", 1)
            result["ordinal"] = ordinal if ordinal in (1, 2, 3, 4, -1) else 1
            result["weekday"] = bounded_int(value.get("weekday"), weekday_for(start_date), 0, 6)
        else:
            result["monthly_mode"] = "day"
            result["month_day"] = bounded_int(value.get("month_day"), date_parts(start_date)[2], 1, 31)
    return result


def normalize_state(value):
    if not isinstance(value, dict):
        return default_state()
    state = default_state()
    state["calendars"] = []
    state["uid_origin"] = clean_uid_origin(value.get("uid_origin", "solaros.local"))
    settings = value.get("settings")
    if isinstance(settings, dict):
        if settings.get("date_format") in VALID_DATE_FORMATS:
            state["settings"]["date_format"] = settings["date_format"]
        if settings.get("time_format") in ("12", "24"):
            state["settings"]["time_format"] = settings["time_format"]
        state["settings"]["week_start"] = bounded_int(settings.get("week_start"), 0, 0, 1)
        state["settings"]["default_duration"] = bounded_int(settings.get("default_duration"), 60, 5, 720)
        reminder = settings.get("default_reminder", 15)
        if reminder in (-1, 0, 5, 15, 30, 60, 1440):
            state["settings"]["default_reminder"] = reminder
        if isinstance(settings.get("show_past_today"), bool):
            state["settings"]["show_past_today"] = settings["show_past_today"]

    next_id = value.get("next_id", 2)
    state["next_id"] = bounded_int(next_id, 2, 1, 99999999)
    used = {}
    greatest = 0
    raw_calendars = value.get("calendars") if isinstance(value.get("calendars"), list) else []
    for raw in raw_calendars[:MAX_CALENDARS]:
        if not isinstance(raw, dict):
            continue
        ident = raw.get("id")
        if not valid_id(ident, "c") or ident in used:
            ident = new_id(state, "c")
        used[ident] = True
        try:
            greatest = max(greatest, int(ident[1:]))
        except Exception:
            pass
        state["calendars"].append({
            "id": ident,
            "name": clean_text(raw.get("name"), "Calendar", 48),
            "visible": raw.get("visible") if isinstance(raw.get("visible"), bool) else True,
            "source_url": clean_text(raw.get("source_url"), "", MAX_SOURCE_URL),
            "last_sync": valid_stamp(raw.get("last_sync"), ""),
        })
    if not state["calendars"]:
        state["calendars"].append({"id": "c1", "name": "Personal", "visible": True,
                                   "source_url": "", "last_sync": ""})
        used["c1"] = True
        greatest = max(greatest, 1)
    calendar_ids = {}
    for item in state["calendars"]:
        calendar_ids[item["id"]] = True
    fallback_calendar = state["calendars"][0]["id"]

    raw_events = value.get("events") if isinstance(value.get("events"), list) else []
    for raw in raw_events[:MAX_EVENTS]:
        if not isinstance(raw, dict):
            continue
        start_date = valid_date(raw.get("start_date"), "")
        if not start_date:
            continue
        ident = raw.get("id")
        if not valid_id(ident, "e") or ident in used:
            ident = new_id(state, "e")
        used[ident] = True
        try:
            greatest = max(greatest, int(ident[1:]))
        except Exception:
            pass
        all_day = raw.get("all_day") is True
        start_time = "" if all_day else valid_time(raw.get("start_time"), "09:00")
        end_date = valid_date(raw.get("end_date"), start_date)
        if end_date < start_date:
            end_date = start_date
        end_time = "" if all_day else valid_time(raw.get("end_time"), start_time)
        calendar_id = raw.get("calendar_id")
        if calendar_id not in calendar_ids:
            calendar_id = fallback_calendar
        reminder = raw.get("reminder", -1)
        if reminder not in (-1, 0, 5, 15, 30, 60, 1440):
            reminder = -1
        reminded = []
        if isinstance(raw.get("reminded"), list):
            for day in raw["reminded"][-16:]:
                day = valid_date(day, "")
                if day and day not in reminded:
                    reminded.append(day)
        skipped = []
        if isinstance(raw.get("skip_dates"), list):
            for day in raw["skip_dates"][-64:]:
                day = valid_date(day, "")
                if day and day not in skipped:
                    skipped.append(day)
        created = valid_stamp(raw.get("created"), start_date + "T00:00")
        uid = clean_text(raw.get("uid"), "", 160)
        if not uid:
            uid = ident + "-" + uid_time_from_stamp(created) + "@" + state["uid_origin"]
        state["events"].append({
            "id": ident,
            "uid": uid,
            "calendar_id": calendar_id,
            "title": clean_text(raw.get("title"), "Untitled event"),
            "start_date": start_date,
            "start_time": start_time,
            "end_date": end_date,
            "end_time": end_time,
            "all_day": all_day,
            "location": clean_text(raw.get("location"), "", MAX_LOCATION),
            "notes": clean_notes(raw.get("notes")),
            "created": created,
            "dtstamp": valid_ics_stamp(raw.get("dtstamp"), ""),
            "reminder": reminder,
            "repeat": normalize_repeat(raw.get("repeat"), start_date),
            "skip_dates": skipped,
            "reminded": reminded,
        })
    if state["next_id"] <= greatest:
        state["next_id"] = 1 if greatest >= 99999999 else greatest + 1
    state["version"] = STATE_VERSION
    return state


def add_calendar(state, name, source_url=""):
    if len(state["calendars"]) >= MAX_CALENDARS:
        return None
    item = {"id": new_id(state, "c"), "name": clean_text(name, "Calendar", 48),
            "visible": True,
            "source_url": clean_text(source_url, "", MAX_SOURCE_URL),
            "last_sync": ""}
    state["calendars"].append(item)
    return item


def delete_calendar(state, calendar_id, delete_events=False):
    if len(state["calendars"]) <= 1:
        return False
    replacement = ""
    for item in state["calendars"]:
        if item.get("id") != calendar_id:
            replacement = item.get("id")
            break
    if not replacement:
        return False
    state["calendars"] = [item for item in state["calendars"] if item.get("id") != calendar_id]
    if delete_events:
        state["events"] = [event for event in state["events"]
                           if event.get("calendar_id") != calendar_id]
    else:
        for event in state["events"]:
            if event.get("calendar_id") == calendar_id:
                event["calendar_id"] = replacement
    return True


def add_event(state, fields, now):
    if len(state["events"]) >= MAX_EVENTS:
        return None
    start_date = valid_date(fields.get("start_date"), date_key(now))
    all_day = fields.get("all_day") is True
    start_time = "" if all_day else valid_time(fields.get("start_time"), "09:00")
    end_date = valid_date(fields.get("end_date"), start_date)
    if end_date < start_date:
        end_date = start_date
    end_time = "" if all_day else valid_time(fields.get("end_time"), start_time)
    calendar_id = fields.get("calendar_id", "")
    valid_calendar = False
    for calendar in state["calendars"]:
        if calendar.get("id") == calendar_id:
            valid_calendar = True
            break
    if not valid_calendar:
        calendar_id = state["calendars"][0]["id"]
    ident = new_id(state, "e")
    item = {
        "id": ident,
        "uid": make_uid(ident, now, state.get("uid_origin", "solaros.local")),
        "calendar_id": calendar_id,
        "title": clean_text(fields.get("title"), "Untitled event"),
        "start_date": start_date,
        "start_time": start_time,
        "end_date": end_date,
        "end_time": end_time,
        "all_day": all_day,
        "location": clean_text(fields.get("location"), "", MAX_LOCATION),
        "notes": clean_notes(fields.get("notes")),
        "created": timestamp(now),
        "dtstamp": valid_ics_stamp(
            fields.get("dtstamp"), uid_time(fields.get("utc_now", now)) + "Z"),
        "reminder": fields.get("reminder") if fields.get("reminder") in (-1, 0, 5, 15, 30, 60, 1440) else -1,
        "repeat": normalize_repeat(fields.get("repeat"), start_date),
        "skip_dates": [],
        "reminded": [],
    }
    state["events"].append(item)
    return item


def set_uid_origin(state, origin, utc_now=None):
    """Apply the current device identity and upgrade legacy local UIDs."""
    origin = clean_uid_origin(origin)
    changed = state.get("uid_origin") != origin
    state["uid_origin"] = origin
    for event in state.get("events", []):
        ident = event.get("id", "")
        if event.get("uid") == ident + "@solaros":
            event["uid"] = (ident + "-" + uid_time_from_stamp(event.get("created", "")) +
                            "@" + origin)
            changed = True
        if not valid_ics_stamp(event.get("dtstamp"), ""):
            event["dtstamp"] = uid_time(utc_now or {}) + "Z"
            changed = True
    return changed


def replace_calendar_events(state, calendar_id, incoming):
    """Replace one subscribed calendar after a successful staged parse."""
    found = False
    for calendar in state.get("calendars", []):
        if calendar.get("id") == calendar_id:
            found = True
            break
    if not found:
        raise ValueError("calendar no longer exists")
    retained = []
    previous = {}
    for event in state.get("events", []):
        if event.get("calendar_id") == calendar_id:
            uid = event.get("uid", "")
            if uid:
                previous[uid] = event
        else:
            retained.append(event)
    if len(retained) + len(incoming) > MAX_EVENTS:
        raise ValueError("calendar would exceed the 1024 event limit")

    used = {}
    for calendar in state.get("calendars", []):
        used[calendar.get("id", "")] = True
    for event in retained:
        used[event.get("id", "")] = True
    next_value = bounded_int(state.get("next_id"), 1, 1, 99999999)
    for event in incoming:
        while True:
            ident = "e" + str(next_value)
            next_value = 1 if next_value >= 99999999 else next_value + 1
            if ident not in used:
                used[ident] = True
                break
        event["id"] = ident
        event["calendar_id"] = calendar_id
        old = previous.get(event.get("uid", ""))
        if old:
            event["reminder"] = old.get("reminder", -1)
            event["reminded"] = old.get("reminded", [])[-16:]
        retained.append(event)
    state["events"] = retained
    state["next_id"] = next_value
    return len(incoming)


def find_event(state, event_id):
    for event in state["events"]:
        if event.get("id") == event_id:
            return event
    return None


def delete_event(state, event_id):
    before = len(state["events"])
    state["events"] = [event for event in state["events"] if event.get("id") != event_id]
    return len(state["events"]) != before


def skip_occurrence(event, date):
    date = valid_date(date, "")
    if not date or not event.get("repeat"):
        return False
    skipped = event.setdefault("skip_dates", [])
    if date not in skipped:
        skipped.append(date)
    if len(skipped) > 64:
        del skipped[:-64]
    return True


def repeat_label(rule):
    if not isinstance(rule, dict) or not rule:
        return "Does not repeat"
    kind = rule.get("kind")
    interval = bounded_int(rule.get("interval"), 1, 1, 99)
    suffix = "" if interval == 1 else " every " + str(interval)
    if kind == "weekdays":
        text = "Weekdays"
    elif kind == "weekly":
        names = []
        for day in rule.get("weekdays", []):
            if isinstance(day, int) and 0 <= day <= 6:
                names.append(WEEKDAYS[day])
        text = "Weekly" + suffix + ": " + ", ".join(names)
    elif kind == "monthly":
        if rule.get("monthly_mode") == "nth_weekday":
            words = {1: "first", 2: "second", 3: "third", 4: "fourth", -1: "last"}
            day = bounded_int(rule.get("weekday"), 0, 0, 6)
            text = "Monthly" + suffix + ": " + words.get(rule.get("ordinal"), "first") + " " + WEEKDAYS[day]
        else:
            text = "Monthly" + suffix + ": day " + str(rule.get("month_day", 1))
    elif kind == "yearly":
        text = "Yearly" + suffix
    elif kind == "daily":
        text = "Daily" + suffix
    else:
        return "Does not repeat"
    if rule.get("until"):
        text += " until " + rule["until"]
    return text


def recurrence_due(event, date):
    rule = event.get("repeat")
    if not isinstance(rule, dict) or not rule:
        return False
    date = valid_date(date, "")
    start = event.get("start_date", "")
    if not date or date < start or date in event.get("skip_dates", []):
        return False
    until = rule.get("until", "")
    if until and date > until:
        return False
    interval = bounded_int(rule.get("interval"), 1, 1, 99)
    kind = rule.get("kind")
    difference = date_to_ordinal(date) - date_to_ordinal(start)
    if kind == "daily":
        return difference % interval == 0
    weekday = weekday_for(date)
    if kind == "weekdays":
        if not 1 <= weekday <= 5:
            return False
        start_week = date_to_ordinal(start) - weekday_for(start)
        date_week = date_to_ordinal(date) - weekday
        return ((date_week - start_week) // 7) % interval == 0
    if kind == "weekly":
        if weekday not in rule.get("weekdays", [weekday_for(start)]):
            return False
        start_week = date_to_ordinal(start) - weekday_for(start)
        date_week = date_to_ordinal(date) - weekday
        return ((date_week - start_week) // 7) % interval == 0
    year, month, day = date_parts(date)
    start_year, start_month, start_day = date_parts(start)
    if kind == "monthly":
        month_difference = (year - start_year) * 12 + month - start_month
        if month_difference < 0 or month_difference % interval != 0:
            return False
        if rule.get("monthly_mode") == "nth_weekday":
            if weekday != bounded_int(rule.get("weekday"), weekday_for(start), 0, 6):
                return False
            ordinal = rule.get("ordinal", 1)
            if ordinal == -1:
                return day + 7 > days_in_month(year, month)
            return ((day - 1) // 7) + 1 == ordinal
        return day == bounded_int(rule.get("month_day"), start_day, 1, 31)
    if kind == "yearly":
        return month == start_month and day == start_day and (year - start_year) % interval == 0
    return False


def calendar_visible(state, calendar_id):
    for item in state["calendars"]:
        if item.get("id") == calendar_id:
            return item.get("visible", True)
    return False


def event_occurs_on(event, date):
    if event.get("repeat"):
        return recurrence_due(event, date)
    start = event.get("start_date", "")
    end = event.get("end_date", start)
    return bool(start and start <= date <= end)


def occurrence_sort_key(item):
    date, event = item
    return (date, 0 if event.get("all_day") else 1,
            event.get("start_time", ""), event.get("title", "").lower())


def occurrences_between(state, start, end, include_hidden=False, limit=512):
    start = valid_date(start, "2000-01-01")
    end = valid_date(end, start)
    if end < start:
        start, end = end, start
    result = []
    day = start
    while day <= end and len(result) < limit:
        for event in state["events"]:
            if not include_hidden and not calendar_visible(state, event.get("calendar_id", "")):
                continue
            if event_occurs_on(event, day):
                result.append((day, event))
                if len(result) >= limit:
                    break
        day = add_days(day, 1)
    result.sort(key=occurrence_sort_key)
    return result


def events_on(state, date, include_hidden=False):
    return occurrences_between(state, date, date, include_hidden)


def occurrence_counts(state, start, end, include_hidden=False):
    """Count a date range without allocating and sorting occurrence records."""
    start = valid_date(start, "2000-01-01")
    end = valid_date(end, start)
    if end < start:
        start, end = end, start
    visible = {}
    if not include_hidden:
        for calendar in state.get("calendars", []):
            if calendar.get("visible", True):
                visible[calendar.get("id", "")] = True
    counts = {}
    for event in state.get("events", []):
        if not include_hidden and event.get("calendar_id", "") not in visible:
            continue
        event_start = event.get("start_date", "")
        if not event_start or event_start > end:
            continue
        if event.get("repeat"):
            day = start if start > event_start else event_start
            while day <= end:
                if recurrence_due(event, day):
                    counts[day] = counts.get(day, 0) + 1
                day = add_days(day, 1)
        else:
            event_end = event.get("end_date", event_start)
            if event_end < start:
                continue
            day = start if start > event_start else event_start
            last = end if end < event_end else event_end
            while day <= last:
                counts[day] = counts.get(day, 0) + 1
                day = add_days(day, 1)
    return counts


def search_events(state, query, limit=128):
    query = clean_text(query, "", 80).lower()
    if not query:
        return []
    result = []
    for event in state["events"]:
        haystack = " ".join((event.get("title", ""), event.get("location", ""),
                             event.get("notes", ""))).lower()
        if query in haystack:
            result.append(event)
            if len(result) >= limit:
                break
    result.sort(key=lambda event: (event.get("start_date", ""), event.get("start_time", "")))
    return result


def reminder_stamp(event, occurrence_date):
    minutes = event.get("reminder", -1)
    if minutes not in (0, 5, 15, 30, 60, 1440):
        return ""
    start_time = event.get("start_time", "09:00") if not event.get("all_day") else "09:00"
    date, time = add_minutes(occurrence_date, start_time, -minutes)
    return date + "T" + time


def due_reminders(state, now, lookback_days=1):
    if now.get("clock_integrity") is False:
        return []
    today = date_key(now)
    current = timestamp(now)
    result = []
    # A reminder for an event shortly after midnight can become due on the
    # preceding day, so include tomorrow's occurrences without using epoch
    # arithmetic (which can overflow SolarOS's small-int MicroPython build).
    for occurrence_date, event in occurrences_between(
            state, add_days(today, -lookback_days), add_days(today, 1)):
        if not event.get("repeat") and occurrence_date != event.get("start_date"):
            continue
        if occurrence_date in event.get("reminded", []):
            continue
        reminder = reminder_stamp(event, occurrence_date)
        start_time = event.get("start_time", "09:00") if not event.get("all_day") else "09:00"
        start = occurrence_date + "T" + start_time
        if reminder and reminder <= current <= start:
            result.append((occurrence_date, event))
    return result


def mark_reminded(event, occurrence_date):
    values = event.setdefault("reminded", [])
    if occurrence_date not in values:
        values.append(occurrence_date)
    if len(values) > 16:
        del values[:-16]


def ics_escape(value):
    value = value.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
    return value.replace("\n", "\\n")


def ics_unescape(value):
    result = ""
    index = 0
    while index < len(value):
        if value[index:index + 2] in ("\\n", "\\N"):
            result += "\n"
            index += 2
        elif value[index:index + 2] in ("\\,", "\\;", "\\\\"):
            result += value[index + 1]
            index += 2
        else:
            result += value[index]
            index += 1
    return result


def ics_date(value):
    value = value.strip()
    if len(value) < 8:
        return "", ""
    try:
        date = make_date(int(value[:4]), int(value[4:6]), int(value[6:8]))
    except Exception:
        return "", ""
    if not valid_date(date, ""):
        return "", ""
    time = ""
    if len(value) >= 13 and value[8:9] == "T":
        try:
            time = pad2(int(value[9:11])) + ":" + pad2(int(value[11:13]))
        except Exception:
            time = ""
        time = valid_time(time, "")
    return date, time


def ics_datetime(date, time=""):
    year, month, day = date_parts(date)
    value = str(year) + pad2(month) + pad2(day)
    if time:
        value += "T" + time[:2] + time[3:5] + "00"
    return value


def repeat_to_rrule(rule):
    if not rule:
        return ""
    mapping = {"daily": "DAILY", "weekdays": "WEEKLY", "weekly": "WEEKLY",
               "monthly": "MONTHLY", "yearly": "YEARLY"}
    freq = mapping.get(rule.get("kind"))
    if not freq:
        return ""
    parts = ["FREQ=" + freq]
    interval = bounded_int(rule.get("interval"), 1, 1, 99)
    if interval != 1:
        parts.append("INTERVAL=" + str(interval))
    if rule.get("kind") == "weekdays":
        parts.append("BYDAY=MO,TU,WE,TH,FR")
    elif rule.get("kind") == "weekly":
        names = []
        for day in rule.get("weekdays", []):
            if isinstance(day, int) and 0 <= day <= 6:
                names.append(ICS_WEEKDAYS[day])
        if names:
            parts.append("BYDAY=" + ",".join(names))
    elif rule.get("kind") == "monthly":
        if rule.get("monthly_mode") == "nth_weekday":
            ordinal = rule.get("ordinal", 1)
            prefix = "-1" if ordinal == -1 else str(ordinal)
            day = bounded_int(rule.get("weekday"), 0, 0, 6)
            parts.append("BYDAY=" + prefix + ICS_WEEKDAYS[day])
        else:
            parts.append("BYMONTHDAY=" + str(rule.get("month_day", 1)))
    if rule.get("until"):
        parts.append("UNTIL=" + ics_datetime(rule["until"]))
    return ";".join(parts)


def parse_rrule(value, start_date):
    fields = {}
    for part in value.split(";"):
        if "=" in part:
            name, content = part.split("=", 1)
            fields[name.upper()] = content.upper()
    freq = fields.get("FREQ", "")
    kind = {"DAILY": "daily", "WEEKLY": "weekly", "MONTHLY": "monthly",
            "YEARLY": "yearly"}.get(freq)
    if not kind:
        return {}
    result = {"kind": kind, "interval": 1, "until": ""}
    try:
        result["interval"] = max(1, min(99, int(fields.get("INTERVAL", "1"))))
    except Exception:
        pass
    if fields.get("UNTIL"):
        result["until"] = ics_date(fields["UNTIL"])[0]
    byday = fields.get("BYDAY", "")
    if freq == "WEEKLY" and byday == "MO,TU,WE,TH,FR":
        result["kind"] = "weekdays"
    elif freq == "WEEKLY":
        selected = []
        for code in byday.split(","):
            code = code[-2:]
            if code in ICS_WEEKDAYS:
                selected.append(ICS_WEEKDAYS.index(code))
        result["weekdays"] = selected or [weekday_for(start_date)]
    elif freq == "MONTHLY":
        if byday:
            code = byday[-2:]
            prefix = byday[:-2]
            if code in ICS_WEEKDAYS:
                try:
                    ordinal = int(prefix) if prefix else 1
                except Exception:
                    ordinal = 1
                if ordinal not in (1, 2, 3, 4, -1):
                    ordinal = 1
                result["monthly_mode"] = "nth_weekday"
                result["ordinal"] = ordinal
                result["weekday"] = ICS_WEEKDAYS.index(code)
        if "monthly_mode" not in result:
            result["monthly_mode"] = "day"
            try:
                result["month_day"] = max(1, min(31, int(fields.get("BYMONTHDAY", date_parts(start_date)[2]))))
            except Exception:
                result["month_day"] = date_parts(start_date)[2]
    return normalize_repeat(result, start_date)


def folded_ics_lines(source):
    pending = None
    for physical in source:
        physical = physical.rstrip("\r\n")
        if physical.startswith((" ", "\t")) and pending is not None:
            pending += physical[1:]
        else:
            if pending is not None:
                yield pending
            pending = physical
    if pending is not None:
        yield pending


def import_ics(source, state, now, calendar_id=""):
    if not calendar_id:
        calendar_id = state["calendars"][0]["id"]
    known = {}
    for item in state["events"]:
        known[item.get("uid", "")] = True
    current = None
    added = 0
    skipped = 0
    for line in folded_ics_lines(source):
        upper = line.upper()
        if upper == "BEGIN:VEVENT":
            current = {"exdates": []}
            continue
        if upper == "END:VEVENT":
            if current is None:
                continue
            start_date = current.get("start_date", "")
            uid = clean_text(current.get("uid"), "", 160)
            if not start_date or (uid and uid in known) or len(state["events"]) >= MAX_EVENTS:
                skipped += 1
                current = None
                continue
            fields = {
                "calendar_id": calendar_id,
                "title": current.get("title", "Untitled event"),
                "start_date": start_date,
                "start_time": current.get("start_time", ""),
                "end_date": current.get("end_date", start_date),
                "end_time": current.get("end_time", ""),
                "all_day": not bool(current.get("start_time")),
                "location": current.get("location", ""),
                "notes": current.get("notes", ""),
                "reminder": -1,
                "repeat": parse_rrule(current.get("rrule", ""), start_date),
                "dtstamp": current.get("dtstamp", ""),
                "utc_now": now,
            }
            event = add_event(state, fields, now)
            if event is not None:
                if uid:
                    event["uid"] = uid
                    known[uid] = True
                event["skip_dates"] = current.get("exdates", [])[-64:]
                added += 1
            else:
                skipped += 1
            current = None
            continue
        if current is None or ":" not in line:
            continue
        raw_name, value = line.split(":", 1)
        name = raw_name.split(";", 1)[0].upper()
        if name == "UID":
            current["uid"] = value
        elif name == "DTSTAMP":
            current["dtstamp"] = valid_ics_stamp(value, "")
        elif name == "SUMMARY":
            current["title"] = ics_unescape(value)
        elif name == "LOCATION":
            current["location"] = ics_unescape(value)
        elif name == "DESCRIPTION":
            current["notes"] = ics_unescape(value)
        elif name == "DTSTART":
            current["start_date"], current["start_time"] = ics_date(value)
        elif name == "DTEND":
            date, time = ics_date(value)
            if "VALUE=DATE" in raw_name.upper() and date:
                date = add_days(date, -1)
            current["end_date"], current["end_time"] = date, time
        elif name == "RRULE":
            current["rrule"] = value
        elif name == "EXDATE":
            for item in value.split(","):
                date = ics_date(item)[0]
                if date and date not in current["exdates"]:
                    current["exdates"].append(date)
    return added, skipped


def fold_ics_line(line, width=70):
    if len(line) <= width:
        return [line]
    lines = [line[:width]]
    line = line[width:]
    while line:
        lines.append(" " + line[:width - 1])
        line = line[width - 1:]
    return lines


def iter_ics_lines(state):
    for line in ("BEGIN:VCALENDAR", "VERSION:2.0",
                 "PRODID:-//SolarOS//Calendar//EN", "CALSCALE:GREGORIAN"):
        yield line
    for event in state["events"]:
        lines = ["BEGIN:VEVENT",
                 "UID:" + ics_escape(event.get("uid", event.get("id", "") + "@solaros")),
                 "DTSTAMP:" + valid_ics_stamp(event.get("dtstamp"), "20000101T000000Z"),
                 "SUMMARY:" + ics_escape(event.get("title", "Untitled event"))]
        if event.get("all_day"):
            lines.append("DTSTART;VALUE=DATE:" + ics_datetime(event["start_date"]))
            lines.append("DTEND;VALUE=DATE:" + ics_datetime(add_days(event.get("end_date", event["start_date"]), 1)))
        else:
            lines.append("DTSTART:" + ics_datetime(event["start_date"], event.get("start_time", "09:00")))
            lines.append("DTEND:" + ics_datetime(event.get("end_date", event["start_date"]), event.get("end_time", event.get("start_time", "09:00"))))
        if event.get("location"):
            lines.append("LOCATION:" + ics_escape(event["location"]))
        if event.get("notes"):
            lines.append("DESCRIPTION:" + ics_escape(event["notes"]))
        rrule = repeat_to_rrule(event.get("repeat"))
        if rrule:
            lines.append("RRULE:" + rrule)
        if event.get("skip_dates"):
            exdates = []
            for day in event["skip_dates"]:
                exdates.append(ics_datetime(day))
            lines.append("EXDATE;VALUE=DATE:" + ",".join(exdates))
        lines.append("END:VEVENT")
        for line in lines:
            for folded in fold_ics_line(line):
                yield folded
    yield "END:VCALENDAR"


def write_ics(state, output):
    """Write incrementally so a large calendar is never duplicated in RAM."""
    for line in iter_ics_lines(state):
        output.write(line)
        output.write("\r\n")


def export_ics(state):
    return "\r\n".join(iter_ics_lines(state)) + "\r\n"
