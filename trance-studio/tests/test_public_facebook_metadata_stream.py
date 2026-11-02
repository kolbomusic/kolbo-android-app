"""Test privacy-bounded public OG video CDN fallback; no cookies or auth."""
import io
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
import link_import as li


class FacebookPublicMediaStreamTests(unittest.TestCase):
    def test_metadata_has_public_cdn_candidate_but_not_untrusted_host(self):
        page = b"""<html><head>
        <meta property="og:url" content="https://www.facebook.com/reel/4301066573492911">
        <meta property="og:video:secure_url" content="https://video.xx.fbcdn.net/v/t42.1790-2/sample.mp4?tok=abc&amp;x=1">
        <meta property="og:video" content="https://127.0.0.1/private.mp4">
        </head></html>"""
        self.assertEqual(li._facebook_html_media_urls(page),
            ["https://video.xx.fbcdn.net/v/t42.1790-2/sample.mp4?tok=abc&x=1"])
        self.assertEqual(li._facebook_html_video_urls(
            page,"https://www.facebook.com/share/v/1Demo/"),
            ["https://www.facebook.com/reel/4301066573492911"])

    def test_do_not_download_arbitrary_metadata_url(self):
        for url in ("https://127.0.0.1/a.mp4", "http://video.xx.fbcdn.net/v/a",
                    "https://video.xx.fbcdn.net.evil.example/a",
                    "https://video.xx.fbcdn.net:5443/a",
                    "https://evil.test/video.mp4",
                    "https://localhost/video.mp4"):
            with self.subTest(url=url):
                self.assertIsNone(li._trusted_facebook_media_url(url))

    def test_public_stream_succeeds_only_media_without_cookies(self):
        payload=b"0"*8192
        class Resp:
            headers={"Content-Type":"video/mp4","Content-Length":str(len(payload))}
            def __enter__(self):return self
            def __exit__(self,*args):return False
            def __init__(self):self.inner=io.BytesIO(payload)
            def read(self,n):return self.inner.read(n)
        class Opener:
            def open(self,req,timeout):
                assert req.get_header("Cookie") is None
                assert req.get_header("Authorization") is None
                return Resp()
        with tempfile.TemporaryDirectory() as root:
            code=li._try_public_facebook_cdn(
                "https://video.xx.fbcdn.net/v/small.mp4",Path(root),
                deadline=time.monotonic()+10,opener=Opener())
            self.assertEqual(code,"ok")
            self.assertEqual((Path(root)/"shared.mp4").stat().st_size,len(payload))

    def test_html_or_oversized_payload_is_rejected(self):
        class Resp:
            def __init__(self,headers):self.headers=headers
            def __enter__(self):return self
            def __exit__(self,*args):return False
            def read(self,n):return b"<html>Access denied</html>"
        class Opener:
            def __init__(self,headers):self.headers=headers
            def open(self,*args,**kwargs):return Resp(self.headers)
        with tempfile.TemporaryDirectory() as root:
            folder=Path(root)
            self.assertEqual(li._try_public_facebook_cdn(
                "https://video.xx.fbcdn.net/v/a.mp4",folder,
                deadline=time.monotonic()+10,
                opener=Opener({"Content-Type":"text/html"})),"invalid_mime")
            self.assertEqual(li._try_public_facebook_cdn(
                "https://video.xx.fbcdn.net/v/a.mp4",folder,
                deadline=time.monotonic()+10,
                opener=Opener({"Content-Type":"video/mp4",
                               "Content-Length":str(li.MAX_VIDEO+1)})),"size")

    def test_cdn_redirect_restricted(self):
        from urllib.request import Request
        redirects=li._FacebookCdnOnlyRedirects()
        for destination in ("https://127.0.0.1/private",
                            "http://video.xx.fbcdn.net/a.mp4",
                            "https://facebook.com/a.mp4",
                            "https://video.xx.fbcdn.net.evil.test/a"):
            with self.subTest(dest=destination),self.assertRaises(li.LinkImportError):
                redirects.redirect_request(
                    Request("https://video.xx.fbcdn.net/v/a.mp4"),None,
                    302,"Moved",{},destination)

    def test_end_to_end_public_metadata_cdn_candidate_accepted(self):
        user="https://www.facebook.com/share/v/1Demo/"
        cdn="https://video.xx.fbcdn.net/v/test.mp4"
        attempted=[]
        def fake_download(url,folder,*,deadline,format_spec,impersonate=False):
            attempted.append(("yt-dlp",url))
            return "extractor"
        def fake_cdn(url,folder,*,deadline):
            attempted.append(("cdn",url))
            (folder/"shared.mp4").write_bytes(b"\x00"*4096)
            return "ok"
        with tempfile.TemporaryDirectory() as root:
            with patch.object(li,"_facebook_public_candidates",return_value=[user,cdn]),\
                 patch.object(li,"_try_public_download",side_effect=fake_download),\
                 patch.object(li,"_try_public_facebook_cdn",side_effect=fake_cdn),\
                 patch.object(li,"_media_probe",return_value=12):
                output,mime=li.fetch_public_social_media(user,root,timeout=30)
                self.assertEqual(output.name,"shared.mp4")
                self.assertEqual(mime,"video/mp4")
        self.assertEqual(attempted,[("yt-dlp",user),("cdn",cdn)])

    def test_extractor_code_does_not_assert_private(self):
        with tempfile.TemporaryDirectory() as root:
            with patch.object(li,"_facebook_public_candidates",
                              return_value=["https://www.facebook.com/reel/4301066573492911"]),\
                 patch.object(li,"_try_public_download",return_value="extractor"):
                with self.assertRaises(li.LinkImportError) as issue:
                    li.fetch_public_social_media(
                        "https://www.facebook.com/reel/4301066573492911",root,timeout=8)
        self.assertEqual(issue.exception.code,"extractor_parse")
        self.assertIn("לא בהכרח",str(issue.exception))


if __name__ == "__main__":
    unittest.main()
