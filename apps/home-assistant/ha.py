import solaros
from solaros import gfx
import json
import sys

CONFIG_PATH   = sys.argv[0].rsplit('/', 1)[0] + '/ha.cfg'
GETCH_MS      = 500
REFRESH_TICKS = 60   # * 500ms = 30s
SLEEP_TICKS   = 60   # * 500ms = 30s

BAR_H   = 30
ROW_H   = 30
ICON_SZ = 16
F_MAIN  = gfx.FONT_BOLD_18
F_SUB   = gfx.FONT_BOLD_18

TOGGLE_DOMAINS = ('light.', 'switch.', 'fan.')
MAX_SECTIONS   = 8
MAX_ENTITIES   = 8

SEG = [
    (1,1,1,1,1,1,0),(0,1,1,0,0,0,0),(1,1,0,1,1,0,1),(1,1,1,1,0,0,1),
    (0,1,1,0,0,1,1),(1,0,1,1,0,1,1),(1,0,1,1,1,1,1),(1,1,1,0,0,0,0),
    (1,1,1,1,1,1,1),(1,1,1,1,0,1,1),
]

def _section_icon(label):
    l = label.lower()
    if any(w in l for w in ('light', 'lamp')):                  return 'lightbulb'
    if any(w in l for w in ('fan', 'vent')):                    return 'aperture'
    if any(w in l for w in ('energy','power','solar','grid')):  return 'bolt'
    return 'pulse'

def load_config():
    cfg = {"url": "", "token": "", "sections": []}
    cur = None
    try:
        with open(CONFIG_PATH) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if line.startswith('[') and ']' in line:
                    label = line[1:line.index(']')]
                    label = label[0].upper() + label[1:] if label else label
                    if label and len(cfg['sections']) < MAX_SECTIONS:
                        cur = {"label": label, "entities": [],
                               "toggleable": False, "icon": _section_icon(label)}
                        cfg['sections'].append(cur)
                    continue
                if '=' not in line:
                    continue
                k, v = line.split('=', 1)
                k, v = k.strip(), v.strip()
                if cur is None:
                    if k == 'url':     cfg['url']   = v
                    elif k == 'token': cfg['token'] = v
                elif len(cur['entities']) < MAX_ENTITIES:
                    cur['entities'].append({"id": k, "label": v, "state": "?"})
    except Exception as e:
        return None, str(e)
    if not cfg['url'] or not cfg['token']:
        return None, "missing url or token in " + CONFIG_PATH
    cfg['sections'] = [s for s in cfg['sections'] if s['entities']]
    if not cfg['sections']:
        return None, "no sections defined in " + CONFIG_PATH
    for sec in cfg['sections']:
        sec['toggleable'] = any(e['id'].startswith(TOGGLE_DOMAINS) for e in sec['entities'])
    return cfg, None

def fetch_state(cfg, entity_id):
    try:
        r = solaros.http.get(
            cfg['url'] + '/api/states/' + entity_id,
            {"Authorization": "Bearer " + cfg['token']},
            10000, 4096)
        if r['status_code'] == 200:
            body = r['body']
            if isinstance(body, (bytes, bytearray)):
                body = body.decode()
            return json.loads(body).get('state', '?')
        return 'err' + str(r['status_code'])
    except Exception:
        return '!'

def toggle(cfg, entity_id):
    try:
        solaros.http.post(
            cfg['url'] + '/api/services/homeassistant/toggle',
            ('{"entity_id":"' + entity_id + '"}').encode(),
            {"Authorization": "Bearer " + cfg['token'],
             "Content-Type": "application/json"},
            10000, 256)
    except Exception:
        pass

def format_state(sec_label, entity_id, state):
    if state in ('?', '!') or state.startswith('err'):
        return state
    l = sec_label.lower()
    if 'temp' in l or 'climate' in l:
        try:
            return '{:.1f}\xb0'.format(float(state))
        except Exception:
            return state
    if entity_id.startswith('binary_sensor.'):
        return 'on' if state == 'on' else 'off'
    if 'battery' in entity_id or 'batt' in l:
        return state + '%'
    if any(w in l for w in ('energy', 'power', 'solar', 'grid', 'watt')):
        try:
            val = float(state)
            if val >= 1000:
                return '{:.1f} kW'.format(val / 1000)
            return str(int(val)) + ' W'
        except Exception:
            return state
    return state

def fetch_section(cfg, sec):
    for e in sec['entities']:
        e['state'] = fetch_state(cfg, e['id'])

def fetch_all(cfg):
    for sec in cfg['sections']:
        fetch_section(cfg, sec)

def draw_popup(w, h, msg):
    pw, ph = 120, 28
    x = (w - pw) // 2
    y = (h - ph) // 2
    gfx.color(gfx.BLACK)
    gfx.fill_rect(x, y, pw, ph)
    gfx.color(gfx.WHITE)
    gfx.rect(x + 1, y + 1, pw - 2, ph - 2)
    gfx.font(gfx.FONT_BOLD_14)
    gfx.text(x + 10, y + ph - 8, msg)
    gfx.present()

def draw_digit(x, y, dw, dh, st, n):
    s   = SEG[n]
    mid = dh // 2
    iw  = dw - 2 * st
    th  = mid - st
    bh  = dh - mid - 2 * st
    if s[0]: gfx.fill_rect(x + st,      y,            iw, st)
    if s[1]: gfx.fill_rect(x + dw - st, y + st,       st, th)
    if s[2]: gfx.fill_rect(x + dw - st, y + mid + st, st, bh)
    if s[3]: gfx.fill_rect(x + st,      y + dh - st,  iw, st)
    if s[4]: gfx.fill_rect(x,           y + mid + st, st, bh)
    if s[5]: gfx.fill_rect(x,           y + st,       st, th)
    if s[6]: gfx.fill_rect(x + st,      y + mid,      iw, st)

def draw_clock(w, h):
    dt     = solaros.time.datetime()
    hour   = dt['hour']
    ampm   = 'AM' if hour < 12 else 'PM'
    h12    = hour % 12 or 12
    digits = [h12 // 10, h12 % 10, dt['minute'] // 10, dt['minute'] % 10]
    days   = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun']
    date_str = '{} {}/{}/{}'.format(days[dt['weekday']], dt['month'], dt['day'], dt['year'])

    PAD    = 4
    FOOT   = 18
    COL_W  = 14
    GAP    = 4
    dh     = h - 2 * PAD - FOOT
    dw     = (w - 2 * PAD - COL_W - 4 * GAP) // 4
    st     = max(3, dw // 8)
    dot_sz = max(4, st)

    gfx.clear(gfx.BLACK)
    gfx.color(gfx.WHITE)

    x = PAD
    draw_digit(x, PAD, dw, dh, st, digits[0]); x += dw + GAP
    draw_digit(x, PAD, dw, dh, st, digits[1]); x += dw + GAP
    dot_x = x + (COL_W - dot_sz) // 2
    gfx.fill_rect(dot_x, PAD + dh // 3,     dot_sz, dot_sz)
    gfx.fill_rect(dot_x, PAD + 2 * dh // 3, dot_sz, dot_sz)
    x += COL_W + GAP
    draw_digit(x, PAD, dw, dh, st, digits[2]); x += dw + GAP
    draw_digit(x, PAD, dw, dh, st, digits[3])

    gfx.font(gfx.FONT_BOLD_14)
    gfx.text(w - 34, h - 4, ampm)
    gfx.text(6,      h - 4, date_str)
    gfx.present()

def draw(cfg, screen, cursor, w, h):
    gfx.clear(gfx.WHITE)
    sections = cfg['sections']

    title = "Home Assistant" if screen == 0 else "Home Assistant - " + sections[screen - 1]['label']
    gfx.color(gfx.BLACK)
    gfx.fill_rect(0, 0, w, BAR_H)
    gfx.color(gfx.WHITE)
    gfx.font(F_SUB)
    gfx.text(6, BAR_H - 6, title)

    show_hint = (screen == 0)
    if show_hint:
        gfx.color(gfx.BLACK)
        gfx.fill_rect(0, h - BAR_H, w, BAR_H)
        gfx.color(gfx.DARK)
        gfx.font(F_SUB)
        gfx.text(6, h - 5, "enter=open  q=exit")

    top    = BAR_H + 4
    bottom = h - BAR_H if show_hint else h - 4
    visible = (bottom - top) // ROW_H

    if screen == 0:
        count  = len(sections)
        offset = max(0, cursor - visible + 1) if cursor >= visible else 0
        for i in range(offset, count):
            row_top = top + (i - offset) * ROW_H
            if row_top + ROW_H > bottom:
                break
            y        = row_top + ROW_H - 4
            sec      = sections[i]
            selected = (cursor == i)
            on_count = sum(1 for e in sec['entities'] if e['state'] == 'on')
            sub      = str(on_count) + " on" if sec['toggleable'] else "read only"

            if selected:
                gfx.color(gfx.DARK)
                gfx.fill_rect(0, row_top, w, ROW_H)

            icon_y = row_top + (ROW_H - ICON_SZ) // 2
            gfx.color(gfx.WHITE if selected else (gfx.BLACK if on_count > 0 else gfx.DARK))
            gfx.icon(6, icon_y, sec['icon'], ICON_SZ)

            gfx.color(gfx.WHITE if selected else gfx.BLACK)
            gfx.font(F_MAIN)
            gfx.text(30, y, sec['label'])

            gfx.color(gfx.WHITE if selected else gfx.DARK)
            gfx.font(gfx.FONT_BOLD_14 if sub == "read only" else F_SUB)
            gfx.text(w - 80, y, sub)

        if count > visible:
            bar_h = max(12, (bottom - top) * visible // count)
            bar_y = top + (bottom - top - bar_h) * offset // max(1, count - visible)
            gfx.color(gfx.DARK)
            gfx.fill_rect(w - 4, bar_y, 4, bar_h)
    else:
        sec      = sections[screen - 1]
        entities = sec['entities']
        count    = len(entities)
        offset   = max(0, cursor - visible + 1) if cursor >= visible else 0

        for idx in range(offset, count):
            row_top = top + (idx - offset) * ROW_H
            if row_top + ROW_H > bottom:
                break
            y        = row_top + ROW_H - 10
            e        = entities[idx]
            selected = (idx == cursor)
            is_on    = e['state'] == 'on'

            if selected:
                gfx.color(gfx.DARK)
                gfx.fill_rect(0, row_top, w, ROW_H)

            if sec['toggleable']:
                icon_y = row_top + (ROW_H - ICON_SZ) // 2
                gfx.color(gfx.WHITE if selected else (gfx.BLACK if is_on else gfx.DARK))
                gfx.icon(6, icon_y, sec['icon'], ICON_SZ)

            x_label = 30 if sec['toggleable'] else 10
            gfx.color(gfx.WHITE if selected else gfx.BLACK)
            gfx.font(F_MAIN)
            gfx.text(x_label, y, e['label'])

            display_state = format_state(sec['label'], e['id'], e['state'])
            gfx.color(gfx.WHITE if selected else gfx.DARK)
            gfx.font(F_SUB)
            gfx.text(w - 90, y, display_state)

        if count > visible:
            bar_h = max(12, (bottom - top) * visible // count)
            bar_y = top + (bottom - top - bar_h) * offset // max(1, count - visible)
            gfx.color(gfx.DARK)
            gfx.fill_rect(w - 4, bar_y, 4, bar_h)

    gfx.present()

def show_setup_screen():
    gfx.begin()
    try:
        w, h = gfx.size()
        gfx.clear(gfx.BLACK)
        gfx.color(gfx.WHITE)
        gfx.font(gfx.FONT_BOLD_18)
        gfx.text(6, 20, "Home Assistant")
        gfx.font(gfx.FONT_BOLD_14)
        gfx.text(6, 38, "Setup: create " + CONFIG_PATH)
        gfx.color(gfx.DARK)
        gfx.font(gfx.FONT_BOLD_12)
        y = 56
        for line in (
            "url=http://YOUR_HA_IP:8123",
            "token=YOUR_LONG_LIVED_TOKEN",
            "",
            "[Lights]",
            "light.my_light=My Light",
            "",
            "Any key to exit.",
        ):
            gfx.text(6, y, line)
            y += 13
        gfx.present()
        while not solaros.should_exit():
            if gfx.getch(500) is not None:
                break
    finally:
        gfx.end()

def main():
    cfg, err = load_config()
    if cfg is None:
        show_setup_screen()
        return

    screen      = 0
    cursor      = 0
    idle_ticks  = 0
    sleep_ticks = 0
    sleeping    = False

    gfx.begin()
    try:
        global BAR_H, ROW_H, ICON_SZ, F_MAIN, F_SUB
        w, h = gfx.size()
        BAR_H   = 30
        ROW_H   = (h - 4 - (BAR_H + 4)) // 5
        ICON_SZ = 16
        F_MAIN  = gfx.FONT_BOLD_18
        F_SUB   = gfx.FONT_BOLD_18
        fetch_all(cfg)
        draw(cfg, screen, cursor, w, h)

        while not solaros.should_exit():
            key = gfx.getch(GETCH_MS)

            if key is None:
                idle_ticks  += 1
                sleep_ticks += 1
                if not sleeping and sleep_ticks >= SLEEP_TICKS:
                    sleeping = True
                    draw_clock(w, h)
                elif sleeping:
                    draw_clock(w, h)
                elif idle_ticks >= REFRESH_TICKS:
                    idle_ticks = 0
                    if screen == 0:
                        fetch_all(cfg)
                    else:
                        fetch_section(cfg, cfg['sections'][screen - 1])
                    draw(cfg, screen, cursor, w, h)
                continue

            sleep_ticks = 0
            if sleeping:
                sleeping = False
                draw(cfg, screen, cursor, w, h)
                continue

            if key == gfx.KEY_ESCAPE or key == 0x92:
                break

            if key == ord('q') or key == ord('Q'):
                if screen != 0:
                    screen = 0
                    cursor = 0
                    draw(cfg, screen, cursor, w, h)
                else:
                    break
                continue

            sections = cfg['sections']
            count = len(sections) if screen == 0 else len(sections[screen - 1]['entities'])

            if key == gfx.KEY_UP:
                cursor = (cursor - 1) % count if count else 0
                draw(cfg, screen, cursor, w, h)

            elif key == gfx.KEY_DOWN:
                cursor = (cursor + 1) % count if count else 0
                draw(cfg, screen, cursor, w, h)

            elif key in (ord('\r'), ord('\n')):
                if screen == 0:
                    screen = cursor + 1
                    cursor = 0
                    idle_ticks = 0
                    fetch_section(cfg, sections[screen - 1])
                    draw(cfg, screen, cursor, w, h)
                elif sections[screen - 1]['toggleable']:
                    entities = sections[screen - 1]['entities']
                    if entities and entities[cursor]['id'].startswith(TOGGLE_DOMAINS):
                        draw_popup(w, h, "Toggling...")
                        toggle(cfg, entities[cursor]['id'])
                        gfx.getch(800)
                        idle_ticks = 0
                        fetch_section(cfg, sections[screen - 1])
                        draw(cfg, screen, cursor, w, h)
    finally:
        gfx.end()

main()
