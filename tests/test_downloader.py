import json
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest

sys.modules.setdefault("yt_dlp", types.SimpleNamespace(YoutubeDL=object))

from app.downloader import MediaDownloader


class DownloaderMediaTests(unittest.TestCase):
    def test_prepares_telegram_video_and_thumbnail(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            temp_dir = Path(directory)
            source = temp_dir / "source.mp4"
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-f",
                    "lavfi",
                    "-i",
                    "testsrc=size=160x90:rate=15",
                    "-t",
                    "1",
                    "-c:v",
                    "mpeg4",
                    str(source),
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )

            prepared = MediaDownloader._prepare_for_telegram(source, temp_dir)
            thumbnail = MediaDownloader._create_thumbnail(prepared, temp_dir, 1)

            probe = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    "stream=codec_type,codec_name,pix_fmt",
                    "-of",
                    "json",
                    str(prepared),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            video = next(
                stream
                for stream in json.loads(probe.stdout)["streams"]
                if stream["codec_type"] == "video"
            )
            self.assertEqual(video["codec_name"], "h264")
            self.assertEqual(video["pix_fmt"], "yuv420p")
            self.assertIsNotNone(thumbnail)
            self.assertGreater(thumbnail.stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()
