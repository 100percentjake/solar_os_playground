"""Keyboard-first graphical Todo List for SolarOS."""

import gc
import json
import sys

import solaros
from solaros import gfx

from todo_core import (add_project, add_recurrence, add_task, clear_completed,
                       date_key, default_state, delete_project, delete_task,
                       export_text, format_date, materialize_recurrences,
                       normalize_state, prune_skipped, recurrence_label,
                       toggle_task)


def app_directory():
    path = sys.argv[0] if sys.argv else "todo.py"
    if not path or "/" not in path:
        try:
            path = __file__
        except NameError:
            path = "todo.py"
    separator = path.rfind("/")
    if separator < 0:
        return "."
    return path[:separator] if separator > 0 else "/"


APP_DIR = app_directory()
STATE_PATH = APP_DIR + "/todo.json"
BACKUP_PATH = STATE_PATH + ".bak"
EXPORT_DIR = "/Downloads"
KEY_ENTER = 13
KEY_LF = 10
KEY_BACKSPACE = 8
KEY_DELETE = 127
ROW_H = 42
HEADER_H = 43
FOOTER_H = 25
LOAD_NOTICE = ""


def clean_text(value):
    if not isinstance(value, str):
        return ""
    return " ".join(value.replace("\r", " ").replace("\n", " ").split())


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


def load_state():
    global LOAD_NOTICE
    found_but_invalid = False
    # A complete temporary file is newer than the backup when an interrupted
    # save left no primary file. Prefer the primary whenever it is readable.
    for path in (STATE_PATH, STATE_PATH + ".tmp", BACKUP_PATH):
        try:
            with open(path, "r") as source:
                raw = json.load(source)
            if not isinstance(raw, dict):
                found_but_invalid = True
                continue
            state = normalize_state(raw)
            if path != STATE_PATH:
                try:
                    solaros.storage.remove(STATE_PATH)
                except OSError:
                    pass
                try:
                    solaros.storage.rename(path, STATE_PATH)
                except OSError:
                    pass
                LOAD_NOTICE = "Recovered task data from an interrupted save."
            return state
        except OSError:
            continue
        except Exception:
            found_but_invalid = True
    if found_but_invalid:
        LOAD_NOTICE = "Task data could not be read and no usable backup was found. A new empty list was opened; the damaged files were left in place."
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


def draw_message(width, height, title, message, footer="Press any key"):
    gfx.clear(gfx.WHITE)
    draw_header(width, title)
    gfx.color(gfx.BLACK)
    gfx.font(gfx.FONT_MONO_14)
    words = clean_text(message).split()
    lines = []
    line = ""
    columns = max(10, (width - 24) // 7)
    for word in words:
        if len(word) > columns:
            if line:
                lines.append(line)
                line = ""
            while len(word) > columns:
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
    y = HEADER_H + 29
    for line in lines[:10]:
        gfx.text(12, y, clip(line, columns))
        y += 20
    draw_footer(width, height, footer)
    gfx.refresh()


def message(width, height, title, text):
    draw_message(width, height, title, text)
    wait_key()


def persist(width, height, state):
    try:
        save_state(state)
        return True
    except Exception as error:
        message(width, height, "Could not save",
                "The change is only in memory and will be lost when the app closes. " + str(error))
        return False


def confirm(width, height, title, text):
    draw_message(width, height, title, text, "Y confirm   any other key cancels")
    return wait_key() in (ord("y"), ord("Y"))


def edit_text(width, height, title, label, initial="", limit=120):
    value = clean_text(initial)[:limit]
    while not solaros.should_exit():
        gfx.clear(gfx.WHITE)
        count = "{}/{}".format(len(value), limit)
        draw_header(width, title, clip(label, 32) + "  " + count)
        gfx.color(gfx.BLACK)
        gfx.font(gfx.FONT_MONO_16)
        columns = max(8, (width - 24) // 8)
        shown = value + "_"
        lines = []
        while shown:
            lines.append(shown[:columns])
            shown = shown[columns:]
        y = HEADER_H + 34
        for line in lines[-8:]:
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
        visible = max(1, (height - HEADER_H - FOOTER_H) // 31)
        start = (selected // visible) * visible
        for row, option in enumerate(options[start:start + visible]):
            index = start + row
            y = HEADER_H + row * 31
            if index == selected:
                gfx.color(gfx.BLACK)
                gfx.fill_rect(4, y + 2, width - 8, 28)
                gfx.color(gfx.WHITE)
            else:
                gfx.color(gfx.BLACK)
            gfx.font(gfx.FONT_MONO_14)
            gfx.text(11, y + 21, clip(option, max(4, (width - 22) // 7)))
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


def task_metadata(task, settings):
    style = settings.get("date_format", "mon_day")
    parts = []
    if task.get("completed") and settings.get("show_completed_dates", True):
        parts.append("done " + format_date(task["completed"], style))
    elif settings.get("show_added_dates", False):
        parts.append("added " + format_date(task.get("created", ""), style))
    if task.get("recurrence_id"):
        parts.append("recurring")
    return "  ".join(parts)


def draw_task_row(width, y, task, selected, settings):
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
    done = bool(task.get("completed"))
    gfx.color(foreground)
    gfx.rect(10, y + 10, 13, 13)
    if done:
        gfx.line(12, y + 16, 16, y + 21)
        gfx.line(16, y + 21, 22, y + 11)
    title = clip(task.get("title", "Untitled"), max(5, (width - 43) // 7))
    gfx.font(gfx.FONT_BOLD_14 if not done else gfx.FONT_MONO_14)
    gfx.text(32, y + 20, title)
    if done:
        gfx.line(31, y + 15, min(width - 10, 32 + len(title) * 7), y + 15)
    meta = task_metadata(task, settings)
    if meta:
        gfx.font(gfx.FONT_MONO_12)
        gfx.text(32, y + 36, clip(meta, max(5, (width - 43) // 6)))


def draw_task_list(width, height, title, subtitle, tasks, selected, settings, footer):
    gfx.clear(gfx.WHITE)
    draw_header(width, title, subtitle)
    visible = max(1, (height - HEADER_H - FOOTER_H) // ROW_H)
    if tasks:
        start = (selected // visible) * visible
        for row, task in enumerate(tasks[start:start + visible]):
            draw_task_row(width, HEADER_H + row * ROW_H, task,
                          start + row == selected, settings)
        page = "{}/{}".format(selected + 1, len(tasks))
        gfx.color(gfx.BLACK)
        gfx.font(gfx.FONT_MONO_12)
        gfx.text(width - 7 - len(page) * 6, 19, page)
    else:
        gfx.color(gfx.DARK)
        gfx.font(gfx.FONT_MONO_16)
        gfx.text(14, HEADER_H + 40, "Nothing here yet.")
        gfx.font(gfx.FONT_MONO_12)
        gfx.text(14, HEADER_H + 61, "Press A to add a task.")
    draw_footer(width, height, footer)
    gfx.refresh()


def filtered_tasks(state, project_id, today=None):
    open_items = []
    completed = []
    for task in state["tasks"]:
        if task.get("skipped"):
            continue
        if task.get("project_id", "") != project_id:
            continue
        if task.get("completed"):
            if state["settings"].get("show_completed", True):
                if today is None or task.get("completed", "")[:10] == today:
                    completed.append(task)
        else:
            open_items.append(task)
    mode = state["settings"].get("sort", "created")
    if mode == "name":
        open_items.sort(key=lambda item: item.get("title", "").lower())
    else:
        open_items.sort(key=lambda item: item.get("created", ""))
    completed.sort(key=lambda item: item.get("completed", ""), reverse=True)
    return open_items + completed


WEEKDAY_NAMES = ("Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday")


def recurrence_kind(width, height, current=None):
    values = ["Daily", "Weekdays (Mon-Fri)", "Weekly (choose days)",
              "Monthly (custom rule)"]
    kinds = ("daily", "weekdays", "weekly", "monthly")
    selected = 0
    if current in kinds:
        selected = kinds.index(current)
    index = choose(width, height, "Repeat", values, selected)
    if index is None:
        return None
    return kinds[index]


def weekly_rule_screen(width, height, initial):
    selected_days = []
    if isinstance(initial, list):
        for value in initial:
            if isinstance(value, int) and 0 <= value <= 6 and value not in selected_days:
                selected_days.append(value)
    cursor = 0
    while not solaros.should_exit():
        gfx.clear(gfx.WHITE)
        draw_header(width, "Weekly schedule", "Space toggles days; S saves")
        row_h = 31
        for row, name in enumerate(WEEKDAY_NAMES):
            y = HEADER_H + row * row_h
            if row == cursor:
                gfx.color(gfx.BLACK)
                gfx.fill_rect(4, y + 2, width - 8, row_h - 3)
                gfx.color(gfx.WHITE)
            else:
                gfx.color(gfx.BLACK)
            mark = "[x] " if row in selected_days else "[ ] "
            gfx.font(gfx.FONT_MONO_14)
            gfx.text(12, y + 21, mark + name)
        draw_footer(width, height, "Space toggle   S save   Esc cancel")
        gfx.refresh()
        key = wait_key()
        if key == gfx.KEY_ESCAPE:
            return None
        if key in (gfx.KEY_UP, ord("k")):
            cursor = (cursor - 1) % 7
        elif key in (gfx.KEY_DOWN, ord("j")):
            cursor = (cursor + 1) % 7
        elif key in (ord(" "), KEY_ENTER, KEY_LF):
            if cursor in selected_days:
                selected_days.remove(cursor)
            else:
                selected_days.append(cursor)
                selected_days.sort()
        elif key in (ord("s"), ord("S")):
            if selected_days:
                return {"weekdays": selected_days}
            message(width, height, "Weekly schedule", "Select at least one day.")
    return None


def number_picker(width, height, title, label, value, low, high):
    value = max(low, min(high, int(value)))
    while not solaros.should_exit():
        gfx.clear(gfx.WHITE)
        draw_header(width, title, label)
        gfx.color(gfx.BLACK)
        gfx.font(gfx.FONT_BOLD_20)
        shown = str(value)
        gfx.text((width - len(shown) * 10) // 2, HEADER_H + 75, shown)
        gfx.font(gfx.FONT_MONO_14)
        gfx.text(20, HEADER_H + 115, "Left/Down decreases")
        gfx.text(20, HEADER_H + 138, "Right/Up increases")
        draw_footer(width, height, "Enter save   Esc cancel")
        gfx.refresh()
        key = wait_key()
        if key == gfx.KEY_ESCAPE:
            return None
        if key in (gfx.KEY_LEFT, gfx.KEY_DOWN, ord("j")):
            value = high if value <= low else value - 1
        elif key in (gfx.KEY_RIGHT, gfx.KEY_UP, ord("k")):
            value = low if value >= high else value + 1
        elif key in (KEY_ENTER, KEY_LF):
            return value
    return None


def monthly_rule_screen(width, height, initial, now):
    mode = initial.get("monthly_mode", "day") if isinstance(initial, dict) else "day"
    selected = 1 if mode == "nth_weekday" else 0
    choice_index = choose(width, height, "Monthly schedule",
                          ["A numbered day of the month", "The Nth weekday of the month"],
                          selected)
    if choice_index is None:
        return None
    if choice_index == 0:
        current = initial.get("month_day", now.get("day", 1)) if isinstance(initial, dict) else now.get("day", 1)
        day = number_picker(width, height, "Monthly schedule", "Day of the month", current, 1, 31)
        if day is None:
            return None
        return {"monthly_mode": "day", "month_day": day}
    ordinals = ["First", "Second", "Third", "Fourth", "Last"]
    ordinal_values = (1, 2, 3, 4, -1)
    old_ordinal = initial.get("ordinal", 1) if isinstance(initial, dict) else 1
    old_index = 0
    if old_ordinal in ordinal_values:
        old_index = ordinal_values.index(old_ordinal)
    ordinal_index = choose(width, height, "Monthly schedule", ordinals, old_index)
    if ordinal_index is None:
        return None
    old_weekday = initial.get("weekday", now.get("weekday", 0)) if isinstance(initial, dict) else now.get("weekday", 0)
    weekday = choose(width, height, "Monthly schedule", list(WEEKDAY_NAMES), int(old_weekday))
    if weekday is None:
        return None
    return {"monthly_mode": "nth_weekday", "ordinal": ordinal_values[ordinal_index],
            "weekday": weekday}


def build_recurrence_rule(width, height, kind, current, now):
    if kind == "weekly":
        selected = current.get("weekdays") if isinstance(current, dict) else None
        if not selected and isinstance(current, dict) and "weekday" in current:
            selected = [int(current.get("weekday", 0))]
        if not selected:
            selected = [int(now.get("weekday", 0))]
        return weekly_rule_screen(width, height, selected)
    if kind == "monthly":
        return monthly_rule_screen(width, height, current or {}, now)
    return {}


def apply_recurrence_rule(item, kind, rule, now):
    item["kind"] = kind
    for name in ("weekdays", "monthly_mode", "month_day", "ordinal"):
        if name in item:
            del item[name]
    # Weekday is also the compatibility/default value for weekly and monthly.
    item["weekday"] = int(now.get("weekday", 0))
    if isinstance(rule, dict):
        for name in rule:
            item[name] = rule[name]


def create_task_flow(width, height, state, project_id, recurring=False):
    if recurring and len(state["recurrences"]) >= 128:
        message(width, height, "Recurring task limit",
                "This device already has 128 recurrence rules. Remove an old rule first.")
        return False
    title = edit_text(width, height, "New task", "What needs doing?")
    if not title:
        return False
    now = now_value()
    if recurring:
        if now.get("clock_integrity") is False:
            message(width, height, "Clock not set",
                    "Set or synchronize the SolarOS clock before creating a recurrence rule.")
            return False
        kind = recurrence_kind(width, height)
        if kind is None:
            return False
        rule = build_recurrence_rule(width, height, kind, None, now)
        if rule is None:
            return False
        add_recurrence(state, title, kind, now, project_id, rule)
        materialize_recurrences(state, now)
    else:
        add_task(state, title, now, project_id)
    return persist(width, height, state)


def task_list_screen(width, height, state, project=None):
    project_id = project.get("id", "") if project else ""
    selected = 0
    checked_date = ""
    while not solaros.should_exit():
        now = now_value()
        today = date_key(now)
        if today != checked_date:
            changed = prune_skipped(state, today) > 0
            if materialize_recurrences(state, now):
                changed = True
            if changed:
                persist(width, height, state)
            checked_date = today
        tasks = filtered_tasks(state, project_id, None if project else today)
        if selected >= len(tasks):
            selected = max(0, len(tasks) - 1)
        title = project.get("name", "Project") if project else "Today"
        open_count = 0
        for item in tasks:
            if not item.get("completed"):
                open_count += 1
        if now.get("clock_integrity") is False:
            date_text = "Clock not set"
        else:
            date_text = format_date(today, state["settings"].get("date_format", "mon_day"))
        subtitle = "{}  |  {} open  |  sort: {}".format(
            date_text, open_count, state["settings"].get("sort", "created"))
        if project:
            footer = "Enter done  A add  R repeat  E edit  X delete"
        else:
            footer = "Enter done  A add  R repeat  P projects  S settings"
        draw_task_list(width, height, title, subtitle, tasks, selected,
                       state["settings"], footer)
        key = wait_key()
        if key == gfx.KEY_ESCAPE or key in (ord("q"), ord("Q"), gfx.KEY_LEFT):
            return
        if key in (gfx.KEY_UP, ord("k")) and tasks:
            selected = (selected - 1) % len(tasks)
        elif key in (gfx.KEY_DOWN, ord("j")) and tasks:
            selected = (selected + 1) % len(tasks)
        elif key in (KEY_ENTER, KEY_LF, ord(" ")) and tasks:
            toggle_task(state, tasks[selected]["id"], now_value())
            persist(width, height, state)
        elif key in (ord("a"), ord("A")):
            create_task_flow(width, height, state, project_id, False)
        elif key in (ord("r"), ord("R")):
            create_task_flow(width, height, state, project_id, True)
        elif key in (ord("e"), ord("E")) and tasks:
            value = edit_text(width, height, "Edit task", "Task title",
                              tasks[selected].get("title", ""))
            if value:
                tasks[selected]["title"] = value
                persist(width, height, state)
        elif key in (ord("x"), ord("X"), KEY_DELETE) and tasks:
            selected_task = tasks[selected]
            recurring_occurrence = bool(selected_task.get("recurrence_id"))
            prompt_title = "Skip occurrence" if recurring_occurrence else "Delete task"
            prompt = ("Remove this occurrence only? The recurrence rule will remain."
                      if recurring_occurrence else selected_task.get("title", ""))
            if confirm(width, height, prompt_title, prompt):
                delete_task(state, tasks[selected]["id"])
                persist(width, height, state)
        elif not project and key in (ord("p"), ord("P")):
            projects_screen(width, height, state)
        elif not project and key in (ord("s"), ord("S")):
            settings_screen(width, height, state)
        elif key in (ord("o"), ord("O")):
            state["settings"]["sort"] = ("name" if state["settings"].get("sort") == "created"
                                            else "created")
            persist(width, height, state)


def draw_projects(width, height, state, selected):
    gfx.clear(gfx.WHITE)
    draw_header(width, "Projects", "Separate lists for bigger efforts")
    projects = state["projects"]
    row_h = 39
    visible = max(1, (height - HEADER_H - FOOTER_H) // row_h)
    start = (selected // visible) * visible if projects else 0
    open_counts = {}
    for task in state["tasks"]:
        if not task.get("completed") and not task.get("skipped"):
            ident = task.get("project_id", "")
            if ident:
                open_counts[ident] = open_counts.get(ident, 0) + 1
    for row, project in enumerate(projects[start:start + visible]):
        index = start + row
        y = HEADER_H + row * row_h
        if index == selected:
            gfx.color(gfx.BLACK)
            gfx.fill_rect(4, y + 2, width - 8, row_h - 3)
            gfx.color(gfx.WHITE)
        else:
            gfx.color(gfx.BLACK)
        open_count = open_counts.get(project.get("id"), 0)
        gfx.font(gfx.FONT_BOLD_14)
        gfx.text(12, y + 18, clip(project.get("name", "Project"), max(6, (width - 90) // 7)))
        count = str(open_count) + " open"
        gfx.font(gfx.FONT_MONO_12)
        gfx.text(width - 12 - len(count) * 6, y + 18, count)
    if not projects:
        gfx.color(gfx.DARK)
        gfx.font(gfx.FONT_MONO_16)
        gfx.text(14, HEADER_H + 40, "No projects yet.")
    draw_footer(width, height, "A add  Enter open  X delete  Esc back")
    gfx.refresh()


def projects_screen(width, height, state):
    selected = 0
    while not solaros.should_exit():
        projects = state["projects"]
        if selected >= len(projects):
            selected = max(0, len(projects) - 1)
        draw_projects(width, height, state, selected)
        key = wait_key()
        if key in (gfx.KEY_ESCAPE, gfx.KEY_LEFT, ord("q"), ord("Q")):
            return
        if key in (gfx.KEY_UP, ord("k")) and projects:
            selected = (selected - 1) % len(projects)
        elif key in (gfx.KEY_DOWN, ord("j")) and projects:
            selected = (selected + 1) % len(projects)
        elif key in (KEY_ENTER, KEY_LF, gfx.KEY_RIGHT) and projects:
            task_list_screen(width, height, state, projects[selected])
        elif key in (ord("a"), ord("A")):
            if len(projects) >= 64:
                message(width, height, "Project limit",
                        "This device already has 64 projects. Remove one before adding another.")
                continue
            name = edit_text(width, height, "New project", "Project name")
            if name:
                add_project(state, name, now_value())
                persist(width, height, state)
                selected = len(state["projects"]) - 1
        elif key in (ord("x"), ord("X"), KEY_DELETE) and projects:
            project = projects[selected]
            if confirm(width, height, "Delete project",
                       "Delete the project and all of its tasks? " + project.get("name", "")):
                delete_project(state, project.get("id"))
                persist(width, height, state)


def recurrences_screen(width, height, state):
    selected = 0
    while not solaros.should_exit():
        items = state["recurrences"]
        labels = []
        for item in items:
            mark = "ON " if item.get("active", True) else "OFF"
            labels.append("{}  {}  {}".format(mark, recurrence_label(item),
                                               item.get("title", "")))
        if selected >= len(labels):
            selected = max(0, len(labels) - 1)
        if not labels:
            message(width, height, "Recurring tasks", "No recurring tasks yet. Add one from a task list with R.")
            return
        chosen = choose(width, height, "Recurring tasks", labels, selected,
                        "Enter actions   Esc back")
        if chosen is None:
            return
        selected = chosen
        item = items[selected]
        action = choose(width, height, item.get("title", "Recurring task"),
                        ["Pause" if item.get("active", True) else "Resume",
                         "Edit title", "Edit schedule", "Delete template"])
        if action == 0:
            item["active"] = not item.get("active", True)
            if item["active"]:
                materialize_recurrences(state, now_value())
            persist(width, height, state)
        elif action == 1:
            title = edit_text(width, height, "Edit recurrence", "Task title",
                              item.get("title", ""))
            if title:
                item["title"] = title
                persist(width, height, state)
        elif action == 2:
            now = now_value()
            if now.get("clock_integrity") is False:
                message(width, height, "Clock not set",
                        "Set or synchronize the SolarOS clock before editing a recurrence rule.")
                continue
            kind = recurrence_kind(width, height, item.get("kind", "daily"))
            if kind is not None:
                rule = build_recurrence_rule(width, height, kind, item, now)
                if rule is not None:
                    apply_recurrence_rule(item, kind, rule, now)
                    materialize_recurrences(state, now)
                    persist(width, height, state)
        elif action == 3 and confirm(width, height, "Delete recurrence",
                                     "Existing task history will remain."):
            ident = item.get("id")
            state["recurrences"] = [value for value in items if value.get("id") != ident]
            persist(width, height, state)


def write_export(state, markdown):
    ensure_directory(EXPORT_DIR)
    now = now_value()
    today = date_key(now) if now.get("clock_integrity") is not False else "undated"
    extension = ".md" if markdown else ".txt"
    path = EXPORT_DIR + "/todo-list-" + today + extension
    temporary = path + ".tmp"
    with open(temporary, "w") as output:
        output.write(export_text(state, markdown))
        output.flush()
    backup = path + ".bak"
    try:
        solaros.storage.remove(backup)
    except OSError:
        pass
    had_primary = True
    try:
        solaros.storage.rename(path, backup)
    except OSError:
        had_primary = False
    try:
        solaros.storage.rename(temporary, path)
    except Exception:
        if had_primary:
            try:
                solaros.storage.rename(backup, path)
            except OSError:
                pass
        raise
    if had_primary:
        try:
            solaros.storage.remove(backup)
        except OSError:
            pass
    return path


def date_style_name(value):
    return {"mon_day": "Sep 11", "ymd": "2026-09-11", "mdy": "09/11/2026",
            "dmy": "11/09/2026"}.get(value, "Sep 11")


def settings_screen(width, height, state):
    selected = 0
    while not solaros.should_exit():
        settings = state["settings"]
        options = [
            "Completed tasks: " + ("shown" if settings.get("show_completed", True) else "hidden"),
            "Added dates: " + ("shown" if settings.get("show_added_dates", False) else "hidden"),
            "Completed dates: " + ("shown" if settings.get("show_completed_dates", True) else "hidden"),
            "Date format: " + date_style_name(settings.get("date_format", "mon_day")),
            "Open-task sort: " + settings.get("sort", "created"),
            "Manage recurring tasks",
            "Clear completed general tasks",
            "Clear completed in a project",
            "Export as plain text",
            "Export as Markdown",
        ]
        chosen = choose(width, height, "Settings", options, selected)
        if chosen is None:
            return
        selected = chosen
        changed = False
        if chosen == 0:
            settings["show_completed"] = not settings.get("show_completed", True)
            changed = True
        elif chosen == 1:
            settings["show_added_dates"] = not settings.get("show_added_dates", False)
            changed = True
        elif chosen == 2:
            settings["show_completed_dates"] = not settings.get("show_completed_dates", True)
            changed = True
        elif chosen == 3:
            values = ["Sep 11", "2026-09-11", "09/11/2026", "11/09/2026"]
            index = choose(width, height, "Date format", values)
            if index is not None:
                settings["date_format"] = ("mon_day", "ymd", "mdy", "dmy")[index]
                changed = True
        elif chosen == 4:
            settings["sort"] = "name" if settings.get("sort") == "created" else "created"
            changed = True
        elif chosen == 5:
            recurrences_screen(width, height, state)
        elif chosen == 6:
            if confirm(width, height, "Clear completed", "Remove completed tasks from the general list?"):
                removed = clear_completed(state, "")
                if persist(width, height, state):
                    message(width, height, "Clear completed", "Removed {} task(s).".format(removed))
        elif chosen == 7:
            projects = state["projects"]
            if not projects:
                message(width, height, "Clear completed", "There are no projects.")
                continue
            index = choose(width, height, "Choose project",
                           [item.get("name", "Project") for item in projects])
            if index is not None:
                project = projects[index]
                if confirm(width, height, "Clear completed", project.get("name", "Project")):
                    removed = clear_completed(state, project.get("id", ""))
                    if persist(width, height, state):
                        message(width, height, "Clear completed", "Removed {} task(s).".format(removed))
        elif chosen in (8, 9):
            try:
                path = write_export(state, chosen == 9)
                message(width, height, "Export complete", "Saved to " + path)
            except Exception as error:
                message(width, height, "Export failed", str(error))
        if changed:
            persist(width, height, state)


def main():
    state = load_state()
    gfx.begin()
    try:
        width, height = gfx.size()
        if LOAD_NOTICE:
            message(width, height, "Storage recovery", LOAD_NOTICE)
        while not solaros.should_exit():
            task_list_screen(width, height, state, None)
            if solaros.should_exit():
                break
            # Escape from Today is the app's exit. Navigation into Projects and
            # Settings happens from within the Today loop.
            break
    finally:
        gfx.end()


if __name__ == "__main__":
    main()
