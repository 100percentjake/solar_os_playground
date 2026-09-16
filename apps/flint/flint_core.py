"""Portable text and metadata helpers for the SolarOS Flint app."""


INDEX_VERSION = 1
MAX_NOTES = 512
MAX_NOTE_BYTES = 32768
MAX_TITLE = 100
MAX_PATH = 240
MAX_TAGS = 16
MAX_LINKS = 32
MAX_TAG = 40
MAX_BLOCK = 4096


def unsafe_character(code):
    return (code < 32 or 127 <= code <= 159 or
            0x200B <= code <= 0x200F or 0x202A <= code <= 0x202E or
            0x2060 <= code <= 0x206F or code == 0xFEFF or
            0xD800 <= code <= 0xDFFF)


def clean_line(value, limit=MAX_TITLE):
    if not isinstance(value, str):
        return ""
    output = []
    for char in value:
        code = ord(char)
        output.append(" " if unsafe_character(code) else char)
    return " ".join("".join(output).split())[:limit]


def clean_document(value, limit=MAX_NOTE_BYTES):
    if not isinstance(value, str):
        return ""
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    output = []
    for char in value[:limit]:
        code = ord(char)
        if char in ("\n", "\t"):
            output.append(char)
        elif unsafe_character(code):
            output.append(" ")
        else:
            output.append(char)
    return "".join(output)


def utf8_size(value, stop_after=0):
    """Count encoded bytes without allocating a second UTF-8 copy."""
    if not isinstance(value, str):
        return 0
    total = 0
    for char in value:
        code = ord(char)
        if code <= 0x7F:
            total += 1
        elif code <= 0x7FF:
            total += 2
        elif code <= 0xFFFF:
            total += 3
        else:
            total += 4
        if stop_after and total > stop_after:
            return total
    return total


def letter_or_digit(char):
    """MicroPython EXTRA omits str.isalnum(); keep this allocation-free."""
    if not char:
        return False
    code = ord(char)
    return (48 <= code <= 57 or 65 <= code <= 90 or 97 <= code <= 122 or
            code >= 160 and not unsafe_character(code))


def all_digits(value):
    if not value:
        return False
    for char in value:
        code = ord(char)
        if code < 48 or code > 57:
            return False
    return True


def normalize_path(path):
    if not isinstance(path, str):
        return ""
    path = path.replace("\\", "/")
    absolute = path.startswith("/")
    parts = []
    for part in path.split("/"):
        if not part or part == ".":
            continue
        if part == "..":
            if parts:
                parts.pop()
            elif not absolute:
                return ""
        else:
            parts.append(part)
    result = "/".join(parts)
    if absolute:
        result = "/" + result
    return result if len(result) <= MAX_PATH else ""


def inside(root, path):
    root = normalize_path(root)
    path = normalize_path(path)
    if root == "/":
        return path.startswith("/")
    root = root.rstrip("/")
    return bool(root and (path == root or path.startswith(root + "/")))


def safe_filename(value, fallback="Untitled"):
    value = clean_line(value, MAX_TITLE)
    output = []
    for char in value:
        code = ord(char)
        if (48 <= code <= 57 or 65 <= code <= 90 or 97 <= code <= 122 or
                char in ("-", "_", " ")):
            output.append(char)
        else:
            output.append("-")
    value = "".join(output).strip(" .-_")
    while "  " in value:
        value = value.replace("  ", " ")
    while "- -" in value:
        value = value.replace("- -", "-")
    while "--" in value:
        value = value.replace("--", "-")
    return (value or fallback)[:64]


def basename(path):
    path = normalize_path(path)
    return path.rsplit("/", 1)[-1]


def dirname(path):
    path = normalize_path(path)
    if "/" not in path.rstrip("/"):
        return "/" if path.startswith("/") else ""
    result = path.rstrip("/").rsplit("/", 1)[0]
    return result or "/"


def stem(path):
    name = basename(path)
    lowered = name.lower()
    for suffix in (".markdown", ".md", ".txt"):
        if lowered.endswith(suffix):
            return name[:-len(suffix)]
    return name


def is_note_path(path):
    lowered = basename(path).lower()
    return lowered.endswith(".md") or lowered.endswith(".markdown") or lowered.endswith(".txt")


def split_blocks(text):
    """Split Markdown on blank lines without discarding multi-line blocks."""
    text = clean_document(text)
    blocks = []
    current = []
    in_fence = False
    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped and not in_fence:
            if current:
                blocks.append("\n".join(current).rstrip())
                current = []
        else:
            current.append(line.rstrip())
        if stripped.startswith("```"):
            in_fence = not in_fence
    if current:
        blocks.append("\n".join(current).rstrip())
    return blocks


def join_blocks(blocks):
    clean = []
    for block in blocks:
        value = clean_document(block, MAX_BLOCK).strip("\n")
        if value.strip():
            clean.append(value)
    return "\n\n".join(clean).rstrip() + ("\n" if clean else "")


def extract_title(text, path=""):
    in_fence = False
    for line in clean_document(text, 4096).split("\n"):
        stripped = line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if not in_fence and stripped.startswith("#"):
            title = clean_line(stripped.lstrip("#").strip(), MAX_TITLE)
            if title:
                return title
    return clean_line(stem(path).replace("_", " ").replace("-", " "), MAX_TITLE) or "Untitled"


def _tag_character(char):
    return letter_or_digit(char) or char in ("-", "_", "/")


def extract_tags(text):
    tags = []
    seen = {}
    text = clean_document(text)
    index = 0
    in_code = False
    while index < len(text):
        if text.startswith("```", index):
            in_code = not in_code
            index += 3
            continue
        if not in_code and text[index] == "#" and (index == 0 or not _tag_character(text[index - 1])):
            end = index + 1
            while end < len(text) and _tag_character(text[end]):
                end += 1
            tag = clean_line(text[index + 1:end], MAX_TAG).lower()
            if tag and tag not in seen and not all_digits(tag):
                seen[tag] = True
                tags.append(tag)
                if len(tags) >= MAX_TAGS:
                    break
            index = end
        else:
            index += 1
    return tags


def extract_links(text):
    links = []
    seen = {}
    in_code = False
    for line in clean_document(text).split("\n"):
        if line.strip().startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        index = 0
        in_inline_code = False
        while index < len(line) - 1:
            if line[index] == "`":
                in_inline_code = not in_inline_code
                index += 1
                continue
            if in_inline_code or not line.startswith("[[", index):
                index += 1
                continue
            end = line.find("]]", index + 2)
            if end < 0:
                break
            raw = line[index + 2:end]
            target = raw.split("|", 1)[0].split("#", 1)[0]
            target = clean_line(target, MAX_TITLE)
            key = target.lower()
            if target and key not in seen:
                seen[key] = True
                links.append(target)
                if len(links) >= MAX_LINKS:
                    return links
            index = end + 2
    return links


def link_items(text):
    items = []
    in_code = False
    for line in clean_document(text).split("\n"):
        if line.strip().startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        index = 0
        in_inline_code = False
        while index < len(line) - 1:
            if line[index] == "`":
                in_inline_code = not in_inline_code
                index += 1
                continue
            if in_inline_code or not line.startswith("[[", index):
                index += 1
                continue
            end = line.find("]]", index + 2)
            if end < 0:
                break
            raw = line[index + 2:end]
            pieces = raw.split("|", 1)
            target_with_heading = clean_line(pieces[0], MAX_TITLE)
            target_parts = target_with_heading.split("#", 1)
            target = target_parts[0]
            heading = clean_line(target_parts[1], MAX_TITLE) if len(target_parts) > 1 else ""
            label = clean_line(pieces[1] if len(pieces) > 1 else target_with_heading, MAX_TITLE)
            if target:
                items.append({"target": target, "heading": heading,
                              "label": label or target})
                if len(items) >= MAX_LINKS:
                    return items
            index = end + 2
    return items


def strip_inline(text):
    """Produce readable plain text without attempting full Markdown parsing."""
    text = clean_line(text, MAX_NOTE_BYTES)
    output = []
    index = 0
    while index < len(text):
        if text.startswith("![[", index):
            end = text.find("]]", index + 3)
            if end >= 0:
                label = clean_line(text[index + 3:end], 80)
                output.append("[Image omitted" + (": " + label if label else "") + "]")
                index = end + 2
                continue
        if text.startswith("![", index):
            middle = text.find("](", index + 2)
            end = text.find(")", middle + 2) if middle >= 0 else -1
            if middle >= 0 and end >= 0:
                alt = clean_line(text[index + 2:middle], 80)
                output.append("[Image omitted" + (": " + alt if alt else "") + "]")
                index = end + 1
                continue
        if text.startswith("[[", index):
            end = text.find("]]", index + 2)
            if end >= 0:
                raw = text[index + 2:end]
                pieces = raw.split("|", 1)
                output.append(clean_line(pieces[-1], MAX_TITLE))
                index = end + 2
                continue
        if text[index] == "[":
            middle = text.find("](", index + 1)
            end = text.find(")", middle + 2) if middle >= 0 else -1
            if middle >= 0 and end >= 0:
                output.append(text[index + 1:middle])
                index = end + 1
                continue
        if text[index] in ("*", "_", "`", "~"):
            index += 1
            continue
        output.append(text[index])
        index += 1
    return clean_line("".join(output), MAX_NOTE_BYTES)


def preview(text, limit=140):
    for block in split_blocks(text):
        value = block.strip()
        if value.startswith("#"):
            continue
        plain = strip_inline(value)
        if plain:
            return plain[:limit]
    return ""


def metadata(path, text, size=0):
    return {
        "path": normalize_path(path),
        "title": extract_title(text, path),
        "tags": extract_tags(text),
        "links": extract_links(text),
        "preview": preview(text),
        "size": max(0, min(int(size) if isinstance(size, int) else 0, MAX_NOTE_BYTES)),
    }


def normalize_metadata(value):
    if not isinstance(value, dict):
        return None
    path = normalize_path(value.get("path", ""))
    if not is_note_path(path):
        return None
    title = clean_line(value.get("title", ""), MAX_TITLE) or extract_title("", path)
    tags = []
    for item in value.get("tags", []) if isinstance(value.get("tags"), list) else []:
        item = clean_line(item, MAX_TAG).lower()
        if item and item not in tags:
            tags.append(item)
            if len(tags) >= MAX_TAGS:
                break
    links = []
    seen_links = {}
    for item in value.get("links", []) if isinstance(value.get("links"), list) else []:
        item = clean_line(item, MAX_TITLE)
        key = item.lower()
        if item and key not in seen_links:
            seen_links[key] = True
            links.append(item)
            if len(links) >= MAX_LINKS:
                break
    return {"path": path, "title": title, "tags": tags, "links": links,
            "preview": clean_line(value.get("preview", ""), 140),
            "size": max(0, min(value.get("size", 0), MAX_NOTE_BYTES))
                    if isinstance(value.get("size", 0), int) else 0}


def normalize_index(value, root):
    result = {"version": INDEX_VERSION, "notes": [], "favorites": [], "recent": [],
              "folders": [], "root": normalize_path(root)}
    if not isinstance(value, dict):
        return result
    seen = {}
    raw_notes = value.get("notes", [])
    if isinstance(raw_notes, list):
        for raw in raw_notes:
            item = normalize_metadata(raw)
            if item and inside(root, item["path"]) and item["path"].lower() not in seen:
                seen[item["path"].lower()] = True
                result["notes"].append(item)
                if len(result["notes"]) >= MAX_NOTES:
                    break
    raw_favorites = value.get("favorites", [])
    if isinstance(raw_favorites, list):
        for raw in raw_favorites:
            path = normalize_path(raw)
            if inside(root, path) and path.lower() in seen and path not in result["favorites"]:
                result["favorites"].append(path)
    raw_recent = value.get("recent", [])
    if isinstance(raw_recent, list):
        for raw in raw_recent:
            path = normalize_path(raw)
            if (inside(root, path) and path.lower() in seen and
                    path not in result["recent"]):
                result["recent"].append(path)
                if len(result["recent"]) >= 20:
                    break
    raw_folders = value.get("folders", [])
    seen_folders = {}
    if isinstance(raw_folders, list):
        for raw in raw_folders:
            path = normalize_path(raw)
            key = path.lower()
            if (inside(root, path) and path != root and key not in seen_folders):
                seen_folders[key] = True
                result["folders"].append(path)
                if len(result["folders"]) >= MAX_NOTES:
                    break
    return result


def upsert(index, item):
    path = item.get("path", "").lower()
    for position, old in enumerate(index.get("notes", [])):
        if old.get("path", "").lower() == path:
            index["notes"][position] = item
            return
    if len(index.get("notes", [])) >= MAX_NOTES:
        raise ValueError("vault index is full")
    index.setdefault("notes", []).append(item)


def remove_from_index(index, path):
    lowered = normalize_path(path).lower()
    index["notes"] = [item for item in index.get("notes", [])
                      if item.get("path", "").lower() != lowered]
    index["favorites"] = [item for item in index.get("favorites", [])
                          if normalize_path(item).lower() != lowered]
    index["recent"] = [item for item in index.get("recent", [])
                       if normalize_path(item).lower() != lowered]


def touch_recent(index, path):
    path = normalize_path(path)
    old = index.get("recent", [])
    if path and old and normalize_path(old[0]).lower() == path.lower():
        return False
    recent = [item for item in index.get("recent", [])
              if normalize_path(item).lower() != path.lower()]
    if path:
        recent.insert(0, path)
    index["recent"] = recent[:20]
    return index["recent"] != old


def title_key(value):
    return clean_line(value, MAX_TITLE).lower().replace("_", " ").replace("-", " ")


def resolve_links(index, target, current_path=""):
    """Return link matches with relative and same-folder notes first."""
    target = clean_line(target, MAX_TITLE)
    if not target:
        return []
    key = title_key(target)
    target_path = normalize_path(target).lower()
    base = target if target.startswith("/") else dirname(current_path) + "/" + target
    relative = normalize_path(base).lower()
    has_extension = is_note_path(relative)
    relative_paths = (relative,) if has_extension else (
        relative + ".md", relative + ".markdown", relative + ".txt")
    exact = []
    nearby = []
    others = []
    seen = {}
    for item in index.get("notes", []):
        path = item.get("path", "")
        lowered = normalize_path(path).lower()
        if not lowered or lowered in seen:
            continue
        if lowered in relative_paths:
            exact.append(item)
            seen[lowered] = True
        elif title_key(item.get("title", "")) == key or title_key(stem(path)) == key:
            (nearby if dirname(path).lower() == dirname(current_path).lower()
             else others).append(item)
            seen[lowered] = True
        elif target_path and (lowered.endswith("/" + target_path) or
                              (not has_extension and any(lowered.endswith("/" + target_path + suffix)
                                                         for suffix in (".md", ".markdown", ".txt")))):
            others.append(item)
            seen[lowered] = True
    exact.sort(key=lambda item: item.get("path", "").lower())
    nearby.sort(key=lambda item: item.get("path", "").lower())
    others.sort(key=lambda item: item.get("path", "").lower())
    return exact + nearby + others


def resolve_link(index, target, current_path=""):
    candidates = resolve_links(index, target, current_path)
    return candidates[0] if candidates else None


def backlinks(index, path):
    target = None
    for item in index.get("notes", []):
        if item.get("path", "").lower() == normalize_path(path).lower():
            target = item
            break
    if target is None:
        return []
    result = []
    for item in index.get("notes", []):
        if item is target:
            continue
        for link in item.get("links", []):
            matches = resolve_links(index, link, item.get("path", ""))
            if any(match.get("path", "").lower() == path.lower() for match in matches):
                result.append(item)
                break
    result.sort(key=lambda item: item.get("title", "").lower())
    return result


def search_index(index, query):
    query = clean_line(query, MAX_TITLE).lower()
    if not query:
        return []
    result = []
    for item in index.get("notes", []):
        values = [item.get("title", ""), item.get("preview", ""),
                  " ".join(item.get("tags", [])), " ".join(item.get("links", []))]
        if any(query in value.lower() for value in values if isinstance(value, str)):
            result.append(item)
    result.sort(key=lambda item: item.get("title", "").lower())
    return result


def all_tags(index):
    counts = {}
    for item in index.get("notes", []):
        for tag in item.get("tags", []):
            counts[tag] = counts.get(tag, 0) + 1
    result = [{"tag": key, "count": value} for key, value in counts.items()]
    result.sort(key=lambda item: item["tag"])
    return result


def notes_for_tag(index, tag):
    key = clean_line(tag, MAX_TAG).lower()
    result = [item for item in index.get("notes", []) if key in item.get("tags", [])]
    result.sort(key=lambda item: item.get("title", "").lower())
    return result


def rename_links(text, old_title, new_title):
    """Update exact wiki-link targets while preserving aliases and headings."""
    old_key = title_key(old_title)
    text = clean_document(text)
    output = []
    in_fence = False
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            output.append(line)
            continue
        if in_fence:
            output.append(line)
            continue
        changed = []
        index = 0
        in_inline_code = False
        while index < len(line):
            if line[index] == "`":
                in_inline_code = not in_inline_code
                changed.append("`")
                index += 1
                continue
            if in_inline_code or not line.startswith("[[", index):
                changed.append(line[index])
                index += 1
                continue
            end = line.find("]]", index + 2)
            if end < 0:
                changed.append(line[index:])
                break
            changed.append("[[")
            raw = line[index + 2:end]
            alias = ""
            target = raw
            if "|" in target:
                target, alias = target.split("|", 1)
                alias = "|" + alias
            heading = ""
            if "#" in target:
                target, heading = target.split("#", 1)
                heading = "#" + heading
            name = target.rsplit("/", 1)[-1]
            lowered_name = name.lower()
            suffix = (".markdown" if lowered_name.endswith(".markdown") else
                      ".txt" if lowered_name.endswith(".txt") else
                      ".md" if lowered_name.endswith(".md") else "")
            base = name[:-len(suffix)] if suffix else name
            if title_key(base) == old_key:
                prefix = target[:-len(name)] if name else target
                target = prefix + new_title + suffix
            changed.append(target + heading + alias + "]]" )
            index = end + 2
        output.append("".join(changed))
    return "\n".join(output)


def rename_title_heading(text, new_title):
    """Rename the first Markdown heading outside fenced code, wherever it occurs."""
    text = clean_document(text)
    lines = text.split("\n")
    in_fence = False
    for position, line in enumerate(lines):
        stripped = line.lstrip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence or not stripped.startswith("#"):
            continue
        level = 0
        while level < len(stripped) and stripped[level] == "#" and level < 6:
            level += 1
        if level and level < len(stripped) and stripped[level] in (" ", "\t"):
            indent = line[:len(line) - len(stripped)]
            lines[position] = indent + "#" * level + " " + clean_line(new_title, MAX_TITLE)
            return "\n".join(lines)
    return text
