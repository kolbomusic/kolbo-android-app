"""Ensure short Facebook public HTML share pages are recognized without unsafe URLs."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"backend"))
import link_import


class PublicFacebookHtmlTest(unittest.TestCase):
    def test_og_and_canonical_video_tags(self):
        page=b"""<html><head>
        <meta property="og:url" content="https://www.facebook.com/reel/1800066080991078/">
        <link rel="canonical" href="https://www.facebook.com/watch/?v=1800066080991078&amp;ref=public">
        </head></html>"""
        urls=link_import._facebook_html_video_urls(
            page,"https://www.facebook.com/share/v/AaB0012/")
        self.assertEqual(len(urls),2)
        self.assertEqual(urls[0],"https://www.facebook.com/reel/1800066080991078/")
        self.assertIn("v=1800066080991078&ref=public",urls[1])

    def test_html_meta_refresh(self):
        page=b"""<meta http-equiv="refresh"
        content="0;URL=https://www.facebook.com/reel/1800066080991078/">"""
        self.assertEqual(
            link_import._facebook_html_video_urls(page,
                "https://www.facebook.com/share/v/AaB0012/"),
            ["https://www.facebook.com/reel/1800066080991078/"])

    def test_unsafe_or_unrelated_metadata_ignored(self):
        page=b"""<html><head>
        <meta property="og:url" content="https://facebook.com.evil.test/reel/1800066080991078">
        <link rel="canonical" href="javascript:alert(1)">
        <meta property="twitter:url" content="https://www.facebook.com/login">
        <meta http-equiv="refresh" content="0; URL=http://www.facebook.com/reel/1800066080991078">
        <meta property="al:web:url" content="https://www.facebook.com:8443/reel/1800066080991078">
        </head></html>"""
        self.assertEqual(link_import._facebook_html_video_urls(
            page,"https://www.facebook.com/share/v/AaB0012/"),[])

    def test_html_page_with_no_redirect_resolves_and_retries(self):
        page=b'<meta property="og:url" content="https://www.facebook.com/videos/1800066080991078/">'
        class Resp:
            headers={"Content-Type":"text/html; charset=utf-8"}
            def __enter__(self):return self
            def __exit__(self,*args):return False
            def geturl(self):return "https://www.facebook.com/share/v/AaB0012/"
            def read(self,limit):return page[:limit]
        class Client:
            def open(self,*args,**kwargs):return Resp()
        candidate="https://www.facebook.com/share/v/AaB0012/"
        found=link_import._facebook_public_candidates(candidate,opener=Client())
        self.assertEqual(found[0],candidate)
        self.assertIn("https://www.facebook.com/videos/1800066080991078/",found)
        self.assertIn("https://www.facebook.com/watch/?v=1800066080991078",found)
        self.assertTrue(any("/plugins/video.php?href=" in c for c in found))

    def test_no_follow_up_on_login_page(self):
        class Resp:
            headers={"Content-Type":"text/html"}
            def __enter__(self):return self
            def __exit__(self,*args):return False
            def geturl(self):return "https://www.facebook.com/login"
            def read(self,limit):return b'<meta property="og:url" content="https://www.facebook.com/login">'
        class Client:
            def open(self,*args,**kwargs):return Resp()
        candidate="https://www.facebook.com/share/v/AaB0012/"
        self.assertEqual(link_import._facebook_public_candidates(candidate,opener=Client()),[candidate])


if __name__=="__main__":unittest.main()
