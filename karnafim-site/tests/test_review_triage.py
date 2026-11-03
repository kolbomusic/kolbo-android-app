"""Reviewer-assist triage does not publish, call networks or decide identities."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from review_triage import review_hints

routine=review_hints("חוויות מחזור", "סיפור קצר מאימון בשטח", "story")
assert routine.priority=="רגילה"
assert routine.manual_confirmation is False
assert routine.reasons==()

media=review_hints("הקלטת זיכרון","", "voice", ["audio"])
assert media.manual_confirmation and any("זכויות שימוש" in x for x in media.reasons)

fallen=review_hints("לזכר יוני שרעבי", "חברנו נפל בקרב", "story")
assert fallen.manual_confirmation
assert any("חללים" in x for x in fallen.reasons)

privacy=review_hints("חברים","פנו אלי בכתובת person@example.com", "story")
assert privacy.manual_confirmation
assert all("person@example.com" not in x for x in privacy.reasons)

link=review_hints("מקור זיכרון", "https://example.org/photo", "story")
assert link.manual_confirmation
assert any("מקור חיצוני" in x for x in link.reasons)
assert len(link.reasons)<=4

print("PASS: private local reviewer hints and mandatory human review for sensitive posts")
