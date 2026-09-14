"""Graphical launcher configuration editor for SolarOS."""

import gc
import json
import sys

import solaros
from solaros import gfx

from launcher_builder_core import (MAX_COLUMNS, MAX_ROWS, MAX_ITEMS, MAX_NAME,
                                   MAX_COMMAND, clean_text, default_config, display_name,
                                   first_empty, item_at, merge_commands,
                                   move_item, normalize_config, parse_aliases,
                                   resize_grid, suggested_icon, valid_command)
from launcher_icons import ICON_NAMES, POPULAR_ICONS


KEY_ENTER = 13
KEY_LF = 10
KEY_BACKSPACE = 8
KEY_DELETE = 127
HEADER_H = 43
FOOTER_H = 25
LOAD_NOTICE = ""


def command_file_argument():
    index = 1
    while index < len(sys.argv):
        if sys.argv[index] == "--file" and index + 1 < len(sys.argv):
            return sys.argv[index + 1]
        index += 1
    return "/launcher.json"


CONFIG_PATH = command_file_argument()
TEMP_PATH = CONFIG_PATH + ".tmp"
BACKUP_PATH = CONFIG_PATH + ".bak"


def clip(value, count):
    value = value if isinstance(value, str) else ""
    if len(value) <= count:
        return value
    if count < 2:
        return value[:count]
    return value[:count - 1] + "~"


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


def draw_footer(width, height, value):
    y = height - FOOTER_H
    gfx.color(gfx.BLACK)
    gfx.fill_rect(0, y, width, FOOTER_H)
    gfx.color(gfx.WHITE)
    gfx.font(gfx.FONT_MONO_12)
    gfx.text(7, y + 17, clip(value, max(1, (width - 14) // 6)))


def wrap_text(value, columns, limit=20):
    lines = []
    for paragraph in (value if isinstance(value, str) else "").replace("\r", "").split("\n"):
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
                lines.append(line)
                line = word
            else:
                line = trial
        if line:
            lines.append(line)
        if len(lines) >= limit:
            break
    return lines[:limit]


def draw_message(width, height, title, value, footer="Press any key"):
    gfx.clear(gfx.WHITE)
    draw_header(width, title)
    gfx.color(gfx.BLACK)
    gfx.font(gfx.FONT_MONO_14)
    columns = max(10, (width - 24) // 7)
    y = HEADER_H + 27
    visible = max(1, (height - HEADER_H - FOOTER_H - 8) // 20)
    for line in wrap_text(value, columns, visible):
        gfx.text(12, y, line)
        y += 20
    draw_footer(width, height, footer)
    gfx.refresh()


def message(width, height, title, value):
    draw_message(width, height, title, value)
    wait_key()


def confirm(width, height, title, value):
    draw_message(width, height, title, value, "Y confirm   any other key cancels")
    return wait_key() in (ord("y"), ord("Y"))


def edit_text(width, height, title, label, initial="", limit=120):
    value = clean_text(initial, "", limit)
    while not solaros.should_exit():
        gfx.clear(gfx.WHITE)
        draw_header(width, title, clip(label, 30) + "  {}/{}".format(len(value), limit))
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
        footer = "Maximum length reached" if len(value) >= limit else "Enter accept   Esc cancel   Backspace delete"
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
    selected = selected if 0 <= selected < len(options) else 0
    while not solaros.should_exit():
        gfx.clear(gfx.WHITE)
        draw_header(width, title, "{}/{}".format(selected + 1, len(options)))
        visible = max(1, (height - HEADER_H - FOOTER_H) // 31)
        start = (selected // visible) * visible
        row = 0
        while row < visible and start + row < len(options):
            index = start + row
            y = HEADER_H + row * 31
            if index == selected:
                gfx.color(gfx.BLACK)
                gfx.fill_rect(4, y + 2, width - 8, 28)
                gfx.color(gfx.WHITE)
            else:
                gfx.color(gfx.BLACK)
            gfx.font(gfx.FONT_MONO_14)
            gfx.text(11, y + 21, clip(options[index], max(4, (width - 22) // 7)))
            row += 1
        draw_footer(width, height, footer)
        gfx.refresh()
        key = wait_key()
        if key in (gfx.KEY_ESCAPE, ord("q"), ord("Q")):
            return None
        if key in (gfx.KEY_UP, ord("k")):
            selected = (selected - 1) % len(options)
        elif key in (gfx.KEY_DOWN, ord("j")):
            selected = (selected + 1) % len(options)
        elif key in (KEY_ENTER, KEY_LF, gfx.KEY_RIGHT):
            return selected
    return None


def read_aliases(path, source_name):
    try:
        with open(path, "r") as source:
            return parse_aliases(source, source_name)
    except OSError:
        return []


def native_commands():
    result = []
    try:
        entries = solaros.apps.list()
    except Exception:
        entries = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        command = valid_command(entry.get("name"))
        if not command:
            continue
        result.append({"name": display_name(command),
                       "command": command,
                       "detail": clean_text(entry.get("summary"), "", 100),
                       "source": "Built in"})
    return result


def command_catalogs():
    native = native_commands()
    user = read_aliases("/.shell/alias", "User alias")
    playground = read_aliases("/.shell/playground", "Playground")
    return native, user, playground, merge_commands(native, user, playground)


def load_config():
    global LOAD_NOTICE
    damaged = False
    for path in (CONFIG_PATH, TEMP_PATH, BACKUP_PATH):
        try:
            with open(path, "r") as source:
                value = json.load(source)
            config = normalize_config(value, ICON_NAMES)
            if path != CONFIG_PATH:
                try:
                    solaros.storage.remove(CONFIG_PATH)
                except OSError:
                    pass
                try:
                    solaros.storage.rename(path, CONFIG_PATH)
                    LOAD_NOTICE = "Recovered launcher settings from an interrupted save."
                except OSError:
                    pass
            return config
        except OSError:
            continue
        except Exception:
            damaged = True
    if damaged:
        LOAD_NOTICE = "The existing launcher file was invalid. It was not overwritten; the default layout is open in memory."
    else:
        LOAD_NOTICE = "No launcher file was found. The native default layout is open in memory."
    return default_config()


def save_config(config):
    clean = normalize_config(config, ICON_NAMES)
    with open(TEMP_PATH, "w") as output:
        json.dump(clean, output)
        output.flush()
    try:
        solaros.storage.remove(BACKUP_PATH)
    except OSError:
        pass
    had_primary = True
    try:
        solaros.storage.rename(CONFIG_PATH, BACKUP_PATH)
    except OSError:
        had_primary = False
    try:
        solaros.storage.rename(TEMP_PATH, CONFIG_PATH)
    except Exception:
        if had_primary:
            try:
                solaros.storage.rename(BACKUP_PATH, CONFIG_PATH)
            except OSError:
                pass
        raise
    if had_primary:
        try:
            solaros.storage.remove(BACKUP_PATH)
        except OSError:
            pass
    gc.collect()


def choose_number(width, height, title, value, low, high):
    current = value
    while not solaros.should_exit():
        gfx.clear(gfx.WHITE)
        draw_header(width, title)
        gfx.color(gfx.BLACK)
        gfx.font(gfx.FONT_BOLD_16)
        text = str(current)
        gfx.text((width - len(text) * 8) // 2, height // 2, text)
        draw_footer(width, height, "Left/Right change   Enter accept   Esc cancel")
        gfx.refresh()
        key = wait_key()
        if key == gfx.KEY_ESCAPE:
            return None
        if key in (KEY_ENTER, KEY_LF):
            return current
        if key in (gfx.KEY_LEFT, gfx.KEY_DOWN, ord("-")):
            current = high if current <= low else current - 1
        elif key in (gfx.KEY_RIGHT, gfx.KEY_UP, ord("+")):
            current = low if current >= high else current + 1
    return None


def grid_size_flow(width, height, config):
    columns = choose_number(width, height, "Grid columns", config["layout"]["columns"], 1, MAX_COLUMNS)
    if columns is None:
        return False
    rows = choose_number(width, height, "Grid rows", config["layout"]["rows"], 1, MAX_ROWS)
    if rows is None:
        return False
    if columns == config["layout"]["columns"] and rows == config["layout"]["rows"]:
        return False
    count = len(config["items"])
    if columns * rows < count:
        message(width, height, "Grid too small", "A {}x{} grid has {} cells, but this launcher has {} items. Remove items first or choose a larger grid.".format(columns, rows, columns * rows, count))
        return False
    if not confirm(width, height, "Resize grid", "Change to {} columns by {} rows? Existing items will be packed from left to right, retaining their current order.".format(columns, rows)):
        return False
    return resize_grid(config, columns, rows)


def icon_size_for_cell(cell_width, cell_height, labels=True):
    available_h = cell_height - (18 if labels else 4)
    limit = min(cell_width - 6, available_h - 4)
    for size in (64, 48, 32, 16, 8):
        if size <= limit:
            return size
    return 8


def draw_safe_icon(x, y, name, size):
    try:
        gfx.icon(x, y, name, size)
    except Exception:
        gfx.icon(x, y, "question-mark", size)


def draw_grid(width, height, config, column, row, footer, fullscreen=False):
    gfx.clear(gfx.WHITE)
    top = 0 if fullscreen else HEADER_H
    bottom = height if fullscreen else height - FOOTER_H
    columns = config["layout"]["columns"]
    rows = config["layout"]["rows"]
    selected_item = item_at(config, column, row)
    if not fullscreen:
        subtitle = "{}x{}  {} item{}".format(columns, rows, len(config["items"]), "" if len(config["items"]) == 1 else "s")
        if selected_item is not None:
            subtitle += "  " + selected_item["name"]
        else:
            subtitle += "  Empty cell"
        draw_header(width, "Launcher Builder", subtitle)
    cell_width = max(1, width // columns)
    cell_height = max(1, (bottom - top) // rows)
    show_labels = cell_width >= 55 and cell_height >= 38
    size = icon_size_for_cell(cell_width, cell_height, show_labels)
    for grid_row in range(rows):
        y0 = top + grid_row * (bottom - top) // rows
        y1 = top + (grid_row + 1) * (bottom - top) // rows
        for grid_column in range(columns):
            x0 = grid_column * width // columns
            x1 = (grid_column + 1) * width // columns
            selected = grid_column == column and grid_row == row and not fullscreen
            if selected:
                gfx.color(gfx.BLACK)
                gfx.fill_rect(x0 + 1, y0 + 1, max(1, x1 - x0 - 2), max(1, y1 - y0 - 2))
                foreground = gfx.WHITE
            else:
                foreground = gfx.BLACK
            gfx.color(gfx.DARK if not selected else gfx.WHITE)
            gfx.rect(x0, y0, max(1, x1 - x0), max(1, y1 - y0))
            item = item_at(config, grid_column, grid_row)
            if item is not None:
                gfx.color(foreground)
                label_h = 17 if show_labels else 0
                icon_x = x0 + max(0, (x1 - x0 - size) // 2)
                icon_y = y0 + max(1, (y1 - y0 - label_h - size) // 2)
                draw_safe_icon(icon_x, icon_y, item["icon"], size)
                if show_labels:
                    gfx.font(gfx.FONT_MONO_12)
                    chars = max(1, (x1 - x0 - 6) // 6)
                    label = clip(item["name"], chars)
                    gfx.text(x0 + max(3, (x1 - x0 - len(label) * 6) // 2), y1 - 5, label)
            elif selected:
                gfx.color(gfx.WHITE)
                gfx.font(gfx.FONT_BOLD_16)
                gfx.text(x0 + max(2, (x1 - x0 - 8) // 2), y0 + max(16, (y1 - y0) // 2 + 5), "+")
    if not fullscreen:
        draw_footer(width, height, footer)
    gfx.refresh()


def icon_grid(width, height, names, selected, title):
    columns = 5 if width >= 350 else 4
    rows = 3
    page_size = columns * rows
    start = (selected // page_size) * page_size
    gfx.clear(gfx.WHITE)
    draw_header(width, title, "{}-{} of {}".format(start + 1, min(start + page_size, len(names)), len(names)))
    body_h = height - HEADER_H - FOOTER_H
    for offset in range(page_size):
        index = start + offset
        if index >= len(names):
            break
        column = offset % columns
        row = offset // columns
        x0 = column * width // columns
        x1 = (column + 1) * width // columns
        y0 = HEADER_H + row * body_h // rows
        y1 = HEADER_H + (row + 1) * body_h // rows
        active = index == selected
        if active:
            gfx.color(gfx.BLACK)
            gfx.fill_rect(x0 + 2, y0 + 2, x1 - x0 - 4, y1 - y0 - 4)
            foreground = gfx.WHITE
        else:
            foreground = gfx.BLACK
        gfx.color(foreground)
        draw_safe_icon(x0 + (x1 - x0 - 32) // 2, y0 + 5, names[index], 32)
        gfx.font(gfx.FONT_MONO_12)
        label = clip(names[index], max(2, (x1 - x0 - 4) // 6))
        gfx.text(x0 + max(2, (x1 - x0 - len(label) * 6) // 2), y1 - 7, label)
    draw_footer(width, height, "Arrows choose  / search  A all/popular  Enter")
    gfx.refresh()
    return columns, page_size


def icon_picker(width, height, initial="folder"):
    all_icons = False
    query = ""
    names = list(POPULAR_ICONS)
    if initial not in names:
        names.insert(0, initial)
    selected = names.index(initial) if initial in names else 0
    while not solaros.should_exit():
        title = "All icons" if all_icons else "Popular icons"
        if query:
            title = "Icons: " + query
        columns, page_size = icon_grid(width, height, names, selected, title)
        key = wait_key()
        if key == gfx.KEY_ESCAPE:
            return None
        if key in (KEY_ENTER, KEY_LF):
            return names[selected]
        if key in (gfx.KEY_LEFT, ord("h")):
            selected = (selected - 1) % len(names)
        elif key in (gfx.KEY_RIGHT, ord("l")):
            selected = (selected + 1) % len(names)
        elif key in (gfx.KEY_UP, ord("k")):
            selected = (selected - columns) % len(names)
        elif key in (gfx.KEY_DOWN, ord("j")):
            selected = (selected + columns) % len(names)
        elif key == getattr(gfx, "KEY_PAGE_UP", -1001):
            selected = max(0, selected - page_size)
        elif key == getattr(gfx, "KEY_PAGE_DOWN", -1002):
            selected = min(len(names) - 1, selected + page_size)
        elif key in (ord("a"), ord("A")):
            all_icons = not all_icons
            query = ""
            names = list(ICON_NAMES if all_icons else POPULAR_ICONS)
            selected = names.index(initial) if initial in names else 0
        elif key == ord("/"):
            value = edit_text(width, height, "Search icons", "Part of icon name", query, 40)
            if value is not None:
                query = value.lower()
                names = [name for name in ICON_NAMES if query in name]
                if not names:
                    message(width, height, "No icons", "No native icon name contains '" + query + "'.")
                    names = list(ICON_NAMES if all_icons else POPULAR_ICONS)
                    query = ""
                selected = 0
    return None


def pick_command(width, height):
    native, user, playground, all_commands = command_catalogs()
    source_names = ["All available apps", "Built-in apps", "Playground apps", "User aliases", "Manual command"]
    source_lists = [all_commands, native, playground, user]
    source = choose(width, height, "Choose app source", source_names)
    if source is None:
        return None
    if source == 4:
        entered = edit_text(width, height, "Manual command", "Shell command or script path", "", MAX_COMMAND)
        if entered is None:
            return None
        command = valid_command(entered)
        if not command:
            message(width, height, "Invalid command", "Enter a non-empty command. Comments beginning with # cannot be launcher commands.")
            return None
        first = command.split(" ", 1)[0].split("/")[-1]
        if first.endswith(".py"):
            first = first[:-3]
        return {"name": display_name(first) or "App",
                "command": command, "detail": "Manual", "source": "Manual"}
    entries = source_lists[source]
    if not entries:
        message(width, height, "No apps found", "There are no entries in that source. Playground installs are read from /.shell/playground and user aliases from /.shell/alias.")
        return None
    labels = []
    for entry in entries:
        labels.append(entry["name"] + "  [" + entry.get("source", "") + "]")
    selected = choose(width, height, source_names[source], labels)
    return entries[selected] if selected is not None else None


def add_item_flow(width, height, config, column, row):
    if len(config["items"]) >= MAX_ITEMS:
        message(width, height, "Item limit", "SolarOS supports at most 32 launcher items. Empty cells are still allowed in larger grids.")
        return False
    source = pick_command(width, height)
    if source is None:
        return False
    title = edit_text(width, height, "Item title", "Text shown under the icon", source["name"], MAX_NAME)
    if not title:
        return False
    inferred = suggested_icon(source["command"], title)
    icon = icon_picker(width, height, inferred)
    if icon is None:
        return False
    config["items"].append({"name": title, "icon": icon,
                            "command": source["command"],
                            "column": column, "row": row})
    return True


def edit_item_flow(width, height, config, item):
    action = choose(width, height, item["name"],
                    ["Edit title", "Change command", "Change icon", "Move or swap", "Delete item"])
    if action is None:
        return False
    if action == 0:
        title = edit_text(width, height, "Item title", "Text shown under the icon", item["name"], MAX_NAME)
        if not title or title == item["name"]:
            return False
        item["name"] = title
        return True
    if action == 1:
        source = pick_command(width, height)
        if source is None or source["command"] == item["command"]:
            return False
        item["command"] = source["command"]
        return True
    if action == 2:
        icon = icon_picker(width, height, item["icon"])
        if icon is None or icon == item["icon"]:
            return False
        item["icon"] = icon
        return True
    if action == 3:
        return move_flow(width, height, config, item)
    if len(config["items"]) <= 1:
        message(width, height, "Cannot delete", "The native launcher requires at least one item.")
        return False
    if confirm(width, height, "Delete item", "Remove '" + item["name"] + "' from the launcher?"):
        config["items"].remove(item)
        return True
    return False


def move_flow(width, height, config, item):
    column = item["column"]
    row = item["row"]
    columns = config["layout"]["columns"]
    rows = config["layout"]["rows"]
    while not solaros.should_exit():
        target = item_at(config, column, row)
        wording = "Enter move" if target is None or target is item else "Enter swap with " + target["name"]
        draw_grid(width, height, config, column, row, wording + "   Esc cancel")
        key = wait_key()
        if key == gfx.KEY_ESCAPE:
            return False
        if key in (KEY_ENTER, KEY_LF):
            if column == item["column"] and row == item["row"]:
                return False
            return move_item(config, item, column, row)
        if key in (gfx.KEY_LEFT, ord("h")):
            column = (column - 1) % columns
        elif key in (gfx.KEY_RIGHT, ord("l")):
            column = (column + 1) % columns
        elif key in (gfx.KEY_UP, ord("k")):
            row = (row - 1) % rows
        elif key in (gfx.KEY_DOWN, ord("j")):
            row = (row + 1) % rows
    return False


def preview(width, height, config):
    draw_grid(width, height, config, 0, 0, "", True)
    wait_key()


def save_with_message(width, height, config):
    try:
        save_config(config)
        message(width, height, "Launcher saved", "Saved to " + CONFIG_PATH + ". The next time Launcher opens, it will use this layout.")
        return True
    except Exception as error:
        message(width, height, "Could not save", "The edited layout remains in memory. " + str(error))
        return False


def editor(width, height, config):
    column = 0
    row = 0
    dirty = False
    while not solaros.should_exit():
        footer = "Enter add/edit  G grid  P preview  S save  Esc"
        draw_grid(width, height, config, column, row, footer)
        key = wait_key()
        columns = config["layout"]["columns"]
        rows = config["layout"]["rows"]
        if key in (gfx.KEY_LEFT, ord("h")):
            column = (column - 1) % columns
        elif key in (gfx.KEY_RIGHT, ord("l")):
            column = (column + 1) % columns
        elif key in (gfx.KEY_UP, ord("k")):
            row = (row - 1) % rows
        elif key in (gfx.KEY_DOWN, ord("j")):
            row = (row + 1) % rows
        elif key in (KEY_ENTER, KEY_LF):
            item = item_at(config, column, row)
            if item is None:
                dirty = add_item_flow(width, height, config, column, row) or dirty
            else:
                dirty = edit_item_flow(width, height, config, item) or dirty
        elif key in (ord("g"), ord("G")):
            if grid_size_flow(width, height, config):
                dirty = True
                column = min(column, config["layout"]["columns"] - 1)
                row = min(row, config["layout"]["rows"] - 1)
        elif key in (ord("p"), ord("P")):
            preview(width, height, config)
        elif key in (ord("s"), ord("S")):
            if save_with_message(width, height, config):
                dirty = False
        elif key == gfx.KEY_ESCAPE or key in (ord("q"), ord("Q")):
            if not dirty:
                return
            choice = choose(width, height, "Unsaved changes", ["Save and exit", "Discard and exit", "Keep editing"])
            if choice == 0:
                if save_with_message(width, height, config):
                    return
            elif choice == 1:
                return
        gc.collect()


def main():
    config = load_config()
    gfx.begin()
    try:
        width, height = gfx.size()
        if LOAD_NOTICE:
            message(width, height, "Launcher configuration", LOAD_NOTICE)
        editor(width, height, config)
    finally:
        gfx.end()


if __name__ == "__main__":
    main()
