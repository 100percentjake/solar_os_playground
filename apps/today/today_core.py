"""Small, dependency-free data helpers for the SolarOS Today dashboard."""


def clean(value, fallback="", limit=160):
    if not isinstance(value, str):
        value = fallback
    value = " ".join(value.replace("\r", " ").replace("\n", " ").split())
    return (value[:limit] or fallback)


def pad2(value):
    value = str(int(value))
    return "0" + value if len(value) < 2 else value


def date_key(now):
    try:
        return "{}-{}-{}".format(int(now.get("year", 2000)),
                                 pad2(now.get("month", 1)),
                                 pad2(now.get("day", 1)))
    except Exception:
        return "2000-01-01"


def days_in_month(year, month):
    if month == 2:
        return 29 if ((year % 4 == 0 and year % 100 != 0) or year % 400 == 0) else 28
    return 30 if month in (4, 6, 9, 11) else 31


def date_parts(value):
    try:
        return int(value[:4]), int(value[5:7]), int(value[8:10])
    except Exception:
        return 2000, 1, 1


def date_ordinal(value):
    year, month, day = date_parts(value)
    previous = year - 1
    total = previous * 365 + previous // 4 - previous // 100 + previous // 400
    for current in range(1, month):
        total += days_in_month(year, current)
    return total + day


def weekday(value):
    # SolarOS/C convention: Sunday is zero.
    return date_ordinal(value) % 7


def calendar_visible(state, calendar_id):
    for calendar in state.get("calendars", []):
        if isinstance(calendar, dict) and calendar.get("id") == calendar_id:
            return calendar.get("visible", True)
    return False


def recurring_event_due(event, today):
    rule = event.get("repeat")
    if not isinstance(rule, dict) or not rule:
        return False
    start = event.get("start_date", "")
    if not start or today < start or today in event.get("skip_dates", []):
        return False
    until = rule.get("until", "")
    if until and today > until:
        return False
    interval = rule.get("interval", 1)
    if not isinstance(interval, int) or isinstance(interval, bool) or interval < 1:
        interval = 1
    difference = date_ordinal(today) - date_ordinal(start)
    kind = rule.get("kind")
    day = weekday(today)
    if kind == "daily":
        return difference % interval == 0
    if kind == "weekdays":
        if day < 1 or day > 5:
            return False
        return ((date_ordinal(today) - day -
                 (date_ordinal(start) - weekday(start))) // 7) % interval == 0
    if kind == "weekly":
        if day not in rule.get("weekdays", [weekday(start)]):
            return False
        return ((date_ordinal(today) - day -
                 (date_ordinal(start) - weekday(start))) // 7) % interval == 0
    year, month, month_day = date_parts(today)
    sy, sm, start_day = date_parts(start)
    if kind == "monthly":
        months = (year - sy) * 12 + month - sm
        if months < 0 or months % interval:
            return False
        if rule.get("monthly_mode") == "nth_weekday":
            wanted = rule.get("weekday", weekday(start))
            if day != wanted:
                return False
            ordinal = rule.get("ordinal", 1)
            return (month_day + 7 > days_in_month(year, month)) if ordinal == -1 else (((month_day - 1) // 7) + 1 == ordinal)
        return month_day == rule.get("month_day", start_day)
    if kind == "yearly":
        return month == sm and month_day == start_day and (year - sy) % interval == 0
    return False


def today_events(state, today):
    result = []
    if not isinstance(state, dict):
        return result
    for event in state.get("events", []):
        if not isinstance(event, dict):
            continue
        if not calendar_visible(state, event.get("calendar_id", "")):
            continue
        if event.get("repeat"):
            due = recurring_event_due(event, today)
        else:
            start = event.get("start_date", "")
            due = bool(start and start <= today <= event.get("end_date", start))
        if due:
            result.append(event)
    result.sort(key=lambda item: (0 if item.get("all_day") else 1,
                                  item.get("start_time", ""),
                                  clean(item.get("title", "")).lower()))
    return result


def recurring_task_due(item, today):
    if item.get("active") is False or today < item.get("start", today):
        return False
    day = weekday(today)
    kind = item.get("kind", "daily")
    if kind == "weekdays":
        return 1 <= day <= 5
    if kind == "weekly":
        selected = item.get("weekdays")
        return day in selected if isinstance(selected, list) and selected else day == item.get("weekday", day)
    if kind == "monthly":
        year, month, month_day = date_parts(today)
        if item.get("monthly_mode") == "nth_weekday":
            if day != item.get("weekday", day):
                return False
            ordinal = item.get("ordinal", 1)
            return (month_day + 7 > days_in_month(year, month)) if ordinal == -1 else (((month_day - 1) // 7) + 1 == ordinal)
        return month_day == item.get("month_day", 1)
    return True


def today_tasks(state, today):
    """Return general tasks plus due recurrence rules not yet materialized."""
    result = []
    occurrences = {}
    if not isinstance(state, dict):
        return result
    for task in state.get("tasks", []):
        if not isinstance(task, dict) or task.get("skipped"):
            continue
        if task.get("occurrence") == today and task.get("recurrence_id"):
            occurrences[task["recurrence_id"]] = True
        if task.get("project_id", ""):
            continue
        completed = task.get("completed", "")
        if not completed or completed[:10] == today:
            result.append(task)
    for rule in state.get("recurrences", []):
        if (isinstance(rule, dict) and not rule.get("project_id", "") and
                rule.get("id") not in occurrences and recurring_task_due(rule, today)):
            result.append({"title": rule.get("title", "Recurring task"),
                           "completed": "", "virtual": True,
                           "recurrence_id": rule.get("id", "")})
    result.sort(key=lambda item: (1 if item.get("completed") else 0,
                                  item.get("created", ""),
                                  clean(item.get("title", "")).lower()))
    return result


def recent_notes(index, limit=20):
    if not isinstance(index, dict):
        return []
    by_path = {}
    for item in index.get("notes", []):
        if isinstance(item, dict) and isinstance(item.get("path"), str):
            by_path[item["path"].lower()] = item
    result = []
    for path in index.get("recent", []):
        if isinstance(path, str) and path.lower() in by_path:
            result.append(by_path[path.lower()])
            if len(result) >= limit:
                break
    return result


def unread_posts(cache, limit=50):
    posts = cache.get("posts", []) if isinstance(cache, dict) else []
    result = []
    for item in posts:
        if isinstance(item, dict) and not item.get("read"):
            result.append(item)
            if len(result) >= limit:
                break
    return result
