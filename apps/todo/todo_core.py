"""Data model and export helpers for the SolarOS Todo List app.

This module deliberately avoids CPython-only conveniences so the same logic can
be tested on a desktop and run in SolarOS's constrained MicroPython build.
"""


STATE_VERSION = 2
MAX_TITLE = 120
VALID_KINDS = ("daily", "weekdays", "weekly", "monthly")
VALID_DATE_FORMATS = ("mon_day", "ymd", "mdy", "dmy")


def clean_label(value, fallback="", limit=MAX_TITLE):
    if not isinstance(value, str):
        value = fallback
    value = " ".join(value.replace("\r", " ").replace("\n", " ").split())
    if len(value) > limit:
        value = value[:limit]
    return value or fallback


def valid_id(value, prefix):
    if not isinstance(value, str) or len(value) < 2 or len(value) > 10:
        return False
    if value[0] != prefix:
        return False
    for char in value[1:]:
        if char < "0" or char > "9":
            return False
    return True


def valid_date(value, fallback="2000-01-01"):
    if not isinstance(value, str) or len(value) < 10:
        return fallback
    sample = value[:10]
    if sample[4:5] != "-" or sample[7:8] != "-":
        return fallback
    for index, char in enumerate(sample):
        if index not in (4, 7) and (char < "0" or char > "9"):
            return fallback
    try:
        year = int(sample[:4])
        month = int(sample[5:7])
        day = int(sample[8:10])
        if year < 1 or month < 1 or month > 12:
            return fallback
        if day < 1 or day > days_in_month(year, month):
            return fallback
    except Exception:
        return fallback
    return sample


def valid_stamp(value, fallback="2000-01-01T00:00:00"):
    if not isinstance(value, str):
        return fallback
    date = valid_date(value, "")
    if not date:
        return fallback
    if len(value) >= 19 and value[10:11] == "T" and value[13:14] == ":" and value[16:17] == ":":
        return value[:19]
    return date + "T00:00:00"


def pad2(value):
    value = str(int(value))
    return "0" + value if len(value) < 2 else value


def date_key(now):
    return "{}-{}-{}".format(now.get("year", 2000), pad2(now.get("month", 1)),
                             pad2(now.get("day", 1)))


def timestamp(now):
    return "{}T{}:{}:{}".format(date_key(now), pad2(now.get("hour", 0)),
                                pad2(now.get("minute", 0)), pad2(now.get("second", 0)))


def default_state():
    return {
        "version": STATE_VERSION,
        "next_id": 1,
        "settings": {
            "show_completed": True,
            "show_added_dates": False,
            "show_completed_dates": True,
            "date_format": "mon_day",
            "sort": "created",
        },
        "projects": [],
        "tasks": [],
        "recurrences": [],
    }


def normalize_state(value):
    if not isinstance(value, dict):
        return default_state()
    base = default_state()
    settings = value.get("settings")
    if isinstance(settings, dict):
        for name in ("show_completed", "show_added_dates", "show_completed_dates"):
            if isinstance(settings.get(name), bool):
                base["settings"][name] = settings[name]
        if settings.get("date_format") in VALID_DATE_FORMATS:
            base["settings"]["date_format"] = settings["date_format"]
        if settings.get("sort") in ("created", "name"):
            base["settings"]["sort"] = settings["sort"]
    next_id = value.get("next_id", 1)
    # Keep the bound comfortably inside SolarOS MicroPython's tagged small-int
    # range. Merely compiling a larger literal can fail on constrained builds.
    if isinstance(next_id, int) and not isinstance(next_id, bool) and 0 < next_id < 100000000:
        base["next_id"] = next_id
    # Repair a stale counter without relying on IDs fitting a machine integer.
    greatest = 0
    raw_groups = []
    for name in ("projects", "tasks", "recurrences"):
        group = value.get(name)
        raw_groups.append(group if isinstance(group, list) else [])
    for group in raw_groups:
        for item in group:
            if not isinstance(item, dict):
                continue
            ident = item.get("id", "")
            if isinstance(ident, str) and 1 < len(ident) <= 10:
                digits = ident[1:]
                valid = True
                for char in digits:
                    if char < "0" or char > "9":
                        valid = False
                        break
                if valid:
                    try:
                        number = int(digits)
                        if number > greatest:
                            greatest = number
                    except Exception:
                        pass
    if base["next_id"] <= greatest:
        base["next_id"] = greatest + 1

    used = {}
    project_ids = {}
    for raw in raw_groups[0]:
        if not isinstance(raw, dict):
            continue
        ident = raw.get("id")
        if not valid_id(ident, "p") or ident in used:
            ident = new_id(base, "p")
        used[ident] = True
        project_ids[ident] = True
        base["projects"].append({
            "id": ident,
            "name": clean_label(raw.get("name"), "Untitled project"),
            "created": valid_stamp(raw.get("created")),
        })

    recurrence_ids = {}
    for raw in raw_groups[2]:
        if not isinstance(raw, dict):
            continue
        ident = raw.get("id")
        if not valid_id(ident, "r") or ident in used:
            ident = new_id(base, "r")
        used[ident] = True
        recurrence_ids[ident] = True
        project_id = raw.get("project_id", "")
        if project_id not in project_ids:
            project_id = ""
        kind = raw.get("kind", "daily")
        if kind not in VALID_KINDS:
            kind = "daily"
        weekday = raw.get("weekday", 0)
        if not isinstance(weekday, int) or isinstance(weekday, bool) or not 0 <= weekday <= 6:
            weekday = 0
        month_day = raw.get("month_day", 1)
        if not isinstance(month_day, int) or isinstance(month_day, bool):
            month_day = 1
        month_day = max(1, min(31, month_day))
        ordinal = raw.get("ordinal", 1)
        if ordinal not in (1, 2, 3, 4, -1):
            ordinal = 1
        selected = []
        if isinstance(raw.get("weekdays"), list):
            for day in raw["weekdays"]:
                if (isinstance(day, int) and not isinstance(day, bool) and
                        0 <= day <= 6 and day not in selected):
                    selected.append(day)
        selected.sort()
        item = {
            "id": ident,
            "title": clean_label(raw.get("title"), "Recurring task"),
            "project_id": project_id,
            "kind": kind,
            "active": raw.get("active") if isinstance(raw.get("active"), bool) else True,
            "created": valid_stamp(raw.get("created")),
            "start": valid_date(raw.get("start")),
            "weekday": weekday,
            "month_day": month_day,
        }
        if selected:
            item["weekdays"] = selected
        if raw.get("monthly_mode") == "nth_weekday":
            item["monthly_mode"] = "nth_weekday"
            item["ordinal"] = ordinal
        else:
            item["monthly_mode"] = "day"
        base["recurrences"].append(item)

    for raw in raw_groups[1]:
        if not isinstance(raw, dict):
            continue
        ident = raw.get("id")
        if not valid_id(ident, "t") or ident in used:
            ident = new_id(base, "t")
        used[ident] = True
        project_id = raw.get("project_id", "")
        if project_id not in project_ids:
            project_id = ""
        recurrence_id = raw.get("recurrence_id", "")
        if recurrence_id not in recurrence_ids:
            recurrence_id = ""
        item = {
            "id": ident,
            "title": clean_label(raw.get("title"), "Untitled task"),
            "project_id": project_id,
            "created": valid_stamp(raw.get("created")),
            "completed": valid_stamp(raw.get("completed"), "") if raw.get("completed") else "",
        }
        if recurrence_id:
            item["recurrence_id"] = recurrence_id
            item["occurrence"] = valid_date(raw.get("occurrence"), item["created"][:10])
            if raw.get("skipped") is True:
                item["skipped"] = True
        base["tasks"].append(item)
    return base


def new_id(state, prefix):
    ident = prefix + str(state["next_id"])
    state["next_id"] += 1
    return ident


def add_project(state, name, now):
    project = {"id": new_id(state, "p"), "name": clean_label(name, "Untitled project"),
               "created": timestamp(now)}
    state["projects"].append(project)
    return project


def add_task(state, title, now, project_id="", recurrence_id="", occurrence=""):
    task = {
        "id": new_id(state, "t"),
        "title": clean_label(title, "Untitled task"),
        "project_id": project_id or "",
        "created": timestamp(now),
        "completed": "",
    }
    if recurrence_id:
        task["recurrence_id"] = recurrence_id
        task["occurrence"] = occurrence
    state["tasks"].append(task)
    return task


def add_recurrence(state, title, kind, now, project_id="", rule=None):
    recurrence = {
        "id": new_id(state, "r"),
        "title": clean_label(title, "Recurring task"),
        "project_id": project_id or "",
        "kind": kind,
        "active": True,
        "created": timestamp(now),
        "start": date_key(now),
        "weekday": int(now.get("weekday", 0)),
        "month_day": int(now.get("day", 1)),
    }
    if isinstance(rule, dict):
        for name in ("weekdays", "monthly_mode", "month_day", "ordinal", "weekday"):
            if name in rule:
                recurrence[name] = rule[name]
    state["recurrences"].append(recurrence)
    return recurrence


def recurrence_due(item, now):
    if not item.get("active", True):
        return False
    today = date_key(now)
    if today < item.get("start", today):
        return False
    kind = item.get("kind", "daily")
    weekday = int(now.get("weekday", 0))
    if kind == "weekdays":
        # SolarOS exposes C's tm_wday: Sunday=0 through Saturday=6.
        return 1 <= weekday <= 5
    if kind == "weekly":
        selected = item.get("weekdays")
        if isinstance(selected, list) and selected:
            return weekday in selected
        # Compatibility with Todo List 1.0's single-day weekly records.
        return weekday == int(item.get("weekday", weekday))
    if kind == "monthly":
        day = int(now.get("day", 1))
        if item.get("monthly_mode", "day") == "nth_weekday":
            if weekday != int(item.get("weekday", weekday)):
                return False
            ordinal = int(item.get("ordinal", 1))
            if ordinal == -1:
                return day + 7 > days_in_month(int(now.get("year", 2000)),
                                               int(now.get("month", 1)))
            return ((day - 1) // 7) + 1 == ordinal
        return day == int(item.get("month_day", 1))
    return True


def materialize_recurrences(state, now):
    """Create today's due instances, never a backlog of missed occurrences."""
    if now.get("clock_integrity") is False:
        return 0
    today = date_key(now)
    existing = {}
    for task in state["tasks"]:
        if task.get("occurrence") == today and task.get("recurrence_id"):
            existing[task["recurrence_id"]] = True
    count = 0
    for item in state["recurrences"]:
        ident = item.get("id", "")
        if recurrence_due(item, now) and ident not in existing:
            add_task(state, item.get("title", "Recurring task"), now,
                     item.get("project_id", ""), item.get("id", ""), today)
            existing[ident] = True
            count += 1
    return count


def find_task(state, task_id):
    for task in state["tasks"]:
        if task.get("id") == task_id:
            return task
    return None


def toggle_task(state, task_id, now):
    task = find_task(state, task_id)
    if task is None:
        return False
    task["completed"] = "" if task.get("completed") else timestamp(now)
    return True


def delete_task(state, task_id):
    task = find_task(state, task_id)
    if task is None:
        return False
    if task.get("recurrence_id") and task.get("occurrence"):
        # A removed generated occurrence must remain as a tiny tombstone until
        # the date changes, or materialization would immediately recreate it.
        task["skipped"] = True
        task["completed"] = ""
        return True
    state["tasks"] = [item for item in state["tasks"] if item.get("id") != task_id]
    return True


def prune_skipped(state, today):
    before = len(state["tasks"])
    state["tasks"] = [item for item in state["tasks"]
                      if not (item.get("skipped") and item.get("occurrence") != today)]
    return before - len(state["tasks"])


def delete_project(state, project_id):
    state["tasks"] = [item for item in state["tasks"]
                      if item.get("project_id", "") != project_id]
    state["recurrences"] = [item for item in state["recurrences"]
                            if item.get("project_id", "") != project_id]
    before = len(state["projects"])
    state["projects"] = [item for item in state["projects"]
                         if item.get("id") != project_id]
    return len(state["projects"]) != before


def clear_completed(state, project_id):
    before = len(state["tasks"])
    state["tasks"] = [item for item in state["tasks"]
                      if not (item.get("project_id", "") == project_id and
                              bool(item.get("completed")))]
    return before - len(state["tasks"])


def _sort_open(items, mode):
    if mode == "name":
        items.sort(key=lambda item: item.get("title", "").lower())
    else:
        items.sort(key=lambda item: item.get("created", ""))


def tasks_for(state, project_id, today_only_completed=False):
    open_items = []
    completed = []
    today = None
    if isinstance(today_only_completed, str):
        today = today_only_completed
    for task in state["tasks"]:
        if task.get("skipped"):
            continue
        if task.get("project_id", "") != project_id:
            continue
        done = task.get("completed", "")
        if done:
            if state["settings"].get("show_completed", True):
                if today is None or done[:10] == today:
                    completed.append(task)
        else:
            open_items.append(task)
    _sort_open(open_items, state["settings"].get("sort", "created"))
    completed.sort(key=lambda item: item.get("completed", ""), reverse=True)
    return open_items + completed


MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
WEEKDAYS = ("Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat")


def days_in_month(year, month):
    if month == 2:
        leap = (year % 4 == 0 and year % 100 != 0) or year % 400 == 0
        return 29 if leap else 28
    if month in (4, 6, 9, 11):
        return 30
    return 31


def format_date(value, style):
    if not isinstance(value, str) or len(value) < 10:
        return ""
    parts = value[:10].split("-")
    if len(parts) != 3:
        return ""
    year, month, day = parts
    if style == "ymd":
        return year + "-" + month + "-" + day
    if style == "dmy":
        return day + "/" + month + "/" + year
    if style == "mdy":
        return month + "/" + day + "/" + year
    try:
        return MONTHS[int(month) - 1] + " " + str(int(day))
    except Exception:
        return value[:10]


def recurrence_label(item):
    kind = item.get("kind", "daily")
    if kind == "weekdays":
        return "Weekdays"
    if kind == "weekly":
        selected = item.get("weekdays")
        if not isinstance(selected, list) or not selected:
            selected = [int(item.get("weekday", 0))]
        names = []
        for day in selected:
            if isinstance(day, int) and 0 <= day <= 6:
                names.append(WEEKDAYS[day])
        return "Weekly: " + ", ".join(names)
    if kind == "monthly":
        if item.get("monthly_mode", "day") == "nth_weekday":
            ordinal = int(item.get("ordinal", 1))
            words = {1: "first", 2: "second", 3: "third", 4: "fourth", -1: "last"}
            weekday = int(item.get("weekday", 0))
            name = WEEKDAYS[weekday] if 0 <= weekday <= 6 else "day"
            return "Monthly: {} {}".format(words.get(ordinal, "first"), name)
        return "Monthly: day " + str(int(item.get("month_day", 1)))
    return "Daily"


def export_text(state, markdown=False):
    lines = ["# Todo List" if markdown else "TODO LIST", ""]
    groups = [("General", "")]
    for project in state["projects"]:
        groups.append((project.get("name", "Project"), project.get("id", "")))
    for name, project_id in groups:
        safe_name = markdown_escape(name) if markdown else clean_label(name, "Project")
        lines.append("## " + safe_name if markdown else safe_name.upper())
        items = [item for item in state["tasks"]
                 if item.get("project_id", "") == project_id and not item.get("skipped")]
        items.sort(key=lambda item: (bool(item.get("completed")), item.get("created", "")))
        if not items:
            lines.append("(No tasks)")
        for item in items:
            mark = "x" if item.get("completed") else " "
            prefix = "- [{}] ".format(mark) if markdown else "[{}] ".format(mark)
            title = clean_label(item.get("title"), "Untitled task")
            line = prefix + (markdown_escape(title) if markdown else title)
            if item.get("completed"):
                line += " (completed {})".format(item["completed"][:10])
            lines.append(line)
        lines.append("")
    if state["recurrences"]:
        lines.append("## Recurring" if markdown else "RECURRING")
        for item in state["recurrences"]:
            status = "active" if item.get("active", True) else "paused"
            prefix = "- " if markdown else ""
            title = clean_label(item.get("title"), "Recurring task")
            if markdown:
                title = markdown_escape(title)
            lines.append(prefix + "{} ({}, {})".format(title,
                         recurrence_label(item), status))
        lines.append("")
    return "\n".join(lines)


def markdown_escape(value):
    value = clean_label(value)
    result = ""
    for char in value:
        if char in "\\`*_{}[]<>#":
            result += "\\"
        result += char
    return result
