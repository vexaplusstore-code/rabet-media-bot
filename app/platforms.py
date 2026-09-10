from __future__ import annotations

from dataclasses import dataclass
import re
from urllib.parse import urlparse


URL_RE = re.compile(r"https?://[^\s<>]+", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class Platform:
    key: str
    label: str


PLATFORMS: dict[str, Platform] = {
    "x.com": Platform("x", "X / تويتر"),
    "twitter.com": Platform("x", "X / تويتر"),
    "tiktok.com": Platform("tiktok", "TikTok"),
    "instagram.com": Platform("instagram", "Instagram"),
    "youtube.com": Platform("youtube", "YouTube"),
    "youtu.be": Platform("youtube", "YouTube"),
}


class UnsupportedUrl(ValueError):
    pass


def extract_first_url(text: str) -> str:
    match = URL_RE.search(text or "")
    if not match:
        raise UnsupportedUrl("لم أعثر على رابط صالح في الرسالة.")
    return match.group(0).rstrip(".,،؛!?)]}")


def identify_platform(url: str) -> Platform:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise UnsupportedUrl("الرابط غير صالح.")
    if parsed.username or parsed.password:
        raise UnsupportedUrl("هذا النوع من الروابط غير مسموح.")

    host = parsed.hostname.lower().rstrip(".")
    if host.startswith("www."):
        host = host[4:]

    for domain, platform in PLATFORMS.items():
        if host == domain or host.endswith(f".{domain}"):
            return platform
    raise UnsupportedUrl(
        "المنصة غير مدعومة حاليًا. أرسل رابطًا عامًا من X أو TikTok أو Instagram أو YouTube."
    )

