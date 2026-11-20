"""A short companion that recaps highlights and points to the full video."""

from __future__ import annotations

from src.textutil import collect_text, unexpected_numbers

HIGHLIGHTS = 4
SKIP = ("ทวน", "ก่อนปิด", "ช่องนี้เป็นใคร", "ทำไมคลิป", "ทำไมต้อง")


def build_short_script(script: dict, channel: dict) -> dict:
    thumb = script.get("thumbnail") or {}
    title = _short_title(script["title"])
    sections = [_spoken(section, index == 0, channel["name"]) for index, section in enumerate(_pick(script["sections"]))]
    sections.append(_cta(script, channel["name"]))
    return {
        "id": f"{script['id']}-short",
        "title": title,
        "as_of": script["as_of"],
        "as_of_iso": script.get("as_of_iso", ""),
        "tags": list(script.get("tags") or []),
        "description_lead": f"ไฮไลต์จากคลิปเต็มเรื่อง {script['title']}",
        "thumbnail": {
            "kicker": "ไฮไลต์",
            "title": thumb.get("title") or "ดูคลิปเต็ม",
            "big": thumb.get("big") or "ในช่อง",
        },
        "sources": script.get("sources") or [],
        "sections": sections,
        "full_title": script["title"],
    }


def guard_numbers(short: dict, facts: dict) -> None:
    allowed = {str(item) for item in facts.get("allowed_numbers") or []}
    patterns = list(facts.get("phone_patterns") or [])
    bad = unexpected_numbers(collect_text(short), allowed, patterns)
    if bad:
        raise RuntimeError("คลิปสั้นมีตัวเลขนอกแฟ้มข้อเท็จจริง: " + ", ".join(bad[:12]))


def build_extra_shorts(script: dict, channel: dict, highlight: dict) -> list[dict]:
    """Extra Shorts in other formats, each saying something the highlight Short did not.

    quiz:  ask the topic's quiz question, give a beat to think, then reveal the answer.
    focus: one part of the topic (preferably a warning) explained on its own.
    Everything comes from the checked script and seo.json, so no new facts are added.
    """
    extras = []
    for maker in (_quiz_short, _focus_short):
        short = maker(script, channel, highlight)
        if short:
            extras.append(short)
    return extras


def _doc(script: dict, kind: str, title: str, lead: str, kicker: str, sections: list[dict]) -> dict:
    thumb = script.get("thumbnail") or {}
    return {
        "id": f"{script['id']}-{kind}",
        "kind": kind,
        "title": _fit_title(title),
        "as_of": script["as_of"],
        "as_of_iso": script.get("as_of_iso", ""),
        "tags": list(script.get("tags") or []),
        "description_lead": lead,
        "thumbnail": {
            "kicker": kicker,
            "title": thumb.get("title") or "ดูคลิปเต็ม",
            "big": thumb.get("big") or "ในช่อง",
        },
        "sources": script.get("sources") or [],
        "sections": sections,
        "full_title": script["title"],
    }


_ORDINAL = ["หนึ่ง", "สอง", "สาม", "สี่"]


def _chunks(text: str, width: int = 18) -> list[str]:
    """Split at the spaces Thai writers already use, so the card never breaks inside a word."""
    rows: list[str] = []
    for word in text.split():
        if rows and len(rows[-1]) + 1 + len(word) <= width:
            rows[-1] += " " + word
        else:
            rows.append(word)
    return rows or [text]


def _quiz_short(script: dict, channel: dict, highlight: dict) -> dict | None:
    from src.seo import topic_seo

    quiz = topic_seo(script).get("quiz") or {}
    question = (quiz.get("question") or "").strip()
    options = [option.strip() for option in quiz.get("options") or [] if option.strip()][:4]
    answer_index = "ABCD".find((quiz.get("answer") or "").strip().upper()[:1])
    if not question or len(options) < 2 or not 0 <= answer_index < len(options):
        return None
    # The points card numbers each row 1, 2, 3 by itself, so speak the same numbers.
    spoken_options = " ".join(
        f"ข้อที่{_ORDINAL[index]} {option}" for index, option in enumerate(options)
    )
    letter = _ORDINAL[answer_index]
    sections = [
        {
            "heading": "ทายก่อนเฉลย",
            "group": "คำถาม",
            "layout": "title",
            "lines": _chunks(question),
            "narration": (
                f"สวัสดีค่ะ ช่อง{channel['name']} วันนี้ลองทายก่อนนะคะ {question}"
            ),
        },
        {
            "heading": "เลือกข้อไหนดี",
            "group": "ตัวเลือก",
            "layout": "points",
            "lines": options,
            "narration": f"{spoken_options} ลองตอบในใจก่อนค่ะ หนึ่ง สอง สาม",
        },
        {
            "heading": f"เฉลย ข้อที่{letter}",
            "group": "เฉลย",
            "layout": "title",
            "lines": _chunks(options[answer_index]),
            "narration": (
                f"เฉลยค่ะ ข้อที่{letter} {options[answer_index]} "
                "พิมพ์ตอบในคอมเมนต์ได้เลยว่าคุณตอบถูกไหมคะ"
            ),
        },
        _cta(script, channel["name"]),
    ]
    return _doc(
        script,
        "quiz",
        f"ทายก่อนเฉลย | {question}",
        f"ควิซจากคลิปเต็มเรื่อง {script['title']}",
        "ทายก่อนเฉลย",
        sections,
    )


def _focus_short(script: dict, channel: dict, highlight: dict) -> dict | None:
    used = {section["heading"] for section in highlight.get("sections") or []}
    groups: dict[str, list[dict]] = {}
    for section in script["sections"]:
        if _skip(section) or section["heading"] in used or section.get("layout") in ("title", "end"):
            continue
        groups.setdefault(section.get("group") or section["heading"], []).append(section)
    if not groups:
        return None

    # Prefer a warning group, then the group with the most unused sections.
    def score(item: tuple[str, list[dict]]) -> tuple[int, int]:
        name, sections = item
        warns = sum(1 for section in sections if section.get("layout") == "warning")
        return (warns, len(sections))

    group, chosen = max(groups.items(), key=score)
    chosen = chosen[:3]
    spoken = []
    for index, section in enumerate(chosen):
        item = _spoken(section, False, channel["name"])
        if index == 0:
            item["narration"] = f"สวัสดีค่ะ ช่อง{channel['name']} เรื่องนี้ต้องรู้ค่ะ {group} " + item["narration"]
        spoken.append(item)
    spoken.append(_cta(script, channel["name"]))
    warning = any(section.get("layout") == "warning" for section in chosen)
    kicker = "ระวัง" if warning else "ต้องรู้"
    label = f"{group}!" if group.startswith(kicker) else f"{kicker}! {group}"
    return _doc(
        script,
        "focus",
        f"{label} | {script['title']}",
        f"เจาะเรื่อง{group} จากคลิปเต็มเรื่อง {script['title']}",
        kicker,
        spoken,
    )


def _fit_title(title: str) -> str:
    return title if len(title) <= 100 else title[:99].rstrip() + "…"


def build_short_description(script: dict, short: dict, channel: dict, full_url: str) -> str:
    from src.seo import build_hashtags

    hashtags = " ".join(["#shorts", *build_hashtags(script)[:4]])
    sources = "\n".join(f"- {item['name']} {item['url']}" for item in script.get("sources") or [])
    lead = short.get("description_lead") or f"ไฮไลต์จากคลิปเต็มเรื่อง {script['title']}"
    return (
        f"{lead}\n\n"
        "คลิปนี้สรุปเฉพาะจุดสำคัญ ไม่ได้ลงรายละเอียดทั้งหมด\n"
        f"ดูคลิปเต็มได้ที่ลิงก์นี้\n{full_url}\n"
        f"กดติดตามช่อง\n{channel['channel_url']}?sub_confirmation=1\n\n"
        f"ข้อมูล ณ {script['as_of']}\n\n"
        f"แหล่งที่มา\n{sources}\n\n"
        "ช่องนี้ไม่ใช่หน่วยงานรัฐ ไม่เคยขอข้อมูลส่วนตัว เลขบัตรประชาชน รหัส OTP หรือให้โอนเงินใดๆ\n"
        "เสียงบรรยายสร้างด้วย AI (text-to-speech) เป็นเสียงสังเคราะห์ ไม่ใช่บุคคลจริง\n"
        "คลิปนี้เป็นการอธิบายประกาศสาธารณะ ไม่ใช่คำแนะนำการเงินส่วนตัว\n\n"
        f"{hashtags}\n"
    )


def build_short_comment(script: dict, full_url: str) -> str:
    return (
        f"ดูคลิปเต็ม: {full_url}\n"
        f"ข้อมูล ณ {script['as_of']}\n"
        "ช่องนี้ไม่ใช่หน่วยงานรัฐ ไม่ขอเลขบัตรประชาชน รหัส OTP และไม่มีทางให้โอนเงิน"
    )


def _short_title(title: str) -> str:
    prefix = "ไฮไลต์ | "
    room = 100 - len(prefix)
    trimmed = title if len(title) <= room else title[: room - 1].rstrip() + "…"
    return prefix + trimmed


def _skip(section: dict) -> bool:
    heading = section.get("heading") or ""
    return any(part in heading for part in SKIP)


def _pick(sections: list[dict]) -> list[dict]:
    chosen: list[dict] = []

    def add(section: dict) -> None:
        if section in chosen or len(chosen) >= HIGHLIGHTS or _skip(section):
            return
        chosen.append(section)

    for layout in ("title", "warning", "numbers"):
        for section in sections:
            if section.get("layout") != layout:
                continue
            before = len(chosen)
            add(section)
            if len(chosen) > before:
                break
    points = [section for section in sections if section.get("layout") == "points"]
    for section in points:
        if len(section.get("lines") or []) >= 3:
            add(section)
    for section in points:
        add(section)
    if not chosen and sections:
        chosen.append(sections[0])
    return chosen


def _spoken(section: dict, first: bool, channel_name: str) -> dict:
    lines = [line.strip() for line in section.get("lines") or [] if line.strip()]
    detail = " ".join(lines)
    if first:
        narration = (
            f"สวัสดีค่ะ ช่อง{channel_name} นี่คือไฮไลต์ของคลิปเต็มค่ะ "
            f"{section['heading']} {detail}"
        )
    else:
        narration = f"{section['heading']} ค่ะ {detail}"
    layout = section.get("layout") or "points"
    if layout == "numbers" and len(lines) > 3:
        layout = "points"
    return {
        "heading": section["heading"],
        "group": section.get("group") or section["heading"],
        "layout": layout,
        "lines": lines,
        "narration": narration,
    }


def _cta(script: dict, channel_name: str) -> dict:
    as_of = script["as_of"]
    return {
        "heading": "ดูคลิปเต็มในช่อง",
        "group": "ชวนดูคลิปเต็ม",
        "layout": "title",
        "lines": [
            "กดติดตามช่องนี้",
            "ดูคลิปเต็มในช่อง",
            "ลิงก์อยู่ในคำอธิบาย",
        ],
        "narration": (
            f"นี่เป็นแค่ไฮไลต์ค่ะ คลิปเต็มอธิบายทีละขั้น "
            f"กดติดตามช่อง{channel_name} ไว้ก่อน "
            f"แล้วเปิดคลิปเต็มจากลิงก์ในคำอธิบายใต้คลิปนี้ "
            f"ช่องนี้ไม่ใช่หน่วยงานรัฐ อย่าโอนเงินให้ใคร "
            f"เสียงนี้สร้างด้วยเอไอ ไม่ใช่บุคคลจริง และไม่ใช่คำแนะนำการเงินส่วนตัว "
            f"ข้อมูล ณ {as_of} "
            f"ถ้าไม่แน่ใจ ให้สอบถามองค์กรปกครองส่วนท้องถิ่นตามทะเบียนบ้านก่อนแชร์ต่อค่ะ"
        ),
    }
