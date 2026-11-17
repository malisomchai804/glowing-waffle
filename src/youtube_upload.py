"""Upload finished videos to the channel, private or scheduled to go public."""

from __future__ import annotations

import os
from pathlib import Path


def _clean(text: str) -> str:
    """YouTube rejects titles, descriptions and tags that contain < or >."""
    return text.replace("<", "(").replace(">", ")")


def _fit_bytes(text: str, limit: int) -> str:
    """YouTube limits descriptions to 5000 bytes; Thai letters are 3 bytes each in UTF-8."""
    data = text.encode("utf-8")
    if len(data) <= limit:
        return text
    return data[:limit].decode("utf-8", errors="ignore").rstrip()


def secrets_ready() -> bool:
    return all(
        os.environ.get(name)
        for name in ("YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET", "YOUTUBE_REFRESH_TOKEN")
    )


def _client():
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    credentials = Credentials(
        token=None,
        refresh_token=os.environ["YOUTUBE_REFRESH_TOKEN"],
        client_id=os.environ["YOUTUBE_CLIENT_ID"],
        client_secret=os.environ["YOUTUBE_CLIENT_SECRET"],
        token_uri="https://oauth2.googleapis.com/token",
    )
    return build("youtube", "v3", credentials=credentials, cache_discovery=False)


def upload_video(
    video: Path,
    thumbnail: Path | None,
    title: str,
    description: str,
    tags: list[str],
    category_id: str,
    publish_at: str | None = None,
    captions: Path | None = None,
) -> str:
    """publish_at is an RFC 3339 time; YouTube flips the video from private to public then."""
    from googleapiclient.http import MediaFileUpload

    youtube = _client()
    status = {
        "privacyStatus": "private",
        "selfDeclaredMadeForKids": False,
        "containsSyntheticMedia": True,
        "embeddable": True,
    }
    if publish_at:
        status["publishAt"] = publish_at
    body = {
        "snippet": {
            "title": _clean(title)[:100],
            "description": _fit_bytes(_clean(description), 4900),
            "tags": [_clean(tag) for tag in tags[:30]],
            "categoryId": category_id,
            "defaultLanguage": "th",
            "defaultAudioLanguage": "th",
        },
        "status": status,
    }
    media = MediaFileUpload(str(video), mimetype="video/mp4", resumable=True, chunksize=8 * 1024 * 1024)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    response = None
    while response is None:
        progress, response = request.next_chunk()
        if progress:
            print(f"อัปโหลด {int(progress.progress() * 100)}%")
    video_id = response["id"]

    if thumbnail and thumbnail.exists():
        try:
            youtube.thumbnails().set(
                videoId=video_id,
                media_body=MediaFileUpload(str(thumbnail), mimetype="image/jpeg"),
            ).execute()
        except Exception as exc:  # noqa: BLE001 - needs a phone-verified channel
            print(f"ตั้งภาพปกไม่สำเร็จ (อัปโหลดเองใน Studio ได้): {exc}")

    if captions and captions.exists():
        try:
            youtube.captions().insert(
                part="snippet",
                body={"snippet": {"videoId": video_id, "language": "th", "name": "ไทย", "isDraft": False}},
                media_body=MediaFileUpload(str(captions), mimetype="application/octet-stream"),
            ).execute()
        except Exception as exc:  # noqa: BLE001 - needs the youtube.force-ssl scope
            print(f"อัปซับไตเติลไม่สำเร็จ (อัปเองใน Studio ได้): {exc}")
    return video_id


# --- After-upload helpers. Each one is best-effort: a failure prints a note and
# --- never stops the run, because the video itself is already safely uploaded.

_playlist_cache: dict[str, str] = {}


def ensure_playlist(title: str, description: str = "") -> str | None:
    """Return the id of the channel playlist with this title, creating it public if missing."""
    if not title:
        return None
    if title in _playlist_cache:
        return _playlist_cache[title]
    try:
        youtube = _client()
        token = None
        while True:
            page = youtube.playlists().list(
                part="snippet", mine=True, maxResults=50, pageToken=token
            ).execute()
            for item in page.get("items", []):
                if item["snippet"]["title"].strip() == title.strip():
                    _playlist_cache[title] = item["id"]
                    return item["id"]
            token = page.get("nextPageToken")
            if not token:
                break
        created = youtube.playlists().insert(
            part="snippet,status",
            body={
                "snippet": {
                    "title": title[:150],
                    "description": description[:4900],
                    "defaultLanguage": "th",
                },
                "status": {"privacyStatus": "public"},
            },
        ).execute()
        _playlist_cache[title] = created["id"]
        print(f"สร้างเพลย์ลิสต์ใหม่: {title}")
        return created["id"]
    except Exception as exc:  # noqa: BLE001 - needs the youtube.force-ssl scope
        print(f"หา/สร้างเพลย์ลิสต์ไม่สำเร็จ (เพิ่มเองใน Studio ได้): {exc}")
        return None


def add_to_playlist(playlist_id: str | None, video_id: str) -> bool:
    if not playlist_id or not video_id:
        return False
    try:
        _client().playlistItems().insert(
            part="snippet",
            body={
                "snippet": {
                    "playlistId": playlist_id,
                    "resourceId": {"kind": "youtube#video", "videoId": video_id},
                }
            },
        ).execute()
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"เพิ่มเข้าเพลย์ลิสต์ไม่สำเร็จ: {exc}")
        return False


def video_status(video_id: str) -> str | None:
    """'public', 'private', 'unlisted', or None when the video is gone or unreadable."""
    try:
        items = _client().videos().list(part="status", id=video_id).execute().get("items", [])
        return items[0]["status"]["privacyStatus"] if items else None
    except Exception as exc:  # noqa: BLE001
        print(f"อ่านสถานะคลิป {video_id} ไม่สำเร็จ: {exc}")
        return None


def post_comment(video_id: str, text: str) -> str | None:
    """Post a top-level comment as the channel. YouTube's API cannot pin it; pin in Studio."""
    try:
        response = _client().commentThreads().insert(
            part="snippet",
            body={
                "snippet": {
                    "videoId": video_id,
                    "topLevelComment": {"snippet": {"textOriginal": text[:9000]}},
                }
            },
        ).execute()
        return response["id"]
    except Exception as exc:  # noqa: BLE001 - needs the youtube.force-ssl scope
        print(f"โพสต์คอมเมนต์ไม่สำเร็จ: {exc}")
        return None
