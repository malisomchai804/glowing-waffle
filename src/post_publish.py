"""Post the comment on each uploaded video once YouTube has made it public.

YouTube does not accept comments on private or scheduled videos, so the render job only
records what it uploaded. This job runs a few times a day, finds videos that went public
and have no comment yet, and posts the summary + quiz comment as the channel.
The API cannot pin comments: pin it once in Studio (Comments > three dots > Pin).
"""

from __future__ import annotations

import sys

from src.make_video import STATE, build_comment, load, save, script_path, write_log, write_summary
from src.seo import watch_next


def _comment_for(entry: dict, done: list[dict], short: bool) -> str | None:
    try:
        script = load(script_path(entry["id"]))
    except FileNotFoundError:
        print(f"ไม่พบบท {entry['id']} ข้ามคอมเมนต์")
        return None
    if short:
        from src.short_video import build_short_comment
        from src.seo import quiz_text

        quiz = quiz_text(script)
        text = build_short_comment(script, f"https://youtu.be/{entry['youtube_id']}")
        return text + (f"\n\n{quiz}" if quiz else "")
    more = watch_next(done, entry["id"], entry.get("playlist_id") or None)
    return build_comment(script, more)


def main() -> int:
    from src.youtube_upload import post_comment, secrets_ready, video_status

    if not secrets_ready():
        print("ยังไม่มีคีย์ยูทูบ ข้าม")
        return 0
    state = load(STATE)
    done = [item for item in state.get("done", []) if isinstance(item, dict)]
    changed = False
    for entry in done:
        for id_key, comment_key, short in (
            ("youtube_id", "comment_id", False),
            ("short_youtube_id", "short_comment_id", True),
        ):
            video_id = entry.get(id_key)
            # Only entries the uploader marked with comment_key are handled, so videos
            # uploaded before this feature (or by hand) are never commented on twice.
            if not video_id or comment_key not in entry or entry.get(comment_key):
                continue
            status = video_status(video_id)
            if status != "public":
                print(f"{video_id}: ยังเป็น {status} รอเผยแพร่ก่อนค่อยคอมเมนต์")
                continue
            text = _comment_for(entry, done, short)
            if not text:
                continue
            comment_id = post_comment(video_id, text)
            if comment_id:
                entry[comment_key] = comment_id
                changed = True
                write_summary(
                    f"คอมเมนต์แล้ว https://www.youtube.com/watch?v={video_id}&lc={comment_id} "
                    "(ปักหมุดเองใน Studio: Comments > จุดสามจุด > Pin)"
                )
        for extra in entry.get("extra_shorts") or []:
            video_id = extra.get("youtube_id")
            if not video_id or extra.get("comment_id"):
                continue
            status = video_status(video_id)
            if status != "public":
                print(f"{video_id}: ยังเป็น {status} รอเผยแพร่ก่อนค่อยคอมเมนต์")
                continue
            from src.short_video import build_short_comment

            try:
                text = build_short_comment(load(script_path(entry["id"])), f"https://youtu.be/{entry['youtube_id']}")
            except FileNotFoundError:
                continue
            comment_id = post_comment(video_id, text)
            if comment_id:
                extra["comment_id"] = comment_id
                changed = True
                write_summary(f"คอมเมนต์แล้ว https://www.youtube.com/watch?v={video_id}&lc={comment_id}")
    if changed:
        save(STATE, state)
        write_log(state)
    return 0


if __name__ == "__main__":
    sys.exit(main())
