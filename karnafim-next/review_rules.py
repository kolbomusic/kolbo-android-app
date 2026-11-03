"""Conservative first-pass triage for a private veterans' community.

This is NOT an AI classifier and never grants publication permission.
Human reviewers must verify military, personal and memorial claims.
"""
import re

SENSITIVE_PATTERNS=(
    (r"(?:\b\d{9}\b|\b05\d[- ]?\d{7}\b)", "ייתכן שמופיעים פרטי קשר או מספר מזהה אישי"),
    (r"(?:כתובת מגורים|מספר תעודת זהות|טלפון אישי)", "ייתכן שמופיע מידע אישי"),
    (r"(?:מיקום בזמן אמת|מיקום מדויק|מידע מסווג|סודי ביותר)", "נדרש בירור לגבי מידע ביטחוני או מיקום רגיש"),
    (r"(?:נפל בקרב|נהרג בקרב|חלל צה״ל|ז״ל)", "נדרש אימות פרטי הנצחה ממקור אמין"),
)

def triage(title, body, kind, media_count=0):
    """Return (risk_level, reason) without inspecting or retaining private media."""
    text=(title+" "+body)[:4500]
    notes=[]
    for pattern, reason in SENSITIVE_PATTERNS:
        if re.search(pattern,text,re.IGNORECASE):
            notes.append(reason)
    if media_count:
        notes.append("קובצי מדיה מחייבים בדיקת זכויות, פרטיות ותוכן")
    if kind=="event":
        notes.append("יש לבדוק פרטי אירוע ומיקום לפני פרסום")
    if notes:
        return "review", "; ".join(dict.fromkeys(notes))
    return "standard", "התקבלה לבדיקה. לא נמצאו סימני סיכון בסיסיים בטקסט; עדיין נדרש אישור מנהל."
