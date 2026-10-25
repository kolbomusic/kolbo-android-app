#!/usr/bin/env python3
"""Refresh a local CSV mirror of Israeli Chance draw results.

Preference: verify the official archive CSV endpoint, otherwise use the
attributed public third-party archive. Never fabricate an outcome.
Changes are additive, idempotent, and conflict-checked. All times are Israel local.
"""
import csv
import datetime as dt
import html
import io
import os
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "chance-data" / "chance-latest.csv"
SOURCE = ROOT / "chance-data" / "source.txt"
VALID = set(("7", "8", "9", "10", "J", "Q", "K", "A"))
HEADERS = {"User-Agent": "KolboChanceAI/1.1 (+https://github.com/kolbomusic/kolbo-android-app; research-only)", "Accept": "text/html,text/csv,*/*"}
SOURCES = [
    "https://www.pais.co.il/Chance/chance_resultsDownload.aspx",
    "https://www.pais.co.il/chance/chance_resultsDownload.aspx",
]
ARCHIVE = "https://hatulbul.com/chance/archive"
MIN_FRESH_ROWS = 10


def fetch(url):
    req = Request(url, headers=HEADERS)
    with urlopen(req, timeout=24) as response:
        content = response.read(4_000_000)
        if response.read(1):
            raise ValueError("Response exceeded size cap")
        encoding = response.headers.get_content_charset() or "utf-8"
        try:
            return content.decode(encoding)
        except UnicodeError:
            return content.decode("cp1255")


def normalize_rank(s):
    s = str(s).strip().upper().replace("\ufeff", "")
    if s in VALID:
        return s
    return {"11": "J", "12": "Q", "13": "K", "14": "A"}.get(s)


def result(row_id, date, cards):
    if not re.fullmatch(r"\d{4,9}", str(row_id)):
        return None
    cards = tuple(normalize_rank(c) for c in cards)
    if len(cards) != 4 or any(c not in VALID for c in cards):
        return None
    try:
        date = str(date).strip().split(" ")[0]
        day, mon, year = map(int, date.split("/"))
        d = dt.date(year, mon, day)
        if d > dt.date.today() + dt.timedelta(days=2) or d < dt.date(2000, 1, 1):
            return None
    except (ValueError, TypeError):
        return None
    return (str(row_id), date, *cards)


def official_csv(text):
    # Unlike Lotto, the official Chance CSV download URL has not been independently
    # confirmed. Accept it ONLY if it really returns suitable CSV columns and rows.
    if "<html" in text[:300].lower() or "<!doctype" in text[:300].lower():
        return []
    rows = list(csv.reader(io.StringIO(text.lstrip("\ufeff"))))
    if not rows:
        return []
    header = [h.strip().lower() for h in rows[0]]
    def find(name_variants):
        return next((i for i, cell in enumerate(header) if cell in name_variants), -1)
    columns = [find(("תלתן", "club", "clubs", "♣")),
               find(("יהלום", "diamond", "diamonds", "♦")),
               find(("לב", "heart", "hearts", "♥")),
               find(("עלה", "spade", "spades", "♠"))]
    id_col = find(("מספר הגרלה", "מס' הגרלה", "draw", "draw_id", "draw id"))
    date_col = find(("תאריך", "תאריך הגרלה", "date", "draw_date"))
    if -1 in columns or id_col < 0 or date_col < 0:
        return []
    out = []
    for cols in rows[1:]:
        if max(*columns, id_col, date_col) >= len(cols):
            continue
        v = result(cols[id_col], cols[date_col], [cols[c] for c in columns])
        if v:
            out.append(v)
    return out


class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.pieces = []
    def handle_data(self, data):
        if data.strip():
            self.pieces.append(data.strip())


def parse_archive(text):
    parser = TextExtractor()
    parser.feed(text)
    data = re.sub(r"\s+", " ", html.unescape(" ".join(parser.pieces)))
    # Each draw has a stable draw number, date, and four rank+suit pairs.
    chunks = re.split(r"(?=הגרלה\s*\d{4,9}\b)", data)
    parsed = []
    for chunk in chunks:
        start = re.match(r"הגרלה\s*(\d{4,9})\s*(\d{1,2}/\d{1,2}/\d{4})", chunk)
        if not start:
            continue
        rank_suit = re.findall(r"(10|[7-9JQKA])\s*([♠♥♦♣])", chunk[:240], re.IGNORECASE)
        if len(rank_suit) != 4 or len(set(suit for _, suit in rank_suit)) != 4:
            continue
        mapping = {suit: rank.upper() for rank, suit in rank_suit}
        item = result(start.group(1), start.group(2), [mapping[s] for s in ("♣", "♦", "♥", "♠")])
        if item:
            parsed.append(item)
    return parsed


def load_current():
    if not OUT.exists():
        return {}
    result_rows = {}
    with OUT.open(encoding="utf-8-sig", newline="") as f:
        for cols in list(csv.reader(f))[1:]:
            if len(cols) != 6:
                continue
            item = result(cols[0], cols[1], cols[2:])
            if item:
                result_rows[item[0]] = item
    return result_rows


def collect():
    for official in SOURCES:
        try:
            text = fetch(official)
            rows = official_csv(text)
            if len(rows) >= MIN_FRESH_ROWS:
                print("Found verified official CSV structure", official, len(rows))
                return rows, "מפעל הפיס — ארכיון צ׳אנס (CSV)"
            print("Official CSV URL returned non-CSV/unrecognized data:", official, len(rows))
        except Exception as error:
            print("Official endpoint unavailable:", official, str(error)[:130])
    combined = []
    for page in range(1, 5):
        url = ARCHIVE if page == 1 else ARCHIVE + "?page=" + str(page)
        try:
            text = fetch(url)
            rows = parse_archive(text)
            print("Alternative archive page", page, "parsed", len(rows))
            if not rows:
                if page == 1:
                    raise ValueError("No valid rows on first page")
                break
            combined.extend(rows)
        except Exception as error:
            if page == 1:
                raise
            print("Could not read older page", page, str(error)[:130])
            break
    return combined, "חתול בול — ארכיון צד שלישי, דורש אימות מול מפעל הפיס"


def main():
    incoming, provenance = collect()
    if len(incoming) < MIN_FRESH_ROWS:
        raise SystemExit("Refusing update: too few independently valid draw rows")
    original = load_current()
    merged = dict(original)
    added = 0
    for item in incoming:
        if item[0] in merged:
            if merged[item[0]][2:] != item[2:]:
                raise SystemExit("Source conflict for draw " + item[0] + ": previous CSV preserved")
            continue
        merged[item[0]] = item
        added += 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    temp = OUT.with_suffix(".csv.tmp")
    with temp.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["מספר הגרלה", "תאריך", "תלתן", "יהלום", "לב", "עלה"])
        for key in sorted(merged, key=int):
            w.writerow(merged[key])
    os.replace(temp, OUT)
    SOURCE.write_text(provenance + "\n" + dt.datetime.now(dt.timezone.utc).isoformat() + "\n", encoding="utf-8")
    print("Data updated:", len(merged), "records, new", added, "latest draw", max(map(int, merged)))


if __name__ == "__main__":
    main()
