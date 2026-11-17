"""Animated on-screen cards (ASS subtitle animation) plus the sound-effect cue list.

Every animation is an ASS override tag rendered by libass inside ffmpeg, so the
render stays a single fast ffmpeg pass on GitHub Actions. The same timing drives
the sound effects, so a pop always lands exactly when a bullet appears.

Motion is kept calm on purpose: the audience is older viewers, so nothing flashes,
text never moves while it is meant to be read, and every reveal is under half a second.
"""

from __future__ import annotations

import re

from src.textutil import ass_escape, ass_time

# ASS colours are &HAABBGGRR
INK = "&H000C121A&"
TEAL = "&H00474C0E&"
TEAL_HI = "&H005C6313&"
GOLD = "&H002D7CA6&"
GOLD_SOFT = "&H0088B9D6&"
WARN = "&H00321F7A&"
WHITE = "&H00FFFFFF&"
RED = "&H003539E5&"

HEADER_COLOR = {"title": TEAL, "points": TEAL, "numbers": TEAL, "warning": WARN, "end": TEAL}

Cue = tuple[float, str]


def _dialog(start: float, end: float, style: str, text: str, layer: int = 1) -> str:
    return f"Dialogue: {layer},{ass_time(start)},{ass_time(max(end, start + 0.05))},{style},,0,0,0,,{text}"


def _rect(x1: int, y1: int, x2: int, y2: int) -> str:
    return f"m {x1} {y1} l {x2} {y1} {x2} {y2} {x1} {y2}"


def _round_rect(w: int, h: int, r: int) -> str:
    k = int(r * 0.45)  # bezier handle for a near-circular corner
    return (
        f"m {r} 0 l {w - r} 0 b {w - k} 0 {w} {k} {w} {r} l {w} {h - r} "
        f"b {w} {h - k} {w - k} {h} {w - r} {h} l {r} {h} b {k} {h} 0 {h - k} 0 {h - r} "
        f"l 0 {r} b 0 {k} {k} 0 {r} 0"
    )


def _shape(start: float, end: float, tags: str, path: str, layer: int = 0) -> str:
    return _dialog(start, end, "Shape", "{" + tags + r"\p1}" + path + r"{\p0}", layer)


def reveal_times(start: float, end: float, count: int) -> list[float]:
    """When each bullet appears: one by one through the first half of the section."""
    if count <= 0:
        return []
    first = start + 0.55
    if count == 1:
        return [first]
    span = min((end - start) * 0.5, (count - 1) * 3.2)
    step = max(0.6, span / (count - 1))
    return [min(first + i * step, end - 0.5) for i in range(count)]


_COUNTABLE = re.compile(r"^(\D*?)(\d{1,3}(?:,\d{3})+|\d+)(\D*)$")


def _countable(text: str) -> tuple[str, int, str, bool] | None:
    match = _COUNTABLE.match(text.strip())
    if not match:
        return None
    raw = match.group(2)
    value = int(raw.replace(",", ""))
    if value < 10 or 1900 <= value <= 2100 or 2400 <= value <= 2700:
        return None  # tiny numbers and years look odd counting up
    return match.group(1), value, match.group(3), "," in raw


def piece_events(piece: dict, as_of: str, vertical: bool, fit_rows, wrap_lines) -> tuple[list[str], list[Cue]]:
    start, end, layout = piece["start"], piece["end"], piece["layout"]
    lines = [line.strip() for line in piece["lines"] if line.strip()]
    events: list[str] = []
    cues: list[Cue] = []
    width = 1080 if vertical else 1920
    header_h = 300 if vertical else 220
    cx = width // 2

    # Header plate (static) and heading that slides down into place.
    events.append(_shape(start, end, rf"\an7\pos(0,0)\1c{HEADER_COLOR.get(layout, TEAL)}", _rect(0, 0, width, header_h)))
    if vertical:
        heading = r"\N".join(ass_escape(row) for row in fit_rows(piece["heading"], 24))
        events.append(_dialog(start, end, "Head", rf"{{\an5\move({cx},{110},{cx},{150},0,320)\fad(260,0)}}" + heading, 2))
    else:
        heading = ass_escape(r"\N".join(fit_rows(piece["heading"], 40)))
        events.append(_dialog(start, end, "Head", rf"{{\an8\move({cx},{44},{cx},{76},0,320)\fad(260,0)}}" + heading, 2))

    if layout == "warning":
        cues.append((start + 0.25, "alert"))
        if not vertical:
            pulse = "".join(
                rf"\t({i * 600},{i * 600 + 300},\fscx118\fscy118)\t({i * 600 + 300},{i * 600 + 600},\fscx100\fscy100)"
                for i in range(3)
            )
            events.append(_shape(start, end, rf"\an5\pos(1800,110)\1c&H0050C8F5&{pulse}", "m 52 0 l 104 90 l 0 90", 2))
            events.append(_dialog(start, end, "Mark", rf"{{\an5\pos(1800,122)\fs58{pulse}}}!", 3))

    if layout == "numbers" and len(lines) >= 2:
        kick_y, big_y, body_y = (420, 760, 980) if vertical else (300, 530, 720)
        events.append(_dialog(start, end, "Kicker", rf"{{\an8\move({cx},{kick_y - 24},{cx},{kick_y},0,300)\fad(280,0)}}" + ass_escape(lines[0]), 2))
        big_at = start + 0.45
        count = _countable(lines[1])
        settle = big_at
        if count:
            prefix, value, suffix, commas = count
            steps = 14
            for i in range(steps):
                t0 = big_at + i * 0.055
                eased = 1 - (1 - (i + 1) / steps) ** 3
                shown = int(round(value * eased)) if i < steps - 1 else value
                text = f"{prefix}{shown:,}{suffix}" if commas else f"{prefix}{shown}{suffix}"
                fade = r"\fad(150,0)" if i == 0 else ""
                events.append(_dialog(t0, t0 + 0.055, "Big", rf"{{\an5\pos({cx},{big_y}){fade}}}" + ass_escape(text), 2))
                if i % 3 == 0:
                    cues.append((t0, "tick"))
            settle = big_at + steps * 0.055
            events.append(_dialog(settle, end, "Big", rf"{{\an5\pos({cx},{big_y})\fscx114\fscy114\t(0,220,\fscx100\fscy100)}}" + ass_escape(lines[1]), 2))
        else:
            events.append(
                _dialog(big_at, end, "Big", rf"{{\an5\pos({cx},{big_y})\fad(120,0)\fscx60\fscy60\t(0,240,\fscx112\fscy112)\t(240,400,\fscx100\fscy100)}}" + ass_escape(lines[1]), 2)
            )
        cues.append((settle, "ding"))
        bar_w = 420 if vertical else 520
        events.append(_shape(settle, end, rf"\an5\pos({cx},{big_y + (110 if vertical else 92)})\1c{GOLD}\fscx0\t(0,420,\fscx100)", _round_rect(bar_w, 12, 6), 1))
        if len(lines) > 2:
            body = r"\N".join(ass_escape(row) for row in wrap_lines(lines[2:], 22 if vertical else 36))
            q = r"\q2" if vertical else ""
            events.append(_dialog(settle + 0.3, end, "Body", rf"{{\an8\pos({cx},{body_y}){q}\fad(400,0)}}" + body, 2))
        return events, cues

    # Content area between the header (+progress bar) and the footer, or the Short's logo.
    top, bottom = (340, 1410) if vertical else (262, 950)
    card_x, card_w = (50, 980) if vertical else (110, 1700)

    if layout == "title":
        size_first, size_rest = (88, 68) if vertical else (92, 64)
        rows = []
        for line in lines:
            rows.extend(fit_rows(line, (19 if not rows else 24) if vertical else (30 if not rows else 40)))
        if not rows:
            return events, cues
        heights = [int((size_first if i == 0 else size_rest) * 1.42) for i in range(len(rows))]
        card_h = sum(heights) + 90
        mid = (top + bottom) // 2
        card_y = mid - card_h // 2
        move = rf"\move({card_x},{card_y + 40},{card_x},{card_y},0,420)\fad(320,0)"
        events.append(_shape(start, end, rf"\an7{move}\1c&H000000&\1a&HE0&", _round_rect(card_w + 8, card_h + 10, 34), 1))
        events.append(_shape(start, end, rf"\an7{move}\1c{WHITE}", _round_rect(card_w, card_h, 30), 1))
        events.append(_shape(start, end, rf"\an7\move({card_x + card_w // 2 - 90},{card_y + 40},{card_x + card_w // 2 - 90},{card_y},0,420)\fad(320,0)\1c{GOLD}", _round_rect(180, 10, 5), 2))
        parts = []
        for index, row in enumerate(rows):
            size = size_first if index == 0 else size_rest
            colour = TEAL if index == 0 else INK
            delay = 300 + index * 280
            parts.append(rf"{{\fs{size}\1c{colour}\alpha&HFF&\t({delay},{delay + 360},\alpha&H00&)}}" + ass_escape(row))
        events.append(_dialog(start, end, "Body", rf"{{\an5\pos({card_x + card_w // 2},{mid + 8})}}" + r"\N".join(parts), 2))
        cues.append((start + 0.3, "pop"))
        return events, cues

    # Bullet points as cards that slide in one at a time. The newest card's text is teal
    # so the eye knows where the narrator is; it returns to ink when the next one arrives.
    size = 66 if vertical else 68
    line_h = int(size * 1.42)
    bullets = [rows for rows in (fit_rows(line, 25 if vertical else 40) for line in lines) if rows]
    if not bullets:
        return events, cues
    gap = 24
    pad = 44
    heights = [len(rows) * line_h + pad for rows in bullets]
    total_h = sum(heights) + gap * (len(bullets) - 1)
    if total_h > bottom - top:  # very long section: shrink the cards to fit
        scale = (bottom - top - gap * (len(bullets) - 1)) / (total_h - gap * (len(bullets) - 1))
        heights = [int(h * scale) for h in heights]
        size = int(size * scale)
        total_h = sum(heights) + gap * (len(bullets) - 1)
    y = top + max(0, (bottom - top - total_h) // 2)
    times = reveal_times(start, end, len(bullets))
    badge = 76
    for index, (rows, height, t0) in enumerate(zip(bullets, heights, times)):
        t1 = times[index + 1] if index + 1 < len(times) else min(end, t0 + 6)
        move = rf"\move({card_x - 70},{y},{card_x},{y},0,380)\fad(280,0)"
        events.append(_shape(t0, end, rf"\an7{move}\1c&H000000&\1a&HE4&", _round_rect(card_w + 6, height + 8, 26), 1))
        events.append(_shape(t0, end, rf"\an7{move}\1c{WHITE}", _round_rect(card_w, height, 24), 1))
        bx, by = card_x + 26, y + (height - badge) // 2
        events.append(_shape(t0, end, rf"\an7\move({bx - 70},{by},{bx},{by},0,380)\fad(280,0)\1c{TEAL}", _round_rect(badge, badge, badge // 2), 2))
        events.append(_dialog(t0, end, "Mark", rf"{{\an5\move({bx - 70 + badge // 2},{by + badge // 2},{bx + badge // 2},{by + badge // 2},0,380)\fad(280,0)\1c{WHITE}\fs44}}{index + 1}", 3))
        text = r"\N".join(ass_escape(row) for row in rows)
        tx, ty = card_x + 26 + badge + 30, y + height // 2
        events.append(_dialog(t0, t1, "Body", rf"{{\an4\move({tx - 70},{ty},{tx},{ty},0,380)\fad(280,0)\fs{size}\1c{TEAL_HI}}}" + text, 3))
        if t1 < end:
            events.append(_dialog(t1, end, "Body", rf"{{\an4\pos({tx},{ty})\fs{size}\1c{INK}\t(0,300,\1c{INK})}}" + text, 3))
        cues.append((t0, "pop"))
        y += height + gap
    return events, cues


def timeline_events(pieces: list[dict], total: float, vertical: bool, as_of: str) -> tuple[list[str], list[Cue]]:
    """Things that span sections: footer, progress bar, wipe transitions, subscribe reminders."""
    width = 1080 if vertical else 1920
    height = 1920 if vertical else 1080
    header_h = 300 if vertical else 220
    events: list[str] = []
    cues: list[Cue] = []

    if vertical:
        foot = ass_escape("ไม่ใช่หน่วยงานรัฐ  ·  เสียงสังเคราะห์") + r"\N" + ass_escape(f"ข้อมูล ณ {as_of}")
        events.append(_dialog(0, total, "Foot", r"{\an5\pos(540,1845)}" + foot, 2))
    else:
        foot = ass_escape(f"ไม่ใช่หน่วยงานรัฐ  ·  เสียงสังเคราะห์  ·  ข้อมูล ณ {as_of}")
        events.append(_dialog(0, total, "Foot", r"{\an2\pos(960,1052)}" + foot, 2))

    # Progress bar under the header: a soft gold track that fills as the video plays.
    events.append(_shape(0, total, rf"\an7\pos(0,0)\1c{GOLD_SOFT}", _rect(0, header_h, width, header_h + 12), 0))
    ms = int(total * 1000)
    events.append(
        _shape(0, total, rf"\an7\pos(0,0)\1c{GOLD}\clip(0,{header_h},1,{header_h + 12})\t(0,{ms},\clip(0,{header_h},{width},{header_h + 12}))", _rect(0, header_h, width, header_h + 12), 1)
    )

    # Wipe: a teal panel with a gold edge sweeps across while the slide changes underneath.
    for piece in pieces[1:]:
        at = piece["start"]
        half = 0.24
        events.append(_shape(at - half, at + half, rf"\an7\move({-width - 30},0,{width + 30},0)\1c{TEAL}", _rect(0, 0, width, height), 6))
        events.append(_shape(at - half, at + half, rf"\an7\move({-30},0,{2 * width + 30},0)\1c{GOLD}", _rect(0, 0, 22, height), 7))
        cues.append((at - half, "whoosh"))

    # Subscribe reminder pill, twice in a long video (not in Shorts: the UI already shows it).
    if not vertical and total > 240:
        for share in (0.27, 0.64):
            at = _quiet_moment(pieces, total * share)
            w, h = 470, 86
            x, y = width - w - 40, 1080 - 108 - h - 26
            events.append(_shape(at, at + 4.8, rf"\an7\move({width + 20},{y},{x},{y},0,420)\fad(0,320)\1c{RED}", _round_rect(w, h, 43), 4))
            events.append(_dialog(at, at + 4.8, "Pill", rf"{{\an5\move({width + 20 + w // 2},{y + h // 2},{x + w // 2},{y + h // 2},0,420)\fad(0,320)}}" + ass_escape("กดติดตาม + กดกระดิ่ง"), 5))
            cues.append((at + 0.1, "pop"))
    return events, cues


def _quiet_moment(pieces: list[dict], near: float) -> float:
    """Start the reminder a few seconds into a section, never on top of a transition."""
    for piece in pieces:
        if piece["start"] <= near < piece["end"]:
            if piece["end"] - piece["start"] > 9:
                return max(near, piece["start"] + 3.0) if near + 5 < piece["end"] else piece["start"] + 3.0
    return near
