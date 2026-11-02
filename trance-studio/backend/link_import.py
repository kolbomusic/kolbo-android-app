"""Bounded public social-video import for explicit user initiated link sharing.

Never fetch arbitrary URLs from the server. This importer intentionally only
accepts a short list of public social/video domains with supported extractors.
Private/login/DRM pages fail closed. No browser cookies or account tokens.
"""
from __future__ import annotations

import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

MAX_VIDEO=45*1024*1024
MAX_AUDIO=15*1024*1024
MAX_SECONDS=120.5
ALLOWED_HOSTS=(
    "facebook.com","fb.watch","instagram.com","tiktok.com","tiktokv.com",
    "vimeo.com",
    "twitter.com","x.com","reddit.com","redd.it","dailymotion.com",
    "dai.ly","soundcloud.com","twitch.tv","clips.twitch.tv",
    "pinterest.com","pin.it",
)
MEDIA_EXT={".mp4":"video/mp4",".webm":"video/webm",".mov":"video/quicktime",
           ".m4a":"audio/mp4",".mp3":"audio/mpeg",".ogg":"audio/ogg",
           ".opus":"audio/ogg",".wav":"audio/wav",".flac":"audio/flac",
           ".aac":"audio/aac",".3gp":"video/3gpp",".3gpp":"video/3gpp"}


class LinkImportError(ValueError):
    """User-safe failure with privacy-preserving diagnostic codes."""
    def __init__(self,message,*,code="unavailable",attempts=0):
        super().__init__(message)
        self.code=code
        self.attempts=int(attempts)


def validate_public_link(raw):
    value=str(raw or "").strip()
    if not value or len(value)>2048 or any(c.isspace() for c in value):
        raise LinkImportError("יש לשתף קישור HTTPS קצר לתוכן ציבורי יחיד.")
    try:
        url=urlsplit(value)
        host=(url.hostname or "").lower().rstrip(".")
        port=url.port
    except ValueError as exc:
        raise LinkImportError("כתובת הקישור אינה תקינה.") from exc
    if (url.scheme!="https" or not host or url.username or url.password or
            port not in (None,443) or "\\" in value or
            host.startswith("xn--") or
            not any(host==root or host.endswith("."+root)
                    for root in ALLOWED_HOSTS)):
        raise LinkImportError(
            "הקישור אינו מאתר וידאו נתמך לייבוא. ניתן לשתף את קובץ המדיה עצמו.")
    if url.path.startswith("//"):
        raise LinkImportError("כתובת הקישור אינה תקינה.")
    return value


def _media_probe(path):
    try:
        output=subprocess.check_output(
            ["ffprobe","-v","error","-show_entries","format=duration",
             "-of","default=noprint_wrappers=1:nokey=1",str(path)],
            timeout=10,stderr=subprocess.DEVNULL)
        duration=float(output.decode().strip())
        if not 0.15<duration<=MAX_SECONDS:
            raise LinkImportError("משך הסרטון גדול משתי דקות או שאינו תקין.")
    except (ValueError,subprocess.CalledProcessError,subprocess.TimeoutExpired) as exc:
        if isinstance(exc,LinkImportError):raise
        raise LinkImportError("לא התקבל קובץ שמע או וידאו תקין.") from exc
    return duration



class _FacebookOnlyRedirects(HTTPRedirectHandler):
    """Never follow a shortened share URL into a different site or private IP."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        try:
            parts=urlsplit(newurl)
            host=(parts.hostname or "").lower().rstrip(".")
            allowed=host=="facebook.com" or host.endswith(".facebook.com")
            allowed=allowed or host=="fb.watch" or host.endswith(".fb.watch")
            if not (parts.scheme=="https" and allowed and parts.port in (None,443)
                    and not parts.username and not parts.password):
                raise LinkImportError("Facebook הפנתה את הקישור לכתובת שאינה נתמכת.")
        except ValueError as exc:
            raise LinkImportError("קישור ההפניה אינו תקין.") from exc
        return super().redirect_request(req,fp,code,msg,headers,newurl)


def _facebook_video_id(url):
    """Parse only an actual Facebook reel/video ID, never an opaque share token."""
    parts=urlsplit(url)
    host=(parts.hostname or "").lower().rstrip(".")
    if host!="facebook.com" and not host.endswith(".facebook.com"):
        return None
    path=parts.path
    # Public Facebook permalink can contain a video slug between /videos/
    # and its numeric ID, e.g. /natgeo/videos/title/1016464114801712/.
    match=re.search(r"/(?:videos|reel)/(?:[^/?#]+/)?(\d{8,22})(?:/|$)",path)
    if match:return match.group(1)
    if path.rstrip("/") in ("/watch", "/watch/"):
        key=parse_qs(parts.query).get("v",[""])[0]
        if re.fullmatch(r"\d{8,22}",key):return key
    return None


class _PublicFacebookMeta(HTMLParser):
    """Read only canonical/OG URLs from an already public HTML page."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links=[]
        self.media=[]

    def handle_starttag(self, tag, pairs):
        a=dict(pairs)
        if tag=="meta":
            kind=(a.get("property") or a.get("name") or "").lower()
            if kind in ("og:video","og:video:url","og:video:secure_url"):
                self.media.append(a.get("content") or "")
            elif kind in ("og:url","twitter:url","al:web:url"):
                self.links.append(a.get("content") or "")
            elif (a.get("http-equiv") or "").lower()=="refresh":
                m=re.match(r"^\s*\d+(?:\.\d+)?\s*;\s*url\s*=\s*['\"]?([^'\"\s]+)",
                           a.get("content") or "",re.IGNORECASE)
                if m:self.links.append(m.group(1))
        elif tag=="link" and "canonical" in (a.get("rel") or "").lower().split():
            self.links.append(a.get("href") or "")


def _trusted_facebook_video_url(value, base):
    """No offsite metadata links, unsafe protocols, ports, credentials or non-video pages."""
    try:
        resolved=urljoin(base,value.strip())
        u=urlsplit(resolved)
        host=(u.hostname or "").lower().rstrip(".")
        if (u.scheme!="https" or
            not (host=="facebook.com" or host.endswith(".facebook.com")) or
            u.port not in (None,443) or u.username or u.password or
            "\\" in resolved or len(resolved)>2048):
            return None
        return resolved if _facebook_video_id(resolved) else None
    except ValueError:
        return None


def _facebook_html_video_urls(html, base):
    """Extract at most three official public video links from bounded HTML."""
    if not html:return []
    parser=_PublicFacebookMeta()
    try:
        parser.feed(html[:150000].decode("utf-8","replace"))
        parser.close()
    except (ValueError,TypeError):
        return []
    results=[]
    for link in parser.links[:18]:
        if isinstance(link,str):
            safe=_trusted_facebook_video_url(link,base)
            if safe and safe not in results:results.append(safe)
    return results[:3]



def _trusted_facebook_media_url(value):
    """Allow only canonical public Facebook CDN video addresses, no arbitrary hosts."""
    try:
        u=urlsplit(str(value or "").strip())
        host=(u.hostname or "").lower().rstrip(".")
        if (u.scheme!="https" or not (host=="fbcdn.net" or host.endswith(".fbcdn.net"))
            or u.port not in (None,443) or u.username or u.password
            or "\\" in value or len(value)>2048 or not u.path.startswith("/")):
            return None
        return value
    except (ValueError,AttributeError):
        return None


def _facebook_html_media_urls(html):
    """Extract only explicitly advertised public og:video metadata."""
    if not html:return []
    parser=_PublicFacebookMeta()
    try:
        parser.feed(html[:150000].decode("utf-8","replace"))
        parser.close()
    except (ValueError,TypeError):
        return []
    results=[]
    for value in parser.media[:12]:
        safe=_trusted_facebook_media_url(value)
        if safe and safe not in results:results.append(safe)
    return results[:2]


class _FacebookCdnOnlyRedirects(HTTPRedirectHandler):
    """Keep a public media fetch on fbcdn.net; do not allow redirect-to-localhost."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not _trusted_facebook_media_url(newurl):
            raise LinkImportError("הקישור הציבורי הפנה למקור מדיה לא מאושר.",
                                  code="unsafe_redirect")
        return super().redirect_request(req,fp,code,msg,headers,newurl)


def _try_public_facebook_cdn(url, folder, *, deadline, opener=None):
    """Stream only public og:video MP4, capped by timeout/size/type; no cookies."""
    if not _trusted_facebook_media_url(url):
        return "unsafe_url"
    opener=opener or build_opener(_FacebookCdnOnlyRedirects)
    destination=folder/"shared.mp4"
    try:
        req=Request(url,headers={
            "User-Agent":"Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/126 Safari/537.36",
            "Accept":"video/mp4,video/*;q=0.9",
        },method="GET")
        with opener.open(req,timeout=min(8,max(1,deadline-time.monotonic()))) as response:
            mime=(response.headers.get("Content-Type") or "").split(";",1)[0].lower().strip()
            if mime not in ("video/mp4","application/octet-stream"):
                return "invalid_mime"
            length=response.headers.get("Content-Length")
            if length and (not length.isdigit() or int(length)>MAX_VIDEO):
                return "size"
            total=0
            with destination.open("wb") as stream:
                while True:
                    if time.monotonic()>=deadline:return "timeout"
                    data=response.read(64*1024)
                    if not data:break
                    total+=len(data)
                    if total>MAX_VIDEO:return "size"
                    stream.write(data)
            if total<2048:return "invalid_file"
            return "ok"
    except (OSError,URLError,HTTPError,LinkImportError):
        return "unavailable"

def _safe_facebook_page_url(candidate):
    """Only public HTTPS Facebook page redirects; never off-domain/localhost."""
    try:
        p=urlsplit(candidate)
        host=(p.hostname or "").lower().rstrip(".")
        return bool(
            p.scheme=="https" and p.port in (None,443) and
            not p.username and not p.password and
            len(candidate)<=2048 and "\\" not in candidate and
            (host=="facebook.com" or host.endswith(".facebook.com") or
             host=="fb.watch" or host.endswith(".fb.watch")))
    except (ValueError,TypeError):
        return False


def _facebook_public_browser_candidates(url, *, timeout=7):
    """Resolve a publicly accessible Facebook short share through curl_cffi.

    urllib mobile-lookalike requests often yield a login/landing page, while
    real Chrome 99 HTTP/TLS negotiation exposes the 3xx video destination.
    Redirects are followed manually and never allowed off Facebook; only
    public HTML head metadata is inspected, no account cookies or private APIs.
    """
    if not _safe_facebook_page_url(url):return []
    try:
        from curl_cffi import requests as chrome_requests
    except ImportError:
        return []
    deadline=time.monotonic()+max(1,min(timeout,9))
    current=url
    discovered=[]
    for _ in range(5):
        if deadline-time.monotonic()<.6:break
        response=None
        try:
            response=chrome_requests.get(
                current,impersonate="chrome99",allow_redirects=False,
                stream=True,timeout=min(4,max(1,deadline-time.monotonic())),
                headers={"Accept":"text/html,application/xhtml+xml"})
            location=response.headers.get("Location","")
            if response.status_code in (301,302,303,307,308) and location:
                follow=urljoin(current,location)
                if not _safe_facebook_page_url(follow):break
                direct=_trusted_facebook_video_url(follow,current)
                if direct and direct not in discovered:discovered.append(direct)
                current=follow
                continue
            direct=_trusted_facebook_video_url(current,url)
            if direct and direct not in discovered:discovered.append(direct)
            mime=(response.headers.get("Content-Type") or "").lower()
            if response.status_code==200 and (
                "text/html" in mime or "application/xhtml+xml" in mime):
                chunks=[]
                size=0
                for chunk in response.iter_content(chunk_size=32768):
                    if not chunk:continue
                    room=150000-size
                    if room<=0:break
                    chunks.append(chunk[:room])
                    size+=min(len(chunk),room)
                    if size>=150000:break
                html=b"".join(chunks)
                for video in _facebook_html_video_urls(html,current):
                    if video not in discovered:discovered.append(video)
                for media in _facebook_html_media_urls(html):
                    if media not in discovered:discovered.append(media)
            break
        except Exception:
            # Network/library differences are expected on free hosts;
            # preserve the ordinary extractor path without disclosing URLs.
            break
        finally:
            if response is not None:
                response.close()
    return discovered[:4]


def _facebook_public_candidates(url, *, opener=None, timeout=7):
    """Try redirects and public HTML metadata of a Facebook short-share link.

    A share/v/ page often responds HTTP 200 with a canonical URL inside HTML,
    rather than redirecting. No cookies, login, private APIs or offsite URLs.
    """
    raw=urlsplit(url)
    host=(raw.hostname or "").lower().rstrip(".")
    if not (host=="fb.watch" or host.endswith(".fb.watch")
            or host=="facebook.com" or host.endswith(".facebook.com")):
        return [url]
    candidates=[url]
    if "/share/" in raw.path or host.endswith("fb.watch"):
        client=opener or build_opener(_FacebookOnlyRedirects)
        try:
            req=Request(url,headers={
                "User-Agent":"Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/126 Safari/537.36",
                "Accept":"text/html,application/xhtml+xml",
            },method="GET")
            with client.open(req,timeout=timeout) as response:
                destination=response.geturl()
                direct=_trusted_facebook_video_url(destination,url)
                if direct:candidates.append(direct)
                headers=getattr(response,"headers",{})
                content_type=(headers.get("Content-Type") or "") if hasattr(headers,"get") else ""
                if not content_type or "text/html" in content_type or "application/xhtml+xml" in content_type:
                    read=getattr(response,"read",None)
                    if callable(read):
                        html=read(150000)
                        candidates.extend(_facebook_html_video_urls(html,destination))
                        # Direct CDN metadata is public HTML metadata, not
                        # scraped private API tokens or signed-in session data.
                        candidates.extend(_facebook_html_media_urls(html))
        except (OSError,URLError,HTTPError,ValueError,LinkImportError):
            pass  # The original public link still gets one bounded extraction.
        # Chrome public HTML can advertise the actual video bytes even if
        # urllib has already resolved the numeric ID. Earlier versions skipped
        # Chrome in that case, losing an independent (no-login) recovery path.
        # Preserve injected test openers to keep mocked tests deterministic.
        if opener is None and not any(_trusted_facebook_media_url(c) for c in candidates):
            candidates.extend(_facebook_public_browser_candidates(
                url,timeout=min(5,timeout)))
    ids={i for c in candidates if (i:=_facebook_video_id(c))}
    if len(ids)>1:
        # Different IDs from public metadata/redirects: do not risk silently
        # downloading an unrelated video in response to the user's link.
        raise LinkImportError("קישור השיתוף הפנה לסרטונים שונים; הייבוא נעצר כדי למנוע הורדת סרטון שגוי.",
                              code="ambiguous_share")
    video_id=next(iter(ids),None)
    if video_id:
        watch=f"https://www.facebook.com/watch/?v={video_id}"
        candidates.extend([
            watch,
            f"https://www.facebook.com/reel/{video_id}/",
            "https://www.facebook.com/plugins/video.php?href="+quote(watch,safe=""),
        ])
    return list(dict.fromkeys(candidates))[:8]


def _readable_failure(stderr):
    # No raw URL, title or user speech appears in error messages or logs.
    raw=stderr.lower()
    if any(key in raw for key in ("log in","login required","sign in","login to", "private video","not available")):
        return "private"
    if any(key in raw for key in ("403 forbidden","http error 403","429 too many","blocked by")):
        return "restricted"
    if "cannot parse data" in raw or "no video formats found" in raw:
        return "extractor"
    if "unsupported url" in raw:
        return "unsupported"
    if "duration > 120" in raw or "does not pass filter" in raw:
        return "duration"
    if "file is larger" in raw or "max-filesize" in raw:
        return "size"
    return "unavailable"


def _try_public_download(url, folder, *, deadline, format_spec, impersonate=False):
    command=[
        sys.executable,"-m","yt_dlp","--ignore-config",
        "--no-playlist","--no-progress","--no-warnings",
        "--no-cache-dir","--no-write-thumbnail","--no-write-subs",
        "--no-write-auto-subs","--restrict-filenames",
        "--socket-timeout","8","--retries","1","--fragment-retries","1",
        "--max-filesize","45M","--match-filter","duration <= 120",
        "--format",format_spec,
        "--merge-output-format","mp4",
        "--output",str(folder/"shared.%(ext)s"),url
    ]
    if impersonate:
        # Public Chrome 99 TLS/client profile can restore Facebook extraction
        # on some layouts. No user cookies, passwords or login sessions.
        command[3:3]=["--impersonate","chrome-99"]
    # Capture bounded diagnostics without adding user's private URL to logs.
    with tempfile.TemporaryFile(mode="w+b") as error_stream:
        try:
            process=subprocess.Popen(command,stdout=subprocess.DEVNULL,
                                     stderr=error_stream)
        except (OSError,ValueError) as exc:
            raise LinkImportError("מנוע ייבוא הקישורים אינו זמין כרגע.") from exc
        try:
            while process.poll() is None:
                if time.monotonic()>deadline:
                    return "timeout"
                size=sum(p.stat().st_size for p in folder.iterdir() if p.is_file())
                if size>MAX_VIDEO+3*1024*1024:
                    return "size"
                time.sleep(.3)
            if process.returncode==0:
                return "ok"
            error_stream.seek(0)
            return _readable_failure(error_stream.read(12000).decode("utf-8","replace"))
        finally:
            if process.poll() is None:
                process.terminate()
                try:process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=2)


def fetch_public_social_media(url, directory, *,timeout=70):
    """Try independent *public* URL forms, bounded by one time/byte budget.

    Never bypass authentication, use browser cookies, expose raw URLs or
    silently replace the media with another public video. Always validate the
    actually downloaded file (size, type and duration) with ffprobe.
    """
    url=validate_public_link(url)
    folder=Path(directory)
    folder.mkdir(parents=True,exist_ok=True)
    deadline=time.monotonic()+min(max(timeout,1),90)
    candidates=_facebook_public_candidates(url,timeout=min(6,max(1,deadline-time.monotonic())))
    failures=[]
    is_facebook=(urlsplit(url).hostname or "").lower().rstrip(".").endswith("facebook.com") or (urlsplit(url).hostname or "").lower().rstrip(".")=="fb.watch"
    # FaceBook share/v -> canonical video -> watch URL -> reel / official
    # public embed. An unsupported social site remains a single attempt.
    attempts=candidates[:8]
    if len(attempts)>1:
        # Avoid a single dead extractor using the entire 70-second budget.
        attempt_limit=max(7,min(19,(deadline-time.monotonic())/len(attempts)))
    else:
        attempt_limit=max(1,deadline-time.monotonic())
    for index, candidate in enumerate(attempts):
        for output in folder.iterdir():
            if output.is_file():output.unlink(missing_ok=True)
        if deadline-time.monotonic()<2:break
        format_spec=(
            "bv*[height<=720][ext=mp4]+ba[ext=m4a]/b[ext=mp4]/"
            "b[height<=720]/ba[ext=m4a]/bestaudio"
        ) if index==0 else "b[ext=mp4]/b[height<=720]/best"
        if _trusted_facebook_media_url(candidate):
            code=_try_public_facebook_cdn(candidate,folder,
                    deadline=min(deadline,time.monotonic()+attempt_limit))
        else:
            code=_try_public_download(candidate,folder,
                                      deadline=min(deadline,time.monotonic()+attempt_limit),
                                      format_spec=format_spec,
                                      impersonate=is_facebook and index>0)
        if (code in ("extractor","restricted","unavailable") and
                is_facebook and index==0 and len(attempts)==1 and
                deadline-time.monotonic()>=5):
            # Only one opaque share link available: attempt independent Chrome
            # HTTP transport before giving up; time and size caps remain.
            for output in folder.iterdir():
                if output.is_file():output.unlink(missing_ok=True)
            code=_try_public_download(candidate,folder,deadline=deadline,
                                      format_spec="b[ext=mp4]/b[height<=720]/best",
                                      impersonate=True)
        if code!="ok":
            failures.append(code)
            if code=="size":break
            continue
        media=[p for p in folder.iterdir() if p.is_file() and
               p.name.startswith("shared.") and p.suffix.lower() in MEDIA_EXT]
        if len(media)!=1:
            failures.append("invalid_file")
            continue
        result=media[0]
        mime=MEDIA_EXT[result.suffix.lower()]
        cap=MAX_VIDEO if mime.startswith("video/") else MAX_AUDIO
        if not 2048<=result.stat().st_size<=cap:
            failures.append("size")
            continue
        try:
            _media_probe(result)
        except LinkImportError:
            failures.append("duration")
            continue
        return result,mime
    if "size" in failures:
        raise LinkImportError("גודל הסרטון חורג מ־45MB.",code="size",attempts=len(failures))
    if "duration" in failures:
        raise LinkImportError("המדיה ארוכה משתי דקות או אינה בפורמט נתמך.",code="duration",attempts=len(failures))
    if "private" in failures or "restricted" in failures:
        raise LinkImportError(
            "השרת קיבל שגיאת הרשאה או הגבלת גישה מ־Facebook. אי אפשר לייבא סרטון שמוגבל לצפייה ללא הרשאה.",
            code="access_restricted",attempts=len(failures))
    if "extractor" in failures:
        raise LinkImportError(
            "מנוע החילוץ של Facebook לא הצליח לפענח את דף הסרטון (Cannot parse data). "
            "זה לא בהכרח אומר שהסרטון פרטי או חסום.",
            code="extractor_parse",attempts=len(failures))
    raise LinkImportError(
        "לא התקבל קובץ וידאו תקין מהמקורות הציבוריים שנבדקו.",
        code="no_public_media",attempts=len(failures))
