"""Confirm official pages still show the figures baked into a script."""

from __future__ import annotations

import urllib.error
import urllib.request

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


def check_sources(script: dict) -> list[str]:
    """Return warnings. Raise if a live page no longer contains a required figure."""
    warnings: list[str] = []
    for source in script.get("sources") or []:
        url = source.get("url")
        needed = source.get("must_contain") or []
        if not url or not needed:
            continue
        request = urllib.request.Request(url, headers={"User-Agent": UA})
        try:
            with urllib.request.urlopen(request, timeout=40) as response:
                body = response.read().decode("utf-8", "replace")
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            warnings.append(f"เปิดแหล่งไม่สำเร็จ จึงยังใช้บทที่ตรวจไว้แล้ว: {url} ({exc})")
            continue
        missing = [item for item in needed if item not in body]
        if missing:
            raise RuntimeError(
                "หยุดเรนเดอร์ เพราะหน้าแหล่งข้อมูลไม่พบตัวเลข "
                + ", ".join(missing)
                + f" ที่ {url} ให้อัปเดตบทก่อนทำคลิป"
            )
        print(f"แหล่งยังมีตัวเลขที่ใช้อยู่: {source.get('name')}")
    return warnings
