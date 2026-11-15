"""Optional script writer. It may only use numbers from the fact file."""

from __future__ import annotations

import json
import os
import re
import urllib.request
from pathlib import Path

from src.validate import validate

ROOT = Path(__file__).resolve().parents[1]
BANK = ROOT / "facts" / "topic_bank.json"
SCRIPTS = ROOT / "topics" / "scripts"
QUEUE = ROOT / "topics" / "queue.json"


def _parse_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()
    return json.loads(text)


def _ask(model: str, prompt: str, key: str) -> str:
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={key}"
    )
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.4, "responseMimeType": "application/json"},
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        body = json.loads(response.read().decode("utf-8"))
    return body["candidates"][0]["content"]["parts"][0]["text"]


def generate_next(facts: dict, channel: dict) -> str:
    bank = json.loads(BANK.read_text(encoding="utf-8"))
    existing = {path.stem for path in SCRIPTS.glob("*.json")}
    topic = next((item for item in bank["topics"] if item["id"] not in existing), None)
    if topic is None:
        raise RuntimeError("ชุดหัวข้อสำรองถูกใช้ครบแล้ว")
    key = os.environ["GEMINI_API_KEY"]
    prompt = f"""
เขียนบทคลิปยูทูบภาษาไทยสำหรับช่อง "{channel['name']}"
โทนเป็นลูกหลานอธิบายให้ผู้ใหญ่ฟัง พูดธรรมชาติ ใช้ "ค่ะ" สุภาพ ไม่ใช่ภาษาประกาศราชการ
ความยาวคำบรรยายรวมทุกท่อนต้องอยู่ระหว่าง 12000 ถึง 13200 ตัวอักษร เพื่อให้เสียงยาว 12 ถึง 15 นาที

หัวข้อ: {topic['title']}
มุมที่ต้องเล่า: {topic['angle']}

ใช้ได้เฉพาะข้อเท็จจริงใน JSON นี้ ห้ามแต่งจำนวนเงิน วันที่จ่าย หรือเบอร์โทรที่ไม่มีอยู่ด้านล่าง
ถ้าข้อเท็จจริงไม่พอ ให้พูดตรง ๆ ว่าให้สอบถามองค์กรปกครองส่วนท้องถิ่น ห้ามพูดว่า "ได้ทุกคน"
ทุกบทต้องมีประโยค: ไม่ใช่หน่วยงานรัฐ, ข้อมูล ณ, เอไอ, สอบถาม, อย่าโอนเงิน, ไม่ใช่บุคคลจริง, ไม่ใช่คำแนะนำการเงิน
ห้ามตั้งชื่อเสียงให้เป็นคนจริง ห้ามเลียนเสียงคนมีชื่อเสียง และห้ามทำเป็นผู้เชี่ยวชาญการเงินส่วนตัว

ข้อเท็จจริง:
{json.dumps(facts, ensure_ascii=False)}

ตอบเป็น JSON เท่านั้น ตามรูปนี้
{{
  "id": "{topic['id']}",
  "title": "ไม่เกิน 90 ตัวอักษร",
  "as_of": "{facts['as_of']}",
  "as_of_iso": "{facts['as_of_iso']}",
  "tags": ["แท็ก", "แท็ก"],
  "description_lead": "ย่อหน้าเกริ่นใต้คลิป",
  "thumbnail": {{"kicker": "", "title": "", "big": ""}},
  "sources": [{{"name": "", "url": "", "must_contain": ["600"]}}],
  "sections": [
    {{"group": "", "heading": "", "layout": "title", "lines": ["", ""], "narration": ""}}
  ]
}}
layout ได้แค่ title, points, numbers, warning, end
""".strip()
    last_error = "ไม่มีคำตอบ"
    for model in channel.get("gemini_models") or ["gemini-2.5-flash"]:
        try:
            raw = _ask(model, prompt, key)
            script = _parse_json(raw)
            errors = validate(script, facts)
            if errors:
                last_error = " ; ".join(errors)
                print(f"{model} เขียนบทไม่ผ่านเกณฑ์: {last_error}")
                continue
            dest = SCRIPTS / f"{script['id']}.json"
            dest.write_text(json.dumps(script, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            queue = json.loads(QUEUE.read_text(encoding="utf-8"))
            if script["id"] not in queue["order"]:
                queue["order"].append(script["id"])
                QUEUE.write_text(json.dumps(queue, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(f"เขียนบทใหม่ด้วย {model}: {script['id']}")
            return script["id"]
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
            print(f"{model} ใช้ไม่ได้: {last_error[:240]}")
    raise RuntimeError(f"สร้างบทใหม่อัตโนมัติไม่สำเร็จ: {last_error}")
