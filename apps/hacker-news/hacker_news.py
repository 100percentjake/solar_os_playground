"""Read-only Hacker News story and comment browser for SolarOS MicroPython."""

import gc
import json

import solaros
from solaros import tui


API = "https://hacker-news.firebaseio.com/v0/"
FEEDS = [
    ("Top", "topstories"),
    ("Best", "beststories"),
    ("New", "newstories"),
    ("Ask", "askstories"),
    ("Show", "showstories"),
]
STORY_LIMIT = 20
CHILD_LIMIT = 30
HTTP_LIMIT = 48 * 1024
COMMENT_TEXT_LIMIT = 1800
KEY_ENTER = 10
KEY_RETURN = 13
SMALL_INT_MAX = "1073741823"
SMALL_INT_MIN_ABS = "1073741824"
LAST_FRAME = []


def clean_space(value):
    if not isinstance(value, str):
        return ""
    return " ".join(value.replace("\r", " ").replace("\n", " ").split())


def clip(value, width):
    value = clean_space(value)
    if width < 1:
        return ""
    if len(value) <= width:
        return value
    return value[:max(0, width - 1)] + "~"


def decode_entities(text):
    named = {"amp": "&", "lt": "<", "gt": ">", "quot": '"',
             "apos": "'", "nbsp": " ", "#x27": "'", "#39": "'"}
    result = []
    at = 0
    while at < len(text):
        if text[at] != "&":
            result.append(text[at])
            at += 1
            continue
        end = text.find(";", at + 1, at + 14)
        if end < 0:
            result.append("&")
            at += 1
            continue
        name = text[at + 1:end]
        value = named.get(name)
        if value is None and name.startswith("#"):
            try:
                value = chr(int(name[2:], 16) if name[:2].lower() == "#x"
                            else int(name[1:]))
            except Exception:
                value = None
        result.append(value if value is not None else text[at:end + 1])
        at = end + 1
    return "".join(result)


def html_to_text(value):
    """Render the deliberately small HTML subset used by HN comments."""
    if not isinstance(value, str):
        return ""
    output = []
    at = 0
    while at < len(value):
        if value[at] != "<":
            output.append(value[at])
            at += 1
            continue
        end = value.find(">", at + 1)
        if end < 0:
            break
        tag = value[at + 1:end].strip().lower()
        if (tag.startswith("p") or tag.startswith("br") or
                tag.startswith("/pre") or tag.startswith("pre")):
            output.append("\n")
        at = end + 1
    lines = []
    for raw in decode_entities("".join(output)).replace("\xa0", " ").split("\n"):
        line = clean_space(raw)
        if line:
            lines.append(line)
        elif lines and lines[-1] != "":
            lines.append("")
    return "\n".join(lines).strip()


def wrap(value, width):
    if width < 1:
        return []
    result = []
    for paragraph in str(value or "").replace("\r", "").split("\n"):
        paragraph = clean_space(paragraph)
        if not paragraph:
            if result and result[-1] != "":
                result.append("")
            continue
        while len(paragraph) > width:
            cut = paragraph.rfind(" ", 0, width + 1)
            if cut < 1:
                cut = width
            result.append(paragraph[:cut])
            paragraph = paragraph[cut:].lstrip()
        result.append(paragraph)
    return result or [""]


def domain(url):
    value = clean_space(url)
    marker = value.find("://")
    if marker >= 0:
        value = value[marker + 3:]
    value = value.split("/")[0].split("?")[0]
    return value[4:] if value.startswith("www.") else value


def large_integer(token):
    negative = token.startswith("-")
    digits = token[1:] if negative else token
    digits = digits.lstrip("0") or "0"
    limit = SMALL_INT_MIN_ABS if negative else SMALL_INT_MAX
    return len(digits) > len(limit) or (len(digits) == len(limit) and digits > limit)


def quote_large_integers(source):
    """Protect SolarOS's small-int-only JSON decoder from large integers."""
    output = []
    index = 0
    in_string = False
    escaped = False
    length = len(source)
    while index < length:
        character = source[index]
        if in_string:
            output.append(character)
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            index += 1
            continue
        if character == '"':
            in_string = True
            output.append(character)
            index += 1
            continue
        if character == "-" or (character >= "0" and character <= "9"):
            start = index
            if character == "-":
                index += 1
                if index >= length or source[index] < "0" or source[index] > "9":
                    output.append(character)
                    continue
            while index < length and source[index] >= "0" and source[index] <= "9":
                index += 1
            integer_end = index
            if index < length and source[index] == ".":
                index += 1
                while index < length and source[index] >= "0" and source[index] <= "9":
                    index += 1
            if index < length and source[index] in "eE":
                index += 1
                if index < length and source[index] in "+-":
                    index += 1
                while index < length and source[index] >= "0" and source[index] <= "9":
                    index += 1
            token = source[start:index]
            if integer_end == index and large_integer(token):
                output.extend(('"', token, '"'))
            else:
                output.append(token)
            continue
        output.append(character)
        index += 1
    return "".join(output)


def safe_json_loads(source):
    if isinstance(source, bytes):
        source = source.decode("utf-8")
    return json.loads(quote_large_integers(source))


def present_frame(frame, rows, cols):
    """Write only changed rows, without ever presenting a cleared frame."""
    global LAST_FRAME
    normalized = []
    for row in range(rows):
        text, attr = frame[row] if row < len(frame) else ("", 0)
        text = str(text or "")
        padded = (text[:cols] + (" " * cols))[:cols]
        normalized.append((padded, attr))
        if row >= len(LAST_FRAME) or LAST_FRAME[row] != normalized[-1]:
            tui.addstr(row, 0, padded, attr)
    LAST_FRAME = normalized
    tui.refresh()


def show_message(title, message, footer="Please wait"):
    rows, cols = tui.size()
    frame = [("", 0) for unused in range(rows)]
    frame[0] = (clip(" " + title + " ", cols), tui.INVERSE)
    row = 2
    for line in wrap(message, cols - 2):
        if row >= rows - 1:
            break
        frame[row] = (" " + line, 0)
        row += 1
    frame[rows - 1] = (clip(footer, cols), tui.INVERSE)
    present_frame(frame, rows, cols)


def wait_key():
    while not solaros.should_exit():
        key = tui.getch(250)
        if key is not None:
            return key
    return tui.KEY_ESCAPE


def request_json(path):
    response = solaros.http.get(
        API + path, {"Accept": "application/json"}, 20000, HTTP_LIMIT, False)
    status = response.get("status_code", 0)
    if status < 200 or status >= 300:
        raise RuntimeError("HTTP {}".format(status))
    if response.get("truncated"):
        raise RuntimeError("response too large")
    body = response.get("body", b"")
    value = safe_json_loads(body)
    body = None
    response = None
    gc.collect()
    return value


def fetch_item(item_id):
    item_id = str(item_id)
    if not item_id or any(character < "0" or character > "9"
                          for character in item_id):
        raise RuntimeError("invalid item id")
    item = request_json("item/{}.json".format(item_id))
    return item if isinstance(item, dict) else {}


def fetch_stories(feed_key, feed_name, scroll=0):
    ids = request_json(feed_key + ".json")
    if not isinstance(ids, list):
        raise RuntimeError("invalid story list")
    stories = []
    wanted = min(STORY_LIMIT, len(ids))
    draw_stories(stories, scroll, feed_name, loading=(0, wanted))
    for number, item_id in enumerate(ids[:wanted]):
        item = fetch_item(item_id)
        if item.get("type") in ("story", "job", "poll") and not item.get("dead"):
            stories.append(item)
        draw_stories(stories, scroll, feed_name, loading=(number + 1, wanted))
    return stories


def node_from_item(item, depth):
    kids = item.get("kids", [])
    if not isinstance(kids, list):
        kids = []
    return {
        "id": item.get("id", 0),
        "by": clean_space(item.get("by", "[deleted]")),
        "time": item.get("time", 0),
        "text": html_to_text(item.get("text", ""))[:COMMENT_TEXT_LIMIT],
        "depth": depth,
        "kid_ids": kids[:CHILD_LIMIT],
        "children": [],
        "loaded": False,
        "collapsed": False,
        "deleted": bool(item.get("deleted")),
    }


def load_children(parent, progress=None):
    if parent.get("loaded"):
        parent["collapsed"] = False
        return
    children = []
    parent["children"] = children
    parent["loaded"] = True
    parent["collapsed"] = False
    ids = parent.get("kid_ids", [])
    if progress:
        progress(0, len(ids))
    for number, item_id in enumerate(ids):
        item = fetch_item(item_id)
        if item and not item.get("dead"):
            children.append(node_from_item(item, parent.get("depth", -1) + 1))
        if progress:
            progress(number + 1, len(ids))
    gc.collect()


def visible_nodes(root):
    result = []
    stack = list(reversed(root.get("children", [])))
    while stack:
        node = stack.pop()
        result.append(node)
        if node.get("loaded") and not node.get("collapsed"):
            for child in reversed(node.get("children", [])):
                stack.append(child)
    return result


def progress_text(cols, label, done, total):
    total = max(1, total)
    done = min(total, max(0, done))
    count = "{} {}/{} ".format(label, done, total)
    width = max(1, cols - len(count) - 2)
    filled = (done * width) // total
    bar = "[" + ("#" * filled) + ("-" * (width - filled)) + "]"
    return clip(count + bar, cols)


def item_at_line(starts, line):
    if not starts:
        return 0
    selected = 0
    for index, start in enumerate(starts):
        if start > line:
            break
        selected = index
    return selected


def adjacent_item_line(starts, line, direction):
    if not starts:
        return 0
    selected = item_at_line(starts, line)
    if direction > 0:
        selected = min(len(starts) - 1, selected + 1)
    elif line == starts[selected] and selected > 0:
        selected -= 1
    return starts[selected]


def story_render(story, cols, selected):
    title_width = max(8, cols - 2)
    title_lines = wrap(story.get("title", "Untitled"), title_width)
    rendered = []
    for number, line in enumerate(title_lines):
        prefix = "> " if selected and number == 0 else "  "
        rendered.append((0, prefix + line,
                         tui.INVERSE if selected else tui.BOLD))
    meta = "{} pts  {}  {} comments".format(
        story.get("score", 0), story.get("by", "?"),
        story.get("descendants", 0))
    host = domain(story.get("url", "")) or "news.ycombinator.com"
    rendered.append((2, clip(meta + "  " + host, cols - 2), 0))
    rendered.append((0, "-" * cols, 0))
    return rendered


def story_document(stories, cols, selected):
    rendered = []
    starts = []
    for index, story in enumerate(stories):
        starts.append(len(rendered))
        rendered.extend(story_render(story, cols, index == selected))
    return rendered, starts


def draw_stories(stories, scroll, feed_name, note="", loading=None):
    rows, cols = tui.size()
    frame = [("", 0) for unused in range(rows)]
    title = " HN: " + feed_name + " "
    if note:
        title += "| " + note + " "
    frame[0] = (clip(title, cols), tui.INVERSE)
    plain, starts = story_document(stories, cols, -1)
    maximum = max(0, len(plain) - 1)
    scroll = min(maximum, max(0, scroll))
    selected = item_at_line(starts, scroll)
    rendered, starts = story_document(stories, cols, selected)
    row = 1
    for indent, line, attr in rendered[scroll:scroll + rows - 2]:
        frame[row] = ((" " * indent) + clip(line, cols - indent), attr)
        row += 1
    if not stories:
        frame[3] = ("  No stories loaded. Press r to retry.", 0)
    if loading:
        frame[rows - 1] = (
            progress_text(cols, "Stories", loading[0], loading[1]), tui.INVERSE)
    else:
        frame[rows - 1] = (
            clip("Up/Down line  PgUp/PgDn story  Enter open", cols), tui.INVERSE)
    present_frame(frame, rows, cols)
    return scroll, selected, starts, maximum


def comment_lines(node, cols, selected):
    depth = node.get("depth", 0)
    indent = min(depth * 2, max(0, cols // 3))
    width = max(8, cols - indent - 1)
    kids = len(node.get("kid_ids", []))
    if kids:
        marker = "+" if node.get("collapsed") or not node.get("loaded") else "-"
        state = " {}{}".format(marker, kids)
    else:
        state = ""
    head = ("> " if selected else "  ") + node.get("by", "[deleted]") + state
    text = node.get("text") or "[deleted]"
    lines = [(indent, clip(head, width), tui.INVERSE if selected else tui.BOLD)]
    for line in wrap(text, width):
        lines.append((indent, line, 0))
    return lines


def thread_document(nodes, cols, selected):
    rendered = []
    starts = []
    for index, node in enumerate(nodes):
        starts.append(len(rendered))
        rendered.extend(comment_lines(node, cols, index == selected))
        rendered.append((0, "-" * cols, 0))
    return rendered, starts


def draw_thread(story, root, scroll, loading=None):
    rows, cols = tui.size()
    nodes = visible_nodes(root)
    plain, starts = thread_document(nodes, cols, -1)
    maximum = max(0, len(plain) - 1)
    scroll = min(maximum, max(0, scroll))
    selected = item_at_line(starts, scroll)
    rendered, starts = thread_document(nodes, cols, selected)
    frame = [("", 0) for unused in range(rows)]
    frame[0] = (clip(" " + story.get("title", "Discussion") + " ", cols),
                tui.INVERSE)
    available = rows - 2
    row = 1
    for indent, line, attr in rendered[scroll:scroll + available]:
        frame[row] = ((" " * indent) + clip(line, cols - indent), attr)
        row += 1
    if loading:
        frame[rows - 1] = (
            progress_text(cols, "Comments", loading[0], loading[1]), tui.INVERSE)
    else:
        frame[rows - 1] = (
            clip("Up/Down line  PgUp/PgDn comment  Enter +/-", cols), tui.INVERSE)
    present_frame(frame, rows, cols)
    return nodes, scroll, selected, starts, maximum


def show_thread(story, initial_scroll=0):
    root = {"depth": -1, "kid_ids": story.get("kids", [])[:CHILD_LIMIT],
            "children": [], "loaded": False, "collapsed": False}
    try:
        load_children(root, lambda done, total:
                      draw_thread(story, root, initial_scroll,
                                  (done, total)))
    except Exception as error:
        show_message("Could not load comments", str(error), "Press any key")
        wait_key()
        return
    scroll = initial_scroll
    dirty = True
    while not solaros.should_exit():
        if dirty:
            nodes, scroll, selected, starts, maximum = draw_thread(
                story, root, scroll)
            dirty = False
        key = tui.getch(250)
        if key is None:
            continue
        if key in (tui.KEY_ESCAPE, tui.KEY_LEFT, ord("q")):
            return
        if key == tui.KEY_DOWN and scroll < maximum:
            scroll += 1
            dirty = True
        elif key == tui.KEY_UP and scroll > 0:
            scroll -= 1
            dirty = True
        elif key == tui.KEY_PAGE_DOWN and nodes:
            scroll = adjacent_item_line(starts, scroll, 1)
            dirty = True
        elif key == tui.KEY_PAGE_UP:
            scroll = adjacent_item_line(starts, scroll, -1)
            dirty = True
        elif key == tui.KEY_HOME:
            scroll = 0
            dirty = True
        elif key == tui.KEY_END and nodes:
            scroll = maximum
            dirty = True
        elif key in (KEY_ENTER, KEY_RETURN, tui.KEY_RIGHT, ord(" ")) and nodes:
            node = nodes[selected]
            if node.get("kid_ids"):
                try:
                    if not node.get("loaded"):
                        load_children(node, lambda done, total:
                                      draw_thread(story, root, scroll,
                                                  (done, total)))
                    else:
                        node["collapsed"] = not node.get("collapsed")
                except Exception as error:
                    show_message("Could not load replies", str(error), "Press any key")
                    wait_key()
                dirty = True
        elif key == ord("r"):
            return show_thread(story, scroll)


def main():
    feed_index = 0
    stories = []
    scroll = 0
    note = ""
    refresh = True
    dirty = True
    while not solaros.should_exit():
        if refresh:
            try:
                stories = fetch_stories(
                    FEEDS[feed_index][1], FEEDS[feed_index][0], scroll)
                note = ""
            except Exception as error:
                note = "refresh failed: " + str(error)
            refresh = False
            dirty = True
        if dirty:
            scroll, selected, starts, maximum = draw_stories(
                stories, scroll, FEEDS[feed_index][0], note)
            note = ""
            dirty = False
        key = tui.getch(250)
        if key is None:
            continue
        if key in (tui.KEY_ESCAPE, tui.KEY_LEFT, ord("q")):
            return
        if key == tui.KEY_DOWN and scroll < maximum:
            scroll += 1
            dirty = True
        elif key == tui.KEY_UP and scroll > 0:
            scroll -= 1
            dirty = True
        elif key == tui.KEY_PAGE_DOWN and stories:
            scroll = adjacent_item_line(starts, scroll, 1)
            dirty = True
        elif key == tui.KEY_PAGE_UP:
            scroll = adjacent_item_line(starts, scroll, -1)
            dirty = True
        elif key in (KEY_ENTER, KEY_RETURN, tui.KEY_RIGHT) and stories:
            show_thread(stories[selected])
            dirty = True
        elif key == ord("f"):
            feed_index = (feed_index + 1) % len(FEEDS)
            scroll = 0
            refresh = True
        elif key == ord("r"):
            refresh = True


try:
    main()
except Exception as error:
    show_message("Hacker News error", str(error), "Press any key")
    wait_key()
