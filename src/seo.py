"""Tags, hashtags, title options and the upload checklist for each video."""

from __future__ import annotations

import json
from pathlib import Path

from src.textutil import unexpected_numbers

ROOT = Path(__file__).resolve().parents[1]
SEO = ROOT / "topics" / "seo.json"
# YouTube allows 500 characters of tags; multi-word tags count their quotes.
TAG_BUDGET = 480
# More than 15 hashtags makes YouTube ignore every hashtag on the video.
MAX_HASHTAGS = 5


def load_seo() -> dict:
    if SEO.exists():
        return json.loads(SEO.read_text(encoding="utf-8"))
    return {"channel_tags": [], "topics": {}}


def topic_seo(script: dict) -> dict:
    seo = load_seo()
    return seo.get("topics", {}).get(script["id"], {})


def build_tags(script: dict) -> list[str]:
    seo = load_seo()
    extra = seo.get("topics", {}).get(script["id"], {}).get("tags", [])
    pool = [*(script.get("tags") or []), *extra, *seo.get("channel_tags", [])]
    tags: list[str] = []
    used = 0
    for tag in pool:
        tag = tag.strip().lstrip("#")
        if not tag or tag in tags or len(tag) > 100:
            continue
        cost = len(tag) + (2 if " " in tag else 0) + (1 if tags else 0)
        if used + cost > TAG_BUDGET:
            continue
        tags.append(tag)
        used += cost
    return tags


def build_hashtags(script: dict) -> list[str]:
    chosen = topic_seo(script).get("hashtags") or [
        "#สวัสดิการผู้สูงอายุ",
        "#ผู้สูงอายุ",
        "#เบี้ยยังชีพผู้สูงอายุ",
    ]
    clean = []
    for tag in chosen:
        tag = "#" + tag.strip().lstrip("#").replace(" ", "")
        if tag not in clean:
            clean.append(tag)
    return clean[:MAX_HASHTAGS]


def title_options(script: dict) -> list[str]:
    options = [script["title"], *topic_seo(script).get("title_options", [])]
    return [option for index, option in enumerate(options) if option and option not in options[:index]]


def check_seo_numbers(script: dict, facts: dict) -> list[str]:
    entry = topic_seo(script)
    blob = "\n".join(
        [
            *entry.get("title_options", []),
            *entry.get("tags", []),
            *entry.get("hashtags", []),
            entry.get("comment_question", ""),
            entry.get("playlist", ""),
            quiz_text(script),
        ]
    )
    allowed = {str(item) for item in facts.get("allowed_numbers") or []}
    bad = unexpected_numbers(blob, allowed, list(facts.get("phone_patterns") or []))
    return [f"topics/seo.json มีตัวเลขนอกแฟ้มข้อเท็จจริง: {', '.join(bad)}"] if bad else []


DEFAULT_PLAYLIST = "สวัสดิการผู้สูงอายุ อัปเดตล่าสุด"


def playlist_title(script: dict) -> str:
    seo = load_seo()
    return topic_seo(script).get("playlist") or seo.get("default_playlist") or DEFAULT_PLAYLIST


def quiz_text(script: dict) -> str:
    """A tap-to-answer quiz for the comment. Answers in comments are a strong engagement signal."""
    quiz = topic_seo(script).get("quiz") or {}
    question = (quiz.get("question") or "").strip()
    options = [option.strip() for option in quiz.get("options") or [] if option.strip()]
    if not question or len(options) < 2:
        return ""
    letters = "ABCD"
    lines = [f"ควิซ: {question}"]
    lines += [f"{letters[index]}) {option}" for index, option in enumerate(options[:4])]
    lines.append("ตอบแค่ตัวอักษร A B หรือ C ในคอมเมนต์ เฉลยอยู่ในคลิป")
    return "\n".join(lines)


def watch_next(published: list[dict], current_id: str, playlist_id: str | None, limit: int = 3) -> str:
    """Links to earlier uploaded videos and the playlist. Stands in for cards, which the API cannot add."""
    lines = []
    for item in reversed(published):
        if not isinstance(item, dict) or item.get("id") == current_id or not item.get("youtube_id"):
            continue
        lines.append(f"- {item.get('title', '')} https://youtu.be/{item['youtube_id']}")
        if len(lines) >= limit:
            break
    if playlist_id:
        lines.append(f"- ดูทุกตอนในเพลย์ลิสต์ https://www.youtube.com/playlist?list={playlist_id}")
    return ("ดูต่อ\n" + "\n".join(lines)) if lines else ""


def _copy(text: str) -> str:
    return f"```text\n{text.strip()}\n```"


def studio_steps(package: Path, script: dict, channel: dict, seconds: float, short_seconds: float) -> str:
    """One file per video, in the order YouTube Studio asks for each field."""

    def read(name: str) -> str:
        path = package / name
        return path.read_text(encoding="utf-8").strip() if path.exists() else ""

    tags = build_tags(script)
    alt_titles = "\n".join(f"- {title}" for title in title_options(script)[1:]) or "- (none)"
    short_tags = ", ".join(["shorts", *tags][:15])
    return f"""# YouTube Studio steps: {script['id']}

Do these in order. Each grey box is ready to copy and paste.
Data as of {script['as_of']}. Long video {seconds / 60:.1f} min, Short {short_seconds:.0f} s.

---

# PART A. THE LONG VIDEO

## Step 1. Upload the file
Studio > Create > Upload videos > choose `video.mp4` from this folder.

## Step 2. Title
{_copy(read("title.txt"))}

Backup titles, for "Test & compare" later (step 21):
{alt_titles}

## Step 3. Description
{_copy(read("description.txt"))}

## Step 4. Thumbnail
Click "Upload file" and choose `thumbnail.jpg`.
If the button is greyed out, verify the channel first at https://www.youtube.com/verify

## Step 5. Playlists
Automatic when GitHub uploads: added to "{playlist_title(script)}" (created the first time).
If you upload by hand, add it to that playlist yourself.

## Step 6. Audience
Choose: **No, it's not made for kids**.
Age restriction: No.

## Step 7. Click "Show more", then: Paid promotion
Leave unticked.

## Step 8. Altered content
Choose **Yes**. The narration is an AI voice.

## Step 9. Automatic chapters
Leave on. The chapters in the description are used.

## Step 10. Tags ({len(tags)} tags)
{_copy(", ".join(tags))}

## Step 11. Language and captions certification
Video language: **Thai**. Caption certification: none.

## Step 12. License and distribution
Standard YouTube License. Allow embedding: on. Publish to subscriptions feed: on.

## Step 13. Category
**Education**

## Step 14. Comments and ratings
Comments: On. Sort by: Top. Show like count: on.

## Step 15. Next > Video elements: subtitles
Add > Upload file > With timing > choose `captions.srt`. Language: Thai.

## Step 16. End screen (manual: YouTube's API cannot add end screens)
After the first video: Studio > the video > Editor > End screen > **Import from video**, pick the previous video, Save. About 20 seconds.
First time only: build one with **Subscribe** plus **Video: Best for viewer** over the last 20 seconds.

## Step 17. Cards (manual: YouTube's API cannot add cards)
The description and comment already link to earlier videos and the playlist ("ดูต่อ").
Optional: add one card about halfway through, pointing to the playlist.

## Step 18. Next > Checks
Wait for the copyright check to finish. It should say "No issues found".

## Step 19. Visibility
If GitHub uploaded with auto-publish, Studio already shows **Scheduled for 18:00 Thailand**. Do not change it unless you want a different time.
If you uploaded by hand, choose Schedule → 18:00 Thailand → Schedule.

## Step 20. Pin the comment (after the video is public)
GitHub posts this comment (summary + quiz) automatically within about 20 minutes of the video going public.
YouTube's API cannot pin, so: Studio > Comments > the comment > three dots > **Pin**.
If you uploaded by hand, post it yourself first:
{_copy(read("pinned-comment.txt"))}

## Step 21. Test & compare (optional, after 1 to 2 days)
Studio > the video > Details > "Test & compare" under the thumbnail. Add the backup titles from step 2. YouTube keeps whichever one people watch longest.

---

# PART B. THE SHORT (1 to 2 hours after the long video is public)

## Step 22. Upload the Short
Studio > Create > Upload videos > choose `short/video.mp4`.

## Step 23. Short title
{_copy(read("short/title.txt"))}

## Step 24. Short description
Replace the channel link under "ดูคลิปเต็ม" with the long video's link (Studio > the long video > copy link).
{_copy(read("short/description.txt"))}

## Step 25. Short audience and altered content
Not made for kids. Altered content: **Yes**.

## Step 26. Short tags
{_copy(short_tags)}

## Step 27. Related video
Under "Related video", choose the long video. A button to the full video appears on the Short.

## Step 28. Short visibility
Public, or schedule it 1 to 2 hours after the long video.

## Step 29. Short pinned comment
Posted automatically after the Short goes public (with the long video's link). Pin it in Studio.
If you uploaded by hand, replace the link with the long video's link, post it, then pin it:
{_copy(read("short/pinned-comment.txt"))}

---

# PART C. FIRST 48 HOURS

## Step 30. Reply to comments
Reply to every comment in the first one to two hours.

## Step 31. Share
Send the long video to family LINE groups and Facebook groups for older people, with one sentence about what it answers, not just the link.

## Step 32. Community post (quiz)
Community tab > Create post > **Quiz**, and use the quiz from the pinned comment, with the right answer marked.
Or post the thumbnail with the question from the pinned comment.

## Step 33. Check the numbers
After 48 hours: Studio > Analytics > the video. If impressions click-through rate is under about 3%, change the title to a backup title. If average view duration drops sharply in the first 30 seconds, note it for the next script.

## Step 34. Keep it accurate
If a government figure changes, edit the pinned comment the same day.

---

Channel: {channel['name']} {channel['channel_url']}
"""
