"""Offline regression checks for pre-publication triage."""
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from review_rules import triage

level,note=triage("טיול הפלוגה","זיכרון מהאימונים","story")
assert level=="standard" and "אישור מנהל" in note
level,note=triage("זיכרון לחבר ז״ל","סיפור מהשירות","story")
assert level=="review" and "הנצחה" in note
level,note=triage("אירוע מחזור","ניפגש בקרוב","event")
assert level=="review" and "אירוע" in note
level,note=triage("צילום משותף","תמונות מתקופת השירות","photo",2)
assert level=="review" and "מדיה" in note
level,note=triage("סיפור","מספר תעודת זהות 123456789","story")
assert level=="review" and "אישי" in note
assert triage("זיכרון","פרסום רגיל","story")[0]!="published"
print("PASS: conservative triage and memorial/privacy safeguards")
