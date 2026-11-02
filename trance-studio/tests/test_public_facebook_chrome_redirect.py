"""Public Facebook Chrome short-share resolver: redirect safety and no account use."""
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"backend"))
import link_import


class Response:
    def __init__(self, status, headers=None, chunks=()):
        self.status_code=status
        self.headers=headers or {}
        self.chunks=list(chunks)
        self.closed=False
    def iter_content(self,chunk_size):yield from self.chunks
    def close(self):self.closed=True


class FacebookChromeResolutionTests(unittest.TestCase):
    def fake_client(self, pages, seen):
        def get(url,**kwargs):
            seen.append((url,kwargs))
            return pages[url]
        return types.SimpleNamespace(requests=types.SimpleNamespace(get=get))

    def test_bounded_browser_redirect_returns_expected_video(self):
        start="https://www.facebook.com/share/v/1NpnVb9ghX/"
        reel="https://www.facebook.com/reel/1480256363681360"
        pages={start:Response(302,{"Location":reel}),
               reel:Response(200,{"Content-Type":"text/html"},[
                   b'<meta property="og:url" content="https://www.facebook.com/reel/1480256363681360">'])}
        seen=[]
        with patch.dict(sys.modules,{"curl_cffi":self.fake_client(pages,seen)}):
            result=link_import._facebook_public_browser_candidates(start)
        self.assertIn(reel,result)
        self.assertEqual(len(seen),2)
        self.assertTrue(all(p.closed for p in pages.values()))
        self.assertTrue(all(call[1]["allow_redirects"] is False for call in seen))
        self.assertTrue(all("cookies" not in call[1] for call in seen))
        self.assertTrue(all(call[1]["impersonate"]=="chrome99" for call in seen))

    def test_redirect_to_nonfacebook_is_never_fetched(self):
        start="https://www.facebook.com/share/v/test"
        pages={start:Response(302,{"Location":"http://127.0.0.1/latest/meta-data"})}
        seen=[]
        with patch.dict(sys.modules,{"curl_cffi":self.fake_client(pages,seen)}):
            out=link_import._facebook_public_browser_candidates(start)
        self.assertEqual(out,[])
        self.assertEqual(len(seen),1)

    def test_html_metadata_canonical_is_accepted(self):
        start="https://www.facebook.com/share/v/test"
        html=b'<meta property="og:url" content="https://www.facebook.com/reel/1480256363681360">'
        pages={start:Response(200,{"Content-Type":"text/html"},[html])}
        with patch.dict(sys.modules,{"curl_cffi":self.fake_client(pages,[])}):
            out=link_import._facebook_public_browser_candidates(start)
        self.assertEqual(out,["https://www.facebook.com/reel/1480256363681360"])

    def test_disallows_untrusted_pages(self):
        for link in ("https://facebook.com.evil.test/share/v/xx",
                     "http://www.facebook.com/share/v/xx",
                     "https://127.0.0.1/share/v/xx",
                     "https://facebook.com:444/share/v/xx"):
            self.assertFalse(link_import._safe_facebook_page_url(link))

if __name__=="__main__":
    unittest.main()
