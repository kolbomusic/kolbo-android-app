"""Public Facebook fallback with Chrome HTTP transport, without cookies or login."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"backend"))
import link_import


class FacebookBrowserRetryTest(unittest.TestCase):
    def test_short_link_retries_with_chrome_without_login(self):
        link="https://www.facebook.com/share/v/1DemoXYZ/"
        attempts=[]
        def attempt(url,folder,*,deadline,format_spec,impersonate=False):
            attempts.append((url,impersonate))
            if not impersonate:return "extractor"
            (folder/"shared.mp4").write_bytes(b"x"*4096)
            return "ok"
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(link_import,"_facebook_public_candidates",return_value=[link]), \
                 patch.object(link_import,"_try_public_download",side_effect=attempt), \
                 patch.object(link_import,"_media_probe",return_value=12):
                path,mime=link_import.fetch_public_social_media(link,temp,timeout=20)
        self.assertEqual(path.name,"shared.mp4")
        self.assertEqual(mime,"video/mp4")
        self.assertEqual(attempts,[(link,False),(link,True)])

    def test_private_video_not_browser_retried(self):
        link="https://www.facebook.com/share/v/1DemoXYZ/"
        attempts=[]
        def attempt(url,folder,*,deadline,format_spec,impersonate=False):
            attempts.append(impersonate)
            return "private"
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(link_import,"_facebook_public_candidates",return_value=[link]), \
                 patch.object(link_import,"_try_public_download",side_effect=attempt):
                with self.assertRaises(link_import.LinkImportError):
                    link_import.fetch_public_social_media(link,temp,timeout=20)
        self.assertEqual(attempts,[False],"No retry of access-controlled media")

    def test_chrome_retry_does_not_use_session_cookies(self):
        link="https://www.facebook.com/reel/1800066080991078/"
        received=[]
        class FakeProcess:
            returncode=1
            def poll(self):return self.returncode
        def fake_popen(command,**kwargs):
            received.extend(command)
            return FakeProcess()
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(link_import.subprocess,"Popen",side_effect=fake_popen):
                self.assertEqual(link_import._try_public_download(
                    link,Path(temp),deadline=link_import.time.monotonic()+5,
                    format_spec="best",impersonate=True),"unavailable")
        self.assertEqual(received[received.index("--impersonate")+1],"chrome-99")
        self.assertNotIn("--cookies-from-browser",received)
        self.assertNotIn("--cookies",received)
        self.assertNotIn("--username",received)
        self.assertNotIn("--password",received)
        self.assertIn("--max-filesize",received)
        self.assertIn("--socket-timeout",received)


if __name__=="__main__":unittest.main()
