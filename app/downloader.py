from __future__ import annotations

import asyncio
from dataclasses import dataclass
import json
from pathlib import Path
import shutil
import subprocess
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
    thumbnail_path: Path | None
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
                    media_path = self._prepare_for_telegram(media_path, temp_dir)
                except Exception as exc:  # yt-dlp uses multiple exception types
                    last_error = exc
                    continue
                if media_path.stat().st_size <= self.max_bytes:
                    thumbnail_path = self._create_thumbnail(
                        media_path,
                        temp_dir,
                        int(duration) if duration else None,
                    )
                    return DownloadedMedia(
                        path=media_path,
                        thumbnail_path=thumbnail_path,
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
            f"bv*[height<={height}][vcodec^=avc1][ext=mp4]+"
            f"ba[acodec^=mp4a][ext=m4a]/"
            f"b[height<={height}][vcodec^=avc1][ext=mp4]/"
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
    def _prepare_for_telegram(media_path: Path, temp_dir: Path) -> Path:
        """Return an H.264/AAC MP4 with fast-start metadata for Telegram clients."""
        probe_command = [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "stream=codec_type,codec_name,pix_fmt",
            "-of",
            "json",
            str(media_path),
        ]
        try:
            probe = subprocess.run(
                probe_command,
                check=True,
                capture_output=True,
                text=True,
                timeout=30,
            )
            streams = json.loads(probe.stdout).get("streams", [])
        except (subprocess.SubprocessError, json.JSONDecodeError, OSError) as exc:
            raise DownloadError("تعذر فحص ترميز المقطع.") from exc

        video_stream = next(
            (stream for stream in streams if stream.get("codec_type") == "video"),
            None,
        )
        if not video_stream:
            raise DownloadError("الملف الناتج لا يحتوي على صورة فيديو قابلة للعرض.")
        audio_stream = next(
            (stream for stream in streams if stream.get("codec_type") == "audio"),
            None,
        )
        compatible = (
            video_stream.get("codec_name") == "h264"
            and video_stream.get("pix_fmt") in {"yuv420p", "yuvj420p"}
            and (not audio_stream or audio_stream.get("codec_name") == "aac")
        )

        output_path = temp_dir / f"{media_path.stem}-telegram.mp4"
        command = ["ffmpeg", "-y", "-i", str(media_path), "-map", "0:v:0", "-map", "0:a:0?"]
        if compatible:
            command.extend(["-c", "copy"])
        else:
            command.extend(
                [
                    "-c:v",
                    "libx264",
                    "-preset",
                    "veryfast",
                    "-crf",
                    "24",
                    "-pix_fmt",
                    "yuv420p",
                    "-c:a",
                    "aac",
                    "-b:a",
                    "128k",
                ]
            )
        command.extend(["-movflags", "+faststart", str(output_path)])
        try:
            subprocess.run(
                command,
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                timeout=900,
            )
        except (subprocess.SubprocessError, OSError) as exc:
            raise DownloadError("تعذر تجهيز الفيديو بصيغة متوافقة مع Telegram.") from exc

        if media_path != output_path:
            media_path.unlink(missing_ok=True)
        return output_path

    @staticmethod
    def _create_thumbnail(
        media_path: Path,
        temp_dir: Path,
        duration: int | None,
    ) -> Path | None:
        thumbnail_path = temp_dir / f"{media_path.stem}-thumbnail.jpg"
        if duration:
            seek_seconds = min(
                max(duration * 0.15, 0.1),
                max(duration - 0.5, 0),
                30,
            )
        else:
            seek_seconds = 1
        command = [
            "ffmpeg",
            "-y",
            "-ss",
            f"{seek_seconds:.2f}",
            "-i",
            str(media_path),
            "-frames:v",
            "1",
            "-vf",
            "scale=320:-2:force_original_aspect_ratio=decrease",
            "-q:v",
            "5",
            str(thumbnail_path),
        ]
        try:
            subprocess.run(
                command,
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                timeout=60,
            )
        except (subprocess.SubprocessError, OSError):
            return None
        return thumbnail_path if thumbnail_path.exists() else None

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
