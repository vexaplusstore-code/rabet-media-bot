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
    def setUp(self) -> None:
        self.downloader = MediaDownloader(48, 3600)

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

    def test_youtube_uses_pot_profiles_but_other_sites_do_not(self) -> None:
        youtube_profiles = self.downloader._extractor_profiles(
            "https://www.youtube.com/watch?v=abc"
        )
        other_profiles = self.downloader._extractor_profiles(
            "https://www.instagram.com/reel/abc/"
        )

        self.assertEqual(youtube_profiles[0][0], "youtube-mweb-pot")
        self.assertEqual(
            youtube_profiles[0][1]["extractor_args"]["youtube"]["player_client"],
            ["mweb"],
        )
        self.assertIn(
            "youtubepot-bgutilscript",
            youtube_profiles[0][1]["extractor_args"],
        )
        self.assertEqual(other_profiles, [("default", {})])

    def test_bot_challenge_is_not_reported_as_private(self) -> None:
        result = self.downloader._friendly_error(
            RuntimeError("Sign in to confirm you’re not a bot")
        )

        self.assertIn("ليس خاصًا بالضرورة", result)
        self.assertNotIn("خاص فعلًا", result)

    def test_private_video_is_reported_as_private(self) -> None:
        result = self.downloader._friendly_error(RuntimeError("Private video"))

        self.assertIn("خاص فعلًا", result)

    def test_unlisted_video_is_allowed(self) -> None:
        self.downloader._validate_availability({"availability": "unlisted"})

    def test_members_only_video_is_rejected_separately(self) -> None:
        with self.assertRaisesRegex(Exception, "members-only"):
            self.downloader._validate_availability(
                {"availability": "subscriber_only"}
            )


if __name__ == "__main__":
    unittest.main()
