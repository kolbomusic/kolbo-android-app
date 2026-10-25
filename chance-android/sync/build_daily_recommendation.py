#!/usr/bin/env python3
"""Build daily educational Chance card-frequency snapshots.

Only historical counts, NEVER claims of improved next-draw odds.
Runs as standard-library Python in the daily public GitHub Actions workflow.
Public JSON is a PROTOTYPE and must not be treated as a paid-access feed.
"""
import csv
import datetime as dt
import json
from collections import Counter
from itertools import combinations
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
CSV = ROOT / "chance-data" / "chance-latest.csv"
JSON = ROOT / "chance-data" / "daily-recommendation.json"
TEXT = ROOT / "chance-data" / "daily-whatsapp.txt"
RANKS = frozenset(("7", "8", "9", "10", "J", "Q", "K", "A"))
SUITS = ("♣", "♦", "♥", "♠")
SCHEDULE = {
    0: ("09:00","11:00","13:00","15:00","17:00","19:00","21:00"),
    1: ("09:00","11:00","13:00","15:00","17:00","19:00","21:00"),
    2: ("09:00","11:00","13:00","15:00","17:00","19:00","21:00"),
    3: ("09:00","11:00","13:00","15:00","17:00","19:00","21:00"),
    4: ("10:00","12:00","14:00"),
    5: ("21:30","23:30"),
    6: ("09:00","11:00","13:00","15:00","17:00","19:00","21:00"),
}

def load_rows():
    if not CSV.exists():
        raise ValueError("Historical CSV unavailable")
    rows = {}
    with CSV.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        for row in reader:
            try:
                draw_id = int(row["מספר הגרלה"])
                values = [row[name].strip().upper() for name in ("תלתן", "יהלום", "לב", "עלה")]
                date = dt.datetime.strptime(row["תאריך"].strip(), "%d/%m/%Y").date()
                if draw_id<=0 or not all(v in RANKS for v in values):
                    continue
                value = (draw_id, date, values)
                if draw_id in rows and rows[draw_id][2] != values:
                    raise ValueError("Conflicting historical outcome for draw " + str(draw_id))
                rows[draw_id] = value
            except (KeyError, TypeError, ValueError) as err:
                if "Conflicting" in str(err):
                    raise
                continue
    ordered = sorted(rows.values(), key=lambda row: row[0])
    if len(ordered)<40:
        raise ValueError("At least 40 verified rows required")
    return ordered

def find_top(rows, size):
    counts = Counter()
    for _, _, values in rows:
        for indexes in combinations(range(4), size):
            token = tuple((i, values[i]) for i in indexes)
            counts[token] += 1
    # Sort by frequency then deterministic suit/rank order.
    best, count = sorted(counts.items(), key=lambda p: (-p[1], p[0]))[0]
    picks=[{"suit": SUITS[i], "rank":rank, "suit_index":i} for i,rank in best]
    return {
        "cards": picks,
        "label": " + ".join(p["rank"] + p["suit"] for p in picks),
        "historical_hits": count,
        "sample_draws": len(rows),
        "historical_rate_percent": round(count / len(rows) * 100, 2),
        "probability_one_draw": {"numerator":1,"denominator":8**size},
        "expected_hits_for_fixed_combination": round(len(rows)/(8**size), 2),
    }

def main():
    now=dt.datetime.now(ZoneInfo("Asia/Jerusalem"))
    rows=load_rows()
    window=rows[-min(200,len(rows)):]
    last_id, last_date, _ = rows[-1]
    # Do not claim fresh picks if the historical sample is seriously stale.
    age=(now.date()-last_date).days
    if age > 5:
        raise SystemExit("Last draw is %s days old; refusing daily new recommendations" % age)
    pair=find_top(window,2)
    triple=find_top(window,3)
    date=now.date().isoformat()
    schedule=list(SCHEDULE[now.weekday()])
    text=[
        "🃏 צ'אנס נכנס | סקירת נתוני עבר",
        "📅 תאריך: " + now.strftime("%d/%m/%Y") + " (שעון ישראל)",
        "♣ זוג שכיח היסטורית: " + pair["label"],
        "📊 " + str(pair["historical_hits"]) + " מתוך " + str(pair["sample_draws"]) + " הגרלות שנבדקו",
        "♠ שלשה שכיחה היסטורית: " + triple["label"],
        "📊 " + str(triple["historical_hits"]) + " מתוך " + str(triple["sample_draws"]) + " הגרלות שנבדקו",
        "🕐 שעות סגירת מכירה רגילות היום: " + (", ".join(schedule) if schedule else "לא נקבעו"),
        "⚠️ אין בנתונים תחזית או הבטחת זכייה; לכל זוג מוגדר סיכוי של 1 ל־64 בכל הגרלה הוגנת.",
        "לוח הזמנים עשוי להשתנות בחגים. השתתפות בהגרלה לבני 18+ בלבד.",
    ]
    payload={
        "schema_version":1,
        "kind":"historical-frequency-not-prediction",
        "date_israel":date,
        "generated_at_israel":now.isoformat(timespec="seconds"),
        "valid_until_date_israel":date,
        "draw_times_local":schedule,
        "draw_times_are_sales_closing_times":True,
        "data_source":"External archive attributed in chance-data/source.txt; verify against pais.co.il",
        "last_recorded_draw":{"id":last_id,"date":last_date.isoformat()},
        "historical_window":len(window),
        "pair":pair,
        "triple":triple,
        "whatsapp_draft":"\n".join(text),
        "disclaimer_he":"דירוג שכיחות היסטורית בלבד. אין ראיה שהוא משפר הסתברות לזכייה; אין התחייבות או המלצת סכום הימור.",
        "is_public_preview":True,
    }
    JSON.parent.mkdir(parents=True, exist_ok=True)
    JSON.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    TEXT.write_text(payload["whatsapp_draft"]+"\n",encoding="utf-8")
    print("Published historical recommendations",date,"sample",len(window),"last draw",last_id, "age days",age)

if __name__=="__main__":
    main()
