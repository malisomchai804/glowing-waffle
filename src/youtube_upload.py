"""Upload finished videos to the channel, private or scheduled to go public."""

from __future__ import annotations

import os
from pathlib import Path


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
            "title": title[:100],
            "description": description[:4900],
            "tags": tags[:30],
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
