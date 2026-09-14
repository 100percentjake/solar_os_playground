"""Portable model and validation helpers for Launcher Builder."""


MAX_COLUMNS = 8
MAX_ROWS = 8
MAX_ITEMS = 32
MAX_NAME = 47
MAX_COMMAND = 191


def bounded_int(value, fallback, low, high):
    if not isinstance(value, int) or isinstance(value, bool):
        return fallback
    return max(low, min(high, value))


def clean_text(value, fallback="", limit=MAX_NAME):
    if not isinstance(value, str):
        value = fallback
    value = " ".join(value.replace("\r", " ").replace("\n", " ").split())
    cleaned = ""
    for char in value:
        if 32 <= ord(char) < 127:
            cleaned += char
    value = cleaned
    return (value[:limit] or fallback)[:limit]


def display_name(value):
    """Make an ASCII command name readable without relying on str.title()."""
    words = clean_text(value, "", MAX_NAME).replace("-", " ").replace("_", " ").split()
    result = []
    for word in words:
        result.append(word[:1].upper() + word[1:])
    return " ".join(result)


def valid_command(value):
    value = clean_text(value, "", MAX_COMMAND)
    return value if value and not value.startswith("#") else ""


def default_config():
    return {
        "layout": {"columns": 3, "rows": 2},
        "items": [
            {"name": "Files", "icon": "folder", "command": "files", "column": 0, "row": 0},
            {"name": "Manual", "icon": "book", "command": "help", "column": 1, "row": 0},
            {"name": "Wi-Fi", "icon": "wifi", "command": "wifi", "column": 2, "row": 0},
            {"name": "Clock", "icon": "clock", "command": "clock", "column": 0, "row": 1},
            {"name": "Calculator", "icon": "calculator", "command": "calc", "column": 1, "row": 1},
            {"name": "Writer", "icon": "pencil", "command": "writer", "column": 2, "row": 1},
        ],
    }


def normalize_config(value, icon_names):
    if not isinstance(value, dict):
        raise ValueError("configuration must be a JSON object")
    layout = value.get("layout")
    items = value.get("items")
    if not isinstance(layout, dict) or not isinstance(items, list):
        raise ValueError("configuration needs layout and items")
    columns = bounded_int(layout.get("columns"), 0, 1, MAX_COLUMNS)
    rows = bounded_int(layout.get("rows"), 0, 1, MAX_ROWS)
    if not columns or not rows:
        raise ValueError("grid must be between 1x1 and 8x8")
    if not items or len(items) > MAX_ITEMS:
        raise ValueError("launcher needs 1 to 32 items")
    icons = {}
    for name in icon_names:
        icons[name] = True
    occupied = {}
    result = []
    for raw in items:
        if not isinstance(raw, dict):
            raise ValueError("every launcher item must be an object")
        name = clean_text(raw.get("name"), "", MAX_NAME)
        command = valid_command(raw.get("command"))
        icon = raw.get("icon") if isinstance(raw.get("icon"), str) else ""
        column = bounded_int(raw.get("column"), -1, 0, columns - 1)
        row = bounded_int(raw.get("row"), -1, 0, rows - 1)
        if not name or not command or icon not in icons or column < 0 or row < 0:
            raise ValueError("launcher item contains an invalid field")
        key = str(column) + ":" + str(row)
        if key in occupied:
            raise ValueError("two launcher items occupy the same cell")
        occupied[key] = True
        result.append({"name": name, "icon": icon, "command": command,
                       "column": column, "row": row})
    return {"layout": {"columns": columns, "rows": rows}, "items": result}


def item_at(config, column, row):
    for item in config.get("items", []):
        if item.get("column") == column and item.get("row") == row:
            return item
    return None


def first_empty(config):
    columns = config["layout"]["columns"]
    rows = config["layout"]["rows"]
    for row in range(rows):
        for column in range(columns):
            if item_at(config, column, row) is None:
                return column, row
    return None


def resize_grid(config, columns, rows):
    columns = bounded_int(columns, 0, 1, MAX_COLUMNS)
    rows = bounded_int(rows, 0, 1, MAX_ROWS)
    if not columns or not rows:
        return False
    if columns * rows < len(config.get("items", [])):
        return False
    # Repack in the order the user currently sees, rather than the original
    # JSON array order (which may differ after moving and swapping items).
    items = list(config.get("items", []))
    items.sort(key=lambda item: (item.get("row", 0), item.get("column", 0)))
    config["items"] = items
    config["layout"] = {"columns": columns, "rows": rows}
    for index, item in enumerate(items):
        item["column"] = index % columns
        item["row"] = index // columns
    return True


def move_item(config, item, column, row):
    columns = config["layout"]["columns"]
    rows = config["layout"]["rows"]
    if not 0 <= column < columns or not 0 <= row < rows or item not in config["items"]:
        return False
    other = item_at(config, column, row)
    old_column = item["column"]
    old_row = item["row"]
    item["column"] = column
    item["row"] = row
    if other is not None and other is not item:
        other["column"] = old_column
        other["row"] = old_row
    return True


def parse_aliases(source, source_name):
    result = []
    seen = {}
    for raw in source:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 1)
        if len(parts) != 2:
            continue
        name = clean_text(parts[0], "", 32)
        expansion = valid_command(parts[1])
        if not name or not expansion or name in seen:
            continue
        seen[name] = True
        result.append({"name": display_name(name),
                       "command": name, "detail": expansion,
                       "source": source_name})
    return result


def merge_commands(native, user_aliases, playground_aliases):
    result = []
    seen = {}
    for item in native + user_aliases + playground_aliases:
        command = valid_command(item.get("command"))
        key = command.split(" ", 1)[0] if command else ""
        if not key or key in seen:
            continue
        seen[key] = True
        result.append(item)
    return result


def suggested_icon(command, name=""):
    text = (command + " " + name).lower()
    rules = (
        (("calendar",), "calendar"), (("todo", "task"), "task"),
        (("rss", "feed"), "rss"), (("wiki", "web", "browser"), "globe"),
        (("blue", "chat", "message"), "chat"), (("opds", "reader", "book"), "book"),
        (("copy", "ftp", "file"), "folder"), (("music", "audio", "radio"), "musical-note"),
        (("photo", "image", "camera"), "image"), (("mail", "email", "inbox"), "envelope-closed"),
        (("setting", "config"), "cog"), (("terminal", "shell", "ssh", "telnet"), "terminal"),
        (("note", "write", "edit"), "pencil"), (("calc",), "calculator"),
        (("clock", "time"), "clock"), (("weather",), "cloudy"),
        (("wifi", "network"), "wifi"), (("download",), "cloud-download"),
        (("game",), "puzzle-piece"),
    )
    for words, icon in rules:
        for word in words:
            if word in text:
                return icon
    return "grid-four-up"
