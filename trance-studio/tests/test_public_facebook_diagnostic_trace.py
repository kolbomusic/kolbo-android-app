"""Fix Facebook share/v diagnosis 7ecfd487 without exposing user URLs."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"backend"))
import link_import as li


class PublicFacebookDiagnoseRegression(unittest.TestCase):
    def test_slugged_facebook_public_permalink_video_id(self):
        self.assertEqual(
            li._facebook_video_id(
                "https://www.facebook.com/natgeo/videos/english-caption/1016464114801712/"),
            "1016464114801712")
        self.assertEqual(
            li._facebook_video_id("https://www.facebook.com/videos/1016464114801712/"),
            "1016464114801712")

    def test_chrome_public_media_metadata_not_skipped_when_id_already_found(self):
        short="https://www.facebook.com/share/v/1test/"
        canon="https://www.facebook.com/reel/1016464114801712"
        cdn="https://video.xx.fbcdn.net/v/demo.mp4"
        class Response:
            headers={"Content-Type":"text/html"}
            def geturl(self):return canon
            def read(self,n):return b""
            def __enter__(self):return self
            def __exit__(self,*args):return False
        class Opener:
            def open(self,*args,**kwargs):return Response()
        with patch.object(li,"build_opener",return_value=Opener()),\
             patch.object(li,"_facebook_public_browser_candidates",return_value=[cdn]) as browser:
            found=li._facebook_public_candidates(short)
            self.assertIn(canon,found)
            self.assertIn(cdn,found)
            browser.assert_called_once()

    def test_conflicting_public_id_is_rejected_for_correct_video_safety(self):
        link="https://www.facebook.com/share/v/1test/"
        class Response:
            headers={"Content-Type":"text/html"}
            def geturl(self):return "https://www.facebook.com/reel/1016464114801712"
            def read(self,n):return b""
            def __enter__(self):return self
            def __exit__(self,*args):return False
        class Opener:
            def open(self,*args,**kwargs):return Response()
        with patch.object(li,"build_opener",return_value=Opener()), \
             patch.object(li,"_facebook_public_browser_candidates",
                          return_value=["https://www.facebook.com/reel/1480256363681360"]):
            with self.assertRaises(li.LinkImportError) as ctx:
                li._facebook_public_candidates(link)
        self.assertEqual(ctx.exception.code,"ambiguous_share")

    def test_browser_probes_public_mobile_page_for_exact_video_cdn(self):
        short="https://www.facebook.com/share/v/1opaque/"
        video_id="1480256363681360"
        canon=f"https://www.facebook.com/reel/{video_id}/"
        cdn="https://video.xx.fbcdn.net/v/public.mp4"
        class Response:
            headers={"Content-Type":"text/html"}
            def geturl(self):return canon
            def read(self,limit):return b""
            def __enter__(self):return self
            def __exit__(self,*args):return False
        class Opener:
            def open(self,*args,**kwargs):return Response()
        examined=[]
        def browser(url,*,timeout):
            examined.append(url)
            if "/share/" in url:return [canon]
            if url=="https://m.facebook.com/watch/?v="+video_id:
                return [cdn]
            return []
        with patch.object(li,"build_opener",return_value=Opener()), \
             patch.object(li,"_facebook_public_browser_candidates",side_effect=browser):
            found=li._facebook_public_candidates(short)
        self.assertIn(cdn,found)
        self.assertEqual(examined,[short,"https://m.facebook.com/watch/?v="+video_id])
        self.assertIn(f"https://www.facebook.com/watch/?v={video_id}",found)

    def test_different_video_in_mobile_metadata_is_rejected(self):
        short="https://www.facebook.com/share/v/1opaque/"
        canon="https://www.facebook.com/reel/1480256363681360/"
        class Response:
            headers={"Content-Type":"text/html"}
            def geturl(self):return canon
            def read(self,limit):return b""
            def __enter__(self):return self
            def __exit__(self,*args):return False
        class Opener:
            def open(self,*args,**kwargs):return Response()
        with patch.object(li,"build_opener",return_value=Opener()), \
             patch.object(li,"_facebook_public_browser_candidates",
                          side_effect=[[canon],[
                           "https://www.facebook.com/reel/9988776655443322",
                           "https://video.xx.fbcdn.net/v/unrelated.mp4"],[]]):
            found=li._facebook_public_candidates(short)
        self.assertNotIn("https://video.xx.fbcdn.net/v/unrelated.mp4",found)

    def test_trace_steps_codes_never_include_urls(self):
        link="https://www.facebook.com/share/v/1token/"
        links=[
            "https://www.facebook.com/reel/1016464114801712",
            "https://www.facebook.com/watch/?v=1016464114801712"]
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(li,"_facebook_public_candidates",return_value=links),\
                 patch.object(li,"_try_public_download",return_value="extractor"):
                with self.assertRaises(li.LinkImportError) as ctx:
                    li.fetch_public_social_media(link,folder,timeout=30)
        self.assertEqual(ctx.exception.code,"extractor_parse")
        self.assertEqual(ctx.exception.steps,"reel:extractor,watch:extractor")
        self.assertNotIn("1016464114801712",ctx.exception.steps)

if __name__=="__main__":
    unittest.main()
