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


def age(timestamp, now):
    try:
        seconds = max(0, int(now) - int(timestamp))
    except Exception:
        return ""
    if seconds < 3600:
        return "{}m".format(max(1, seconds // 60))
    if seconds < 86400:
        return "{}h".format(seconds // 3600)
    return "{}d".format(seconds // 86400)


def show_message(title, message, footer="Please wait"):
    rows, cols = tui.size()
    tui.clear()
    tui.addstr(0, 0, clip(" " + title + " ", cols), tui.INVERSE)
    row = 2
    for line in wrap(message, cols - 2):
        if row >= rows - 1:
            break
        tui.addstr(row, 1, line)
        row += 1
    tui.addstr(rows - 1, 0, clip(footer, cols), tui.INVERSE)
    tui.refresh()


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
    value = json.loads(body.decode("utf-8"))
    body = None
    response = None
    gc.collect()
    return value


def fetch_item(item_id):
    item = request_json("item/{}.json".format(int(item_id)))
    return item if isinstance(item, dict) else {}


def fetch_stories(feed_key):
    ids = request_json(feed_key + ".json")
    if not isinstance(ids, list):
        raise RuntimeError("invalid story list")
    stories = []
    for number, item_id in enumerate(ids[:STORY_LIMIT]):
        show_message("Hacker News", "Loading story {} of {}".format(
            number + 1, min(STORY_LIMIT, len(ids))))
        item = fetch_item(item_id)
        if item.get("type") in ("story", "job", "poll") and not item.get("dead"):
            stories.append(item)
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


def load_children(parent, progress_title="Discussion"):
    if parent.get("loaded"):
        parent["collapsed"] = False
        return
    children = []
    ids = parent.get("kid_ids", [])
    for number, item_id in enumerate(ids):
        show_message(progress_title, "Loading reply {} of {}".format(
            number + 1, len(ids)))
        item = fetch_item(item_id)
        if item and not item.get("dead"):
            children.append(node_from_item(item, parent.get("depth", -1) + 1))
    parent["children"] = children
    parent["loaded"] = True
    parent["collapsed"] = False
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


def draw_stories(stories, selected, feed_name, note=""):
    rows, cols = tui.size()
    tui.clear()
    title = " HN: " + feed_name + " "
    if note:
        title += "| " + note + " "
    tui.addstr(0, 0, clip(title, cols), tui.INVERSE)
    height = 3
    visible = max(1, (rows - 2) // height)
    start = (selected // visible) * visible
    row = 1
    for index in range(start, min(len(stories), start + visible)):
        story = stories[index]
        prefix = "> " if index == selected else "  "
        attr = tui.INVERSE if index == selected else tui.BOLD
        tui.addstr(row, 0, clip(prefix + story.get("title", "Untitled"), cols), attr)
        meta = "{} pts  {}  {} comments".format(
            story.get("score", 0), story.get("by", "?"),
            story.get("descendants", 0))
        host = domain(story.get("url", "")) or "news.ycombinator.com"
        tui.addstr(row + 1, 2, clip(meta + "  " + host, cols - 2))
        row += height
    if not stories:
        tui.addstr(3, 2, "No stories loaded. Press r to retry.")
    tui.addstr(rows - 1, 0,
               clip("Up/Down Enter comments  f feed  r refresh  q quit", cols),
               tui.INVERSE)
    tui.refresh()


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


def draw_thread(story, root, selected):
    rows, cols = tui.size()
    nodes = visible_nodes(root)
    selected = min(selected, max(0, len(nodes) - 1))
    tui.clear()
    tui.addstr(0, 0, clip(" " + story.get("title", "Discussion") + " ", cols),
               tui.INVERSE)
    available = rows - 3
    before = max(0, selected - max(1, available // 4))
    rendered = []
    selected_row = 0
    for index in range(before, len(nodes)):
        block = comment_lines(nodes[index], cols, index == selected)
        if index == selected:
            selected_row = len(rendered)
        rendered.extend(block)
        rendered.append((0, "-" * cols, 0))
        if len(rendered) >= available and index >= selected:
            break
    if selected_row >= available:
        rendered = rendered[selected_row:selected_row + available]
    row = 1
    for indent, line, attr in rendered[:available]:
        tui.addstr(row, indent, clip(line, cols - indent), attr)
        row += 1
    count = "{} visible / {} total".format(len(nodes), story.get("descendants", 0))
    tui.addstr(rows - 2, 1, clip(count, cols - 2))
    tui.addstr(rows - 1, 0,
               clip("Up/Down PgUp/PgDn  Enter +/- replies  Esc back", cols),
               tui.INVERSE)
    tui.refresh()
    return nodes, selected


def show_thread(story):
    root = {"depth": -1, "kid_ids": story.get("kids", [])[:CHILD_LIMIT],
            "children": [], "loaded": False, "collapsed": False}
    try:
        load_children(root, "Discussion")
    except Exception as error:
        show_message("Could not load comments", str(error), "Press any key")
        wait_key()
        return
    selected = 0
    dirty = True
    while not solaros.should_exit():
        if dirty:
            nodes, selected = draw_thread(story, root, selected)
            dirty = False
        key = tui.getch(250)
        if key is None:
            continue
        if key in (tui.KEY_ESCAPE, tui.KEY_LEFT, ord("q")):
            return
        if key == tui.KEY_DOWN and selected + 1 < len(nodes):
            selected += 1
            dirty = True
        elif key == tui.KEY_UP and selected > 0:
            selected -= 1
            dirty = True
        elif key == tui.KEY_PAGE_DOWN and nodes:
            selected = min(len(nodes) - 1, selected + max(1, tui.size()[0] // 3))
            dirty = True
        elif key == tui.KEY_PAGE_UP:
            selected = max(0, selected - max(1, tui.size()[0] // 3))
            dirty = True
        elif key == tui.KEY_HOME:
            selected = 0
            dirty = True
        elif key == tui.KEY_END and nodes:
            selected = len(nodes) - 1
            dirty = True
        elif key in (KEY_ENTER, KEY_RETURN, tui.KEY_RIGHT, ord(" ")) and nodes:
            node = nodes[selected]
            if node.get("kid_ids"):
                try:
                    if not node.get("loaded"):
                        load_children(node)
                    else:
                        node["collapsed"] = not node.get("collapsed")
                except Exception as error:
                    show_message("Could not load replies", str(error), "Press any key")
                    wait_key()
                dirty = True
        elif key == ord("r"):
            return show_thread(story)


def main():
    feed_index = 0
    stories = []
    selected = 0
    note = ""
    refresh = True
    while not solaros.should_exit():
        if refresh:
            try:
                stories = fetch_stories(FEEDS[feed_index][1])
                selected = 0
                note = ""
            except Exception as error:
                note = "refresh failed: " + str(error)
            refresh = False
        draw_stories(stories, selected, FEEDS[feed_index][0], note)
        note = ""
        key = tui.getch(250)
        if key is None:
            continue
        if key in (tui.KEY_ESCAPE, tui.KEY_LEFT, ord("q")):
            return
        if key == tui.KEY_DOWN and selected + 1 < len(stories):
            selected += 1
        elif key == tui.KEY_UP and selected > 0:
            selected -= 1
        elif key == tui.KEY_PAGE_DOWN and stories:
            selected = min(len(stories) - 1, selected + max(1, tui.size()[0] // 3))
        elif key == tui.KEY_PAGE_UP:
            selected = max(0, selected - max(1, tui.size()[0] // 3))
        elif key in (KEY_ENTER, KEY_RETURN, tui.KEY_RIGHT) and stories:
            show_thread(stories[selected])
        elif key == ord("f"):
            feed_index = (feed_index + 1) % len(FEEDS)
            refresh = True
        elif key == ord("r"):
            refresh = True


try:
    main()
except Exception as error:
    show_message("Hacker News error", str(error), "Press any key")
    wait_key()
