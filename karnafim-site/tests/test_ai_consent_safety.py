"""Verify optional AI moderation cannot leak private content or publish media."""
import os
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import moderation_engine as engine

safe={"title":"זיכרונות מהטירונות","body":"אירוע חביב משירותי","post_type":"story"}
blocked=engine.moderate(safe,[])
assert blocked.status=="held" and not blocked.attempted
os.environ["KARNAFIM_AI_MODERATION"]="on"
os.environ["KARNAFIM_GEMINI_API_KEY"]="synthetic-test-key-NO-OUTBOUND"
assert engine.moderate(safe,[]).status=="held"  # still no consent
assert not engine.moderate(safe,[]).attempted

sensitive=dict(safe,title="לזכר יוני שרעבי",ai_consent=True)
assert engine.moderate(sensitive,[]).status=="held"
assert not engine.moderate(sensitive,[]).attempted

photo=dict(safe,ai_consent=True,post_type="photo")
assert engine.moderate(photo,[]).status=="held"
assert not engine.moderate(photo,[]).attempted

clean_allow={"decision":"allow","confidence":0.99,"risk_flags":[],"reason_he":"תקין"}
assert engine.parse_verdict(clean_allow,False,"synthetic").status=="approved"
assert engine.parse_verdict(clean_allow,True,"synthetic").status=="held"
unsafe={"decision":"reject","confidence":0.99,"risk_flags":["pii"],"reason_he":"רגיש"}
assert engine.parse_verdict(unsafe,True,"synthetic").status=="held"
assert engine.parse_verdict(unsafe,False,"synthetic").status=="rejected"
try:
    engine.parse_verdict({"decision":"allow","confidence":"99%","risk_flags":[]},False,"synthetic")
except ValueError:
    pass
else:
    raise AssertionError("Invalid verdict accepted")
print("PASS: consent is mandatory, no unsafe media review, no AI network calls")
