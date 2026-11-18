"""state/TODO.md: only the jobs YouTube's API cannot do, per video, with direct Studio links.

Rebuilt after every render and every comment post. A video stays on the list from upload
until 10 days after it goes public, so nothing needs ticking off by hand.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

THAI = timezone(timedelta(hours=7))
KEEP_DAYS = 10
_DAYS = ["จันทร์", "อังคาร", "พุธ", "พฤหัสบดี", "ศุกร์", "เสาร์", "อาทิตย์"]
_EN_DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _when(iso: str | None) -> datetime | None:
    if not iso:
        return None
    try:
        return datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).astimezone(THAI)
    except ValueError:
        return None


def _say(moment: datetime | None) -> str:
    if not moment:
        return "time not set"
    return f"{_EN_DAYS[moment.weekday()]} {moment.day} {_MONTHS[moment.month - 1]} {moment:%H:%M}"


def _quiz(entry_id: str) -> dict:
    from src.seo import topic_seo

    quiz = topic_seo({"id": entry_id}).get("quiz") or {}
    if not quiz.get("question") or len(quiz.get("options") or []) < 2:
        return {}
    return quiz


def _video_block(item: dict, previous: dict | None) -> list[str]:
    vid, sid = item.get("youtube_id"), item.get("short_youtube_id")
    goes_live = _when(item.get("publish_at"))
    short_live = _when(item.get("short_publish_at"))
    lines = [
        f"## {_say(goes_live)} · {item.get('title', item['id'])}",
        "",
        f"Public from **{_say(goes_live)}** · Long: https://youtu.be/{vid}"
        + (f" · Short: https://youtube.com/shorts/{sid}" if sid else ""),
        "",
        "### Long video",
    ]
    if item.get("comment_id"):
        lines.append(
            f"- [ ] **Pin the comment**: open https://www.youtube.com/watch?v={vid}&lc={item['comment_id']} "
            "→ three dots on the comment → **Pin**"
        )
    else:
        lines.append(
            f"- [ ] **Pin the comment**: GitHub posts it about 20 min after {_say(goes_live)}. "
            f"Then https://studio.youtube.com/video/{vid}/comments → three dots → **Pin**"
        )
    if previous and previous.get("youtube_id"):
        lines.append(
            f"- [ ] **End screen**: https://studio.youtube.com/video/{vid}/editor → End screen → "
            f"**Import from video** → pick \"{previous.get('title', previous['id'])}\" → **Save**"
        )
    else:
        lines.append(
            f"- [ ] **End screen**: https://studio.youtube.com/video/{vid}/editor → End screen → "
            "add **Subscribe** + **Video: Best for viewer** over the last 20 s → **Save**"
        )
    lines.append(
        f"- [ ] *(optional)* **Card**: same editor → Cards → **Playlist** at about the middle of the video"
    )
    if sid:
        lines += [
            "",
            "### Short",
            f"- [ ] **Related video**: https://studio.youtube.com/video/{sid}/edit → **Related video** → "
            f"choose \"{item.get('title', '')}\" → **Save**",
        ]
        if item.get("short_comment_id"):
            lines.append(
                f"- [ ] **Pin the comment**: open https://www.youtube.com/watch?v={sid}&lc={item['short_comment_id']} "
                "→ three dots → **Pin**"
            )
        else:
            lines.append(
                f"- [ ] **Pin the comment**: GitHub posts it about 20 min after {_say(short_live)}. "
                f"Then https://studio.youtube.com/video/{sid}/comments → three dots → **Pin**"
            )
    quiz = _quiz(item["id"])
    if quiz:
        letters = "ABCD"
        answer = (quiz.get("answer") or "").strip().upper()[:1]
        lines += [
            "",
            "### Community quiz (after the video is public)",
            "- [ ] YouTube → **Create** → **Post** → **Quiz**, paste these, tick the ✅ answer, Post:",
            "",
            "```text",
            quiz["question"],
            "```",
        ]
        for index, option in enumerate(quiz["options"][:4]):
            mark = " ✅ correct" if letters[index] == answer else ""
            lines += [f"Option {letters[index]}{mark}", "```text", option, "```"]
    if goes_live:
        lines += [
            "",
            "### Check (optional)",
            f"- [ ] {_say(goes_live + timedelta(days=2))}: https://studio.youtube.com/video/{vid}/analytics "
            "→ if click-through rate is under about 3 %, change the title to a backup title "
            f"(see [kit](kits/{item['id']}.md), step 2)",
        ]
    return lines + ["", "---", ""]


def write_todo(state: dict, folder: Path) -> Path:
    now = datetime.now(THAI)
    uploaded = [
        item for item in state.get("done", [])
        if isinstance(item, dict) and item.get("youtube_id")
    ]
    uploaded.sort(key=lambda item: item.get("publish_at") or "9999")
    blocks: list[str] = []
    previous = None
    for item in uploaded:
        goes_live = _when(item.get("publish_at"))
        if not goes_live or goes_live + timedelta(days=KEEP_DAYS) >= now:
            blocks += _video_block(item, previous)
        previous = item
    head = [
        "# Manual YouTube jobs",
        "",
        "Only the things YouTube's API cannot do. Everything else (upload, title, description, tags, "
        "thumbnail, captions, playlist, schedule, comments) is automatic.",
        f"Videos stay here until {KEEP_DAYS} days after they go public. Times are Thailand time. "
        f"Updated {_say(now)}.",
        "",
        "About 5 minutes per video. Do the long video after it goes public (18:00), the Short after 20:00.",
        "",
        "---",
        "",
    ]
    body = blocks or ["Nothing to do right now.", ""]
    path = folder / "TODO.md"
    path.write_text("\n".join(head + body), encoding="utf-8")
    return path
