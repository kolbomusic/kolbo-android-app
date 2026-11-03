"""Local, deterministic hints for human moderators.

Never calls an AI provider, never publishes, rejects or changes any database
records, and never guesses whether a person in a photograph is a fallen soldier.
"""
from dataclasses import dataclass
import re


@dataclass(frozen=True)
class ReviewHints:
    priority: str
    reasons: tuple[str, ...]
    manual_confirmation: bool


EMAIL = re.compile(r"[\w.+-]+@[\w.-]+\.[a-z]{2,}", re.I)
PHONE = re.compile(r"(?<!\d)(?:\+972|05[0-9])[-\s]?(?:\d[-\s]?){7,9}(?!\d)")
PERSONAL = re.compile(r"(?:כתובת מגורים|תעודת זהות|מספר אישי|מס[׳']? אישי|סיסמה|כתובת פרטית)", re.I)
MEMORIAL = re.compile(r"(?:הנצחה|חלל(?:ים)?|נפל(?:ו)?\s+בקרב|נהרג(?:ו)?|שרעבי|גרוסמן|ריין|בונימוביץ|אדם גורן)", re.I)
EXTERNAL_LINK = re.compile(r"(?:https?://|www\.)", re.I)


def review_hints(title: str, body: str, kind: str, media_kinds=()) -> ReviewHints:
    """Explain why a reviewer needs extra verification, without leaking PII."""
    text = str(title or "") + " " + str(body or "")
    reasons = []
    if EMAIL.search(text) or PHONE.search(text) or PERSONAL.search(text):
        reasons.append("פרטים אישיים: לבדוק הסכמה ולהסיר פרטי קשר רגישים")
    if MEMORIAL.search(text):
        reasons.append("טענות על חללים או הנצחה: לאמת מול מקורות רשמיים ועדויות")
    if kind != "story" or tuple(media_kinds):
        reasons.append("מדיה או תוכן שאינו סיפור רגיל: לאמת זהות מצולמים וזכויות שימוש")
    if EXTERNAL_LINK.search(text):
        reasons.append("מקור חיצוני: לוודא קישור, אמינות והרשאת שימוש")
    return ReviewHints(
        priority="גבוהה" if reasons else "רגילה",
        reasons=tuple(reasons),
        manual_confirmation=bool(reasons),
    )
