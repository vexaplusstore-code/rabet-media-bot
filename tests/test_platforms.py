import unittest

from app.platforms import UnsupportedUrl, extract_first_url, identify_platform


class PlatformTests(unittest.TestCase):
    def test_extract_url_from_arabic_message(self) -> None:
        self.assertEqual(
            extract_first_url("حمّل هذا https://youtu.be/abc123 من فضلك"),
            "https://youtu.be/abc123",
        )

    def test_all_supported_platforms(self) -> None:
        samples = {
            "https://x.com/user/status/1": "x",
            "https://mobile.twitter.com/user/status/1": "x",
            "https://vm.tiktok.com/abc/": "tiktok",
            "https://www.instagram.com/reel/abc/": "instagram",
            "https://youtube.com/watch?v=abc": "youtube",
        }
        for url, expected in samples.items():
            with self.subTest(url=url):
                self.assertEqual(identify_platform(url).key, expected)

    def test_rejects_domain_confusion(self) -> None:
        with self.assertRaises(UnsupportedUrl):
            identify_platform("https://youtube.com.example.org/watch?v=abc")

    def test_rejects_credentials_in_url(self) -> None:
        with self.assertRaises(UnsupportedUrl):
            identify_platform("https://user:pass@youtube.com/watch?v=abc")


if __name__ == "__main__":
    unittest.main()

