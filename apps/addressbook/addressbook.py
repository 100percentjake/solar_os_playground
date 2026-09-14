"""Graphical personal Contacts app for SolarOS."""

import gc
import json
import sys

import solaros
from solaros import gfx

from addressbook_core import (MAX_ADDRESS, MAX_CONTACTS, MAX_EMAILS,
                              MAX_HANDLES, MAX_NAME, MAX_NOTES, MAX_PHONES,
                              MAX_VALUE, add_contact, clean_notes, clean_text,
                              clone_contact, contact_summary, default_state,
                              delete_contact, empty_contact, normalize_state,
                              replace_contact, search_contacts)


def app_directory():
    path = sys.argv[0] if sys.argv else "addressbook.py"
    if not path or "/" not in path:
        try:
            path = __file__
        except NameError:
            path = "addressbook.py"
    separator = path.rfind("/")
    if separator < 0:
        return "."
    return path[:separator] if separator > 0 else "/"


APP_DIR = app_directory()
DATA_DIR = "/.addressbook"
STATE_PATH = DATA_DIR + "/contacts.json"
TEMP_PATH = STATE_PATH + ".tmp"
BACKUP_PATH = STATE_PATH + ".bak"
LEGACY_STATE_PATH = APP_DIR + "/contacts.json"
LEGACY_TEMP_PATH = LEGACY_STATE_PATH + ".tmp"
LEGACY_BACKUP_PATH = LEGACY_STATE_PATH + ".bak"
KEY_ENTER = 13
KEY_LF = 10
KEY_BACKSPACE = 8
KEY_DELETE = 127
HEADER_H = 43
FOOTER_H = 25
ROW_H = 43
LOAD_NOTICE = ""
MIN_WIDTH = 160
MIN_HEIGHT = 112


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
    return {"year": 2000, "month": 1, "day": 1, "hour": 0, "minute": 0}


def ensure_data_directory():
    try:
        solaros.storage.mkdir(DATA_DIR)
    except OSError:
        pass


def state_document_usable(raw, state):
    if not isinstance(raw, dict) or not isinstance(raw.get("contacts"), list):
        return False
    version = raw.get("version", 1)
    if not isinstance(version, int) or isinstance(version, bool) or version != 1:
        return False
    # Never silently accept a document that would drop records during repair.
    # A valid backup is preferable; if every copy is damaged, leave them all
    # untouched and open an empty in-memory address book with a warning.
    if len(raw["contacts"]) != len(state.get("contacts", [])):
        return False
    return True


def load_state():
    global LOAD_NOTICE
    LOAD_NOTICE = ""
    found_invalid = False
    candidates = ((STATE_PATH, "primary"), (TEMP_PATH, "recovery"),
                  (BACKUP_PATH, "recovery"),
                  (LEGACY_STATE_PATH, "legacy"),
                  (LEGACY_TEMP_PATH, "legacy"),
                  (LEGACY_BACKUP_PATH, "legacy"))
    for path, kind in candidates:
        try:
            with open(path, "r") as source:
                raw = json.load(source)
            state = normalize_state(raw)
            if not state_document_usable(raw, state):
                found_invalid = True
                continue
            del raw
            gc.collect()
            if kind == "recovery":
                try:
                    solaros.storage.remove(STATE_PATH)
                except OSError:
                    pass
                try:
                    solaros.storage.rename(path, STATE_PATH)
                    LOAD_NOTICE = "Recovered contacts from an interrupted save."
                except OSError:
                    pass
            elif kind == "legacy":
                try:
                    save_state(state)
                    LOAD_NOTICE = "Moved existing contacts to update-safe storage."
                except Exception:
                    LOAD_NOTICE = "Loaded existing contacts, but could not move them to update-safe storage."
            return state
        except OSError:
            continue
        except Exception:
            found_invalid = True
            gc.collect()
    if found_invalid:
        LOAD_NOTICE = "Contact data was damaged and no usable recovery copy was found. The damaged files were left in place."
    return default_state()


def save_state(state):
    if not isinstance(state, dict) or not isinstance(state.get("contacts"), list):
        raise ValueError("contact state is invalid")
    clean = normalize_state(state)
    if len(clean["contacts"]) != len(state["contacts"]):
        raise ValueError("refusing to discard an invalid contact")
    with open(TEMP_PATH, "w") as output:
        json.dump(clean, output)
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
        solaros.storage.rename(TEMP_PATH, STATE_PATH)
    except Exception:
        if had_primary:
            try:
                solaros.storage.rename(BACKUP_PATH, STATE_PATH)
            except OSError:
                pass
        raise
    del clean
    gc.collect()


def persist(width, height, state):
    try:
        save_state(state)
        return True
    except Exception as error:
        message(width, height, "Could not save", "The change remains in memory but may be lost when Contacts closes. " + str(error))
        return False


def wait_key():
    while not solaros.should_exit():
        key = gfx.getch(250)
        if key is not None:
            return key
    return gfx.KEY_ESCAPE


def draw_header(width, title, subtitle="", right=""):
    gfx.color(gfx.BLACK)
    gfx.fill_rect(0, 0, width, HEADER_H)
    gfx.color(gfx.WHITE)
    gfx.font(gfx.FONT_BOLD_16)
    reserved = len(right) * 6 + 10 if right else 0
    gfx.text(10, 19, clip(title, max(1, (width - 20 - reserved) // 8)))
    if right:
        gfx.font(gfx.FONT_MONO_12)
        gfx.text(max(10, width - 8 - len(right) * 6), 19, right)
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


def wrap_text(value, columns, maximum=100):
    value = clean_notes(value, 2400)
    lines = []
    for paragraph in value.replace("\r", "").split("\n"):
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
                if line:
                    lines.append(line)
                line = word
            else:
                line = trial
        if line:
            lines.append(line)
        if len(lines) >= maximum:
            break
    return lines[:maximum]


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


def edit_text(width, height, title, label, initial="", limit=MAX_VALUE, notes=False):
    value = clean_notes(initial, limit) if notes else clean_text(initial, "", limit)
    while not solaros.should_exit():
        gfx.clear(gfx.WHITE)
        draw_header(width, title, clip(label, 30) + "  {}/{}".format(len(value), limit))
        gfx.color(gfx.BLACK)
        gfx.font(gfx.FONT_MONO_16)
        columns = max(8, (width - 24) // 8)
        shown = value.replace("\n", " ") + "_"
        lines = []
        while shown:
            lines.append(shown[:columns])
            shown = shown[columns:]
        visible = max(1, (height - HEADER_H - FOOTER_H - 8) // 23)
        y = HEADER_H + 31
        for line in lines[-visible:]:
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


def choose(width, height, title, options, selected=0, footer="Enter choose   Esc cancel", hotkeys=()):
    if not options:
        return None
    if selected < 0 or selected >= len(options):
        selected = 0
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
        if key in hotkeys:
            return key
        if key in (gfx.KEY_UP, ord("k")):
            selected = (selected - 1) % len(options)
        elif key in (gfx.KEY_DOWN, ord("j")):
            selected = (selected + 1) % len(options)
        elif key in (KEY_ENTER, KEY_LF, gfx.KEY_RIGHT):
            return selected
    return None


def manage_values(width, height, title, values, maximum, label):
    changed = False
    selected = 0
    while not solaros.should_exit():
        options = []
        for value in values:
            options.append(value)
        if len(values) < maximum:
            options.append("+ Add " + label)
        selected = min(selected, max(0, len(options) - 1))
        index = choose(width, height, title, options, selected)
        if index is None:
            return changed
        selected = index
        if index == len(values):
            value = edit_text(width, height, "Add " + label, label, "", MAX_VALUE)
            value = clean_text(value)
            if value:
                duplicate = False
                for item in values:
                    if item.lower() == value.lower():
                        duplicate = True
                        break
                if duplicate:
                    message(width, height, "Already stored", "That " + label + " is already on this contact.")
                else:
                    values.append(value)
                    changed = True
        else:
            action = choose(width, height, clip(values[index], 40), ["Edit", "Delete"])
            if action == 0:
                value = edit_text(width, height, "Edit " + label, label, values[index], MAX_VALUE)
                value = clean_text(value)
                if value and value != values[index]:
                    duplicate = False
                    for old_index, old in enumerate(values):
                        if old_index != index and old.lower() == value.lower():
                            duplicate = True
                            break
                    if not duplicate:
                        values[index] = value
                        changed = True
                    else:
                        message(width, height, "Already stored", "That " + label + " is already on this contact.")
            elif action == 1 and confirm(width, height, "Delete " + label, "Remove " + values[index] + "?"):
                del values[index]
                changed = True
                selected = max(0, selected - 1)
    return changed


def handle_label(handle):
    return handle.get("service", "Handle") + ": " + handle.get("value", "")


def edit_handle(width, height, old=None):
    service = old.get("service", "") if isinstance(old, dict) else ""
    value = old.get("value", "") if isinstance(old, dict) else ""
    service = edit_text(width, height, "Handle type", "Service, network, or label", service, 40)
    if service is None:
        return None
    service = clean_text(service, "Handle", 40)
    value = edit_text(width, height, "Handle", "Username or address", value, MAX_VALUE)
    value = clean_text(value)
    if not value:
        return None
    return {"service": service, "value": value}


def manage_handles(width, height, handles):
    changed = False
    selected = 0
    while not solaros.should_exit():
        options = [handle_label(item) for item in handles]
        if len(handles) < MAX_HANDLES:
            options.append("+ Add handle")
        selected = min(selected, max(0, len(options) - 1))
        index = choose(width, height, "Known handles", options, selected)
        if index is None:
            return changed
        selected = index
        if index == len(handles):
            value = edit_handle(width, height)
            if value is not None:
                duplicate = False
                for item in handles:
                    if handle_label(item).lower() == handle_label(value).lower():
                        duplicate = True
                        break
                if not duplicate:
                    handles.append(value)
                    changed = True
                else:
                    message(width, height, "Already stored", "That service and handle are already on this contact.")
        else:
            action = choose(width, height, clip(handle_label(handles[index]), 40), ["Edit", "Delete"])
            if action == 0:
                value = edit_handle(width, height, handles[index])
                if value is not None and value != handles[index]:
                    duplicate = False
                    for old_index, item in enumerate(handles):
                        if old_index != index and handle_label(item).lower() == handle_label(value).lower():
                            duplicate = True
                            break
                    if duplicate:
                        message(width, height, "Already stored", "That service and handle are already on this contact.")
                    else:
                        handles[index] = value
                        changed = True
            elif action == 1 and confirm(width, height, "Delete handle", "Remove " + handle_label(handles[index]) + "?"):
                del handles[index]
                changed = True
                selected = max(0, selected - 1)
    return changed


def editor_labels(contact):
    return [
        "Name: " + (contact.get("name") or "Required"),
        "Phone numbers ({})".format(len(contact.get("phones", []))),
        "Email addresses ({})".format(len(contact.get("emails", []))),
        "Known handles ({})".format(len(contact.get("handles", []))),
        "Address: " + ("Set" if contact.get("address") else "Not set"),
        "Website: " + (contact.get("website") or "Not set"),
        "Notes: " + ("Set" if contact.get("notes") else "Not set"),
    ]


def contact_editor(width, height, original=None):
    new_contact = original is None
    if new_contact:
        contact = empty_contact()
        dirty = False
    else:
        contact = clone_contact(original)
        dirty = False
    selected = 0
    while not solaros.should_exit():
        title = "New contact" if new_contact else "Edit contact"
        action = choose(width, height, title, editor_labels(contact), selected,
                        "Enter edit   S save   Esc cancel", (ord("s"), ord("S")))
        if action is None:
            if dirty and not confirm(width, height, "Discard changes", "Leave this editor without saving the changes?"):
                continue
            return None
        if action in (ord("s"), ord("S")):
            if not contact.get("name"):
                message(width, height, "Name required", "Enter a name before saving this contact.")
                selected = 0
                continue
            return contact
        selected = action
        if action == 0:
            entered = edit_text(width, height, "Contact name", "Name (required)", contact["name"], MAX_NAME)
            if entered is None:
                continue
            value = clean_text(entered, "", MAX_NAME)
            if value and value != contact["name"]:
                contact["name"] = value
                dirty = True
            elif value == "":
                message(width, height, "Name required", "A contact name cannot be blank.")
        elif action == 1:
            dirty = manage_values(width, height, "Phone numbers", contact["phones"], MAX_PHONES, "phone number") or dirty
        elif action == 2:
            dirty = manage_values(width, height, "Email addresses", contact["emails"], MAX_EMAILS, "email address") or dirty
        elif action == 3:
            dirty = manage_handles(width, height, contact["handles"]) or dirty
        elif action == 4:
            value = edit_text(width, height, "Address", "Postal or physical address", contact["address"], MAX_ADDRESS, True)
            if value is not None and value != contact["address"]:
                contact["address"] = clean_notes(value, MAX_ADDRESS)
                dirty = True
        elif action == 5:
            value = edit_text(width, height, "Website", "URL", contact["website"], MAX_VALUE)
            if value is not None and value != contact["website"]:
                contact["website"] = clean_text(value)
                dirty = True
        elif action == 6:
            value = edit_text(width, height, "Notes", "Anything useful about this person", contact["notes"], MAX_NOTES, True)
            if value is not None and value != contact["notes"]:
                contact["notes"] = clean_notes(value, MAX_NOTES)
                dirty = True
    return None


def draw_contact_row(width, y, contact, selected):
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
    gfx.color(foreground)
    try:
        gfx.icon(8, y + 5, "person", 32)
    except Exception:
        pass
    gfx.font(gfx.FONT_BOLD_14)
    gfx.text(41, y + 19, clip(contact.get("name", "Unnamed"), max(6, (width - 51) // 7)))
    gfx.font(gfx.FONT_MONO_12)
    gfx.text(41, y + 36, clip(contact_summary(contact), max(6, (width - 51) // 6)))


def draw_list(width, height, contacts, selected, query):
    gfx.clear(gfx.WHITE)
    subtitle = "{} contact{}".format(len(contacts), "" if len(contacts) == 1 else "s")
    if query:
        subtitle += "  Search: " + query
    page = "{}/{}".format(selected + 1, len(contacts)) if contacts else ""
    draw_header(width, "Contacts", subtitle, page)
    visible = max(1, (height - HEADER_H - FOOTER_H) // ROW_H)
    if contacts:
        start = (selected // visible) * visible
        row = 0
        while row < visible and start + row < len(contacts):
            draw_contact_row(width, HEADER_H + row * ROW_H, contacts[start + row], start + row == selected)
            row += 1
    else:
        gfx.color(gfx.DARK)
        gfx.font(gfx.FONT_MONO_16)
        body_height = height - HEADER_H - FOOTER_H
        message_columns = max(1, (width - 28) // 8)
        hint_columns = max(1, (width - 28) // 6)
        if query:
            gfx.text(14, HEADER_H + min(30, body_height - 8),
                     clip("No matching contacts.", message_columns))
            if body_height >= 68:
                gfx.font(gfx.FONT_MONO_12)
                gfx.text(14, HEADER_H + 54, clip("Press C to clear search.", hint_columns))
        else:
            gfx.text(14, HEADER_H + min(30, body_height - 8),
                     clip("Your address book is empty.", message_columns))
            if body_height >= 68:
                gfx.font(gfx.FONT_MONO_12)
                gfx.text(14, HEADER_H + 54, clip("Press A to add someone.", hint_columns))
    draw_footer(width, height, "Enter open  A add  / search  C clear  Esc exit")
    gfx.refresh()


def add_field(lines, label, values, columns):
    if isinstance(values, str):
        values = [values] if values else []
    if not values:
        return
    lines.append(label)
    for value in values:
        for line in wrap_text(value, max(8, columns - 2)):
            lines.append("  " + line)
    lines.append("")


def detail_lines(contact, columns):
    lines = []
    add_field(lines, "PHONE", contact.get("phones", []), columns)
    add_field(lines, "EMAIL", contact.get("emails", []), columns)
    handles = []
    for handle in contact.get("handles", []):
        handles.append(handle_label(handle))
    add_field(lines, "HANDLES", handles, columns)
    add_field(lines, "ADDRESS", contact.get("address", ""), columns)
    add_field(lines, "WEBSITE", contact.get("website", ""), columns)
    add_field(lines, "NOTES", contact.get("notes", ""), columns)
    if not lines:
        lines = ["No details yet.", "", "Press E to add contact information."]
    return lines


def draw_detail(width, height, contact, lines, scroll):
    gfx.clear(gfx.WHITE)
    visible = max(1, (height - HEADER_H - FOOTER_H - 8) // 19)
    position = ""
    if len(lines) > visible:
        position = "{}-{} / {}".format(scroll + 1, min(scroll + visible, len(lines)), len(lines))
    draw_header(width, contact.get("name", "Contact"), contact_summary(contact), position)
    gfx.color(gfx.BLACK)
    gfx.font(gfx.FONT_MONO_14)
    y = HEADER_H + 20
    for line in lines[scroll:scroll + visible]:
        gfx.text(10, y, clip(line, max(6, (width - 20) // 7)))
        y += 19
    draw_footer(width, height, "Up/Down scroll  E edit  D delete  Esc back")
    gfx.refresh()


def detail_screen(width, height, state, contact):
    scroll = 0
    columns = max(10, (width - 20) // 7)
    lines = detail_lines(contact, columns)
    visible = max(1, (height - HEADER_H - FOOTER_H - 8) // 19)
    while not solaros.should_exit():
        scroll = min(scroll, max(0, len(lines) - visible))
        draw_detail(width, height, contact, lines, scroll)
        key = wait_key()
        if key in (gfx.KEY_ESCAPE, gfx.KEY_LEFT, ord("q"), ord("Q")):
            return contact, False
        if key in (gfx.KEY_UP, ord("k")):
            scroll = max(0, scroll - 1)
        elif key in (gfx.KEY_DOWN, ord("j")):
            scroll = min(max(0, len(lines) - visible), scroll + 1)
        elif key == getattr(gfx, "KEY_PAGE_UP", -1001):
            scroll = max(0, scroll - visible)
        elif key == getattr(gfx, "KEY_PAGE_DOWN", -1002):
            scroll = min(max(0, len(lines) - visible), scroll + visible)
        elif key in (ord("e"), ord("E")):
            edited = contact_editor(width, height, contact)
            if edited is not None:
                replacement = replace_contact(state, edited, now_value())
                if replacement is not None:
                    contact = replacement
                    persist(width, height, state)
                    scroll = 0
                    lines = detail_lines(contact, columns)
        elif key in (ord("d"), ord("D"), KEY_DELETE):
            if confirm(width, height, "Delete contact", "Permanently delete " + contact.get("name", "this contact") + "?"):
                if delete_contact(state, contact.get("id")):
                    persist(width, height, state)
                    return contact, True
    return contact, False


def main_screen(width, height, state):
    query = ""
    selected = 0
    contacts = search_contacts(state, query)
    while not solaros.should_exit():
        if contacts:
            selected = min(selected, len(contacts) - 1)
        else:
            selected = 0
        draw_list(width, height, contacts, selected, query)
        key = wait_key()
        if key in (gfx.KEY_ESCAPE, ord("q"), ord("Q")):
            return
        if key in (gfx.KEY_UP, ord("k")) and contacts:
            selected = (selected - 1) % len(contacts)
        elif key in (gfx.KEY_DOWN, ord("j")) and contacts:
            selected = (selected + 1) % len(contacts)
        elif key == getattr(gfx, "KEY_PAGE_UP", -1001) and contacts:
            visible = max(1, (height - HEADER_H - FOOTER_H) // ROW_H)
            selected = max(0, selected - visible)
        elif key == getattr(gfx, "KEY_PAGE_DOWN", -1002) and contacts:
            visible = max(1, (height - HEADER_H - FOOTER_H) // ROW_H)
            selected = min(len(contacts) - 1, selected + visible)
        elif key in (KEY_ENTER, KEY_LF, gfx.KEY_RIGHT) and contacts:
            old_id = contacts[selected].get("id")
            unused, deleted = detail_screen(width, height, state, contacts[selected])
            contacts = search_contacts(state, query)
            if deleted:
                selected = min(selected, max(0, len(contacts) - 1))
            else:
                for index, item in enumerate(contacts):
                    if item.get("id") == old_id:
                        selected = index
                        break
        elif key in (ord("a"), ord("A")):
            if len(state.get("contacts", [])) >= MAX_CONTACTS:
                message(width, height, "Address book full", "This version supports at most {} contacts to keep JSON parsing within the device's memory budget.".format(MAX_CONTACTS))
            else:
                draft = contact_editor(width, height)
                if draft is not None:
                    try:
                        created = add_contact(state, draft, now_value())
                        persist(width, height, state)
                        query = ""
                        contacts = search_contacts(state)
                        for index, item in enumerate(contacts):
                            if item.get("id") == created.get("id"):
                                selected = index
                                break
                    except Exception as error:
                        message(width, height, "Could not add", str(error))
        elif key == ord("/"):
            value = edit_text(width, height, "Search contacts", "Any name, detail, address, or note", query, MAX_VALUE)
            if value is not None:
                query = value
                selected = 0
                contacts = search_contacts(state, query)
        elif key in (ord("c"), ord("C")):
            query = ""
            selected = 0
            contacts = search_contacts(state)
        gc.collect()


def main():
    ensure_data_directory()
    state = load_state()
    gfx.begin()
    try:
        width, height = gfx.size()
        if width < MIN_WIDTH or height < MIN_HEIGHT:
            gfx.clear(gfx.WHITE)
            gfx.color(gfx.BLACK)
            gfx.font(gfx.FONT_MONO_12)
            gfx.text(4, 14, clip("Contacts needs a 160x112 display.", max(1, (width - 8) // 6)))
            gfx.refresh()
            wait_key()
            return
        if LOAD_NOTICE:
            message(width, height, "Storage recovery", LOAD_NOTICE)
        main_screen(width, height, state)
    finally:
        gfx.end()


if __name__ == "__main__":
    main()
