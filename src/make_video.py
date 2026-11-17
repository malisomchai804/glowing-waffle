"""Build one Thai welfare video, or check that a script is long enough and sourced."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from src.textutil import clock
from src.validate import validate

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "topics" / "scripts"
QUEUE = ROOT / "topics" / "queue.json"
STATE = ROOT / "state" / "published.json"
CHANNEL = ROOT / "channel.json"
FACTS = ROOT / "facts" / "benefits.json"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def save(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def published_ids(state: dict) -> set[str]:
    return {item["id"] if isinstance(item, dict) else item for item in state.get("done", [])}


def resolve_topic(topic: str, state: dict) -> str | None:
    if topic != "next":
        return topic
    done = published_ids(state)
    for item in load(QUEUE).get("order", []):
        if item not in done:
            return item
    return None


def script_path(topic_id: str) -> Path:
    direct = SCRIPTS / f"{topic_id}.json"
    if direct.exists():
        return direct
    matches = list(SCRIPTS.glob(f"{topic_id}*.json"))
    if len(matches) == 1:
        return matches[0]
    raise FileNotFoundError(f"ไม่พบบท {topic_id}")


def estimate_minutes(script: dict, channel: dict) -> float:
    chars = sum(len(section["narration"]) for section in script["sections"])
    pauses = max(0, len(script["sections"]) - 1) * float(channel["section_pause_seconds"])
    return chars / float(channel["chars_per_second"]) / 60 + pauses / 60


def build_description(
    script: dict,
    pieces: list[dict],
    warnings: list[str],
    engines: list[str],
    channel: dict,
    more: str = "",
) -> str:
    from src.seo import build_hashtags

    chapters = []
    seen: set[str] = set()
    for piece in pieces:
        group = piece["group"]
        if group in seen:
            continue
        seen.add(group)
        stamp = "0:00" if not chapters else clock(piece["start"])
        chapters.append(f"{stamp} {group}")
    sources = "\n".join(f"- {item['name']} {item['url']}" for item in script["sources"])
    warning = ("\n".join(warnings) + "\n\n") if warnings else ""
    voice = "เสียงบรรยายสร้างด้วย AI (text-to-speech)"
    if "gtts" in engines:
        voice += " รอบนี้ใช้เสียงสำรอง เพราะเสียงหลักเชื่อมต่อไม่ได้"
    lead = script.get("description_lead", "").strip()
    hashtags = " ".join(build_hashtags(script))
    return (
        f"{script['title']}\n{lead}\n\n"
        f"กดติดตามช่อง {channel['name']}\n{channel['channel_url']}?sub_confirmation=1\n\n"
        f"ข้อมูล ณ {script['as_of']}\n{warning}"
        "มีคลิปสั้นสรุปไฮไลต์ของเรื่องนี้ คู่กับคลิปเต็ม\n\n"
        f"สารบัญ\n" + "\n".join(chapters) + "\n\n"
        + (f"{more}\n\n" if more else "")
        +
        f"แหล่งที่มา\n{sources}\n\n"
        "ช่องนี้ไม่ใช่หน่วยงานรัฐ ไม่เคยขอข้อมูลส่วนตัว เลขบัตรประชาชน รหัส OTP หรือให้โอนเงินใดๆ\n"
        "หากมีผู้แอบอ้างชื่อช่องติดต่อท่าน โปรดอย่าหลงเชื่อ\n"
        f"{voice} เสียงนี้เป็นเสียงสังเคราะห์ ไม่ใช่บุคคลจริง\n"
        "คลิปนี้เป็นการอธิบายประกาศสาธารณะ ไม่ใช่คำแนะนำการเงินส่วนตัว\n"
        "บทเรียบเรียงจากแหล่งด้านบน\n"
        "หากข้อมูลเปลี่ยน จะปักหมุดแจ้งแก้ไขในคอมเมนต์\n\n"
        f"{hashtags}\n"
    )


def _recap_lines(script: dict) -> list[str]:
    for section in reversed(script["sections"]):
        if "ทวน" in section.get("heading", "") and section.get("lines"):
            return [line.strip() for line in section["lines"] if line.strip()][:4]
    return []


def build_comment(script: dict, more: str = "") -> str:
    from src.seo import quiz_text, topic_seo

    recap = "\n".join(f"- {line}" for line in _recap_lines(script))
    question = topic_seo(script).get(
        "comment_question",
        "ที่บ้านเคยเจอโพสต์หรือข้อความเรื่องนี้ไหมคะ เล่าให้ฟังได้ในคอมเมนต์",
    )
    quiz = quiz_text(script)
    return (
        f"สรุปสั้น ข้อมูล ณ {script['as_of']}\n"
        + (f"{recap}\n\n" if recap else "\n")
        + (f"{quiz}\n\n" if quiz else "")
        + f"{question}\n"
        "ขอความกรุณาอย่าพิมพ์เลขบัตรประชาชน เบอร์โทร หรือเลขบัญชีในคอมเมนต์นะคะ\n\n"
        "ถ้าหน่วยงานรัฐปรับตัวเลขหลังวันนี้ เราจะมาแก้ไขในคอมเมนต์นี้\n"
        "ช่องนี้ไม่ใช่หน่วยงานรัฐ ไม่ขอเลขบัตรประชาชน รหัส OTP และไม่มีทางให้โอนเงิน\n"
        "ถ้าคลิปนี้ช่วยได้ ฝากกดติดตาม แล้วส่งต่อให้คนในบ้านด้วยนะคะ"
        + (f"\n\n{more}" if more else "")
    )


def mark_done(entry: dict) -> None:
    state = load(STATE)
    state["done"] = [
        item
        for item in state.get("done", [])
        if (item.get("id") if isinstance(item, dict) else item) != entry["id"]
    ]
    state["done"].append(entry)
    save(STATE, state)
    write_log(state)


def write_log(state: dict) -> None:
    rows = [
        "# Videos already made",
        "",
        "The factory skips every topic listed here when it picks the next video. "
        "This page is rebuilt from `published.json` after each render.",
        "",
        "| # | Topic | Title | Made on | Data as of | Long | Short | Studio steps | YouTube (long) | YouTube (short) | Publishing |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for index, item in enumerate(state.get("done", []), start=1):
        if not isinstance(item, dict):
            item = {"id": item}
        long_link = f"https://youtu.be/{item['youtube_id']}" if item.get("youtube_id") else "not uploaded"
        short_link = (
            f"https://youtube.com/shorts/{item['short_youtube_id']}"
            if item.get("short_youtube_id")
            else "not uploaded"
        )
        long_len = clock(item["seconds"]) if item.get("seconds") else ""
        short_len = clock(item["short_seconds"]) if item.get("short_seconds") else ""
        rows.append(
            f"| {index} | {item['id']} | {item.get('title', '')} | {item.get('rendered_at', '')} | "
            f"{item.get('as_of', '')} | {long_len} | {short_len} | [steps](kits/{item['id']}.md) | "
            f"{long_link} | {short_link} | {item.get('publish', '')} |"
        )
    (STATE.parent / "VIDEOS.md").write_text("\n".join(rows) + "\n", encoding="utf-8")


def _write_short_package(folder: Path, short: dict, result: dict, script: dict, channel: dict, full_url: str) -> str:
    from src.short_video import build_short_comment, build_short_description

    folder.mkdir(parents=True, exist_ok=True)
    (folder / "video.mp4").write_bytes(result["video"].read_bytes())
    (folder / "thumbnail.jpg").write_bytes(result["thumbnail"].read_bytes())
    (folder / "captions.srt").write_text(result["srt"].read_text(encoding="utf-8"), encoding="utf-8")
    description = build_short_description(script, short, channel, full_url)
    (folder / "description.txt").write_text(description, encoding="utf-8")
    (folder / "title.txt").write_text(short["title"] + "\n", encoding="utf-8")
    (folder / "pinned-comment.txt").write_text(build_short_comment(script, full_url), encoding="utf-8")
    return description


_WEEKDAY = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}


def publish_slots(script: dict, channel: dict) -> tuple[str | None, str | None, str]:
    """Next long-video 18:00 Thailand slot (Sun/Tue/Thu/Sat) and Short after it, as UTC."""
    rules = channel.get("publish") or {}
    mode = (os.environ.get("PUBLISH_MODE") or rules.get("mode") or "private").lower()
    if mode != "schedule":
        return None, None, "ตั้งเป็นส่วนตัว ต้องกดเผยแพร่เองใน Studio"
    as_of = script.get("as_of_iso")
    max_age = int(rules.get("max_data_age_days", 20))
    if as_of and (date.today() - date.fromisoformat(as_of)).days > max_age:
        return None, None, (
            f"ข้อมูลเก่ากว่า {max_age} วัน จึงอัปเป็นส่วนตัวแทนการตั้งเวลา "
            "ตรวจตัวเลขแล้วค่อยกดเผยแพร่เอง"
        )
    thailand = timezone(timedelta(hours=float(rules.get("utc_offset_hours", 7))))
    hour, minute = (int(part) for part in str(rules.get("long_time", "18:00")).split(":"))
    allowed = {
        _WEEKDAY[name.strip().lower()[:3]]
        for name in (rules.get("weekdays") or ["sun", "tue", "thu", "sat"])
    }
    lead = timedelta(minutes=int(rules.get("min_lead_minutes", 90)))
    now = datetime.now(thailand)
    slot = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    for _ in range(14):
        if slot.weekday() in allowed and slot - now >= lead:
            break
        slot += timedelta(days=1)
        slot = slot.replace(hour=hour, minute=minute, second=0, microsecond=0)
    else:
        return None, None, "หาเวลาเผยแพร่ไม่เจอ จึงอัปเป็นส่วนตัว"
    short_local = slot + timedelta(minutes=int(rules.get("short_delay_minutes", 120)))
    long_utc = slot.astimezone(timezone.utc)
    short_utc = short_local.astimezone(timezone.utc)
    fmt = "%Y-%m-%dT%H:%M:%SZ"
    note = (
        f"ตั้งเวลาเผยแพร่อัตโนมัติ: คลิปยาว {slot:%Y-%m-%d %H:%M} "
        f"คลิปสั้น {short_local:%Y-%m-%d %H:%M} (เวลาไทย) "
        "ยูทูบจะเปลี่ยนจากส่วนตัวเป็นสาธารณะเองเมื่อถึงเวลา"
    )
    return long_utc.strftime(fmt), short_utc.strftime(fmt), note


def write_studio_steps(package: Path, script: dict, channel: dict, seconds: float, short_seconds: float, keep: bool) -> Path:
    from src.seo import studio_steps

    steps = studio_steps(package, script, channel, seconds, short_seconds)
    (package / "YOUTUBE-STUDIO-STEPS.md").write_text(steps, encoding="utf-8")
    kept = STATE.parent / "kits" / f"{script['id']}.md"
    if keep:
        kept.parent.mkdir(parents=True, exist_ok=True)
        kept.write_text(steps, encoding="utf-8")
    return kept


def write_summary(text: str) -> None:
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    print(text)
    if path:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(text + "\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--topic", default=os.environ.get("TOPIC", "next"))
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--skip-source-check", action="store_true")
    parser.add_argument("--mark", action="store_true")
    parser.add_argument("--no-upload", action="store_true")
    parser.add_argument("--generate-if-empty", action="store_true")
    args = parser.parse_args()

    channel = load(CHANNEL)
    facts = load(FACTS)
    state = load(STATE)
    topic = resolve_topic(args.topic, state)
    if topic is None:
        if args.generate_if_empty and os.environ.get("GEMINI_API_KEY"):
            from src.generate_script import generate_next

            topic = generate_next(facts, channel)
        else:
            write_summary("คิวคลิปว่างแล้ว ไม่มีบทใหม่ให้เรนเดอร์")
            return 0

    from src.seo import check_seo_numbers

    path = script_path(topic)
    script = load(path)
    errors = validate(script, facts) + check_seo_numbers(script, facts)
    minutes = estimate_minutes(script, channel)
    print(f"{script['id']}: ประมาณ {minutes:.1f} นาที จากความยาวบท")
    if errors:
        print("\n".join(errors))
        return 1
    if args.check:
        low = channel["min_seconds"] / 60
        high = channel["max_seconds"] / 60
        if not (low - 1.2 <= minutes <= high + 1.2):
            print("ความยาวโดยประมาณอยู่นอกช่วง 12 ถึง 15 นาทีมากเกินไป")
            return 1
        print("บทผ่านการตรวจ")
        return 0

    as_of = script.get("as_of_iso")
    if as_of and date.today() > date.fromisoformat(as_of) + timedelta(days=45):
        print("คำเตือน: บทนี้อ้างอิงข้อมูลเก่ากว่า 45 วัน ตรวจตัวเลขก่อนกดเผยแพร่")

    warnings: list[str] = []
    if not args.skip_source_check and not args.smoke:
        from src.sources import check_sources

        warnings = check_sources(script)
        for warning in warnings:
            print(warning)

    from src.render import assemble
    from src.short_video import build_short_script, guard_numbers

    work = ROOT / "out" / ("smoke" if args.smoke else script["id"])
    result = assemble(
        script,
        work,
        channel,
        limit_sections=2 if args.smoke else None,
        fit=not args.smoke,
    )
    short_script = build_short_script(script, channel)
    guard_numbers(short_script, facts)
    short_result = assemble(
        short_script,
        work / "short",
        channel,
        limit_sections=None,
        fit=False,
        brief=True,
    )
    from src.seo import build_hashtags, build_tags, title_options

    package = ROOT / "out" / "package"
    if package.exists():
        shutil.rmtree(package)
    package.mkdir(parents=True, exist_ok=True)
    video = package / "video.mp4"
    video.write_bytes(result["video"].read_bytes())
    thumbnail = package / "thumbnail.jpg"
    thumbnail.write_bytes(result["thumbnail"].read_bytes())
    (package / "captions.srt").write_text(result["srt"].read_text(encoding="utf-8"), encoding="utf-8")
    description = build_description(script, result["pieces"], warnings, result["engines"], channel)
    (package / "description.txt").write_text(description, encoding="utf-8")
    (package / "title.txt").write_text(script["title"] + "\n", encoding="utf-8")
    (package / "title-options.txt").write_text("\n".join(title_options(script)) + "\n", encoding="utf-8")
    tags = build_tags(script)
    (package / "tags.txt").write_text(", ".join(tags) + "\n", encoding="utf-8")
    (package / "hashtags.txt").write_text(" ".join(build_hashtags(script)) + "\n", encoding="utf-8")
    (package / "pinned-comment.txt").write_text(build_comment(script), encoding="utf-8")
    (package / "topic.txt").write_text(script["id"] + "\n", encoding="utf-8")

    full_url = channel["channel_url"]
    _write_short_package(package / "short", short_script, short_result, script, channel, full_url)

    seconds = result["audio_seconds"]
    short_seconds = short_result["audio_seconds"]
    write_summary(
        f"เรนเดอร์ {script['id']} ความยาว {seconds / 60:.2f} นาที "
        f"และคลิปสั้น {short_seconds:.0f} วินาที เสียง {', '.join(result['engines'])}"
    )
    youtube_id = ""
    short_id = ""
    upload_extra: dict = {}
    upload = not args.no_upload and not args.smoke and os.environ.get("UPLOAD", "true").lower() != "false"
    publish_note = ""
    if upload:
        from src.youtube_upload import secrets_ready, upload_video

        if secrets_ready():
            from src.seo import playlist_title, watch_next
            from src.youtube_upload import add_to_playlist, ensure_playlist

            long_at, short_at, publish_note = publish_slots(script, channel)
            playlist_id = ensure_playlist(
                playlist_title(script),
                f"รวมคลิปจากช่อง {channel['name']} อธิบายสวัสดิการให้เข้าใจง่าย พร้อมแหล่งที่มา",
            )
            more = watch_next(state.get("done", []), script["id"], playlist_id)
            description = build_description(
                script, result["pieces"], warnings, result["engines"], channel, more
            )
            (package / "description.txt").write_text(description, encoding="utf-8")
            (package / "pinned-comment.txt").write_text(build_comment(script, more), encoding="utf-8")
            youtube_id = upload_video(
                video,
                thumbnail,
                script["title"],
                description,
                tags,
                channel["category_id"],
                publish_at=long_at,
                captions=package / "captions.srt",
            )
            full_url = f"https://youtu.be/{youtube_id}"
            short_description = _write_short_package(
                package / "short", short_script, short_result, script, channel, full_url
            )
            short_id = upload_video(
                package / "short" / "video.mp4",
                None,
                short_script["title"],
                short_description,
                ["shorts", *tags][:15],
                channel["category_id"],
                publish_at=short_at,
                captions=package / "short" / "captions.srt",
            )
            add_to_playlist(playlist_id, youtube_id)
            add_to_playlist(playlist_id, short_id)
            upload_extra = {
                "publish_at": long_at or "",
                "short_publish_at": short_at or "",
                "playlist_id": playlist_id or "",
                "comment_id": "",
                "short_comment_id": "",
            }
            write_summary(
                f"อัปแล้ว: https://youtu.be/{youtube_id} และคลิปสั้น https://youtube.com/shorts/{short_id}\n"
                f"{publish_note}"
            )
        else:
            print("ยังไม่มีคีย์ยูทูบ ข้ามการอัปโหลด ดาวน์โหลดไฟล์จาก artifact ได้")
    write_studio_steps(package, script, channel, seconds, short_seconds, keep=not args.smoke)
    if args.mark and not args.smoke:
        mark_done(
            {
                "id": script["id"],
                "title": script["title"],
                "short_title": short_script["title"],
                "as_of": script["as_of"],
                "rendered_at": date.today().isoformat(),
                "seconds": round(seconds, 1),
                "short_seconds": round(short_seconds, 1),
                "youtube_id": youtube_id,
                "short_youtube_id": short_id,
                "publish": publish_note,
                **upload_extra,
            }
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
