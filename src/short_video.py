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


def build_short_description(script: dict, short: dict, channel: dict, full_url: str) -> str:
    from src.seo import build_hashtags

    hashtags = " ".join(["#shorts", *build_hashtags(script)[:4]])
    sources = "\n".join(f"- {item['name']} {item['url']}" for item in script.get("sources") or [])
    return (
        f"ไฮไลต์จากคลิปเต็มเรื่อง {script['title']}\n\n"
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
