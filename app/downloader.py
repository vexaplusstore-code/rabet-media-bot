from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
import shutil
import tempfile
from typing import Any

import yt_dlp


class DownloadError(RuntimeError):
    pass


class FileTooLarge(DownloadError):
    pass


@dataclass(slots=True)
class DownloadedMedia:
    path: Path
    title: str
    platform: str
    duration: int | None
    temporary_directory: Path

    def cleanup(self) -> None:
        shutil.rmtree(self.temporary_directory, ignore_errors=True)


class MediaDownloader:
    def __init__(self, max_file_mb: int, max_duration_seconds: int) -> None:
        self.max_bytes = max_file_mb * 1024 * 1024
        self.max_duration_seconds = max_duration_seconds

    async def download(self, url: str) -> DownloadedMedia:
        return await asyncio.to_thread(self._download_sync, url)

    def _download_sync(self, url: str) -> DownloadedMedia:
        temp_dir = Path(tempfile.mkdtemp(prefix="media-job-"))
        try:
            metadata = self._extract_metadata(url)
            duration = metadata.get("duration")
            if metadata.get("is_live"):
                raise DownloadError("البث المباشر غير مدعوم.")
            if duration and int(duration) > self.max_duration_seconds:
                raise DownloadError("مدة المقطع تتجاوز الحد المسموح.")

            last_error: Exception | None = None
            for height in (1080, 720, 480, 360):
                self._clear_media_files(temp_dir)
                try:
                    media_path = self._download_quality(url, temp_dir, height)
                except Exception as exc:  # yt-dlp uses multiple exception types
                    last_error = exc
                    continue
                if media_path.stat().st_size <= self.max_bytes:
                    return DownloadedMedia(
                        path=media_path,
                        title=str(metadata.get("title") or "مقطع فيديو")[:200],
                        platform=str(metadata.get("extractor_key") or ""),
                        duration=int(duration) if duration else None,
                        temporary_directory=temp_dir,
                    )
            if last_error and not any(temp_dir.iterdir()):
                raise DownloadError(self._friendly_error(last_error)) from last_error
            raise FileTooLarge("حجم المقطع أكبر من حد الإرسال حتى بعد خفض الجودة.")
        except Exception:
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise

    def _extract_metadata(self, url: str) -> dict[str, Any]:
        options: dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "skip_download": True,
            "socket_timeout": 20,
            "retries": 2,
            "extractor_retries": 2,
        }
        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                info = ydl.extract_info(url, download=False)
        except Exception as exc:
            raise DownloadError(self._friendly_error(exc)) from exc
        if not isinstance(info, dict):
            raise DownloadError("تعذر قراءة معلومات المقطع.")
        return info

    def _download_quality(self, url: str, temp_dir: Path, height: int) -> Path:
        output = str(temp_dir / "%(id)s.%(ext)s")
        format_selector = (
            f"bv*[height<={height}][ext=mp4]+ba[ext=m4a]/"
            f"b[height<={height}][ext=mp4]/b[height<={height}]"
        )
        options: dict[str, Any] = {
            "format": format_selector,
            "outtmpl": output,
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "merge_output_format": "mp4",
            "remuxvideo": "mp4",
            "overwrites": True,
            "continuedl": False,
            "socket_timeout": 30,
            "retries": 3,
            "fragment_retries": 3,
        }
        with yt_dlp.YoutubeDL(options) as ydl:
            ydl.extract_info(url, download=True)
        candidates = [
            path
            for path in temp_dir.iterdir()
            if path.is_file() and path.suffix not in {".part", ".ytdl", ".json"}
        ]
        if not candidates:
            raise DownloadError("لم ينتج عن الرابط ملف قابل للإرسال.")
        return max(candidates, key=lambda path: path.stat().st_size)

    @staticmethod
    def _clear_media_files(temp_dir: Path) -> None:
        for path in temp_dir.iterdir():
            if path.is_file():
                path.unlink(missing_ok=True)

    @staticmethod
    def _friendly_error(exc: Exception) -> str:
        message = str(exc).lower()
        if "private" in message or "login" in message or "sign in" in message:
            return "المقطع خاص أو يتطلب تسجيل الدخول، لذلك لا يمكن تنزيله."
        if "copyright" in message or "unavailable" in message:
            return "المقطع غير متاح أو مقيّد من المنصة."
        if "unsupported url" in message:
            return "صيغة الرابط غير مدعومة حاليًا."
        return "تعذر تنزيل المقطع الآن. قد تكون المنصة غيّرت طريقة عرض المحتوى."

