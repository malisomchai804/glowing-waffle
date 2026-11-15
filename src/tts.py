"""Thai narration via edge-tts, with a backup host and a gTTS reserve."""

from __future__ import annotations

import asyncio
import time
import wave
from pathlib import Path

import edge_tts

BACKUP_READY = False


def wav_seconds(path: Path) -> float:
    with wave.open(str(path), "rb") as handle:
        return handle.getnframes() / float(handle.getframerate())


def _enable_backup_host() -> None:
    global BACKUP_READY
    if BACKUP_READY:
        return
    import edge_tts.communicate as communicate
    from edge_tts.constants import TRUSTED_CLIENT_TOKEN

    communicate.WSS_URL = (
        "wss://api.msedgeservices.com/tts/cognitiveservices/websocket/v1"
        f"?Ocp-Apim-Subscription-Key={TRUSTED_CLIENT_TOKEN}"
    )
    BACKUP_READY = True
    print("สลับไปโฮสต์เสียงสำรองแล้ว")


async def _edge_once(text: str, dest: Path, voice: str, rate: str, pitch: str) -> list[dict]:
    comm = edge_tts.Communicate(
        text,
        voice,
        rate=rate,
        pitch=pitch,
        boundary="SentenceBoundary",
    )
    audio = bytearray()
    bounds: list[dict] = []
    async for chunk in comm.stream():
        if chunk["type"] == "audio":
            audio.extend(chunk["data"])
        elif chunk["type"] == "SentenceBoundary":
            bounds.append(
                {
                    "text": chunk.get("text") or "",
                    "offset": chunk.get("offset") or 0,
                    "duration": chunk.get("duration") or 0,
                }
            )
    if len(audio) < 800:
        raise RuntimeError("ไฟล์เสียงสั้นผิดปกติ")
    dest.write_bytes(audio)
    return bounds


async def _synth_edge(text: str, dest: Path, voice: str, rate: str, pitch: str) -> list[dict]:
    last_error: Exception | None = None
    for attempt in range(5):
        try:
            return await _edge_once(text, dest, voice, rate, pitch)
        except Exception as exc:  # noqa: BLE001 - network voice service is unstable
            last_error = exc
            message = str(exc)
            print(f"เสียงพยายามครั้งที่ {attempt + 1} ไม่ผ่าน: {message[:180]}")
            if "403" in message or attempt == 2:
                _enable_backup_host()
            await asyncio.sleep(2 * (attempt + 1))
    raise RuntimeError(f"สร้างเสียงไม่สำเร็จ: {last_error}")


def _synth_gtts(text: str, dest: Path) -> list[dict]:
    from gtts import gTTS

    gTTS(text, lang="th").save(str(dest))
    return []


def synthesize_section(
    text: str,
    dest_mp3: Path,
    voice: str,
    rate: str,
    pitch: str,
) -> tuple[list[dict], str]:
    try:
        bounds = asyncio.run(_synth_edge(text, dest_mp3, voice, rate, pitch))
        time.sleep(0.4)
        return bounds, "edge"
    except Exception as exc:  # noqa: BLE001
        print(f"ใช้เสียงสำรอง gTTS เพราะเสียงหลักใช้ไม่ได้: {exc}")
        _synth_gtts(text, dest_mp3)
        return [], "gtts"
