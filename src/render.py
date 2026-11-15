"""Turn a checked script into a 1920x1080 video, or a 1080x1920 Short, with on-screen Thai text."""

from __future__ import annotations

import json
import os
import subprocess
import wave
from pathlib import Path

from src.textutil import ass_escape, ass_time, is_mark, srt_time, wrap_thai
from src.tts import synthesize_section, wav_seconds

ROOT = Path(__file__).resolve().parents[1]
FONTS = ROOT / "assets" / "fonts"
LOGO = ROOT / "assets" / "brand" / "logo.jpg"
WIDTH = 1920
HEIGHT = 1080
INTRO_SECONDS = 5.0
OUTRO_SECONDS = 5.5

# Warm paper, near-black ink, deep teal. Sized for older eyes: high contrast,
# no thin gray type, and no meaning carried by red versus green alone.
PAPER = "0xFFF3E4"
INK = "0x1A120C"
TEAL = "0x0E4C47"
GOLD = "0xA67C2D"
WARN = "0x7A1F32"
HEADER_H = 220
BAR_H = 12
FOOT_H = 108
V_WIDTH = 1080
V_HEIGHT = 1920
V_HEADER_H = 300
V_FOOT_H = 150
V_LOGO = 260

HEADER = {
    "title": TEAL,
    "points": TEAL,
    "numbers": TEAL,
    "warning": WARN,
    "end": TEAL,
}


def run_ffmpeg(cmd: list[str], cwd: Path | None = None) -> None:
    result = subprocess.run(
        cmd,
        cwd=None if cwd is None else str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        raise RuntimeError((result.stderr or "ffmpeg failed")[-2500:])


def filter_path(path: Path, cwd: Path) -> str:
    relative = Path(os.path.relpath(path, cwd)).as_posix()
    return relative.replace(":", r"\:").replace("'", r"\'")


def _frame(vertical: bool) -> tuple[int, int]:
    return (V_WIDTH, V_HEIGHT) if vertical else (WIDTH, HEIGHT)


def make_backgrounds(folder: Path, vertical: bool = False) -> dict[str, Path]:
    folder.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    width, height = _frame(vertical)
    header_h = V_HEADER_H if vertical else HEADER_H
    foot_h = V_FOOT_H if vertical else FOOT_H
    for layout, color in HEADER.items():
        dest = folder / f"bg-{layout}.png"
        foot_y = height - foot_h
        video_filter = (
            f"drawbox=x=0:y=0:w={width}:h={header_h}:color={color}:t=fill,"
            f"drawbox=x=0:y={header_h}:w={width}:h={BAR_H}:color={GOLD}:t=fill,"
            f"drawbox=x=0:y={foot_y}:w={width}:h={foot_h}:color={INK}:t=fill"
        )
        run_ffmpeg(
            [
                "ffmpeg",
                "-y",
                "-f",
                "lavfi",
                "-i",
                f"color=c={PAPER}:s={width}x{height}:d=1",
                "-vf",
                video_filter,
                "-frames:v",
                "1",
                str(dest),
            ]
        )
        paths[layout] = dest
    return paths


def _footer(as_of: str) -> str:
    return f"ไม่ใช่หน่วยงานรัฐ  ·  เสียงสังเคราะห์  ·  ข้อมูล ณ {as_of}"


def _dialog(start: float, end: float, style: str, text: str) -> str:
    return (
        f"Dialogue: 0,{ass_time(start)},{ass_time(end)},{style},,0,0,0,,"
        f"{text}"
    )


def _fit_rows(text: str, width: int) -> list[str]:
    rows = wrap_thai(text, width)
    if len(rows) == 2 and len(rows[1]) < 8:
        rows = wrap_thai(text, max(8, (len(text) + 1) // 2))
    return rows


def _vertical_events(piece: dict, as_of: str) -> list[str]:
    start = piece["start"]
    end = piece["end"]
    layout = piece["layout"]
    heading = r"\N".join(ass_escape(row) for row in _fit_rows(piece["heading"], 24))
    foot = ass_escape("ไม่ใช่หน่วยงานรัฐ  ·  เสียงสังเคราะห์") + r"\N" + ass_escape(f"ข้อมูล ณ {as_of}")
    events = [
        _dialog(start, end, "Head", r"{\an5\pos(540,150)}" + heading),
        _dialog(start, end, "Foot", r"{\an5\pos(540,1845)}" + foot),
    ]
    lines = [line.strip() for line in piece["lines"] if line.strip()]
    if layout == "numbers" and len(lines) >= 2:
        events.append(_dialog(start, end, "Kicker", r"{\an8\pos(540,420)}" + ass_escape(lines[0])))
        events.append(_dialog(start, end, "Big", r"{\an5\pos(540,760)}" + ass_escape(lines[1])))
        if len(lines) > 2:
            body = "\\N".join(ass_escape(row) for row in wrap_lines(lines[2:], 22))
            events.append(_dialog(start, end, "Body", r"{\an8\pos(540,980)\q2}" + body))
        return events

    if layout == "title":
        rows = []
        for index, line in enumerate(lines):
            size = 84 if index == 0 else 66
            for row in _fit_rows(line, 18 if index == 0 else 22):
                rows.append(r"{\fs" + str(size) + "}" + ass_escape(row))
        events.append(_dialog(start, end, "Body", r"{\an8\pos(540,440)\q2}" + r"\N\N".join(rows)))
        return events

    rows = []
    for line in lines:
        wrapped = _fit_rows(line, 22)
        if not wrapped:
            continue
        rows.append("• " + ass_escape(wrapped[0]) + "".join(r"\N   " + ass_escape(row) for row in wrapped[1:]))
    events.append(
        _dialog(start, end, "Body", r"{\an7\pos(70,400)\q2}" + r"\N\N".join(rows))
    )
    return events


def _events_for(piece: dict, as_of: str, vertical: bool = False) -> list[str]:
    if vertical:
        return _vertical_events(piece, as_of)
    start = piece["start"]
    end = piece["end"]
    layout = piece["layout"]
    heading = ass_escape("\\N".join(_fit_rows(piece["heading"], 40)))
    events = [
        _dialog(start, end, "Head", r"{\an8\pos(960,76)}" + heading),
        _dialog(start, end, "Foot", r"{\an2\pos(960,1052)}" + ass_escape(_footer(as_of))),
    ]
    lines = [line.strip() for line in piece["lines"] if line.strip()]
    if layout == "numbers" and len(lines) >= 2:
        events.append(
            _dialog(start, end, "Kicker", r"{\an8\pos(960,300)}" + ass_escape(lines[0]))
        )
        events.append(
            _dialog(start, end, "Big", r"{\an5\pos(960,530)}" + ass_escape(lines[1]))
        )
        if len(lines) > 2:
            body = "\\N".join(ass_escape(row) for row in wrap_lines(lines[2:], 36))
            events.append(_dialog(start, end, "Body", r"{\an8\pos(960,720)}" + body))
        return events

    if layout == "title":
        wrapped = []
        for line in lines:
            wrapped.extend(_fit_rows(line, 36))
        body_lines = []
        for index, row in enumerate(wrapped):
            size = 78 if index == 0 else 56
            body_lines.append(r"{\fs" + str(size) + "}" + ass_escape(row))
        events.append(
            _dialog(start, end, "Body", r"{\an8\pos(960,360)}" + r"\N".join(body_lines))
        )
        return events

    bullet_rows = []
    for line in lines:
        wrapped = _fit_rows(line, 40)
        if not wrapped:
            continue
        bullet_rows.append("• " + wrapped[0])
        bullet_rows.extend("   " + row for row in wrapped[1:])
    events.append(
        _dialog(
            start,
            end,
            "Body",
            r"{\an7\pos(110,280)}" + r"\N".join(ass_escape(row) for row in bullet_rows),
        )
    )
    return events


def wrap_lines(lines: list[str], width: int) -> list[str]:
    wrapped: list[str] = []
    for line in lines:
        wrapped.extend(wrap_thai(line, width))
    return wrapped


def write_ass(path: Path, pieces: list[dict], as_of: str, vertical: bool = False) -> None:
    width, height = _frame(vertical)
    if vertical:
        sizes = {"Head": 72, "Body": 64, "Big": 150, "Foot": 38, "Kicker": 60}
    else:
        sizes = {"Head": 64, "Body": 54, "Big": 116, "Foot": 34, "Kicker": 48}
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Head,Kanit,{sizes['Head']},&H00FFFFFF,&H000000FF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,0,0,8,40,40,20,1
Style: Body,Sarabun,{sizes['Body']},&H000C121A,&H000000FF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,0,0,7,80,80,40,1
Style: Big,Kanit,{sizes['Big']},&H00474C0E,&H000000FF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,0,0,5,40,40,0,1
Style: Foot,Sarabun,{sizes['Foot']},&H00EAF6FF,&H000000FF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,0,0,2,20,20,16,1
Style: Kicker,Kanit,{sizes['Kicker']},&H00474C0E,&H000000FF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,0,0,8,40,40,20,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = [
        header.rstrip(),
        *[event for piece in pieces for event in _events_for(piece, as_of, vertical)],
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8-sig")


def write_srt(path: Path, cues: list[tuple[float, float, str]]) -> None:
    blocks = []
    for index, (start, end, text) in enumerate(cues, start=1):
        if end - start < 0.2 or not text.strip():
            continue
        blocks.append(f"{index}\n{srt_time(start)} --> {srt_time(end)}\n{text.strip()}\n")
    path.write_text("\n".join(blocks), encoding="utf-8")


def _silence(dest: Path, seconds: float) -> None:
    run_ffmpeg(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=44100:cl=mono",
            "-t",
            f"{seconds:.3f}",
            "-c:a",
            "pcm_s16le",
            str(dest),
        ]
    )


def _tone_bed(
    dest: Path,
    seconds: float,
    notes: list[tuple[float, float, float, float]],
    air: bool,
) -> None:
    """Short original tones. notes are frequency, start, length, volume."""
    cmd = ["ffmpeg", "-y"]
    filters: list[str] = []
    labels: list[str] = []
    for index, (freq, start, length, volume) in enumerate(notes):
        cmd.extend(
            [
                "-f",
                "lavfi",
                "-i",
                f"sine=frequency={freq}:sample_rate=44100:duration={length:.3f}",
            ]
        )
        fade = max(0.05, length - 0.06)
        delay = int(round(start * 1000))
        filters.append(
            f"[{index}:a]aformat=channel_layouts=mono:sample_rates=44100,"
            f"afade=t=in:d=0.012,afade=t=out:st=0.04:d={fade:.3f},"
            f"volume={volume},adelay={delay}:all=1[n{index}]"
        )
        labels.append(f"[n{index}]")
    if air:
        cmd.extend(
            [
                "-f",
                "lavfi",
                "-i",
                f"anoisesrc=color=brown:sample_rate=44100:duration={seconds:.3f}",
            ]
        )
        filters.append(
            f"[{len(notes)}:a]lowpass=f=240,volume=0.02[air]"
        )
        labels.append("[air]")
    filters.append(
        "".join(labels)
        + f"amix=inputs={len(labels)}:duration=longest:dropout_transition=0:normalize=0,"
        + f"alimiter=limit=0.35,apad=pad_dur={seconds:.3f},atrim=0:{seconds:.3f},"
        + "aformat=sample_fmts=s16:sample_rates=44100:channel_layouts=mono[a]"
    )
    cmd.extend(
        [
            "-filter_complex",
            ";".join(filters),
            "-map",
            "[a]",
            "-c:a",
            "pcm_s16le",
            str(dest),
        ]
    )
    run_ffmpeg(cmd)


def _section_gap(dest: Path, seconds: float) -> None:
    # A soft low knock in the pause, finished before the next sentence.
    _tone_bed(
        dest,
        seconds,
        [
            (174.6, 0.0, 0.20, 0.16),
            (349.2, 0.0, 0.12, 0.05),
        ],
        air=False,
    )


def _require_logo() -> None:
    if not LOGO.is_file():
        raise RuntimeError(f"ไม่พบโลโก้ช่องที่ {LOGO}")


def _brand_events(kind: str, seconds: float, as_of: str, vertical: bool = False) -> list[str]:
    if vertical:
        x, rows = 540, (1120, 1250, 1390)
        notice = ass_escape("ไม่ใช่หน่วยงานรัฐ") + r"\N" + ass_escape("เสียงสังเคราะห์")
        dated = ass_escape("ไม่ใช่หน่วยงานรัฐ") + r"\N" + ass_escape(f"ข้อมูล ณ {as_of}")
        outro_sub = ass_escape("กดติดตาม") + r"\N" + ass_escape("แล้วดูคลิปเต็มในช่อง")
    else:
        x, rows = 960, (760, 860, 960)
        notice = ass_escape("ไม่ใช่หน่วยงานรัฐ  ·  เสียงสังเคราะห์")
        dated = ass_escape(f"ไม่ใช่หน่วยงานรัฐ  ·  ข้อมูล ณ {as_of}")
        outro_sub = ass_escape("กดติดตาม แล้วแชร์ให้คนในบ้าน")
    if kind == "intro":
        texts = [
            ("Brand", 800, ass_escape("สวัสดิการวัยเก๋า")),
            ("BrandSub", 1100, ass_escape("เข้าใจง่าย")),
            ("Fine", 1400, notice),
        ]
        fade_out = 400
    else:
        texts = [
            ("Brand", 700, ass_escape("ขอบพระคุณที่รับชม")),
            ("BrandSub", 1000, outro_sub),
            ("Fine", 1300, dated),
        ]
        fade_out = 500
    if vertical and kind == "outro":
        rows = (1120, 1240, 1450)
    return [
        _dialog(0, seconds, style, rf"{{\an8\fad({fade_in},{fade_out})\pos({x},{y})}}" + text)
        for (style, fade_in, text), y in zip(texts, rows)
    ]


def _write_brand_ass(path: Path, events: list[str], vertical: bool = False) -> None:
    width, height = _frame(vertical)
    sizes = (96, 70, 50) if vertical else (78, 56, 40)
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Brand,Kanit,{sizes[0]},&H000C121A,&H000000FF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,0,0,8,40,40,20,1
Style: BrandSub,Kanit,{sizes[1]},&H00474C0E,&H000000FF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,0,0,8,40,40,20,1
Style: Fine,Sarabun,{sizes[2]},&H000C121A,&H000000FF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,0,0,8,40,40,20,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    path.write_text(header + "\n".join(events) + "\n", encoding="utf-8-sig")


def _render_brand_clip(
    work: Path,
    dest: Path,
    kind: str,
    as_of: str,
    seconds: float | None = None,
    vertical: bool = False,
) -> None:
    _require_logo()
    if seconds is None:
        seconds = INTRO_SECONDS if kind == "intro" else OUTRO_SECONDS
    width, height = _frame(vertical)
    ass = work / f"{kind}.ass"
    _write_brand_ass(ass, _brand_events(kind, seconds, as_of, vertical), vertical)
    wav = work / f"{kind}.wav"
    if kind == "intro":
        notes = [
            (392.0, 0.12, 1.5, 0.13),
            (523.25, 0.28, 1.35, 0.10),
            (659.25, 0.46, 1.15, 0.07),
            (784.0, 0.46, 0.55, 0.04),
        ]
    else:
        notes = [
            (349.23, 0.10, 1.7, 0.13),
            (440.0, 0.32, 1.55, 0.09),
            (523.25, 0.55, 1.4, 0.07),
        ]
    _tone_bed(wav, seconds, notes, air=True)
    # Gold frame, white plate, then the logo eases from small to full size.
    if vertical:
        frame_x, frame_y, frame_w, plate, logo_max, logo_min = 140, 230, 800, 768, 690, 550
    else:
        frame_x, frame_y, frame_w, plate, logo_max, logo_min = 608, 48, 704, 672, 540, 430
    frame_h = frame_w if vertical else 644
    plate_h = plate if vertical else 612
    inner_x, inner_y = frame_x + 16, frame_y + 16
    grow = logo_max - logo_min
    graph = (
        f"[0:v]drawbox=x={frame_x}:y={frame_y}:w={frame_w}:h={frame_h}:color={GOLD}:t=fill,"
        f"drawbox=x={inner_x}:y={inner_y}:w={plate}:h={plate_h}:color=0xFFFFFF:t=fill[plate];"
        f"[1:v]scale={logo_max}:{logo_max}:flags=lanczos,format=rgba,"
        "fade=t=in:st=0:d=0.8:alpha=1,"
        f"scale=w='{logo_min}+{grow}*min(t/1.5,1)':h='{logo_min}+{grow}*min(t/1.5,1)':eval=frame[lg];"
        f"[plate][lg]overlay=x='(W-w)/2':y='{inner_y}+({plate_h}-h)/2+8*sin(2*PI*t/5)*min(t/1.5,1)':eval=frame,"
        f"ass={filter_path(ass, work)}:fontsdir={filter_path(FONTS, work)}[v]"
    )
    run_ffmpeg(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c={PAPER}:s={width}x{height}:r=30:d={seconds:.3f}",
            "-loop",
            "1",
            "-framerate",
            "30",
            "-t",
            f"{seconds:.3f}",
            "-i",
            str(LOGO),
            "-i",
            str(wav),
            "-filter_complex",
            graph,
            "-map",
            "[v]",
            "-map",
            "2:a",
            "-t",
            f"{seconds:.3f}",
            "-r",
            "30",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            "-ar",
            "44100",
            "-ac",
            "1",
            "-movflags",
            "+faststart",
            str(dest),
        ],
        cwd=work,
    )


def _encode_body(
    work: Path,
    listing: Path,
    ass: Path,
    audio: Path,
    dest: Path,
    duration: float,
    vertical: bool = False,
) -> None:
    _require_logo()
    if vertical:
        size = V_LOGO
        top = V_HEIGHT - V_FOOT_H - size - 70
        place = f"x='(W-w)/2':y='{top}+6*sin(2*PI*t/6)'"
    else:
        size = 148
        place = "x=28:y='16+5*sin(2*PI*t/6)'"
    graph = (
        f"[2:v]scale={size}:{size}:flags=lanczos,"
        f"pad={size + 16}:{size + 16}:8:8:0xFFFFFF,"
        f"pad={size + 28}:{size + 28}:6:6:{GOLD},setsar=1,format=rgba[lg];"
        f"[0:v]fps=30,setsar=1,ass={filter_path(ass, work)}:fontsdir={filter_path(FONTS, work)}[base];"
        f"[base][lg]overlay={place}:eval=frame:eof_action=repeat[v]"
    )
    run_ffmpeg(
        [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(listing),
            "-i",
            str(audio),
            "-i",
            str(LOGO),
            "-filter_complex",
            graph,
            "-map",
            "[v]",
            "-map",
            "1:a",
            "-t",
            f"{duration:.3f}",
            "-r",
            "30",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-tune",
            "stillimage",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            "-ar",
            "44100",
            "-ac",
            "1",
            "-movflags",
            "+faststart",
            str(dest),
        ],
        cwd=work,
    )


def _concat_media(paths: list[Path], dest: Path) -> None:
    listing = dest.with_suffix(".ffconcat.txt")
    listing.write_text(
        "ffconcat version 1.0\n"
        + "".join(f"file '{path.resolve().as_posix()}'\n" for path in paths),
        encoding="utf-8",
    )
    run_ffmpeg(
        [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(listing),
            "-c",
            "copy",
            "-movflags",
            "+faststart",
            str(dest),
        ]
    )


def _shift_timeline(pieces: list[dict], cues, seconds: float):
    for piece in pieces:
        piece["start"] += seconds
        piece["end"] += seconds
    shifted = [(start + seconds, end + seconds, text) for start, end, text in cues]
    return pieces, shifted


def _to_wav(src: Path, dest: Path) -> None:
    run_ffmpeg(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(src),
            "-ar",
            "44100",
            "-ac",
            "1",
            "-c:a",
            "pcm_s16le",
            str(dest),
        ]
    )


def _concat(wavs: list[Path], dest: Path) -> None:
    listing = dest.with_suffix(".txt")
    listing.write_text(
        "".join(f"file '{wav.resolve().as_posix()}'\n" for wav in wavs),
        encoding="utf-8",
    )
    run_ffmpeg(
        [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(listing),
            "-c",
            "copy",
            str(dest),
        ]
    )


def _atempo(src: Path, dest: Path, factor: float) -> None:
    run_ffmpeg(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(src),
            "-filter:a",
            f"atempo={factor:.4f}",
            "-ar",
            "44100",
            "-ac",
            "1",
            "-c:a",
            "pcm_s16le",
            str(dest),
        ]
    )


def _cues_for(text: str, bounds: list[dict], start: float) -> list[tuple[float, float, str]]:
    cues: list[tuple[float, float, str]] = []
    if bounds:
        for bound in bounds:
            cue_start = start + (bound["offset"] / 10_000_000)
            cue_end = cue_start + (bound["duration"] / 10_000_000)
            cues.extend(_split_caption(bound["text"], cue_start, cue_end))
        return cues
    return _split_caption(text, start, start + max(1.0, len(text) / 14))


def _split_caption(text: str, start: float, end: float) -> list[tuple[float, float, str]]:
    rows = wrap_thai(text, 38)
    groups = [rows[i : i + 2] for i in range(0, len(rows), 2)] or [[""]]
    weights = [max(1, sum(len(row) for row in group)) for group in groups]
    total = sum(weights)
    span = max(0.4, end - start)
    cursor = start
    cues = []
    for group, weight in zip(groups, weights):
        duration = span * weight / total
        cues.append((cursor, cursor + duration, "\n".join(group)))
        cursor += duration
    return cues


def _scale(pieces, cues, scale: float):
    for piece in pieces:
        piece["start"] *= scale
        piece["end"] *= scale
    return [(start * scale, end * scale, text) for start, end, text in cues]


def _speed_factor(duration: float, low: float, high: float, target: float) -> float:
    if low <= duration <= high:
        return 1.0
    return min(1.08, max(0.90, duration / target))


def _recap_narration(script: dict) -> str:
    bits = ["ทวนจุดที่ควรจำ อีกครั้งแบบช้า ๆ นะคะ"]
    for section in script["sections"]:
        for line in section.get("lines") or []:
            bits.append(line)
    bits.append(
        "จดตัวเลขบนจอไว้ได้เลย แล้วสอบถามองค์กรปกครองส่วนท้องถิ่นตามทะเบียนบ้านก่อนแชร์ต่อค่ะ "
        "ช่องนี้ไม่ใช่หน่วยงานรัฐ อย่าโอนเงินให้ใคร เสียงนี้สร้างด้วยเอไอ ไม่ใช่บุคคลจริง "
        "และไม่ใช่คำแนะนำการเงินส่วนตัว ข้อมูลอยู่บนจอค่ะ"
    )
    return " ".join(bits)


def _cached_voice(text: str, mp3: Path, voice: str, rate: str, pitch: str) -> tuple[list[dict], str]:
    """Reuse a section's audio when an earlier run already voiced the same words."""
    meta = mp3.with_suffix(".json")
    key = {"text": text, "voice": voice, "rate": rate, "pitch": pitch}
    if mp3.exists() and meta.exists():
        saved = json.loads(meta.read_text(encoding="utf-8"))
        if saved.get("key") == key and saved.get("engine") != "gtts":
            return saved["bounds"], saved["engine"]
    bounds, engine = synthesize_section(text, mp3, voice, rate, pitch)
    meta.write_text(
        json.dumps({"key": key, "bounds": bounds, "engine": engine}, ensure_ascii=False),
        encoding="utf-8",
    )
    return bounds, engine


def assemble(
    script: dict,
    work: Path,
    channel: dict,
    limit_sections: int | None,
    fit: bool,
    brief: bool = False,
) -> dict:
    work.mkdir(parents=True, exist_ok=True)
    sections = script["sections"]
    if limit_sections:
        sections = sections[:limit_sections]
    voice = channel["voice"]
    rate = channel["rate"]
    pitch = channel["pitch"]
    pause = float(channel["section_pause_seconds"])
    pieces = []
    cues = []
    wavs: list[Path] = []
    engines: set[str] = set()
    cursor = 0.0
    for index, section in enumerate(sections):
        mp3 = work / f"voice-{index:02d}.mp3"
        wav = work / f"voice-{index:02d}.wav"
        print(f"พากย์ท่อน {index + 1}/{len(sections)} {section['heading']}")
        bounds, engine = _cached_voice(section["narration"], mp3, voice, rate, pitch)
        engines.add(engine)
        _to_wav(mp3, wav)
        spoken = wav_seconds(wav)
        wavs.append(wav)
        cues.extend(_cues_for(section["narration"], bounds, cursor))
        end = cursor + spoken
        hold = pause if index < len(sections) - 1 else 0.0
        if hold:
            silence = work / f"gap-{index:02d}.wav"
            _section_gap(silence, hold)
            wavs.append(silence)
        pieces.append(
            {
                "heading": section["heading"],
                "group": section.get("group") or section["heading"],
                "layout": section.get("layout") or "points",
                "lines": section.get("lines") or [],
                "start": cursor,
                "end": end + hold,
            }
        )
        cursor = end + hold

    audio = work / "voice.wav"
    _concat(wavs, audio)
    duration = wav_seconds(audio)

    intro_seconds = 2.8 if brief else INTRO_SECONDS
    outro_seconds = 3.4 if brief else OUTRO_SECONDS
    chrome = intro_seconds + outro_seconds
    if fit:
        fitting = dict(channel)
        fitting["min_seconds"] = float(channel["min_seconds"]) - chrome
        fitting["max_seconds"] = float(channel["max_seconds"]) - chrome
        fitting["target_seconds"] = float(channel["target_seconds"]) - chrome
        duration, pieces, cues, audio = _fit_length(
            script, work, fitting, pieces, cues, audio, duration, voice, pitch, engines
        )

    vertical = brief
    backgrounds = make_backgrounds(work / "bg", vertical)
    ass = work / "cards.ass"
    write_ass(ass, pieces, script["as_of"], vertical)
    listing = work / "slides.txt"
    slide_lines = ["ffconcat version 1.0"]
    for piece in pieces:
        bg = backgrounds[piece["layout"]]
        slide_lines.append(f"file '{bg.resolve().as_posix()}'")
        slide_lines.append(f"duration {piece['end'] - piece['start']:.3f}")
    slide_lines.append(f"file '{backgrounds[pieces[-1]['layout']].resolve().as_posix()}'")
    listing.write_text("\n".join(slide_lines) + "\n", encoding="utf-8")

    body = work / "video-body.mp4"
    _encode_body(work, listing, ass, audio, body, duration, vertical)
    intro = work / "intro.mp4"
    outro = work / "outro.mp4"
    _render_brand_clip(work, intro, "intro", script["as_of"], intro_seconds, vertical)
    _render_brand_clip(work, outro, "outro", script["as_of"], outro_seconds, vertical)
    video = work / "video.mp4"
    _concat_media([intro, body, outro], video)
    pieces, cues = _shift_timeline(pieces, cues, intro_seconds)
    pieces.insert(
        0,
        {
            "heading": "เปิดคลิป",
            "group": "เปิดคลิป",
            "layout": "title",
            "lines": [],
            "start": 0.0,
            "end": intro_seconds,
        },
    )
    pieces.append(
        {
            "heading": "ปิดคลิป",
            "group": "ปิดคลิป",
            "layout": "end",
            "lines": [],
            "start": intro_seconds + duration,
            "end": intro_seconds + duration + outro_seconds,
        },
    )
    duration = duration + chrome
    srt = work / "captions.srt"
    write_srt(srt, cues)
    thumbnail = work / "thumbnail.jpg"
    _thumbnail(script, work, thumbnail)
    return {
        "video": video,
        "audio_seconds": duration,
        "pieces": pieces,
        "srt": srt,
        "thumbnail": thumbnail,
        "engines": sorted(engines),
    }


def _fit_length(script, work, channel, pieces, cues, audio, duration, voice, pitch, engines):
    low = float(channel["min_seconds"])
    high = float(channel["max_seconds"])
    target = float(channel["target_seconds"])
    factor = _speed_factor(duration, low, high, target)
    if factor != 1.0:
        print(f"ปรับความเร็วเสียง x{factor:.3f} จาก {duration:.0f} วินาที")
        sped = work / "voice-fit.wav"
        _atempo(audio, sped, factor)
        scale = wav_seconds(sped) / duration
        cues = _scale(pieces, cues, scale)
        audio = sped
        duration = wav_seconds(audio)

    stretches = 0
    while duration < low and stretches < 2:
        stretches += 1
        print(f"ความยาวยังไม่ถึง 12 นาที ({duration:.0f} วินาที) เติมท่อนทวน")
        extra_mp3 = work / f"recap-{stretches}.mp3"
        extra_wav = work / f"recap-{stretches}.wav"
        narration = _recap_narration(script)
        bounds, engine = synthesize_section(narration, extra_mp3, voice, "-18%", pitch)
        engines.add(engine)
        _to_wav(extra_mp3, extra_wav)
        silence = work / f"recap-gap-{stretches}.wav"
        _section_gap(silence, 0.4)
        joined = work / f"voice-plus-{stretches}.wav"
        _concat([audio, silence, extra_wav], joined)
        spoken = wav_seconds(extra_wav)
        cues.extend(_cues_for(narration, bounds, duration + 0.4))
        pieces.append(
            {
                "heading": "ทวนอีกครั้ง",
                "group": "ทวนอีกครั้ง",
                "layout": "points",
                "lines": ["ทวนตัวเลขสำคัญ", "สอบถามหน่วยงานในพื้นที่ก่อนแชร์"],
                "start": duration,
                "end": duration + 0.4 + spoken,
            }
        )
        audio = joined
        duration = wav_seconds(audio)

    if duration > high:
        factor = min(1.08, duration / target)
        print(f"คลิปยาวเกิน ปรับความเร็ว x{factor:.3f}")
        sped = work / "voice-trim.wav"
        _atempo(audio, sped, factor)
        scale = wav_seconds(sped) / duration
        cues = _scale(pieces, cues, scale)
        audio = sped
        duration = wav_seconds(audio)

    if duration < low or duration > high + 3:
        raise RuntimeError(
            f"ความยาวสุดท้าย {duration / 60:.2f} นาที อยู่นอกช่วง 12 ถึง 15 นาที"
        )
    return duration, pieces, cues, audio


def _thumb_units(text: str) -> float:
    """Rough Kanit Bold width in font-size units, so long lines shrink instead of hitting the logo."""
    units = 0.0
    for ch in text:
        if is_mark(ch):
            continue
        if ch.isdigit() or ch in ",–-":
            units += 0.54
        elif ch == " ":
            units += 0.24
        else:
            units += 0.4
    return max(units, 1.0)


def _thumbnail(script: dict, work: Path, dest: Path) -> None:
    _require_logo()
    thumb = script.get("thumbnail") or {}
    kicker = thumb.get("kicker") or script["title"]
    title = thumb.get("title") or ""
    big = thumb.get("big") or ""
    bg = work / "thumb-bg.png"
    bar_y = 940
    run_ffmpeg(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c={TEAL}:s=1920x1080:d=1",
            "-vf",
            "drawbox=x=1130:y=0:w=790:h=1080:color=0x13635C:t=fill,"
            f"drawbox=x=0:y={bar_y}:w=1920:h=140:color={INK}:t=fill,"
            f"drawbox=x=0:y={bar_y}:w=1920:h=12:color={GOLD}:t=fill",
            "-frames:v",
            "1",
            str(bg),
        ]
    )
    text_width = 1000
    title_rows = [title] if _thumb_units(title) * 120 <= text_width else _fit_rows(title, max(6, (len(title) + 1) // 2))
    title_size = min(165, int(text_width / max(_thumb_units(row) for row in title_rows))) if title else 0
    big_size = min(240, int(text_width / _thumb_units(big))) if big else 0
    kicker_size = min(84, int((text_width - 60) / _thumb_units(kicker)))
    title_bottom = 250 + len(title_rows) * int(title_size * 1.3)
    events = [
        _dialog(0, 1, "Kicker", rf"{{\an7\pos(100,90)\fs{kicker_size}}}" + ass_escape(kicker)),
        _dialog(
            0,
            1,
            "Title",
            rf"{{\an7\pos(80,250)\fs{title_size}}}" + r"\N".join(ass_escape(row) for row in title_rows),
        ),
        _dialog(0, 1, "Big", rf"{{\an7\pos(80,{title_bottom + 30})\fs{big_size}}}" + ass_escape(big)),
        _dialog(0, 1, "Date", rf"{{\an4\pos(60,{bar_y + 72})}}" + ass_escape(f"ข้อมูล ณ {script['as_of']}")),
        _dialog(0, 1, "Brand", rf"{{\an6\pos(1860,{bar_y + 72})}}" + ass_escape("สวัสดิการวัยเก๋า เข้าใจง่าย")),
    ]
    ass = work / "thumb.ass"
    header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Kicker,Kanit,76,&H000C121A,&H000000FF,&H003FD2FF,&H00000000,-1,0,0,0,100,100,0,0,3,16,0,7,0,0,0,1
Style: Title,Kanit,128,&H00FFFFFF,&H000000FF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,8,5,7,0,0,0,1
Style: Big,Kanit,200,&H003FD2FF,&H000000FF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,10,6,7,0,0,0,1
Style: Date,Sarabun,54,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,0,0,4,0,0,0,1
Style: Brand,Kanit,54,&H003FD2FF,&H000000FF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,0,0,6,0,0,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    ass.write_text(header + "\n".join(events) + "\n", encoding="utf-8-sig")
    png = work / "thumbnail.png"
    run_ffmpeg(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(bg),
            "-i",
            str(LOGO),
            "-filter_complex",
            "[1:v]scale=660:660:flags=lanczos,pad=692:692:16:16:0xFFFFFF,"
            f"pad=716:716:12:12:{GOLD}[lg];"
            f"[0:v]ass={filter_path(ass, work)}:fontsdir={filter_path(FONTS, work)}[base];"
            "[base][lg]overlay=1170:110[v]",
            "-map",
            "[v]",
            "-frames:v",
            "1",
            str(png),
        ],
        cwd=work,
    )
    run_ffmpeg(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(png),
            "-vf",
            "scale=1280:720",
            "-q:v",
            "3",
            str(dest),
        ]
    )


def probe_seconds(path: Path) -> float:
    with wave.open(str(path), "rb") as handle:
        return handle.getnframes() / float(handle.getframerate())
