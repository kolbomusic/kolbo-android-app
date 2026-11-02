"""Investigate how different public browser profiles resolve a known Facebook share/v link.

Only a fixed public test URL is inspected. No credentials, cookies, video
download or user data. Reports only HTTP state, host and recognized video ID.
"""
import json
import sys
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"backend"))
from link_import import _facebook_html_video_urls, _facebook_video_id

URL="https://www.facebook.com/share/v/1NpnVb9ghX/"
EXPECTED="1480256363681360"
CASES=(
    ("chrome99","https://www.facebook.com/share/v/1NpnVb9ghX/"),
    ("chrome120","https://www.facebook.com/share/v/1NpnVb9ghX/"),
    ("safari17_0","https://www.facebook.com/share/v/1NpnVb9ghX/"),
    ("chrome99","https://m.facebook.com/share/v/1NpnVb9ghX/"),
    ("chrome120","https://web.facebook.com/share/v/1NpnVb9ghX/"),
    ("chrome99","https://mbasic.facebook.com/share/v/1NpnVb9ghX/"),
)


def main():
    from curl_cffi import requests
    results=[]
    for profile,url in CASES:
        report={"profile":profile,"entry_host":urlsplit(url).hostname}
        try:
            response=requests.get(
                url,impersonate=profile,timeout=9,allow_redirects=True,
                max_redirects=5,headers={"Accept":"text/html,application/xhtml+xml"})
            final=urlsplit(response.url)
            report.update({"http":response.status_code,
                           "resolved_host":final.hostname,
                           "resolved_id":_facebook_video_id(response.url),
                           "html_ids":[_facebook_video_id(link)
                               for link in _facebook_html_video_urls(
                                   response.content[:150000],response.url)][:3],
                           "content_type":response.headers.get("Content-Type","").split(";")[0],
                           "expected":EXPECTED in response.url or any(
                               _facebook_video_id(link)==EXPECTED for link in
                               _facebook_html_video_urls(response.content[:150000],
                                                         response.url))})
        except Exception as exc:
            report["error_kind"]=type(exc).__name__
        results.append(report)
        print("PUBLIC_SHARE_V_RESOLVE_DIAGNOSTIC="+json.dumps(report),flush=True)
    positive=[x for x in results if x.get("expected")]
    print("PUBLIC_SHARE_V_RESOLVE_WORKING_PROFILES="+json.dumps(
        [x["profile"]+"/"+x["entry_host"] for x in positive]),flush=True)
    return bool(positive)


if __name__=="__main__":
    raise SystemExit(0 if main() else 1)
