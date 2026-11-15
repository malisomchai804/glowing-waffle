"""Reject scripts that invent amounts or skip the channel disclaimer."""

from __future__ import annotations

from src.textutil import collect_text, unexpected_numbers

REQUIRED = (
    "ไม่ใช่หน่วยงานรัฐ",
    "ข้อมูล ณ",
    "เอไอ",
    "สอบถาม",
    "ไม่ใช่บุคคลจริง",
    "ไม่ใช่คำแนะนำการเงิน",
)
LOCAL_OFFICE = ("องค์กรปกครองส่วนท้องถิ่น", "อปท", "เทศบาล", "สำนักงานเขต")


def validate(script: dict, facts: dict) -> list[str]:
    errors: list[str] = []
    if not script.get("id") or not script.get("title") or not script.get("as_of"):
        errors.append("ต้องมี id, title และ as_of")
    if len(script.get("title", "")) > 100:
        errors.append("ชื่อคลิปยาวเกิน 100 ตัวอักษรของยูทูบ")
    sections = script.get("sections") or []
    if len(sections) < 8:
        errors.append("บทสั้นเกินไป ต้องมีอย่างน้อย 8 ท่อน")
    for index, section in enumerate(sections, start=1):
        narration = (section.get("narration") or "").strip()
        if len(narration) < 80:
            errors.append(f"ท่อนที่ {index} คำบรรยายสั้นเกินไป")
        if not section.get("heading") or not section.get("lines"):
            errors.append(f"ท่อนที่ {index} ต้องมี heading และ lines")
        layout = section.get("layout", "points")
        if layout not in {"title", "points", "numbers", "warning", "end"}:
            errors.append(f"ท่อนที่ {index} layout ไม่รู้จัก: {layout}")
    blob = collect_text(script)
    for phrase in REQUIRED:
        if phrase not in blob:
            errors.append(f"บทต้องมีประโยค '{phrase}'")
    if not any(phrase in blob for phrase in LOCAL_OFFICE):
        errors.append("บทต้องบอกให้สอบถามหน่วยงานในพื้นที่")
    if "ไม่ให้โอนเงิน" not in blob and "ห้ามโอน" not in blob and "อย่าโอน" not in blob:
        errors.append("บทต้องเตือนไม่ให้โอนเงิน")
    allowed = set(facts.get("allowed_numbers") or [])
    patterns = list(facts.get("phone_patterns") or [])
    bad = unexpected_numbers(blob, allowed, patterns)
    if bad:
        errors.append("พบบัญชีตัวเลขที่ไม่อยู่ในแฟ้มข้อเท็จจริง: " + ", ".join(bad[:12]))
    if not script.get("sources"):
        errors.append("ต้องมีแหล่งที่มา")
    return errors
