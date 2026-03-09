"""
Aviation format transforms: METAR, TAF, NOTAM → JSON / Plain Text / Markdown

Uses metar and python-metar libraries for parsing real aviation data.
"""

from __future__ import annotations

import re
import orjson
from typing import Any


# ---------------------------------------------------------------------------
# METAR parsing
# ---------------------------------------------------------------------------

def _parse_metar_manual(raw: str) -> dict:
    """Parse a METAR string into structured fields."""
    raw = raw.strip()
    result: dict[str, Any] = {"raw": raw, "type": "METAR"}

    # Station
    m = re.match(r'^(METAR|SPECI)?\s*([A-Z]{4})\s+', raw)
    if m:
        result["station"] = m.group(2)

    # Time
    m = re.search(r'\b(\d{2})(\d{2})(\d{2})Z\b', raw)
    if m:
        result["time"] = {"day": m.group(1), "hour": m.group(2), "minute": m.group(3), "utc": True}

    # Wind
    m = re.search(r'\b(\d{3}|VRB)(\d{2,3})(G(\d{2,3}))?KT\b', raw)
    if m:
        result["wind"] = {
            "direction_deg": None if m.group(1) == "VRB" else int(m.group(1)),
            "variable": m.group(1) == "VRB",
            "speed_kt": int(m.group(2)),
            "gust_kt": int(m.group(4)) if m.group(4) else None,
        }

    # Visibility
    m = re.search(r'\b(\d+(?:/\d+)?|\d+\s+\d+/\d+)\s*SM\b', raw)
    if m:
        vis_str = m.group(1).strip()
        try:
            if '/' in vis_str and ' ' not in vis_str:
                num, den = vis_str.split('/')
                vis = float(num) / float(den)
            elif ' ' in vis_str:
                parts = vis_str.split()
                num, den = parts[1].split('/')
                vis = float(parts[0]) + float(num) / float(den)
            else:
                vis = float(vis_str)
            result["visibility_sm"] = vis
        except Exception:
            result["visibility_sm"] = vis_str

    # Sky conditions
    sky_matches = re.findall(r'\b(FEW|SCT|BKN|OVC|CLR|SKC|CAVOK)(\d{3})?(CB|TCU)?\b', raw)
    if sky_matches:
        result["sky_conditions"] = [
            {
                "cover": s[0],
                "base_ft": int(s[1]) * 100 if s[1] else None,
                "cloud_type": s[2] if s[2] else None,
            }
            for s in sky_matches
        ]

    # Temperature / Dewpoint
    m = re.search(r'\b(M?\d{2})/(M?\d{2})\b', raw)
    if m:
        def parse_temp(t: str) -> int:
            return -int(t[1:]) if t.startswith('M') else int(t)
        result["temperature_c"] = parse_temp(m.group(1))
        result["dewpoint_c"] = parse_temp(m.group(2))

    # Altimeter
    m = re.search(r'\bA(\d{4})\b', raw)
    if m:
        result["altimeter_inhg"] = int(m.group(1)) / 100.0
    m = re.search(r'\bQ(\d{4})\b', raw)
    if m:
        result["altimeter_hpa"] = int(m.group(1))

    # Weather phenomena
    phenomena = re.findall(
        r'\b([-+]?(?:VC)?(?:MI|PR|BC|DR|BL|SH|TS|FZ)?'
        r'(?:DZ|RA|SN|SG|IC|PL|GR|GS|UP|BR|FG|FU|VA|DU|SA|HZ|PY|PO|SQ|FC|SS|DS)+)\b',
        raw
    )
    if phenomena:
        result["weather"] = phenomena

    # Flight category
    vis = result.get("visibility_sm")
    sky = result.get("sky_conditions", [])
    ceiling = None
    for layer in sky:
        if layer["cover"] in ("BKN", "OVC") and layer["base_ft"] is not None:
            ceiling = layer["base_ft"]
            break

    if vis is not None or ceiling is not None:
        if (vis is not None and vis < 1) or (ceiling is not None and ceiling < 500):
            result["flight_category"] = "LIFR"
        elif (vis is not None and vis < 3) or (ceiling is not None and ceiling < 1000):
            result["flight_category"] = "IFR"
        elif (vis is not None and vis < 5) or (ceiling is not None and ceiling < 3000):
            result["flight_category"] = "MVFR"
        else:
            result["flight_category"] = "VFR"

    return result


def _parse_taf_manual(raw: str) -> dict:
    """Parse a TAF string into structured fields."""
    raw = raw.strip()
    result: dict[str, Any] = {"raw": raw, "type": "TAF"}

    # Station
    m = re.match(r'^TAF\s+(?:AMD\s+|COR\s+)?([A-Z]{4})\s+', raw)
    if m:
        result["station"] = m.group(1)

    # Issue time
    m = re.search(r'\b(\d{6})Z\b', raw)
    if m:
        t = m.group(1)
        result["issued"] = {"day": t[0:2], "hour": t[2:4], "minute": t[4:6]}

    # Valid period
    m = re.search(r'\b(\d{2})(\d{2})/(\d{2})(\d{2})\b', raw)
    if m:
        result["valid_period"] = {
            "from_day": m.group(1), "from_hour": m.group(2),
            "to_day": m.group(3), "to_hour": m.group(4),
        }

    # Split into forecast groups
    groups = re.split(r'\b(TEMPO|BECMG|FM\d{6}|PROB\d{2})\b', raw)
    result["forecast_groups"] = len([g for g in groups if g.strip()])

    return result


def _parse_notam_manual(raw: str) -> dict:
    """Parse a NOTAM string into structured fields."""
    raw = raw.strip()
    result: dict[str, Any] = {"raw": raw, "type": "NOTAM"}

    # NOTAM number
    m = re.match(r'^([A-Z]\d{4}/\d{2,4})', raw)
    if m:
        result["notam_number"] = m.group(1)

    # Q line
    m = re.search(r'Q\)\s*([^/]*)/([^/]*)/([^/]*)/([^/]*)/([^/]*)/([^/]*)/([^\n]*)', raw)
    if m:
        result["q_line"] = {
            "fir": m.group(1).strip(),
            "code": m.group(2).strip(),
            "traffic": m.group(3).strip(),
            "purpose": m.group(4).strip(),
            "scope": m.group(5).strip(),
            "lower_fl": m.group(6).strip(),
            "upper_fl": m.group(7).strip(),
        }

    # A) Location
    m = re.search(r'A\)\s*([A-Z]{4})', raw)
    if m:
        result["location"] = m.group(1)

    # B) Start time
    m = re.search(r'B\)\s*(\d{10})', raw)
    if m:
        t = m.group(1)
        result["effective_start"] = f"20{t[0:2]}-{t[2:4]}-{t[4:6]}T{t[6:8]}:{t[8:10]}Z"

    # C) End time
    m = re.search(r'C\)\s*(\d{10}|PERM)', raw)
    if m:
        t = m.group(1)
        if t == "PERM":
            result["effective_end"] = "PERMANENT"
        else:
            result["effective_end"] = f"20{t[0:2]}-{t[2:4]}-{t[4:6]}T{t[6:8]}:{t[8:10]}Z"

    # E) Free text
    m = re.search(r'E\)\s*(.+?)(?=F\)|G\)|$)', raw, re.DOTALL)
    if m:
        result["description"] = m.group(1).strip()

    # F) Lower limit
    m = re.search(r'F\)\s*(.+?)(?=G\)|$)', raw)
    if m:
        result["lower_limit"] = m.group(1).strip()

    # G) Upper limit
    m = re.search(r'G\)\s*(.+?)$', raw)
    if m:
        result["upper_limit"] = m.group(1).strip()

    return result


# ---------------------------------------------------------------------------
# Format helpers
# ---------------------------------------------------------------------------

def _metar_to_plain(parsed: dict) -> str:
    lines = [f"METAR Report — {parsed.get('station', 'Unknown')}"]
    lines.append("-" * 40)
    if "time" in parsed:
        t = parsed["time"]
        lines.append(f"Time: Day {t['day']}, {t['hour']}:{t['minute']}Z")
    if "wind" in parsed:
        w = parsed["wind"]
        dir_str = "Variable" if w["variable"] else f"{w['direction_deg']}°"
        gust_str = f", gusting {w['gust_kt']}kt" if w["gust_kt"] else ""
        lines.append(f"Wind: {dir_str} at {w['speed_kt']}kt{gust_str}")
    if "visibility_sm" in parsed:
        lines.append(f"Visibility: {parsed['visibility_sm']} SM")
    if "sky_conditions" in parsed:
        for s in parsed["sky_conditions"]:
            base = f" at {s['base_ft']}ft" if s["base_ft"] else ""
            lines.append(f"Sky: {s['cover']}{base}")
    if "temperature_c" in parsed:
        lines.append(f"Temperature: {parsed['temperature_c']}°C  Dewpoint: {parsed['dewpoint_c']}°C")
    if "altimeter_inhg" in parsed:
        lines.append(f"Altimeter: {parsed['altimeter_inhg']} inHg")
    if "altimeter_hpa" in parsed:
        lines.append(f"Altimeter: {parsed['altimeter_hpa']} hPa")
    if "weather" in parsed:
        lines.append(f"Weather: {', '.join(parsed['weather'])}")
    if "flight_category" in parsed:
        lines.append(f"Flight Category: {parsed['flight_category']}")
    lines.append(f"\nRaw: {parsed['raw']}")
    return "\n".join(lines)


def _metar_to_markdown(parsed: dict) -> str:
    lines = [f"## METAR — {parsed.get('station', 'Unknown')}\n"]
    if "flight_category" in parsed:
        cat = parsed["flight_category"]
        emoji = {"VFR": "🟢", "MVFR": "🔵", "IFR": "🔴", "LIFR": "🟣"}.get(cat, "⚪")
        lines.append(f"**Flight Category:** {emoji} {cat}\n")
    if "wind" in parsed:
        w = parsed["wind"]
        dir_str = "Variable" if w["variable"] else f"{w['direction_deg']}°"
        gust_str = f", gusting **{w['gust_kt']}kt**" if w["gust_kt"] else ""
        lines.append(f"**Wind:** {dir_str} at **{w['speed_kt']}kt**{gust_str}")
    if "visibility_sm" in parsed:
        lines.append(f"**Visibility:** {parsed['visibility_sm']} SM")
    if "sky_conditions" in parsed:
        sky_strs = []
        for s in parsed["sky_conditions"]:
            base = f" @ {s['base_ft']}ft" if s["base_ft"] else ""
            sky_strs.append(f"{s['cover']}{base}")
        lines.append(f"**Sky:** {', '.join(sky_strs)}")
    if "temperature_c" in parsed:
        lines.append(f"**Temp/Dew:** {parsed['temperature_c']}°C / {parsed['dewpoint_c']}°C")
    if "altimeter_inhg" in parsed:
        lines.append(f"**Altimeter:** {parsed['altimeter_inhg']} inHg")
    lines.append(f"\n```\n{parsed['raw']}\n```")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public handlers
# ---------------------------------------------------------------------------

async def metar_to_json(data: bytes, options: dict | None = None) -> bytes:
    raw = data.decode().strip()
    parsed = _parse_metar_manual(raw)
    return orjson.dumps(parsed, option=orjson.OPT_INDENT_2)


async def metar_to_plain_text(data: bytes, options: dict | None = None) -> bytes:
    raw = data.decode().strip()
    parsed = _parse_metar_manual(raw)
    return _metar_to_plain(parsed).encode()


async def metar_to_markdown(data: bytes, options: dict | None = None) -> bytes:
    raw = data.decode().strip()
    parsed = _parse_metar_manual(raw)
    return _metar_to_markdown(parsed).encode()


async def taf_to_json(data: bytes, options: dict | None = None) -> bytes:
    raw = data.decode().strip()
    parsed = _parse_taf_manual(raw)
    return orjson.dumps(parsed, option=orjson.OPT_INDENT_2)


async def taf_to_plain_text(data: bytes, options: dict | None = None) -> bytes:
    raw = data.decode().strip()
    parsed = _parse_taf_manual(raw)
    lines = [f"TAF Report — {parsed.get('station', 'Unknown')}"]
    lines.append("-" * 40)
    if "issued" in parsed:
        i = parsed["issued"]
        lines.append(f"Issued: Day {i['day']}, {i['hour']}:{i['minute']}Z")
    if "valid_period" in parsed:
        v = parsed["valid_period"]
        lines.append(f"Valid: Day {v['from_day']} {v['from_hour']}Z to Day {v['to_day']} {v['to_hour']}Z")
    lines.append(f"Forecast Groups: {parsed.get('forecast_groups', 'N/A')}")
    lines.append(f"\nRaw:\n{parsed['raw']}")
    return "\n".join(lines).encode()


async def taf_to_markdown(data: bytes, options: dict | None = None) -> bytes:
    raw = data.decode().strip()
    parsed = _parse_taf_manual(raw)
    lines = [f"## TAF — {parsed.get('station', 'Unknown')}\n"]
    if "valid_period" in parsed:
        v = parsed["valid_period"]
        lines.append(f"**Valid:** Day {v['from_day']} {v['from_hour']}Z → Day {v['to_day']} {v['to_hour']}Z\n")
    lines.append(f"```\n{parsed['raw']}\n```")
    return "\n".join(lines).encode()


async def notam_to_json(data: bytes, options: dict | None = None) -> bytes:
    raw = data.decode().strip()
    parsed = _parse_notam_manual(raw)
    return orjson.dumps(parsed, option=orjson.OPT_INDENT_2)


async def notam_to_plain_text(data: bytes, options: dict | None = None) -> bytes:
    raw = data.decode().strip()
    parsed = _parse_notam_manual(raw)
    lines = [f"NOTAM — {parsed.get('notam_number', 'Unknown')}"]
    lines.append("-" * 40)
    if "location" in parsed:
        lines.append(f"Location: {parsed['location']}")
    if "effective_start" in parsed:
        lines.append(f"Effective: {parsed['effective_start']} to {parsed.get('effective_end', 'Unknown')}")
    if "description" in parsed:
        lines.append(f"Description: {parsed['description']}")
    if "lower_limit" in parsed:
        lines.append(f"Altitude: {parsed['lower_limit']} to {parsed.get('upper_limit', 'Unknown')}")
    lines.append(f"\nRaw:\n{parsed['raw']}")
    return "\n".join(lines).encode()


async def notam_to_markdown(data: bytes, options: dict | None = None) -> bytes:
    raw = data.decode().strip()
    parsed = _parse_notam_manual(raw)
    lines = [f"## NOTAM {parsed.get('notam_number', '')}\n"]
    if "location" in parsed:
        lines.append(f"**Location:** {parsed['location']}")
    if "effective_start" in parsed:
        lines.append(f"**Effective:** {parsed['effective_start']} → {parsed.get('effective_end', 'Unknown')}")
    if "description" in parsed:
        lines.append(f"\n**Description:**\n{parsed['description']}")
    lines.append(f"\n```\n{parsed['raw']}\n```")
    return "\n".join(lines).encode()


# ---------------------------------------------------------------------------
# PIREP parsing
# ---------------------------------------------------------------------------

def _parse_pirep_manual(raw: str) -> dict:
    """Parse a PIREP string into structured fields."""
    raw = raw.strip()
    result = {"raw": raw, "type": "PIREP"}

    if raw.startswith("UUA"):
        result["urgency"] = "URGENT"
    else:
        result["urgency"] = "ROUTINE"

    m = re.search(r'OV\s+([A-Z0-9]{3,6})(?:/(\d{3})(\d{3}))?', raw)
    if m:
        result["location"] = {
            "fix": m.group(1),
            "bearing_deg": int(m.group(2)) if m.group(2) else None,
            "distance_nm": int(m.group(3)) if m.group(3) else None,
        }

    m = re.search(r'TM\s+(\d{4})', raw)
    if m:
        t = m.group(1)
        result["time"] = {"hour": t[0:2], "minute": t[2:4], "utc": True}

    m = re.search(r'FL(\d{3})', raw)
    if m:
        result["altitude_ft"] = int(m.group(1)) * 100

    m = re.search(r'TP\s+([A-Z0-9]+)', raw)
    if m:
        result["aircraft_type"] = m.group(1)

    m = re.search(r'SK\s+((?:(?!TA\s|WV\s|TB\s|IC\s|RM\s|FL\d).)+)', raw)
    if m:
        result["sky"] = m.group(1).strip().rstrip("/")

    m = re.search(r'TA\s+(M?\d+)', raw)
    if m:
        t = m.group(1)
        result["temperature_c"] = -int(t[1:]) if t.startswith("M") else int(t)

    m = re.search(r'WV\s+(\d{3})(\d{2,3})', raw)
    if m:
        result["wind"] = {
            "direction_deg": int(m.group(1)),
            "speed_kt": int(m.group(2)),
        }

    m = re.search(r'TB\s+((?:(?!IC\s|RM\s|SK\s|WV\s).)+)', raw)
    if m:
        tb = m.group(1).strip()
        tb = tb.rstrip("/")
        result["turbulence"] = tb
        if any(x in tb.upper() for x in ["SEV", "EXTRM"]):
            result["turbulence_severity"] = "SEVERE"
        elif "MOD" in tb.upper():
            result["turbulence_severity"] = "MODERATE"
        elif "LGT" in tb.upper():
            result["turbulence_severity"] = "LIGHT"
        else:
            result["turbulence_severity"] = "UNKNOWN"

    m = re.search(r'IC\s+([^\n/][^\n]*)', raw)
    if m:
        ic = m.group(1).strip()
        result["icing"] = ic
        if any(x in ic.upper() for x in ["SEV", "HVY"]):
            result["icing_severity"] = "SEVERE"
        elif "MOD" in ic.upper():
            result["icing_severity"] = "MODERATE"
        elif "LGT" in ic.upper():
            result["icing_severity"] = "LIGHT"
        else:
            result["icing_severity"] = "UNKNOWN"

    m = re.search(r'RM\s+(.+)$', raw)
    if m:
        result["remarks"] = m.group(1).strip()

    return result


def _pirep_to_plain(parsed: dict) -> str:
    lines = ["PIREP Report — " + parsed.get("urgency", "ROUTINE")]
    lines.append("-" * 40)
    if "location" in parsed:
        loc = parsed["location"]
        loc_str = loc["fix"]
        if loc["bearing_deg"]:
            loc_str += " " + str(loc["bearing_deg"]) + "deg / " + str(loc["distance_nm"]) + "nm"
        lines.append("Location: " + loc_str)
    if "time" in parsed:
        t = parsed["time"]
        lines.append("Time: " + t["hour"] + ":" + t["minute"] + "Z")
    if "altitude_ft" in parsed:
        lines.append("Altitude: " + str(parsed["altitude_ft"]) + " ft")
    if "aircraft_type" in parsed:
        lines.append("Aircraft: " + parsed["aircraft_type"])
    if "sky" in parsed:
        lines.append("Sky: " + parsed["sky"])
    if "temperature_c" in parsed:
        lines.append("Temperature: " + str(parsed["temperature_c"]) + "C")
    if "wind" in parsed:
        w = parsed["wind"]
        lines.append("Wind: " + str(w["direction_deg"]) + "deg at " + str(w["speed_kt"]) + "kt")
    if "turbulence" in parsed:
        lines.append("Turbulence: " + parsed["turbulence"] + " (" + parsed.get("turbulence_severity", "") + ")")
    if "icing" in parsed:
        lines.append("Icing: " + parsed["icing"] + " (" + parsed.get("icing_severity", "") + ")")
    if "remarks" in parsed:
        lines.append("Remarks: " + parsed["remarks"])
    lines.append("\nRaw: " + parsed["raw"])
    return "\n".join(lines)


def _pirep_to_markdown(parsed: dict) -> str:
    urgency = parsed.get("urgency", "ROUTINE")
    emoji = "🔴" if urgency == "URGENT" else "🔵"
    lines = ["## PIREP " + emoji + " " + urgency + "\n"]
    if "location" in parsed:
        loc = parsed["location"]
        loc_str = loc["fix"]
        if loc["bearing_deg"]:
            loc_str += " (" + str(loc["bearing_deg"]) + "deg/" + str(loc["distance_nm"]) + "nm)"
        lines.append("**Location:** " + loc_str)
    if "time" in parsed:
        t = parsed["time"]
        lines.append("**Time:** " + t["hour"] + ":" + t["minute"] + "Z")
    if "altitude_ft" in parsed:
        lines.append("**Altitude:** " + str(parsed["altitude_ft"]) + " ft")
    if "aircraft_type" in parsed:
        lines.append("**Aircraft:** " + parsed["aircraft_type"])
    if "sky" in parsed:
        lines.append("**Sky:** " + parsed["sky"])
    if "temperature_c" in parsed:
        lines.append("**Temperature:** " + str(parsed["temperature_c"]) + "C")
    if "wind" in parsed:
        w = parsed["wind"]
        lines.append("**Wind:** " + str(w["direction_deg"]) + "deg at " + str(w["speed_kt"]) + "kt")
    if "turbulence" in parsed:
        sev = parsed.get("turbulence_severity", "")
        sev_emoji = {"SEVERE": "🔴", "MODERATE": "🟡", "LIGHT": "🟢"}.get(sev, "⚪")
        lines.append("**Turbulence:** " + sev_emoji + " " + parsed["turbulence"])
    if "icing" in parsed:
        sev = parsed.get("icing_severity", "")
        sev_emoji = {"SEVERE": "🔴", "MODERATE": "🟡", "LIGHT": "🟢"}.get(sev, "⚪")
        lines.append("**Icing:** " + sev_emoji + " " + parsed["icing"])
    if "remarks" in parsed:
        lines.append("**Remarks:** " + parsed["remarks"])
    lines.append("\n```\n" + parsed["raw"] + "\n```")
    return "\n".join(lines)


async def pirep_to_json(data: bytes, options: dict | None = None) -> bytes:
    raw = data.decode().strip()
    parsed = _parse_pirep_manual(raw)
    return orjson.dumps(parsed, option=orjson.OPT_INDENT_2)


async def pirep_to_plain_text(data: bytes, options: dict | None = None) -> bytes:
    raw = data.decode().strip()
    parsed = _parse_pirep_manual(raw)
    return _pirep_to_plain(parsed).encode()


async def pirep_to_markdown(data: bytes, options: dict | None = None) -> bytes:
    raw = data.decode().strip()
    parsed = _parse_pirep_manual(raw)
    return _pirep_to_markdown(parsed).encode()



# ---------------------------------------------------------------------------
# SIGMET parsing
# ---------------------------------------------------------------------------

def _parse_sigmet_manual(raw: str) -> dict:
    raw = raw.strip()
    result = {"raw": raw, "type": "SIGMET"}

    m = re.match(r'^([A-Z]{4})\s+SIGMET', raw)
    if m:
        result["issuing_office"] = m.group(1)

    m = re.search(r'SIGMET\s+([A-Z0-9]+)\s+VALID', raw)
    if m:
        result["identifier"] = m.group(1)

    m = re.search(r'VALID\s+(\d{6})/(\d{6})', raw)
    if m:
        result["valid_from"] = m.group(1)
        result["valid_to"] = m.group(2)

    m = re.search(r'(\w+)\s+FIR', raw)
    if m:
        result["fir"] = m.group(1)

    phenomena = ["OBSC TS", "EMBD TS", "FRQ TS", "SQL TS", "SEV TURB", "SEV ICE",
                 "SEV MTW", "HVY DS", "HVY SS", "VA CLD", "VA ERUPTION", "RDOACT CLD"]
    for p in phenomena:
        if p in raw.upper():
            result["phenomenon"] = p
            break

    if "INTSF" in raw:
        result["intensity"] = "INTENSIFYING"
    elif "WKN" in raw:
        result["intensity"] = "WEAKENING"
    elif "NC" in raw:
        result["intensity"] = "NO CHANGE"

    m = re.search(r'FL(\d{3})/(\d{3})', raw)
    if m:
        result["altitude"] = {
            "lower_fl": int(m.group(1)) * 100,
            "upper_fl": int(m.group(2)) * 100,
        }
    else:
        m = re.search(r'TOP\s+FL(\d{3})', raw)
        if m:
            result["altitude"] = {"top_fl": int(m.group(1)) * 100}

    m = re.search(r'MOV\s+([A-Z]+)\s+(\d+)KT', raw)
    if m:
        result["movement"] = {
            "direction": m.group(1),
            "speed_kt": int(m.group(2)),
        }

    return result


def _sigmet_to_plain(parsed: dict) -> str:
    lines = ["SIGMET -- " + parsed.get("identifier", "Unknown")]
    lines.append("-" * 40)
    if "issuing_office" in parsed:
        lines.append("Issuing Office: " + parsed["issuing_office"])
    if "fir" in parsed:
        lines.append("FIR: " + parsed["fir"])
    if "valid_from" in parsed:
        lines.append("Valid: " + parsed["valid_from"] + " to " + parsed["valid_to"])
    if "phenomenon" in parsed:
        lines.append("Phenomenon: " + parsed["phenomenon"])
    if "intensity" in parsed:
        lines.append("Intensity: " + parsed["intensity"])
    if "altitude" in parsed:
        alt = parsed["altitude"]
        if "lower_fl" in alt:
            lines.append("Altitude: FL" + str(alt["lower_fl"]//100) + " to FL" + str(alt["upper_fl"]//100))
        elif "top_fl" in alt:
            lines.append("Top: FL" + str(alt["top_fl"]//100))
    if "movement" in parsed:
        mv = parsed["movement"]
        lines.append("Movement: " + mv["direction"] + " at " + str(mv["speed_kt"]) + "kt")
    lines.append("Raw: " + parsed["raw"])
    return "\n".join(lines)


def _sigmet_to_markdown(parsed: dict) -> str:
    lines = ["## SIGMET " + parsed.get("identifier", "Unknown") + "\n"]
    if "issuing_office" in parsed:
        lines.append("**Issuing Office:** " + parsed["issuing_office"])
    if "fir" in parsed:
        lines.append("**FIR:** " + parsed["fir"])
    if "valid_from" in parsed:
        lines.append("**Valid:** " + parsed["valid_from"] + " to " + parsed["valid_to"])
    if "phenomenon" in parsed:
        lines.append("**Phenomenon:** " + parsed["phenomenon"])
    if "intensity" in parsed:
        lines.append("**Intensity:** " + parsed["intensity"])
    if "altitude" in parsed:
        alt = parsed["altitude"]
        if "lower_fl" in alt:
            lines.append("**Altitude:** FL" + str(alt["lower_fl"]//100) + " to FL" + str(alt["upper_fl"]//100))
        elif "top_fl" in alt:
            lines.append("**Top:** FL" + str(alt["top_fl"]//100))
    if "movement" in parsed:
        mv = parsed["movement"]
        lines.append("**Movement:** " + mv["direction"] + " at " + str(mv["speed_kt"]) + "kt")
    lines.append("```\n" + parsed["raw"] + "\n```")
    return "\n".join(lines)


async def sigmet_to_json(data: bytes, options: dict | None = None) -> bytes:
    raw = data.decode().strip()
    parsed = _parse_sigmet_manual(raw)
    return orjson.dumps(parsed, option=orjson.OPT_INDENT_2)


async def sigmet_to_plain_text(data: bytes, options: dict | None = None) -> bytes:
    raw = data.decode().strip()
    parsed = _parse_sigmet_manual(raw)
    return _sigmet_to_plain(parsed).encode()


async def sigmet_to_markdown(data: bytes, options: dict | None = None) -> bytes:
    raw = data.decode().strip()
    parsed = _parse_sigmet_manual(raw)
    return _sigmet_to_markdown(parsed).encode()


# ---------------------------------------------------------------------------
# AIRMET parsing
# ---------------------------------------------------------------------------

def _parse_airmet_manual(raw: str) -> dict:
    raw = raw.strip()
    result = {"raw": raw, "type": "AIRMET"}

    if "SIERRA" in raw.upper():
        result["airmet_type"] = "SIERRA"
        result["airmet_type_desc"] = "IFR conditions / Mountain obscuration"
    elif "TANGO" in raw.upper():
        result["airmet_type"] = "TANGO"
        result["airmet_type_desc"] = "Turbulence / Strong surface winds"
    elif "ZULU" in raw.upper():
        result["airmet_type"] = "ZULU"
        result["airmet_type_desc"] = "Icing / Freezing level"

    m = re.match(r'^([A-Z]{4})\s+AIRMET', raw)
    if m:
        result["issuing_center"] = m.group(1)

    m = re.search(r'VALID\s+UNTIL\s+(\d{6})', raw)
    if m:
        result["valid_until"] = m.group(1)

    states = re.findall(r'\b([A-Z]{2})\b', raw)
    us_states = {"AL","AK","AZ","AR","CA","CO","CT","DE","FL","GA","HI","ID","IL","IN",
                 "IA","KS","KY","LA","ME","MD","MA","MI","MN","MS","MO","MT","NE","NV",
                 "NH","NJ","NM","NY","NC","ND","OH","OK","OR","PA","RI","SC","SD","TN",
                 "TX","UT","VT","VA","WA","WV","WI","WY"}
    found_states = [s for s in states if s in us_states]
    if found_states:
        result["states_affected"] = list(dict.fromkeys(found_states))

    m = re.search(r'BLW\s+(\d+)', raw)
    if m:
        result["below_ft"] = int(m.group(1))

    m = re.search(r'BTN\s+(\d+)\s+AND\s+(\d+)', raw)
    if m:
        result["altitude"] = {
            "lower_ft": int(m.group(1)),
            "upper_ft": int(m.group(2)),
        }

    m = re.search(r'TOPS\s+TO\s+FL(\d{3})', raw)
    if m:
        result["tops_fl"] = int(m.group(1)) * 100

    conditions = []
    if "ICG" in raw or "ICING" in raw:
        conditions.append("ICING")
    if "TURB" in raw:
        conditions.append("TURBULENCE")
    if "IFR" in raw:
        conditions.append("IFR CONDITIONS")
    if "MTN OBSCN" in raw or "MTN OBS" in raw:
        conditions.append("MOUNTAIN OBSCURATION")
    if "LLWS" in raw:
        conditions.append("LOW LEVEL WIND SHEAR")
    if conditions:
        result["conditions"] = conditions

    return result


def _airmet_to_plain(parsed: dict) -> str:
    atype = parsed.get("airmet_type", "Unknown")
    lines = ["AIRMET " + atype + " -- " + parsed.get("airmet_type_desc", "")]
    lines.append("-" * 40)
    if "issuing_center" in parsed:
        lines.append("Issuing Center: " + parsed["issuing_center"])
    if "valid_until" in parsed:
        lines.append("Valid Until: " + parsed["valid_until"])
    if "states_affected" in parsed:
        lines.append("States: " + ", ".join(parsed["states_affected"]))
    if "conditions" in parsed:
        lines.append("Conditions: " + ", ".join(parsed["conditions"]))
    if "altitude" in parsed:
        alt = parsed["altitude"]
        lines.append("Altitude: " + str(alt["lower_ft"]) + "ft to " + str(alt["upper_ft"]) + "ft")
    if "below_ft" in parsed:
        lines.append("Below: " + str(parsed["below_ft"]) + "ft")
    if "tops_fl" in parsed:
        lines.append("Tops: FL" + str(parsed["tops_fl"]//100))
    lines.append("Raw: " + parsed["raw"])
    return "\n".join(lines)


def _airmet_to_markdown(parsed: dict) -> str:
    atype = parsed.get("airmet_type", "Unknown")
    emoji = {"SIERRA": "SIERRA", "TANGO": "TANGO", "ZULU": "ZULU"}.get(atype, atype)
    lines = ["## AIRMET " + emoji + "\n"]
    if "airmet_type_desc" in parsed:
        lines.append("**Type:** " + parsed["airmet_type_desc"] + "\n")
    if "issuing_center" in parsed:
        lines.append("**Issuing Center:** " + parsed["issuing_center"])
    if "valid_until" in parsed:
        lines.append("**Valid Until:** " + parsed["valid_until"])
    if "states_affected" in parsed:
        lines.append("**States Affected:** " + ", ".join(parsed["states_affected"]))
    if "conditions" in parsed:
        lines.append("**Conditions:** " + ", ".join(parsed["conditions"]))
    if "altitude" in parsed:
        alt = parsed["altitude"]
        lines.append("**Altitude:** " + str(alt["lower_ft"]) + "ft to " + str(alt["upper_ft"]) + "ft")
    if "below_ft" in parsed:
        lines.append("**Below:** " + str(parsed["below_ft"]) + "ft")
    if "tops_fl" in parsed:
        lines.append("**Tops:** FL" + str(parsed["tops_fl"]//100))
    lines.append("```\n" + parsed["raw"] + "\n```")
    return "\n".join(lines)


async def airmet_to_json(data: bytes, options: dict | None = None) -> bytes:
    raw = data.decode().strip()
    parsed = _parse_airmet_manual(raw)
    return orjson.dumps(parsed, option=orjson.OPT_INDENT_2)


async def airmet_to_plain_text(data: bytes, options: dict | None = None) -> bytes:
    raw = data.decode().strip()
    parsed = _parse_airmet_manual(raw)
    return _airmet_to_plain(parsed).encode()


async def airmet_to_markdown(data: bytes, options: dict | None = None) -> bytes:
    raw = data.decode().strip()
    parsed = _parse_airmet_manual(raw)
    return _airmet_to_markdown(parsed).encode()
