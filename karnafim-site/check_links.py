#!/usr/bin/env python3
"""Site link smoke audit. No authentication, writes, or personal content."""
import ast, re, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urljoin, urlsplit
from urllib.request import Request, urlopen
ROOT = "https://karnafim-community-46.onrender.com"
UA = "Mozilla/5.0 KarnafimLinkCheck/1.0"
BASE = Path(__file__).resolve().parent
PUBLIC = ("/", "/health", "/register", "/login", "/memories", "/discover", "/archive", "/find", "/feed", "/invite", "/favicon.svg", "/favicon.ico")
PROTECTED = ("/chats", "/new-post", "/directory", "/profile", "/password", "/admin", "/community/moderation")
def probe(url):
    try:
        req = Request(url, headers={"User-Agent": UA, "Accept": "text/html,application/json,*/*"})
        with urlopen(req, timeout=12) as r:
            return r.status, r.geturl()
    except HTTPError as exc:
        return exc.code, url
    except (URLError, TimeoutError, OSError) as exc:
        return None, str(exc)[:100]
def archive_sources():
    tree = ast.parse((BASE / "archive_data.py").read_text(encoding="utf-8"))
    a = next(x.value for x in tree.body if isinstance(x, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "ARCHIVE" for t in x.targets))
    return ast.literal_eval(a)
def static_routes():
    routes = set()
    for name in ("app.py", "community_portal.py"):
        tree = ast.parse((BASE / name).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for dec in node.decorator_list:
                    if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute) and dec.func.attr == "route" and dec.args and isinstance(dec.args[0], ast.Constant):
                        routes.add(dec.args[0].value)
    return routes
def check_static_links():
    routes=static_routes()
    for p in PUBLIC + PROTECTED:
        if p not in routes:
            print("INVALID local route:",p)
            return False
    for name in ("app.py","community_portal.py"):
        code=(BASE / name).read_text(encoding="utf-8")
        for p in re.findall(r'''href=["'](/[^"'<> ]+)''',code):
            if p.startswith("/contact/") or p.startswith("/chat/") or p.startswith("/community-media/"):continue
            if p in routes or p.split("?")[0] in routes:continue
            # Browser-generated/form/input paths are not public href URLs.
            print("WARN possible dynamic link",name,p)
    print("PASS static route inventory",len(routes))
    return True
def main():
    errors=0;indeterminate=0
    if not check_static_links():errors+=1
    print("Live public and protected GET routes")
    for p in PUBLIC+PROTECTED:
        status,landing=probe(ROOT+p)
        good = status in ((200,301,302,303,307,308) if p in PUBLIC else (200,301,302,303,307,308,401,403))
        print(" ",p,status,"PASS" if good else "FAIL")
        if not good:errors+=1
    refs=archive_sources()
    urls=sorted({r["url"] for r in refs})
    print("External historical source URLs",len(urls),"across",len(refs),"cards")
    with ThreadPoolExecutor(max_workers=5) as pool:
        pending={pool.submit(probe,u):u for u in urls}
        for future in as_completed(pending):
            status,landing=future.result()
            if status in (404,410):
                print(" BROKEN",status,pending[future]);errors+=1
            elif status is None or status in (403,429,500,502,503,504):
                print(" UNVERIFIED",status,pending[future]);indeterminate+=1
            else:
                print(" CHECKED",status,pending[future])
    print("AUDIT errors=",errors,"unverified=",indeterminate)
    if errors:sys.exit(1)
if __name__=="__main__":main()
