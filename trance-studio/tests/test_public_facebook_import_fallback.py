"""Public Facebook URL retries: independent candidates with no auth or login bypass."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"backend"))
import link_import


class PublicFacebookLinkImportTest(unittest.TestCase):
    def test_public_redirect_canonical_id(self):
        class FakeResponse:
            def __enter__(self):return self
            def __exit__(self,*a):return False
            def geturl(self):
                return "https://www.facebook.com/reel/1800066080991078/?rdid=a"
        class FakeOpener:
            def open(self,*args,**kwargs):return FakeResponse()
        raw="https://www.facebook.com/share/v/1J79vLp2uu/"
        urls=link_import._facebook_public_candidates(raw,opener=FakeOpener())
        self.assertEqual(urls[0],raw)
        self.assertTrue(urls[1].startswith("https://www.facebook.com/reel/1800066080991078/"))
        self.assertIn("https://www.facebook.com/watch/?v=1800066080991078",urls)
        self.assertTrue(any("/plugins/video.php?href=" in item for item in urls))
        self.assertEqual(len(set(urls)),len(urls))

    def test_no_untrusted_redirects(self):
        from urllib.request import Request
        redirects=link_import._FacebookOnlyRedirects()
        for unsafe in ("http://www.facebook.com/reel/1234",
                       "https://127.0.0.1/reel/1234",
                       "https://facebook.com.evil.example/reel/1234",
                       "https://evil.com:443/video",
                       "https://www.facebook.com:444/watch/"):
            with self.subTest(url=unsafe),self.assertRaises(link_import.LinkImportError):
                redirects.redirect_request(Request("https://www.facebook.com/share/v/a"),
                                           None,302,"Moved",{},unsafe)

    def test_opaque_share_token_cannot_be_misread_as_id(self):
        self.assertIsNone(link_import._facebook_video_id(
            "https://www.facebook.com/share/v/1J79vLp2uu/"))
        self.assertIsNone(link_import._facebook_video_id(
            "https://evil.test/reel/1800066080991078"))

    def test_second_public_candidate_can_succeed(self):
        candidates=[
            "https://www.facebook.com/share/v/1J79vLp2uu/",
            "https://www.facebook.com/watch/?v=1800066080991078",
        ]
        seen=[]
        def fake_download(url,folder,*,deadline,format_spec):
            seen.append(url)
            if len(seen)==1:return "extractor"
            (folder/"shared.mp4").write_bytes(b"a"*4096)
            return "ok"
        with tempfile.TemporaryDirectory() as root:
            with patch.object(link_import,"_facebook_public_candidates",return_value=candidates), \
                 patch.object(link_import,"_try_public_download",side_effect=fake_download), \
                 patch.object(link_import,"_media_probe",return_value=12):
                result,mime=link_import.fetch_public_social_media(candidates[0],root,timeout=30)
                self.assertEqual(result.name,"shared.mp4")
                self.assertEqual(mime,"video/mp4")
        self.assertEqual(seen,candidates)

    def test_reject_private_without_attempting_to_bypass(self):
        with tempfile.TemporaryDirectory() as root:
            with patch.object(link_import,"_facebook_public_candidates",
                              return_value=["https://www.facebook.com/watch/?v=1800066080991078"]), \
                 patch.object(link_import,"_try_public_download",return_value="private"):
                with self.assertRaisesRegex(link_import.LinkImportError,"Facebook"):
                    link_import.fetch_public_social_media(
                        "https://www.facebook.com/watch/?v=1800066080991078",root)
        self.assertEqual(link_import._readable_failure("Login required"),"private")
        self.assertEqual(link_import._readable_failure("Cannot parse data"),"extractor")

    def test_reject_unapproved_domains(self):
        for url in ("https://localhost/public", "http://facebook.com/video",
                    "https://fakefacebook.com/watch/123",
                    "https://facebook.com:90/watch/123"):
            with self.subTest(url=url),self.assertRaises(link_import.LinkImportError):
                link_import.validate_public_link(url)


if __name__=="__main__":
    unittest.main()
