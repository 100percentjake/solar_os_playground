# Home Assistant

Control and monitor Home Assistant entities from the graphic display. Browse any combination of lights, fans, sensors, and more. Sections are defined entirely by your config file — only add what you have.

## Configure

Create `ha.cfg` in the same directory as `ha.py`:

```ini
url=http://YOUR_HA_IP:8123
token=YOUR_LONG_LIVED_ACCESS_TOKEN

[Lights]
light.living_room=Living Room
switch.kitchen=Kitchen

[Fans]
fan.bedroom_fan=Bedroom

[Energy]
binary_sensor.grid_status=Grid
sensor.battery_percent=Battery
sensor.solar_production=Solar

[Temperatures]
sensor.outdoor_temp=Outside
sensor.indoor_temp=Inside
```

Generate a long-lived access token in Home Assistant under **Profile → Long-Lived Access Tokens**.

Sections can be named anything. Any section containing `light.*`, `switch.*`, or `fan.*` entities automatically supports toggling. Sensor-only sections are read-only. Unused sections (Energy, Fans, etc.) can simply be omitted.

Up to 8 sections and 8 entities per section are supported.

### Icon mapping

Section icons are chosen automatically by name:

| Name contains | Icon |
|---|---|
| light, lamp | lightbulb |
| fan, vent | fan |
| energy, power, solar, grid | bolt |
| anything else | pulse |

### State formatting

| Entity / section | Display |
|---|---|
| Section name contains "temp" or "climate" | `72.3°` |
| Section name contains "energy", "power", "solar", "grid" | `1.2 kW` / `450 W` |
| `binary_sensor.*` | `on` / `off` |
| Entity ID contains "battery" | `85%` |
| Anything else | raw state |

## Controls

| Key | Action |
|-----|--------|
| Up / Down | Move cursor |
| Enter | Open section / toggle entity |
| Q | Go back / exit |
| Escape | Exit |

The display refreshes automatically every 30 seconds. After 60 seconds of inactivity a full-screen 7-segment clock appears; any key returns to the app.

## Requirements

Home Assistant requires SolarOS 4.8.4, Wi-Fi, a graphic display, and the Python and Playground packages. The `solaros.http` and `solaros.time` APIs must be available (included in standard Wi-Fi builds).
