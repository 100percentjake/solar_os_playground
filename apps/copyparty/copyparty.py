"""Interactive copyparty file client for SolarOS MicroPython."""

import binascii
import gc
import json
import sys

import solaros
from solaros import gfx


def app_directory():
    path = sys.argv[0] if sys.argv else "copyparty.py"
    if not path or "/" not in path:
        try:
            path = __file__
        except NameError:
            path = "copyparty.py"
    slash = path.rfind("/")
    return path[:slash] if slash > 0 else "."


APP_DIR = app_directory()
CONFIG_PATH = APP_DIR + "/config.json"
LIST_PATH = APP_DIR + "/listing.tmp"
LIST_ITEMS_PATH = APP_DIR + "/listing-items.tmp"
LIST_STAGE_PATH = APP_DIR + "/listing-next.tmp"
LIST_STAGE_ITEMS_PATH = APP_DIR + "/listing-next-items.tmp"
LIST_BACKUP_ITEMS_PATH = APP_DIR + "/listing-previous-items.tmp"
FOLDER_PLAN_PATH = APP_DIR + "/download-plan.tmp"
LIST_LIMIT = 512 * 1024
LIST_MEMORY_LIMIT = 96 * 1024
LIST_PAGE_SIZE = 24
LIST_NODE_LIMIT = 32 * 1024
FILE_LIMIT = 64 * 1024 * 1024
UPLOAD_LIMIT = 64 * 1024
FOLDER_FILE_LIMIT = 256
FOLDER_DIR_LIMIT = 256
PROGRESS_STEP = 256 * 1024
STREAM_WRITE_BUFFER = 16 * 1024
STREAM_GC_STEP = 512 * 1024
STREAM_IDLE_MS = 250
RANGE_BLOCK_SIZE = 64 * 1024
DISPLAY_SIZE_CAP = 999 * 1024 * 1024
MAX_SAVED_SERVERS = 20

KEY_ENTER = 10
KEY_RETURN = 13
KEY_BACKSPACE = 8
KEY_DELETE_CHAR = 127

HEADER_H = 46
FOOTER_H = 29
ROW_H = 43
MIN_WIDTH = 160
MIN_HEIGHT = 112


def clean(value):
    if not isinstance(value, str):
        return ""
    # Remote filenames, server errors, and saved config are all untrusted.
    # Strip terminal controls (including ANSI ESC and bidi overrides) before
    # any value reaches the renderer.
    output = []
    for character in value:
        code = ord(character)
        if (code < 32 or code == 127 or 128 <= code <= 159 or
                0x202A <= code <= 0x202E or 0x2066 <= code <= 0x2069):
            output.append(" ")
        else:
            output.append(character)
    return " ".join("".join(output).split())


def clip(value, width):
    value = clean(value)
    if len(value) <= width:
        return value
    return value[:max(0, width - 1)] + ("~" if width else "")


def wrap(value, width):
    if width < 1:
        return []
    output = []
    for paragraph in str(value or "").replace("\r", "").split("\n"):
        paragraph = clean(paragraph)
        if not paragraph:
            if output and output[-1] != "":
                output.append("")
            continue
        while len(paragraph) > width:
            cut = paragraph.rfind(" ", 0, width + 1)
            if cut < 1:
                cut = width
            output.append(paragraph[:cut])
            paragraph = paragraph[cut:].lstrip()
        output.append(paragraph)
    return output or [""]


def message(title, body, footer="Press any key"):
    width, height = gfx.size()
    gfx.clear(gfx.WHITE)
    draw_header(width, title)
    gfx.color(gfx.BLACK)
    gfx.font(gfx.FONT_MONO_14)
    columns = max(8, (width - 24) // 7)
    y = HEADER_H + 25
    for line in wrap(body, columns):
        if y > height - FOOTER_H - 5:
            break
        gfx.text(12, y, clip(line, columns))
        y += 20
    draw_footer(width, height, footer)
    gfx.refresh()


def draw_header(width, title, subtitle="", right=""):
    gfx.color(gfx.WHITE)
    gfx.fill_rect(0, 0, width, HEADER_H)
    gfx.color(gfx.BLACK)
    gfx.rect(0, 0, width, HEADER_H)
    gfx.font(gfx.FONT_BOLD_16)
    reserved = len(right) * 6 + 10 if right else 0
    gfx.text(10, 19, clip(title, max(1, (width - 20 - reserved) // 8)))
    if right:
        gfx.font(gfx.FONT_MONO_12)
        gfx.text(max(10, width - 8 - len(right) * 6), 19, right)
    if subtitle:
        gfx.font(gfx.FONT_MONO_12)
        gfx.text(10, 37, clip(subtitle, max(1, (width - 20) // 6)))


def draw_footer(width, height, value):
    y = height - FOOTER_H
    gfx.color(gfx.WHITE)
    gfx.fill_rect(0, y, width, FOOTER_H)
    gfx.color(gfx.BLACK)
    gfx.rect(0, y, width, FOOTER_H)
    gfx.font(gfx.FONT_MONO_12)
    gfx.text(7, y + 18, clip(value, max(1, (width - 14) // 6)))


def wait_key():
    while not solaros.should_exit():
        key = gfx.getch(250)
        if key is not None:
            return key
    return gfx.KEY_ESCAPE


def edit_text(title, label, initial="", maximum=512, secret=False):
    value = initial
    dirty = True
    while not solaros.should_exit():
        if dirty:
            width, height = gfx.size()
            gfx.clear(gfx.WHITE)
            draw_header(width, title, label + "  {}/{}".format(len(value), maximum))
            gfx.color(gfx.BLACK)
            gfx.font(gfx.FONT_MONO_16)
            shown = "*" * len(value) if secret else value
            columns = max(8, (width - 24) // 8)
            lines = wrap(shown + "_", columns)
            visible = max(1, (height - HEADER_H - FOOTER_H - 8) // 23)
            y = HEADER_H + 31
            for line in lines[-visible:]:
                gfx.text(12, y, clip(line, columns))
                y += 23
            draw_footer(width, height, "Enter accept   Esc cancel   Backspace delete")
            gfx.refresh()
            dirty = False
        key = gfx.getch(250)
        if key is None:
            continue
        if key == gfx.KEY_ESCAPE:
            return None
        if key == KEY_ENTER or key == KEY_RETURN:
            return value.strip()
        if key == KEY_BACKSPACE or key == KEY_DELETE_CHAR or key == gfx.KEY_DELETE:
            value = value[:-1]
            dirty = True
        elif isinstance(key, int) and 32 <= key <= 126 and len(value) < maximum:
            value += chr(key)
            dirty = True
    return None


def confirm(title, body):
    message(title, body, "y confirm  any other key cancel")
    key = wait_key()
    return key == ord("y") or key == ord("Y")


def remove_if_present(path):
    try:
        solaros.storage.remove(path)
    except OSError:
        pass


def move_if_present(source, target):
    try:
        solaros.storage.rename(source, target)
        return True
    except OSError:
        return False


def ensure_tree(path):
    path = path.replace("\\", "/")
    pieces = path.split("/")
    current = "/" if path.startswith("/") else ""
    for piece in pieces:
        if not piece:
            continue
        current = current.rstrip("/") + "/" + piece
        try:
            solaros.storage.mkdir(current)
        except OSError:
            pass


def parent_path(path):
    path = path.rstrip("/")
    slash = path.rfind("/")
    if slash <= 0:
        return "/"
    return path[:slash]


def join_path(left, right):
    if left == "/":
        return "/" + right.lstrip("/")
    return left.rstrip("/") + "/" + right.lstrip("/")


def basename(path):
    path = path.replace("\\", "/").rstrip("/")
    slash = path.rfind("/")
    return path[slash + 1:] if slash >= 0 else path


def safe_name(value):
    value = clean(value)
    output = []
    forbidden = '\\/:?*"<>|~'
    for character in value:
        code = ord(character)
        if character in forbidden or code < 32 or code == 127:
            output.append("~{:X}".format(code))
        else:
            output.append(character)
    value = "".join(output).strip()
    if value == "." or value == "..":
        return "download"
    return value or "download"


def server_name_from_url(url):
    value = str(url or "")
    marker = value.find("://")
    if marker >= 0:
        value = value[marker + 3:]
    value = value.split("/", 1)[0]
    return clean(value) or "copyparty server"


def normalize_server(value):
    if not isinstance(value, dict):
        return None
    url = clean(str(value.get("url") or "")).strip()
    if not url:
        return None
    lower_url = url.lower()
    if not lower_url.startswith("http://") and not lower_url.startswith("https://"):
        url = "http://" + url
    elif lower_url.startswith("http://"):
        url = "http://" + url[7:]
    else:
        url = "https://" + url[8:]
    origin = url_origin(url)
    authority = origin.split("://", 1)[-1]
    if (not authority or "@" in authority or "?" in url or "#" in url or
            any(character in " \t\r\n" for character in url)):
        return None
    url = url.rstrip("/") + "/"
    username = clean(str(value.get("username") or ""))[:128]
    password = str(value.get("password") or "")[:512]
    if ":" in username or has_header_control(username) or has_header_control(password):
        return None
    return {
        "name": clean(str(value.get("name") or ""))[:64] or server_name_from_url(url),
        "url": url,
        "username": username,
        "password": password,
        "download_dir": clean(str(value.get("download_dir") or
                                  "/Downloads/copyparty"))[:512],
    }


def new_server_url(value):
    """Give a bare host copyparty's stock port; preserve explicit URLs."""
    value = clean(str(value or "")).strip()
    lower = value.lower()
    if lower.startswith("http://") or lower.startswith("https://"):
        return value
    authority = value.split("/", 1)[0]
    if authority and ":" not in authority:
        return value + ":3923" if "/" not in value else authority + ":3923/" + value.split("/", 1)[1]
    return value


def friendly_error(error, config=None):
    message_text = clean(str(error)) or "unknown error"
    if ("HTTP_CONNECT" in message_text or "connection" in message_text.lower() or
            "connect" in message_text.lower()):
        url = clean(str((config or {}).get("url") or ""))
        return (message_text + ". Check that the server address includes its port; "
                "stock copyparty uses :3923. Current address: " + (url or "unset"))
    return message_text


def load_config():
    value = None
    try:
        with open(CONFIG_PATH, "r") as source:
            value = json.load(source)
    except Exception:
        pass
    servers = []
    selected = 0
    if isinstance(value, dict) and isinstance(value.get("servers"), list):
        for entry in value["servers"][:MAX_SAVED_SERVERS]:
            server = normalize_server(entry)
            if server is not None:
                servers.append(server)
        candidate = value.get("selected", 0)
        if isinstance(candidate, int) and candidate >= 0:
            selected = candidate
    elif isinstance(value, dict):
        # Migrate the original one-server config without dropping credentials.
        server = normalize_server(value)
        if server is not None:
            servers.append(server)
    if selected >= len(servers):
        selected = max(0, len(servers) - 1)
    return {"version": 2, "selected": selected, "servers": servers}


def save_config(config):
    temporary = CONFIG_PATH + ".tmp"
    backup = CONFIG_PATH + ".bak"
    with open(temporary, "w") as output:
        json.dump(config, output)
        output.flush()
    remove_if_present(backup)
    had_previous = move_if_present(CONFIG_PATH, backup)
    try:
        solaros.storage.rename(temporary, CONFIG_PATH)
    except Exception:
        if had_previous:
            solaros.storage.rename(backup, CONFIG_PATH)
        raise
    remove_if_present(backup)


def edit_server(existing=None):
    existing = existing if isinstance(existing, dict) else {}
    title = "Edit server" if existing.get("url") else "Add server"
    name = edit_text(title, "Connection name", existing.get("name", ""), 64)
    if name is None:
        return None
    url = edit_text(title, "Server URL (bare host uses port 3923)",
                    existing.get("url", ""))
    if url is None:
        return None
    if not url:
        message("Invalid server", "A server URL is required.", "Press any key")
        wait_key()
        return None
    if not existing.get("url"):
        url = new_server_url(url)
    username = edit_text(title, "Username (optional; --usernames servers)",
                         existing.get("username", ""), 128)
    if username is None:
        return None
    if ":" in username:
        message("Invalid username", "CopyParty usernames cannot contain a colon.",
                "Press any key")
        wait_key()
        return None
    password = edit_text(title, "Password (optional)",
                         existing.get("password", ""), secret=True)
    if password is None:
        return None
    destination = edit_text(title, "Default download folder",
                            existing.get("download_dir", "/Downloads/copyparty"))
    if destination is None:
        return None
    server = normalize_server({
        "name": name,
        "url": url,
        "username": username,
        "password": password,
        "download_dir": destination or "/Downloads/copyparty",
    })
    if server is None:
        message("Invalid server", "Use an HTTP or HTTPS URL without spaces or "
                "control characters. Credentials cannot contain newlines.",
                "Press any key")
        wait_key()
    return server


def draw_server_picker(servers, selected):
    width, height = gfx.size()
    visible = max(1, (height - HEADER_H - FOOTER_H) // ROW_H)
    selected = min(max(0, selected), max(0, len(servers) - 1))
    start = (selected // visible) * visible
    gfx.clear(gfx.WHITE)
    page = "{}/{}".format(selected + 1, len(servers)) if servers else ""
    draw_header(width, "Copyparty", "Saved servers", page)
    if not servers:
        gfx.color(gfx.DARK)
        gfx.font(gfx.FONT_MONO_16)
        gfx.text(14, HEADER_H + 35, clip("No saved servers.", max(1, (width - 28) // 8)))
        gfx.font(gfx.FONT_MONO_12)
        gfx.text(14, HEADER_H + 59, clip("Press N to add a connection.", max(1, (width - 28) // 6)))
    for offset, server in enumerate(servers[start:start + visible]):
        index = start + offset
        y = HEADER_H + offset * ROW_H
        active = index == selected
        if active:
            gfx.color(gfx.BLACK)
            gfx.rect(4, y + 2, width - 8, ROW_H - 3)
            foreground = gfx.BLACK
        else:
            gfx.color(gfx.LIGHT)
            gfx.line(8, y + ROW_H - 1, width - 8, y + ROW_H - 1)
            foreground = gfx.BLACK
        gfx.color(foreground)
        gfx.font(gfx.FONT_BOLD_14)
        gfx.text(12, y + 19, clip(server["name"], max(5, (width - 24) // 7)))
        detail = server["url"]
        if server["username"]:
            detail = server["username"] + " @ " + detail
        gfx.font(gfx.FONT_MONO_12)
        gfx.text(12, y + 36, clip(detail, max(5, (width - 24) // 6)))
    draw_footer(width, height, "Enter connect  N new  E edit  D delete  Esc cancel")
    gfx.refresh()
    return selected


def choose_server(state, selected=None):
    servers = state["servers"]
    if selected is None:
        selected = state.get("selected", 0)
    dirty = True
    while not solaros.should_exit():
        if dirty:
            selected = draw_server_picker(servers, selected)
            dirty = False
        key = gfx.getch(250)
        if key is None:
            continue
        if key in (gfx.KEY_DOWN, ord("j")) and servers:
            next_selected = min(len(servers) - 1, selected + 1)
            dirty = next_selected != selected
            selected = next_selected
        elif key in (gfx.KEY_UP, ord("k")) and servers:
            next_selected = max(0, selected - 1)
            dirty = next_selected != selected
            selected = next_selected
        elif key == getattr(gfx, "KEY_PAGE_DOWN", -1002) and servers:
            next_selected = min(len(servers) - 1,
                                selected + max(1, (gfx.size()[1] - HEADER_H - FOOTER_H) // ROW_H))
            dirty = next_selected != selected
            selected = next_selected
        elif key == getattr(gfx, "KEY_PAGE_UP", -1001) and servers:
            next_selected = max(0, selected - max(1, (gfx.size()[1] - HEADER_H - FOOTER_H) // ROW_H))
            dirty = next_selected != selected
            selected = next_selected
        elif (key == KEY_ENTER or key == KEY_RETURN) and servers:
            state["selected"] = selected
            save_config(state)
            return selected
        elif key in (ord("n"), ord("N")):
            if len(servers) >= MAX_SAVED_SERVERS:
                message("Server limit", "Remove a saved server before adding another.",
                        "Press any key")
                wait_key()
            else:
                server = edit_server()
                if server is not None:
                    servers.append(server)
                    selected = len(servers) - 1
                    state["selected"] = selected
                    save_config(state)
            dirty = True
        elif key in (ord("e"), ord("E")) and servers:
            server = edit_server(servers[selected])
            if server is not None:
                servers[selected] = server
                state["selected"] = selected
                save_config(state)
            dirty = True
        elif key in (ord("d"), ord("D"), gfx.KEY_DELETE) and servers:
            if confirm("Delete saved server",
                       "Remove '{}'?".format(servers[selected]["name"])):
                servers.pop(selected)
                selected = min(selected, max(0, len(servers) - 1))
                state["selected"] = selected
                save_config(state)
            dirty = True
        elif key == gfx.KEY_ESCAPE or key in (ord("q"), ord("Q")):
            return None
    return None


def percent_encode(value):
    safe = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~/"
    output = []
    for byte in value.encode("utf-8"):
        character = chr(byte)
        output.append(character if character in safe else "%{:02X}".format(byte))
    return "".join(output)


def percent_decode(value):
    value = value.split("?")[0].rstrip("/")
    output = bytearray()
    position = 0
    while position < len(value):
        if value[position] == "%" and position + 2 < len(value):
            try:
                output.extend(binascii.unhexlify(value[position + 1:position + 3]))
                position += 3
                continue
            except Exception:
                pass
        output.extend(value[position].encode("utf-8"))
        position += 1
    try:
        return output.decode("utf-8")
    except Exception:
        return str(value)


def auth_headers(config, accept=None):
    headers = {}
    username = config.get("username", "")
    password = config.get("password", "")
    if has_header_control(username) or has_header_control(password) or ":" in username:
        raise RuntimeError("invalid saved credentials")
    if username:
        headers["PW"] = username + ":" + password
    elif password:
        headers["PW"] = password
    if accept:
        headers["Accept"] = accept
    return headers


def has_header_control(value):
    for character in str(value or ""):
        code = ord(character)
        if code < 32 or code == 127:
            return True
    return False


def remote_url(config, path, suffix=""):
    base = config["url"].rstrip("/")
    path = path if path.startswith("/") else "/" + path
    return base + percent_encode(path) + suffix


def url_origin(url):
    scheme = url.find("://")
    if scheme < 0:
        return ""
    slash = url.find("/", scheme + 3)
    return url if slash < 0 else url[:slash]


def require_server_url(config, url):
    expected = url_origin(config.get("url", "")).lower()
    actual = url_origin(url).lower()
    if not expected or actual != expected:
        raise RuntimeError("server link points outside configured server")
    return url


def resolve_href(base_url, href):
    href = str(href or "")
    if href.startswith("http://") or href.startswith("https://"):
        return href
    if href.startswith("//"):
        scheme = base_url.split(":", 1)[0]
        return scheme + ":" + href
    if href.startswith("/"):
        return url_origin(base_url) + href
    clean_base = base_url.split("#", 1)[0].split("?", 1)[0]
    if not clean_base.endswith("/"):
        clean_base += "/"
    return clean_base + href


def add_query_flag(url, flag):
    separator = "&" if "?" in url else "?"
    return url + separator + flag


def quote_json_numbers(text):
    output = []
    position = 0
    quoted = False
    escaped = False
    while position < len(text):
        character = text[position]
        if quoted:
            output.append(character)
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                quoted = False
            position += 1
            continue
        if character == '"':
            quoted = True
            output.append(character)
            position += 1
            continue
        starts_number = ("0" <= character <= "9" or
                         (character == "-" and position + 1 < len(text) and
                          "0" <= text[position + 1] <= "9"))
        if starts_number:
            end = position + 1
            while end < len(text) and text[end] in "0123456789+-.eE":
                end += 1
            output.append('"' + text[position:end] + '"')
            position = end
            continue
        output.append(character)
        position += 1
    return "".join(output)


def capped_size(value):
    value = str(value or "0")
    total = 0
    for character in value:
        if character < "0" or character > "9":
            break
        digit = ord(character) - 48
        if total > (DISPLAY_SIZE_CAP - digit) // 10:
            return DISPLAY_SIZE_CAP
        total = total * 10 + digit
    return total


def ascii_digits(value):
    if not value:
        return False
    for character in value:
        if character < "0" or character > "9":
            return False
    return True


def progress_percent(received, total):
    if not total or total <= 0:
        return 0
    if received >= total:
        return 100
    if total <= 1024:
        return (received * 100) // total
    # Scale to KiB first so the multiplication stays inside small-int builds.
    scaled_received = received // 1024
    scaled_total = (total + 1023) // 1024
    return min(99, (scaled_received * 100) // scaled_total)


def draw_progress(label, received, total=-1):
    width, height = gfx.size()
    gfx.clear(gfx.WHITE)
    draw_header(width, label, "Transfer in progress")
    gfx.color(gfx.BLACK)
    compact = height < 180
    if total and total > 0:
        percent = progress_percent(received, total)
        detail = "{} / {} KiB".format(received // 1024, (total + 1023) // 1024)
        if not compact:
            bar_x = 16
            bar_y = HEADER_H + 34
            bar_width = max(20, width - 32)
            gfx.rect(bar_x, bar_y, bar_width, 24)
            inner = max(0, ((bar_width - 4) * percent) // 100)
            if inner:
                gfx.fill_rect(bar_x + 2, bar_y + 2, inner, 20)
            gfx.font(gfx.FONT_BOLD_20)
            percent_text = "{}%".format(percent)
            gfx.text(max(8, (width - len(percent_text) * 10) // 2), bar_y + 55, percent_text)
        else:
            detail = "{}%  ".format(percent) + detail
    else:
        detail = "{} KiB received".format(received // 1024)
        gfx.font(gfx.FONT_BOLD_20)
        gfx.text(16, HEADER_H + 58, clip(detail, max(1, (width - 32) // 10)))
    gfx.color(gfx.BLACK)
    gfx.font(gfx.FONT_MONO_14)
    detail_y = HEADER_H + 25 if compact else HEADER_H + 112
    gfx.text(16, detail_y, clip(detail, max(1, (width - 32) // 7)))
    draw_footer(width, height, "Please wait")
    gfx.refresh()


def flush_write_buffer(output, buffer, used):
    if used <= 0:
        return 0
    segment = memoryview(buffer)[:used]
    written = output.write(segment)
    del segment
    if written is not None and written != used:
        raise RuntimeError("incomplete storage write")
    return 0


def header_value(response, name):
    wanted = name.lower()
    for key, value in response.get("headers", {}).items():
        if str(key).lower() == wanted:
            return str(value)
    return ""


def content_range_values(value):
    """Return start, end, total from a bytes Content-Range header."""
    value = str(value or "").strip()
    if not value.lower().startswith("bytes "):
        return -1, -1, -1
    value = value[6:]
    dash = value.find("-")
    slash = value.find("/")
    if dash < 1 or slash <= dash + 1:
        return -1, -1, -1
    start_text = value[:dash]
    end_text = value[dash + 1:slash]
    total_text = value[slash + 1:]
    if (not ascii_digits(start_text) or not ascii_digits(end_text) or
            (total_text != "*" and not ascii_digits(total_text))):
        return -1, -1, -1
    start = capped_size(start_text)
    end = capped_size(end_text)
    total = -1 if total_text == "*" else capped_size(total_text)
    return start, end, total


def ranged_get(config, url, output_path, limit, label, progress=None):
    """Download a file in bounded requests so storage stalls cannot lose data."""
    require_server_url(config, url)
    if progress is None:
        draw_progress(label, 0, -1)
    else:
        progress(0, -1)
    gc.collect()
    handle = None
    received = 0
    total = -1
    next_progress = PROGRESS_STEP
    next_gc = STREAM_GC_STEP
    complete = False
    try:
        handle = solaros.http.session_open(url_origin(url))
        head = solaros.http.session_request(
            handle, "HEAD", url, None, auth_headers(config), 30000, 0)
        status = head.get("status_code", 0)
        if status < 200 or status >= 300:
            raise RuntimeError("HTTP {}".format(status or "request failed"))
        total = head.get("content_length", -1)
        if total > limit:
            raise RuntimeError("download exceeds size limit")
        del head
        gc.collect()
        if progress is not None:
            progress(0, total)

        with open(output_path, "wb") as output:
            while (total < 0 or received < total) and not solaros.should_exit():
                end = received + RANGE_BLOCK_SIZE - 1
                if total >= 0 and end >= total:
                    end = total - 1
                headers = auth_headers(config)
                headers["Range"] = "bytes={}-{}".format(received, end)
                response = solaros.http.session_request(
                    handle, "GET", url, None, headers, 30000,
                    RANGE_BLOCK_SIZE)
                status = response.get("status_code", 0)
                body = response.get("body", b"")
                body_size = len(body)

                if status == 206:
                    range_start, range_end, range_total = content_range_values(
                        header_value(response, "Content-Range"))
                    if (range_start != received or range_end < range_start or
                            range_end - range_start + 1 != body_size):
                        raise RuntimeError("server returned an invalid byte range")
                    if range_total >= 0:
                        if total >= 0 and total != range_total:
                            raise RuntimeError("file changed during download")
                        total = range_total
                elif status == 200 and received == 0 and not response.get("truncated"):
                    # A small file may be returned whole even when Range was sent.
                    if total >= 0 and body_size != total:
                        raise RuntimeError("incomplete server response")
                    total = body_size
                elif status < 200 or status >= 300:
                    raise RuntimeError("HTTP {}".format(status or "request failed"))
                else:
                    raise RuntimeError("server does not support ranged downloads")

                if response.get("truncated"):
                    raise RuntimeError("server response exceeded range buffer")
                if body_size <= 0 and (total < 0 or received < total):
                    raise RuntimeError("server returned an empty byte range")
                if received + body_size > limit:
                    raise RuntimeError("download exceeds size limit")
                written = output.write(body)
                if written is not None and written != body_size:
                    raise RuntimeError("incomplete storage write")
                received += body_size
                del body
                del response

                if received >= next_gc:
                    gc.collect()
                    next_gc = received + STREAM_GC_STEP
                if received >= next_progress:
                    if progress is None:
                        draw_progress(label, received, total)
                    else:
                        progress(received, total)
                    next_progress = received + PROGRESS_STEP

            output.flush()
        complete = total >= 0 and received == total
        if complete:
            if progress is None:
                draw_progress(label, received, total)
            else:
                progress(received, total)
    finally:
        if handle is not None:
            solaros.http.session_close(handle)
        gc.collect()
    if not complete:
        raise RuntimeError("download interrupted")
    return received


def stream_get(config, url, output_path, limit, label):
    require_server_url(config, url)
    draw_progress(label, 0, -1)
    gc.collect()
    handle = None
    status = 0
    received = 0
    total = -1
    next_progress = PROGRESS_STEP
    next_gc = STREAM_GC_STEP
    progress_pending = False
    gc_pending = False
    read_timeout = STREAM_IDLE_MS
    write_buffer = bytearray(STREAM_WRITE_BUFFER)
    write_used = 0
    complete = False
    try:
        with open(output_path, "wb") as output:
            handle = solaros.http.stream_open(
                "GET", url, None, auth_headers(config), 30000, False)
            try:
                while not solaros.should_exit():
                    timed_wait = read_timeout > 0
                    event = solaros.http.stream_read(handle, read_timeout)
                    if event is None:
                        if write_used:
                            pending = write_used
                            write_used = 0
                            flush_write_buffer(output, write_buffer, pending)
                        if gc_pending:
                            gc.collect()
                            gc_pending = False
                            next_gc = received + STREAM_GC_STEP
                        if timed_wait and progress_pending:
                            draw_progress(label, received, total)
                            progress_pending = False
                            next_progress = received + PROGRESS_STEP
                        read_timeout = STREAM_IDLE_MS
                        continue

                    read_timeout = 0
                    kind = event.get("type")
                    if kind == "response":
                        status = event.get("status_code", 0)
                        total = event.get("content_length", -1)
                        if status < 200 or status >= 300:
                            raise RuntimeError("HTTP {}".format(status))
                        if total > limit:
                            raise RuntimeError("download exceeds size limit")
                    elif kind == "data":
                        chunk = event.get("data", b"")
                        chunk_len = len(chunk)
                        received += chunk_len
                        if received > limit:
                            raise RuntimeError("download exceeds size limit")
                        if write_used + chunk_len > len(write_buffer):
                            pending = write_used
                            write_used = 0
                            flush_write_buffer(output, write_buffer, pending)
                        end = write_used + chunk_len
                        write_buffer[write_used:end] = chunk
                        write_used = end
                        if write_used == len(write_buffer):
                            pending = write_used
                            write_used = 0
                            flush_write_buffer(output, write_buffer, pending)
                        if received >= next_progress:
                            progress_pending = True
                        if received >= next_gc:
                            gc_pending = True
                        del chunk
                    elif kind == "error":
                        raise RuntimeError(event.get("error_name", "network error"))
                    elif kind == "complete":
                        complete = True
                        del event
                        break
                    del event
            finally:
                if write_used:
                    pending = write_used
                    write_used = 0
                    flush_write_buffer(output, write_buffer, pending)
                output.flush()
            if complete:
                draw_progress(label, received, total)
    finally:
        if handle is not None:
            solaros.http.stream_close(handle)
        del write_buffer
        gc.collect()
    if not complete:
        raise RuntimeError("download interrupted")
    if status < 200 or status >= 300:
        raise RuntimeError("HTTP {}".format(status or "request failed"))
    if total >= 0 and received != total:
        raise RuntimeError("incomplete server response")
    return received


def item_from_node(node, is_dir, base_url=""):
    href = str(node.get("href") or "")
    name = percent_decode(href)
    if "/" in name:
        name = basename(name)
    return {
        "name": clean(name) or "unnamed",
        "href": href,
        "url": resolve_href(base_url, href) if base_url else href,
        "is_dir": is_dir,
        "size": capped_size(node.get("sz")),
    }


def json_array_objects(path, name):
    found = False
    in_array = False
    container_depth = 0
    depth = 0
    quoted = False
    escaped = False
    string_chars = []
    last_string = None
    after_string = False
    object_chars = []
    with open(path, "r") as source:
        while True:
            chunk = source.read(1024)
            if not chunk:
                break
            for character in chunk:
                if not found:
                    if quoted:
                        if escaped:
                            escaped = False
                            string_chars.append(character)
                        elif character == "\\":
                            escaped = True
                            string_chars.append(character)
                        elif character == '"':
                            quoted = False
                            last_string = "".join(string_chars)
                            after_string = True
                        else:
                            string_chars.append(character)
                        continue
                    if character == '"':
                        quoted = True
                        escaped = False
                        string_chars = []
                        continue
                    if character in "{[":
                        container_depth += 1
                        after_string = False
                    elif character in "}]":
                        container_depth -= 1
                        after_string = False
                    elif character == ":" and after_string:
                        if container_depth == 1 and last_string == name:
                            found = True
                        after_string = False
                    elif character not in " \t\r\n":
                        after_string = False
                    continue
                if not in_array:
                    if character == "[":
                        in_array = True
                    else:
                        if character not in " \t\r\n:":
                            raise RuntimeError("invalid directory listing")
                    continue
                if depth == 0:
                    if character == "]":
                        return
                    if character != "{":
                        continue
                    object_chars = [character]
                    depth = 1
                    quoted = False
                    escaped = False
                    continue
                object_chars.append(character)
                if len(object_chars) > LIST_NODE_LIMIT:
                    raise RuntimeError("directory entry exceeds size limit")
                if quoted:
                    if escaped:
                        escaped = False
                    elif character == "\\":
                        escaped = True
                    elif character == '"':
                        quoted = False
                elif character == '"':
                    quoted = True
                elif character == "{":
                    depth += 1
                elif character == "}":
                    depth -= 1
                    if depth == 0:
                        yield json.loads(quote_json_numbers("".join(object_chars)))
                        object_chars = []
    raise RuntimeError("directory listing is missing or incomplete")


class PagedItems:
    def __init__(self, path, offsets, count):
        self.path = path
        self.offsets = offsets
        self.count = count
        self.loaded_page = -1
        self.loaded = []

    def __len__(self):
        return self.count

    def load_page(self, page):
        if page == self.loaded_page:
            return
        records = []
        with open(self.path, "r") as source:
            source.seek(self.offsets[page])
            for unused in range(LIST_PAGE_SIZE):
                line = source.readline()
                if not line:
                    break
                records.append(json.loads(line))
        self.loaded_page = page
        self.loaded = records

    def __getitem__(self, index):
        if isinstance(index, slice):
            start = 0 if index.start is None else index.start
            stop = self.count if index.stop is None else min(index.stop, self.count)
            return [self[position] for position in range(start, stop)]
        if index < 0:
            index += self.count
        if index < 0 or index >= self.count:
            raise IndexError
        page = index // LIST_PAGE_SIZE
        self.load_page(page)
        return self.loaded[index % LIST_PAGE_SIZE]

    def __iter__(self):
        for index in range(self.count):
            yield self[index]


def paged_listing(path, base_url, output_path):
    offsets = []
    count = 0
    remove_if_present(output_path)
    with open(output_path, "w") as output:
        for array_name, is_dir in (("dirs", True), ("files", False)):
            for node in json_array_objects(path, array_name):
                if not isinstance(node, dict):
                    continue
                if count % LIST_PAGE_SIZE == 0:
                    offsets.append(output.tell())
                output.write(json.dumps(item_from_node(node, is_dir, base_url)) + "\n")
                count += 1
        output.flush()
    return PagedItems(output_path, offsets, count)


def fetch_listing(config, remote_path, listing_url=None, label="Reading folder"):
    base_url = listing_url or remote_url(config, remote_path)
    try:
        remove_if_present(LIST_STAGE_PATH)
        remove_if_present(LIST_STAGE_ITEMS_PATH)
        size = stream_get(config, add_query_flag(base_url, "ls"), LIST_STAGE_PATH,
                          LIST_LIMIT, label)
        if size > LIST_MEMORY_LIMIT:
            staged = paged_listing(LIST_STAGE_PATH, base_url,
                                   LIST_STAGE_ITEMS_PATH)
            remove_if_present(LIST_BACKUP_ITEMS_PATH)
            had_previous = move_if_present(LIST_ITEMS_PATH,
                                           LIST_BACKUP_ITEMS_PATH)
            try:
                solaros.storage.rename(LIST_STAGE_ITEMS_PATH, LIST_ITEMS_PATH)
            except Exception:
                if had_previous:
                    solaros.storage.rename(LIST_BACKUP_ITEMS_PATH, LIST_ITEMS_PATH)
                raise
            remove_if_present(LIST_BACKUP_ITEMS_PATH)
            staged.path = LIST_ITEMS_PATH
            return staged
        with open(LIST_STAGE_PATH, "r") as source:
            value = json.loads(quote_json_numbers(source.read()))
    finally:
        remove_if_present(LIST_STAGE_PATH)
        remove_if_present(LIST_STAGE_ITEMS_PATH)
    if not isinstance(value, dict):
        raise RuntimeError("invalid directory listing")
    remove_if_present(LIST_ITEMS_PATH)
    items = []
    for node in value.get("dirs", []):
        if isinstance(node, dict):
            items.append(item_from_node(node, True, base_url))
    for node in value.get("files", []):
        if isinstance(node, dict):
            items.append(item_from_node(node, False, base_url))
    return items


def human_size(size):
    if size < 1024:
        return "{} B".format(size)
    if size < 1024 * 1024:
        return "{} KiB".format((size + 1023) // 1024)
    return "{} MiB".format((size + 1024 * 1024 - 1) // (1024 * 1024))


def draw_browser(remote_path, items, selected, status=""):
    width, height = gfx.size()
    visible = max(1, (height - HEADER_H - FOOTER_H) // ROW_H)
    selected = min(max(0, selected), max(0, len(items) - 1))
    start = (selected // visible) * visible
    gfx.clear(gfx.WHITE)
    page = "{}/{}".format(selected + 1, len(items)) if items else ""
    subtitle = remote_path + (("  " + status) if status else "")
    draw_header(width, "Copyparty", subtitle, page)
    for offset, item in enumerate(items[start:start + visible]):
        index = start + offset
        y = HEADER_H + offset * ROW_H
        active = index == selected
        if active:
            gfx.color(gfx.BLACK)
            gfx.rect(4, y + 2, width - 8, ROW_H - 3)
            foreground = gfx.BLACK
        else:
            gfx.color(gfx.LIGHT)
            gfx.line(8, y + ROW_H - 1, width - 8, y + ROW_H - 1)
            foreground = gfx.BLACK
        gfx.color(foreground)
        try:
            gfx.icon(8, y + 6, "folder" if item["is_dir"] else "file", 28)
        except Exception:
            pass
        text_x = 42
        gfx.font(gfx.FONT_BOLD_14)
        gfx.text(text_x, y + 19, clip(item["name"], max(5, (width - text_x - 10) // 7)))
        gfx.font(gfx.FONT_MONO_12)
        detail = "Folder" if item["is_dir"] else human_size(item["size"])
        gfx.text(text_x, y + 36, detail)
    if not items:
        gfx.color(gfx.DARK)
        gfx.font(gfx.FONT_MONO_16)
        gfx.text(14, HEADER_H + 35, "This folder is empty.")
    draw_footer(width, height,
                "Enter open D get U put M mkdir R reload C servers")
    gfx.refresh()
    return selected


def local_destination(config, name, is_dir):
    default = join_path(config["download_dir"], safe_name(name))
    label = "Destination folder" if is_dir else "Destination file"
    destination = edit_text("Download", label, default)
    if destination and not is_dir and file_exists(destination):
        if not confirm("Replace file", "The destination already exists. Replace it?"):
            return None
    return destination


def file_exists(path):
    try:
        with open(path, "rb"):
            return True
    except OSError:
        return False


def download_file(config, remote_path, local_path, progress=None):
    ensure_tree(parent_path(local_path))
    temporary = local_path + ".incomplete"
    try:
        source_url = (remote_path if remote_path.startswith("http://") or
                      remote_path.startswith("https://") else
                      remote_url(config, remote_path))
        size = ranged_get(config, add_query_flag(source_url, "dl"),
                          temporary, FILE_LIMIT, "Downloading", progress)
        remove_if_present(local_path)
        solaros.storage.rename(temporary, local_path)
        return size
    except Exception:
        raise


def draw_folder_scan(files, folders, current=""):
    body = "Enumerating files...\n\n{} files\n{} folders".format(files, folders)
    if current:
        body += "\n\n" + current
    message("Preparing folder download", body, "Please wait")


def build_folder_plan(config, remote_path, local_path):
    """Enumerate a folder into a disk-backed plan before downloading it."""
    ensure_tree(local_path)
    remove_if_present(FOLDER_PLAN_PATH)
    pending = [(remote_path, local_path, "")]
    files = 0
    folders = 0
    total = 0
    offsets = []
    destinations = {}
    draw_folder_scan(0, 0)
    try:
        with open(FOLDER_PLAN_PATH, "w") as output:
            while pending and not solaros.should_exit():
                remote_dir, local_dir, relative_dir = pending.pop()
                draw_folder_scan(files, folders, relative_dir or "/")
                listing = fetch_listing(config, "/", remote_dir,
                                        "Scanning folder")
                for item in listing:
                    child_remote = item["url"]
                    child_local = join_path(local_dir, safe_name(item["name"]))
                    relative = (relative_dir + "/" if relative_dir else "") + item["name"]
                    if item["is_dir"]:
                        folders += 1
                        if folders > FOLDER_DIR_LIMIT:
                            raise RuntimeError("folder exceeds {} directory limit".format(
                                FOLDER_DIR_LIMIT))
                        ensure_tree(child_local)
                        pending.append((child_remote, child_local, relative))
                    else:
                        files += 1
                        if files > FOLDER_FILE_LIMIT:
                            raise RuntimeError("folder exceeds {} file limit".format(
                                FOLDER_FILE_LIMIT))
                        if item["size"] > FILE_LIMIT:
                            raise RuntimeError("file exceeds 64 MiB limit: " + relative)
                        destination_key = child_local.lower()
                        if destination_key in destinations:
                            raise RuntimeError("folder contains colliding filenames: " +
                                               relative)
                        destinations[destination_key] = True
                        if file_exists(child_local):
                            raise RuntimeError("destination file already exists: " +
                                               child_local)
                        if (files - 1) % LIST_PAGE_SIZE == 0:
                            offsets.append(output.tell())
                        output.write(json.dumps({
                            "name": relative,
                            "url": child_remote,
                            "path": child_local,
                            "size": item["size"],
                        }) + "\n")
                        if total > DISPLAY_SIZE_CAP - item["size"]:
                            total = DISPLAY_SIZE_CAP
                        else:
                            total += item["size"]
                draw_folder_scan(files, folders, relative_dir or "/")
            output.flush()
        if solaros.should_exit():
            raise RuntimeError("download interrupted")
    except Exception:
        remove_if_present(FOLDER_PLAN_PATH)
        raise
    return PagedItems(FOLDER_PLAN_PATH, offsets, files), total


def draw_folder_progress(plan, current, received, file_total,
                         completed_bytes, total_bytes):
    width, height = gfx.size()
    visible = max(1, (height - HEADER_H - FOOTER_H) // 31)
    count = len(plan)
    active = min(max(0, current), max(0, count - 1))
    start = (active // visible) * visible
    gfx.clear(gfx.WHITE)
    title_count = min(current + 1, count) if count else 0
    draw_header(width, "Folder download", "File {} of {}".format(title_count, count))
    for offset, item in enumerate(plan[start:start + visible]):
        index = start + offset
        if index < current:
            marker = "[OK] "
        elif index == current:
            if file_total and file_total > 0:
                marker = "[{:>2}%] ".format(
                    progress_percent(received, file_total))
            else:
                marker = "[>>] "
        else:
            marker = "[  ] "
        y = HEADER_H + offset * 31
        if index == current:
            gfx.color(gfx.BLACK)
            gfx.rect(4, y + 2, width - 8, 28)
            gfx.color(gfx.BLACK)
        else:
            gfx.color(gfx.BLACK)
        gfx.font(gfx.FONT_MONO_14)
        gfx.text(11, y + 21, clip(marker + item["name"], max(4, (width - 22) // 7)))
    if completed_bytes > DISPLAY_SIZE_CAP - received:
        overall = DISPLAY_SIZE_CAP
    else:
        overall = completed_bytes + received
    if total_bytes and total_bytes > 0:
        percent = progress_percent(overall, total_bytes)
        footer = "Overall {}%  {} / {} KiB".format(
            percent, overall // 1024, (total_bytes + 1023) // 1024)
    else:
        footer = "Overall {} KiB  {} / {} files".format(
            overall // 1024, min(current, count), count)
    draw_footer(width, height, footer)
    gfx.refresh()


def download_folder(config, remote_path, local_path):
    plan = None
    try:
        plan, planned_total = build_folder_plan(config, remote_path, local_path)
        completed = 0
        draw_folder_progress(plan, 0, 0,
                             plan[0]["size"] if len(plan) else 0,
                             completed, planned_total)
        for index in range(len(plan)):
            item = plan[index]

            def progress(received, file_total, current=index, done=completed):
                draw_folder_progress(plan, current, received, file_total,
                                     done, planned_total)

            try:
                size = download_file(config, item["url"], item["path"], progress)
            except Exception as error:
                raise RuntimeError("{}: {}".format(item["name"], error))
            if completed > DISPLAY_SIZE_CAP - size:
                completed = DISPLAY_SIZE_CAP
            else:
                completed += size
            draw_folder_progress(plan, index + 1, 0, 0,
                                 completed, planned_total)
        return len(plan), completed
    finally:
        remove_if_present(FOLDER_PLAN_PATH)


def upload_file(config, remote_dir, initial=""):
    path = edit_text("Upload", "Local file", initial)
    if not path:
        return None
    try:
        with open(path, "rb") as source:
            body = source.read(UPLOAD_LIMIT + 1)
    except Exception as error:
        raise RuntimeError("cannot read {}: {}".format(path, error))
    if len(body) > UPLOAD_LIMIT:
        del body
        gc.collect()
        raise RuntimeError("upload exceeds {} KiB limit".format(UPLOAD_LIMIT // 1024))
    name = safe_name(basename(path))
    target = require_server_url(
        config, resolve_href(remote_dir, percent_encode(name)))
    headers = auth_headers(config, "application/json")
    headers["Content-Type"] = "application/octet-stream"
    response = solaros.http.put(add_query_flag(target, "j"), body,
                                headers, 30000, 8192, False)
    del body
    gc.collect()
    status = response.get("status_code", 0)
    if status < 200 or status >= 300:
        if status == 401 or status == 403:
            raise RuntimeError("upload denied (HTTP {}): check permissions".format(status))
        if status == 409:
            raise RuntimeError("a remote file with that name already exists")
        raise RuntimeError("upload failed (HTTP {})".format(status))
    return name


def make_folder(config, remote_dir):
    name = edit_text("Make folder", "Folder name", "", 128)
    if name is None:
        return None
    name = clean(name).strip()
    if (not name or name in (".", "..") or "/" in name or "\\" in name or
            has_header_control(name)):
        raise RuntimeError("enter one folder name without slashes")
    boundary = "solaros-copyparty-folder"
    body = (
        "--" + boundary + "\r\n"
        "Content-Disposition: form-data; name=\"act\"\r\n\r\n"
        "mkdir\r\n--" + boundary + "\r\n"
        "Content-Disposition: form-data; name=\"name\"\r\n\r\n" +
        name + "\r\n--" + boundary + "--\r\n"
    )
    headers = auth_headers(config, "application/json")
    headers["Content-Type"] = "multipart/form-data; boundary=" + boundary
    response = solaros.http.post(remote_dir, body, headers,
                                 30000, 8192, False)
    status = response.get("status_code", 0)
    if status < 200 or status >= 300:
        if status in (401, 403):
            raise RuntimeError("folder creation denied (HTTP {}): check permissions".format(status))
        if status == 409:
            raise RuntimeError("a folder with that name already exists")
        raise RuntimeError("folder creation failed (HTTP {})".format(status))
    return name


def selected_download(config, remote_path, item):
    destination = local_destination(config, item["name"], item["is_dir"])
    if not destination:
        return None
    if item["is_dir"]:
        count, size = download_folder(
            config, item["url"], destination)
        return "downloaded {} files, {}".format(count, human_size(size))
    size = download_file(config, item["url"], destination)
    return "downloaded {}".format(human_size(size))


def file_argument():
    index = 1
    while index < len(sys.argv):
        if sys.argv[index] == "--file" and index + 1 < len(sys.argv):
            return sys.argv[index + 1]
        index += 1
    return ""


def main():
    try:
        solaros.storage.mkdir(APP_DIR)
    except OSError:
        pass
    gfx.begin()
    try:
        width, height = gfx.size()
        if width < MIN_WIDTH or height < MIN_HEIGHT:
            gfx.clear(gfx.WHITE)
            gfx.color(gfx.BLACK)
            gfx.font(gfx.FONT_MONO_12)
            gfx.text(4, 14, clip("Copyparty needs a 160x112 display.", max(1, (width - 8) // 6)))
            gfx.refresh()
            wait_key()
            return
        run_client(load_config())
    finally:
        gfx.end()


def run_client(state):
    if not state["servers"]:
        server = edit_server()
        if server is None:
            return
        state["servers"].append(server)
        save_config(state)
    selected_server = choose_server(state)
    if selected_server is None:
        return
    config = state["servers"][selected_server]
    remote_path = "/"
    current_url = remote_url(config, "/")
    parents = []
    selected = 0
    items = []
    status = "connected to " + config["name"]
    pending_upload = file_argument()
    refresh = True
    dirty = True
    try:
        while not solaros.should_exit():
            if refresh:
                try:
                    items = fetch_listing(config, remote_path, current_url)
                    selected = min(selected, max(0, len(items) - 1))
                    status = "{} items".format(len(items))
                except Exception as error:
                    message("Cannot open folder", friendly_error(error, config),
                            "Press any key")
                    wait_key()
                    if remote_path != "/" and parents:
                        remote_path, current_url = parents.pop()
                        selected = 0
                        dirty = True
                        continue
                    status = friendly_error(error, config)
                refresh = False
                dirty = True
            if dirty:
                selected = draw_browser(remote_path, items, selected, status)
                status = ""
                dirty = False
            key = gfx.getch(250)
            if key is None:
                continue
            if key in (gfx.KEY_DOWN, ord("j")) and items:
                next_selected = min(len(items) - 1, selected + 1)
                dirty = next_selected != selected
                selected = next_selected
            elif key in (gfx.KEY_UP, ord("k")) and items:
                next_selected = max(0, selected - 1)
                dirty = next_selected != selected
                selected = next_selected
            elif key == getattr(gfx, "KEY_PAGE_DOWN", -1002) and items:
                next_selected = min(len(items) - 1,
                                    selected + max(1, (gfx.size()[1] - HEADER_H - FOOTER_H) // ROW_H))
                dirty = next_selected != selected
                selected = next_selected
            elif key == getattr(gfx, "KEY_PAGE_UP", -1001) and items:
                next_selected = max(0, selected - max(1, (gfx.size()[1] - HEADER_H - FOOTER_H) // ROW_H))
                dirty = next_selected != selected
                selected = next_selected
            elif key == KEY_ENTER or key == KEY_RETURN:
                if not items:
                    continue
                item = items[selected]
                if item["is_dir"]:
                    parents.append((remote_path, current_url))
                    remote_path = join_path(remote_path, item["name"])
                    current_url = item["url"]
                    selected = 0
                    refresh = True
                else:
                    try:
                        status = selected_download(config, remote_path, item) or "cancelled"
                        dirty = True
                    except Exception as error:
                        message("Download failed", str(error), "Press any key")
                        wait_key()
                        dirty = True
            elif key in (ord("d"), ord("D")) and items:
                chosen = items[selected]
                if chosen["is_dir"]:
                    # Recursive listing uses the same bounded scratch index.
                    # Rebuild this folder afterward even if the transfer fails.
                    refresh = True
                try:
                    status = selected_download(config, remote_path, chosen) or "cancelled"
                    dirty = True
                except Exception as error:
                    message("Download failed", str(error), "Press any key")
                    wait_key()
                    dirty = True
            elif key in (ord("u"), ord("U")):
                try:
                    name = upload_file(config, current_url, pending_upload)
                    pending_upload = ""
                    status = "uploaded " + name if name else "cancelled"
                    refresh = bool(name)
                    dirty = not refresh
                except Exception as error:
                    message("Upload failed", str(error), "Press any key")
                    wait_key()
                    dirty = True
            elif key in (ord("m"), ord("M")):
                try:
                    name = make_folder(config, current_url)
                    status = "created folder " + name if name else "cancelled"
                    refresh = bool(name)
                    dirty = not refresh
                except Exception as error:
                    message("Make folder failed", str(error), "Press any key")
                    wait_key()
                    dirty = True
            elif key in (ord("r"), ord("R")):
                refresh = True
            elif key in (ord("c"), ord("C")):
                chosen = choose_server(state, selected_server)
                if chosen is not None:
                    selected_server = chosen
                    config = state["servers"][selected_server]
                    remote_path = "/"
                    current_url = remote_url(config, "/")
                    parents = []
                    selected = 0
                    refresh = True
                    status = "connected to " + config["name"]
                else:
                    dirty = True
            elif key == gfx.KEY_ESCAPE or key in (ord("q"), ord("Q"), gfx.KEY_LEFT):
                if remote_path == "/":
                    break
                if parents:
                    remote_path, current_url = parents.pop()
                else:
                    remote_path = "/"
                    current_url = remote_url(config, "/")
                selected = 0
                refresh = True
    except KeyboardInterrupt:
        pass
    except Exception as error:
        message("Application error", str(error), "Press any key")
        wait_key()
    finally:
        remove_if_present(LIST_PATH)
        remove_if_present(LIST_ITEMS_PATH)
        remove_if_present(LIST_STAGE_PATH)
        remove_if_present(LIST_STAGE_ITEMS_PATH)
        remove_if_present(LIST_BACKUP_ITEMS_PATH)
        remove_if_present(FOLDER_PLAN_PATH)
        gc.collect()


if __name__ == "__main__":
    main()
