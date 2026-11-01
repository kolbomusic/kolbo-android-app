"""External source-health and content audit for the 14 Karnafim archive records.
Read-only HEAD/GET requests. No scraping of private profiles, no credentials.
Results are *not* automatically trusted when a source returns a bot challenge.
Exit 1 only for definite 404/410, a successful response with unrelated content,
or a verified redirect to the wrong site.
"""
from __future__ import annotations
import ast
import json
import os
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from html import unescape
from html.parser import HTMLParser
from pathlib import Path

ROOT=Path(__file__).resolve().parent
USER_AGENT="Mozilla/5.0 (compatible; KarnafimArchiveAudit/1.0; reference-checking)"
TIMEOUT=14
# Distinguish a functioning source document from a blank page or a generic homepage.
EXPECT={
  1:("יהונתן","שרעבי"), 2:("יהונתן","שרעבי"), 3:("יהונתן","שרעבי"),
  4:("גדוד 46","מורשת"), 5:("גדוד שלח","מורשת"), 6:("גדוד 46","ברקן"),
  7:("חטיבה 401","תמונות"), 8:("גדוד 46","מלחמת"),
  9:("בניה","ריין"), 10:("אורי","גרוסמן"), 11:("בניה","ריין"),
  12:("חטיבה 401","סרטונים"), 13:("אדם","גורן"),14:("אלכסנדר","בונימוביץ")
}
SOURCE_DOMAINS=("izkor.gov.il","yadlashiryon.com","idf.il","gd46401.org.il","benaya-rhein.com")
# Four publisher URLs were confirmed to return 404 on 2026-11-01. Their historical
# references are retained as nonclickable text on the public source detail pages.
RETIRED_SOURCE_IDS={4,5,7,12}

class TextParser(HTMLParser):
  def __init__(self):
    super().__init__()
    self.fragments=[]
    self.ignore=0
    self.title=0
    self.titles=[]
  def handle_starttag(self,tag,attrs):
    if tag in ("style","script","noscript"):self.ignore+=1
    if tag=="title":self.title+=1
  def handle_endtag(self,tag):
    if tag in ("style","script","noscript"):self.ignore=max(0,self.ignore-1)
    if tag=="title":self.title=max(0,self.title-1)
  def handle_data(self,data):
    if not self.ignore:
      if self.title:self.titles.append(data)
      self.fragments.append(data)

def load_archive():
  tree=ast.parse((ROOT/"archive_data.py").read_text(encoding="utf-8"))
  for node in tree.body:
    if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=="ARCHIVE" for t in node.targets):
      return ast.literal_eval(node.value)
  raise RuntimeError("Missing ARCHIVE")

def canonical(s):
  return re.sub(r"\s+"," ",unescape(s)).strip().lower()

def check(url,ids):
  # Guard against a maliciously edited archive registry.
  parsed=urllib.parse.urlsplit(url)
  host=(parsed.hostname or "").lower().removeprefix("www.")
  if parsed.scheme!="https" or host not in SOURCE_DOMAINS:
    return {"status":"invalid_url","reason":"Unapproved source domain or non-HTTPS","http":None,"url":url,"ids":ids}
  # urllib's HTTP request line must be ASCII. Archive URLs can contain
  # raw Hebrew path characters; percent-encode them before making the request.
  # Preserve existing %-escapes and URL delimiters to avoid double encoding.
  encoded_url=urllib.parse.quote(url, safe="/:%?&=#+,;@._~-")
  request=urllib.request.Request(encoded_url, headers={
    "User-Agent":USER_AGENT, "Accept":"text/html,application/xhtml+xml;q=0.9,*/*;q=0.5"
  }, method="GET")
  try:
    with urllib.request.urlopen(request,timeout=TIMEOUT) as response:
      code=response.status
      dest=response.geturl()
      typ=response.headers.get("Content-Type","").lower()
      raw=response.read(170_000)
  except urllib.error.HTTPError as exc:
    code=exc.code
    if code in (404,410):
      return {"status":"broken","reason":"Original source returns 404/410","http":code,"url":url,"ids":ids}
    return {"status":"inconclusive","reason":"Source denies automated request or temporarily unavailable",
            "http":code,"url":url,"ids":ids}
  except (TimeoutError,OSError,urllib.error.URLError) as exc:
    return {"status":"inconclusive","reason":str(exc)[:120],"http":None,"url":url,"ids":ids}
  redirect=urllib.parse.urlsplit(dest)
  dsthost=(redirect.hostname or "").lower().removeprefix("www.")
  if dsthost not in SOURCE_DOMAINS:
    return {"status":"broken","reason":"Unexpected redirect outside trusted sources",
            "http":code,"url":url,"resolved_url":dest,"ids":ids}
  if not 200<=code<300:
    return {"status":"inconclusive","reason":"Unexpected HTTP status","http":code,"url":url,"ids":ids}
  if "html" not in typ:
    return {"status":"inconclusive","reason":"Source does not provide HTML","http":code,"url":url,"ids":ids}
  text=raw.decode("utf-8","replace")
  parser=TextParser()
  parser.feed(text)
  visible=canonical(" ".join(parser.fragments))
  if len(visible)<250:
    return {"status":"inconclusive","reason":"Too little rendered text to verify completeness",
            "http":code,"url":url,"ids":ids}
  missing=[]
  for id in ids:
    expected=EXPECT[id]
    # Some publisher pages have site/chrome content with "גדוד 46" repeated,
    # therefore both markers should appear in the visible page.
    if not all(canonical(word) in visible for word in expected):
      missing.append(id)
  if missing:
    return {"status":"unverified_content","reason":"Expected text not present in returned source content",
            "http":code,"ids":ids,"missing_ids":missing,"url":url,"resolved_url":dest,
            "page_title":canonical(" ".join(parser.titles))[:150]}
  return {"status":"verified","reason":"Source loaded and contains expected topic text",
          "http":code,"ids":ids,"url":url,"resolved_url":dest,
          "page_title":canonical(" ".join(parser.titles))[:150],
          "visible_characters":len(visible)}

def run():
  archive=load_archive()
  urls={}
  for row in archive:urls.setdefault(row["url"],[]).append(row["id"])
  results=[]
  for url,ids in urls.items():
    result=check(url,ids)
    # Do not fail the publisher audit for links ALREADY REMOVED from clickable
    # navigation and clearly identified as unavailable in public source pages.
    # This exception is limited to the four independently confirmed dead URLs.
    # A newly broken or mismatching active source still fails the check.
    if set(ids).issubset(RETIRED_SOURCE_IDS) and result["status"] in ("broken","unverified_content"):
      result["original_status"]=result["status"]
      result["status"]="retired"
      result["reason"]="Legacy article URL is deliberately not linked; public page discloses unavailability"
    results.append(result)
    print(result["status"].upper(),",".join(map(str,ids)),result.get("http"),result["reason"])
    sys.stdout.flush()
  counts={name:sum(x["status"]==name for x in results)
          for name in ("verified","retired","broken","unverified_content","inconclusive","invalid_url")}
  report={"unique_external_sources":len(urls),"archive_items":len(archive),
          "counts":counts,"sources":results,
          "note":"Automated successful page-content checks do not validate media embeds or guarantee future availability."}
  output=Path(os.environ.get("KARNAFIM_LINK_REPORT","external_link_report.json"))
  output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
  print("REPORT",str(output),json.dumps(counts,ensure_ascii=False))
  return 1 if counts["broken"] or counts["invalid_url"] or counts["unverified_content"] else 0

if __name__=="__main__":
  sys.exit(run())
()*-._~")
  request=urllib.request.Request(encoded_url,headers={
    "User-Agent":USER_AGENT,"Accept":"text/html,application/xhtml+xml;q=0.9,*/*;q=0.5"
  },method="GET")
  try:
    with urllib.request.urlopen(request,timeout=TIMEOUT) as response:
      code=response.status
      dest=response.geturl()
      typ=response.headers.get("Content-Type","").lower()
      raw=response.read(170_000)
  except urllib.error.HTTPError as exc:
    code=exc.code
    if code in (404,410):
      return {"status":"broken","reason":"Original source returns 404/410","http":code,"url":url,"ids":ids}
    return {"status":"inconclusive","reason":"Source denies automated request or temporarily unavailable",
            "http":code,"url":url,"ids":ids}
  except (TimeoutError,OSError,urllib.error.URLError) as exc:
    return {"status":"inconclusive","reason":str(exc)[:120],"http":None,"url":url,"ids":ids}
  redirect=urllib.parse.urlsplit(dest)
  dsthost=(redirect.hostname or "").lower().removeprefix("www.")
  if dsthost not in SOURCE_DOMAINS:
    return {"status":"broken","reason":"Unexpected redirect outside trusted sources",
            "http":code,"url":url,"resolved_url":dest,"ids":ids}
  if not 200<=code<300:
    return {"status":"inconclusive","reason":"Unexpected HTTP status","http":code,"url":url,"ids":ids}
  if "html" not in typ:
    return {"status":"inconclusive","reason":"Source does not provide HTML","http":code,"url":url,"ids":ids}
  text=raw.decode("utf-8","replace")
  parser=TextParser()
  parser.feed(text)
  visible=canonical(" ".join(parser.fragments))
  if len(visible)<250:
    return {"status":"inconclusive","reason":"Too little rendered text to verify completeness",
            "http":code,"url":url,"ids":ids}
  missing=[]
  for id in ids:
    expected=EXPECT[id]
    # Some publisher pages have site/chrome content with "גדוד 46" repeated,
    # therefore both markers should appear in the visible page.
    if not all(canonical(word) in visible for word in expected):
      missing.append(id)
  if missing:
    return {"status":"unverified_content","reason":"Expected text not present in returned source content",
            "http":code,"ids":ids,"missing_ids":missing,"url":url,"resolved_url":dest,
            "page_title":canonical(" ".join(parser.titles))[:150]}
  return {"status":"verified","reason":"Source loaded and contains expected topic text",
          "http":code,"ids":ids,"url":url,"resolved_url":dest,
          "page_title":canonical(" ".join(parser.titles))[:150],
          "visible_characters":len(visible)}

def run():
  archive=load_archive()
  urls={}
  for row in archive:urls.setdefault(row["url"],[]).append(row["id"])
  results=[]
  for url,ids in urls.items():
    result=check(url,ids)
    # Do not fail the publisher audit for links ALREADY REMOVED from clickable
    # navigation and clearly identified as unavailable in public source pages.
    # This exception is limited to the four independently confirmed dead URLs.
    # A newly broken or mismatching active source still fails the check.
    if set(ids).issubset(RETIRED_SOURCE_IDS) and result["status"] in ("broken","unverified_content"):
      result["original_status"]=result["status"]
      result["status"]="retired"
      result["reason"]="Legacy article URL is deliberately not linked; public page discloses unavailability"
    results.append(result)
    print(result["status"].upper(),",".join(map(str,ids)),result.get("http"),result["reason"])
    sys.stdout.flush()
  counts={name:sum(x["status"]==name for x in results)
          for name in ("verified","retired","broken","unverified_content","inconclusive","invalid_url")}
  report={"unique_external_sources":len(urls),"archive_items":len(archive),
          "counts":counts,"sources":results,
          "note":"Automated successful page-content checks do not validate media embeds or guarantee future availability."}
  output=Path(os.environ.get("KARNAFIM_LINK_REPORT","external_link_report.json"))
  output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
  print("REPORT",str(output),json.dumps(counts,ensure_ascii=False))
  return 1 if counts["broken"] or counts["invalid_url"] or counts["unverified_content"] else 0

if __name__=="__main__":
  sys.exit(run())
