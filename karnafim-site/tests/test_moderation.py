"""Offline safety tests: no real API request or user file leaves the test runtime."""
import os
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import moderation_engine as m

def main():
    with patch.dict(os.environ,{},clear=True):
        assert m.moderate({"title":"הטנק שלנו","body":"סיפור מהשירות"},[]).status=="pending_ai"
        assert m.moderate({"title":"פנייה","body":"my-secret@example.org"},[]).status=="rejected"
        assert m.moderate({"title":"פרטי קשר","body":"מספר אישי 12345678"},[]).status=="rejected"
        assert m.moderate({"title":"טיול","body":"סיפור ללא פרטים מזהים"},[]).status=="pending_ai"
    good={"decision":"allow","confidence":0.995,"risk_flags":[],"reason_he":"נבדק"}
    assert m.parse_verdict(good,False,"test").status=="approved"
    assert m.parse_verdict(good,True,"test").status=="approved"
    low={"decision":"allow","confidence":0.6,"risk_flags":[],"reason_he":"לא בטוח"}
    assert m.parse_verdict(low,False,"test").status=="held"
    uncertain={"decision":"review","confidence":0.81,"risk_flags":["identifiable_people"],"reason_he":"אנשים בתמונה"}
    assert m.parse_verdict(uncertain,True,"test").status=="held"
    risky={"decision":"reject","confidence":0.995,"risk_flags":["pii"],"reason_he":"מספר טלפון"}
    assert m.parse_verdict(risky,False,"test").status=="rejected"
    with patch.dict(os.environ,{"KARNAFIM_GEMINI_API_KEY":"fake-test-key","KARNAFIM_AI_MODERATION":"on"}):
        with patch.object(m,"_request_json",return_value=good):
            assert m.moderate({"title":"סיפור","body":"חברים"},[]).status=="approved"
        with patch.object(m,"_request_json",side_effect=TimeoutError()):
            assert m.moderate({"title":"סיפור","body":"חברים"},[]).status=="pending_ai"
        with patch.object(m,"_request_json",return_value=uncertain):
            assert m.moderate({"title":"סיפור","body":"חברים"},[]).status=="held"
    print("PASS AI moderation: consented gate, PII, media, confidence, model failure, no-provider safety")

if __name__=="__main__":main()
