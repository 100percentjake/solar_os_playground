"""Portable data model for the SolarOS Contacts address book."""


STATE_VERSION = 1
MAX_CONTACTS = 256
MAX_NAME = 100
MAX_VALUE = 180
MAX_ADDRESS = 500
MAX_NOTES = 1200
MAX_PHONES = 8
MAX_EMAILS = 8
MAX_HANDLES = 12


def unsafe_character(code):
    return (code < 32 or 127 <= code <= 159 or
            0x200B <= code <= 0x200F or 0x202A <= code <= 0x202E or
            0x2060 <= code <= 0x206F or code == 0xFEFF or
            0xD800 <= code <= 0xDFFF)


def clean_text(value, fallback="", limit=MAX_VALUE):
    if not isinstance(value, str):
        value = fallback
    cleaned = ""
    for char in value:
        code = ord(char)
        if unsafe_character(code):
            cleaned += " "
        else:
            cleaned += char
    value = " ".join(cleaned.split())
    return (value[:limit] or fallback)[:limit]


def clean_notes(value, limit=MAX_NOTES):
    if not isinstance(value, str):
        return ""
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    cleaned = ""
    for char in value:
        code = ord(char)
        if char == "\n":
            cleaned += char
        elif unsafe_character(code):
            cleaned += " "
        else:
            cleaned += char
    lines = []
    for line in cleaned.split("\n"):
        lines.append(" ".join(line.split()))
    return "\n".join(lines).strip()[:limit]


def bounded_int(value, fallback, low, high):
    if not isinstance(value, int) or isinstance(value, bool):
        return fallback
    return max(low, min(high, value))


def valid_stamp(value, fallback="2000-01-01T00:00"):
    if not isinstance(value, str) or len(value) < 16:
        return fallback
    sample = value[:16]
    if sample[4:5] != "-" or sample[7:8] != "-" or sample[10:11] != "T" or sample[13:14] != ":":
        return fallback
    digits = sample[:4] + sample[5:7] + sample[8:10] + sample[11:13] + sample[14:16]
    for char in digits:
        if char < "0" or char > "9":
            return fallback
    try:
        year = int(sample[:4])
        month = int(sample[5:7])
        day = int(sample[8:10])
        hour = int(sample[11:13])
        minute = int(sample[14:16])
        if (year < 1 or year > 9999 or month < 1 or month > 12 or
                day < 1 or day > days_in_month(year, month) or
                hour < 0 or hour > 23 or minute < 0 or minute > 59):
            return fallback
    except Exception:
        return fallback
    return sample


def days_in_month(year, month):
    if month == 2:
        leap = (year % 4 == 0 and year % 100 != 0) or year % 400 == 0
        return 29 if leap else 28
    if month in (4, 6, 9, 11):
        return 30
    return 31


def pad2(value):
    value = str(int(value))
    return "0" + value if len(value) < 2 else value


def timestamp(now):
    try:
        return "{}-{}-{}T{}:{}".format(
            bounded_int(now.get("year"), 2000, 1, 9999),
            pad2(bounded_int(now.get("month"), 1, 1, 12)),
            pad2(bounded_int(now.get("day"), 1, 1, 31)),
            pad2(bounded_int(now.get("hour"), 0, 0, 23)),
            pad2(bounded_int(now.get("minute"), 0, 0, 59)))
    except Exception:
        return "2000-01-01T00:00"


def clean_values(value, limit, maximum):
    result = []
    seen = {}
    if not isinstance(value, list):
        return result
    for raw in value:
        item = clean_text(raw, "", limit)
        key = item.lower()
        if item and key not in seen:
            seen[key] = True
            result.append(item)
            if len(result) >= maximum:
                break
    return result


def clean_handles(value):
    result = []
    seen = {}
    if not isinstance(value, list):
        return result
    for raw in value:
        if isinstance(raw, dict):
            service = clean_text(raw.get("service"), "Handle", 40)
            handle = clean_text(raw.get("value"), "", MAX_VALUE)
        elif isinstance(raw, str):
            service = "Handle"
            handle = clean_text(raw, "", MAX_VALUE)
        else:
            continue
        key = (service + "\n" + handle).lower()
        if handle and key not in seen:
            seen[key] = True
            result.append({"service": service, "value": handle})
            if len(result) >= MAX_HANDLES:
                break
    return result


def empty_contact(name="", stamp="2000-01-01T00:00"):
    return {
        "id": "",
        "name": clean_text(name, "", MAX_NAME),
        "phones": [],
        "emails": [],
        "handles": [],
        "address": "",
        "website": "",
        "notes": "",
        "created": stamp,
        "updated": stamp,
    }


def normalize_contact(raw, fallback_id="", fallback_stamp="2000-01-01T00:00"):
    if not isinstance(raw, dict):
        return None
    name = clean_text(raw.get("name"), "", MAX_NAME)
    if not name:
        return None
    ident = raw.get("id") if isinstance(raw.get("id"), str) else fallback_id
    if not valid_id(ident):
        ident = fallback_id
    created = valid_stamp(raw.get("created"), fallback_stamp)
    updated = valid_stamp(raw.get("updated"), created)
    return {
        "id": ident,
        "name": name,
        "phones": clean_values(raw.get("phones"), MAX_VALUE, MAX_PHONES),
        "emails": clean_values(raw.get("emails"), MAX_VALUE, MAX_EMAILS),
        "handles": clean_handles(raw.get("handles")),
        "address": clean_notes(raw.get("address"), MAX_ADDRESS),
        "website": clean_text(raw.get("website"), "", MAX_VALUE),
        "notes": clean_notes(raw.get("notes"), MAX_NOTES),
        "created": created,
        "updated": updated,
    }


def default_state():
    return {"version": STATE_VERSION, "next_id": 1, "contacts": []}


def valid_id(value):
    if not isinstance(value, str) or len(value) < 2 or len(value) > 12 or value[:1] != "c":
        return False
    for char in value[1:]:
        if char < "0" or char > "9":
            return False
    return True


def new_id(state):
    # SolarOS MicroPython uses tagged small integers on this build.
    value = bounded_int(state.get("next_id"), 1, 1, 99999999)
    used = {}
    for contact in state.get("contacts", []):
        used[contact.get("id", "")] = True
    start = value
    while "c" + str(value) in used:
        value += 1
        if value > 99999999:
            value = 1
        if value == start:
            raise ValueError("no contact IDs available")
    state["next_id"] = value + 1 if value < 99999999 else 1
    return "c" + str(value)


def normalize_state(value):
    state = default_state()
    if not isinstance(value, dict):
        return state
    candidate_next = value.get("next_id")
    if (not isinstance(candidate_next, int) or isinstance(candidate_next, bool) or
            candidate_next < 1 or candidate_next > 99999999):
        candidate_next = 1
    state["next_id"] = candidate_next
    raw_contacts = value.get("contacts")
    if not isinstance(raw_contacts, list):
        return state
    used = {}
    greatest = 0
    accepted = 0
    for raw in raw_contacts:
        if accepted >= MAX_CONTACTS:
            break
        contact = normalize_contact(raw)
        if contact is None:
            continue
        ident = contact.get("id")
        if not valid_id(ident) or ident in used:
            ident = new_id(state)
            contact["id"] = ident
        used[ident] = True
        state["contacts"].append(contact)
        accepted += 1
        try:
            number = int(ident[1:])
            if number > greatest:
                greatest = number
        except Exception:
            pass
    if state["next_id"] <= greatest:
        state["next_id"] = greatest + 1 if greatest < 99999999 else 1
    return state


def clone_contact(contact):
    result = empty_contact(contact.get("name", ""), contact.get("created", "2000-01-01T00:00"))
    result["id"] = contact.get("id", "")
    result["phones"] = list(contact.get("phones", []))
    result["emails"] = list(contact.get("emails", []))
    result["handles"] = []
    for handle in contact.get("handles", []):
        result["handles"].append({"service": handle.get("service", "Handle"),
                                  "value": handle.get("value", "")})
    for name in ("address", "website", "notes", "updated"):
        result[name] = contact.get(name, result.get(name, ""))
    return result


def add_contact(state, contact, now):
    if len(state.get("contacts", [])) >= MAX_CONTACTS:
        raise ValueError("contact limit reached")
    stamp = timestamp(now)
    clean = normalize_contact(contact, "", stamp)
    if clean is None:
        raise ValueError("name is required")
    clean["id"] = new_id(state)
    clean["created"] = stamp
    clean["updated"] = stamp
    state["contacts"].append(clean)
    return clean


def replace_contact(state, contact, now):
    ident = contact.get("id") if isinstance(contact, dict) else ""
    if not valid_id(ident):
        return None
    clean = normalize_contact(contact, ident, timestamp(now))
    if clean is None:
        raise ValueError("name is required")
    clean["id"] = ident
    clean["updated"] = timestamp(now)
    for index, old in enumerate(state.get("contacts", [])):
        if old.get("id") == ident:
            clean["created"] = old.get("created", clean["created"])
            state["contacts"][index] = clean
            return clean
    return None


def delete_contact(state, ident):
    contacts = state.get("contacts", [])
    for index, contact in enumerate(contacts):
        if contact.get("id") == ident:
            del contacts[index]
            return True
    return False


def contact_matches(contact, needle):
    # Check one field at a time. Joining an entire record into a temporary
    # string made searches needlessly spike the MicroPython heap for long notes.
    for name in ("name", "address", "website", "notes"):
        value = contact.get(name, "")
        if isinstance(value, str) and needle in value.lower():
            return True
    for name in ("phones", "emails"):
        for value in contact.get(name, []):
            if isinstance(value, str) and needle in value.lower():
                return True
    for handle in contact.get("handles", []):
        service = handle.get("service", "")
        value = handle.get("value", "")
        if ((isinstance(service, str) and needle in service.lower()) or
                (isinstance(value, str) and needle in value.lower())):
            return True
    return False


def search_contacts(state, query=""):
    needle = clean_text(query, "", MAX_VALUE).lower()
    result = []
    for contact in state.get("contacts", []):
        if not needle or contact_matches(contact, needle):
            result.append(contact)
    result.sort(key=lambda contact: contact.get("name", "").lower())
    return result


def contact_summary(contact):
    for field in ("phones", "emails"):
        values = contact.get(field, [])
        if values:
            return values[0]
    handles = contact.get("handles", [])
    if handles:
        return handles[0].get("service", "Handle") + ": " + handles[0].get("value", "")
    if contact.get("website"):
        return contact["website"]
    if contact.get("address"):
        return contact["address"].split("\n", 1)[0]
    return "No contact details"
