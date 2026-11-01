"""Faithful, bounded Hebrew narration segmentation for actual AI video shots.

No generic word-halving, invented actions, actors, dialog, or summaries.
Two clips remain a free-community quota constraint, NOT a claim that two
one-second movies can faithfully portray a complex spoken narrative.

Scene continuity is only an auxiliary instruction based on nouns that occur
EXPLICITLY in the user's ASR text. Approximate scene timing is calculated by
the existing vocal energy aligner elsewhere; it is not forced word alignment.
"""
from __future__ import annotations
import re

HEBREW_WORDS = re.compile(r"[\u05d0-\u05ea]{2,}")
ACTORS = (
    ("חמור", ("חמור", "חמורה", "החמור", "החמורה", "חמורים")),
    ("חקלאי", ("חקלאי", "חקלאית", "החקלאי", "החקלאית")),
    ("כלב", ("כלב", "כלבה", "הכלב", "הכלבה", "כלבים")),
    ("משאית", ("משאית", "המשאית", "משאיות")),
    ("איש", ("איש", "האיש", "גבר", "הגבר", "בחור")),
    ("אישה", ("אישה", "האישה", "בחורה", "הבחורה")),
    ("ילד", ("ילד", "הילד", "ילדה", "הילדה")),
    ("סוס", ("סוס", "הסוס", "סוסים")),
    ("חתול", ("חתול", "החתול", "חתולה", "החתולה")),
    ("פרה", ("פרה", "הפרה", "פרות")),
    ("רכב", ("רכב", "הרכב", "מכונית", "המכונית", "אוטו")),
    ("תינוק", ("תינוק", "התינוק", "תינוקת", "התינוקת")),
)
# Standalone connectors indicate spoken chronological transitions.
# Preserve them in the following shot so the original account is auditable.
TRANSITION = re.compile(
    r"(?=\b(?:ואז|אחר\s+כך|ואחר\s+כך|לאחר\s+מכן|אחרי\s+זה|"
    r"פתאום|ולפתע|בהמשך|לבסוף)\b)"
)
CLAUSE_PUNCT = re.compile(r"(?<=[.!?;])\s+|[,،]\s+(?=(?:ואז|ואחר|אחר|פתאום|ולפתע|לאחר|לבסוף)\b)")
# Only distinct explicitly named subjects, not simple attached pronouns.
NEW_SUBJECT = re.compile(
    r"\s+(?=(?:והחקלאי|והחמור|והכלב|והמשאית|והאישה|והאיש|"
    r"והילד|והילדה|והסוס|והתינוק|והתינוקת)\b)"
)
MAX_TRANSCRIPT_LENGTH = 4000
MAX_SCENES = 2


def _actors_in(text):
    words=set(HEBREW_WORDS.findall(text))
    return [name for name,forms in ACTORS if words.intersection(forms)]


def _clauses(transcript):
    clean=re.sub(r"[\x00-\x1f\x7f]+"," ",str(transcript or ""))[:MAX_TRANSCRIPT_LENGTH]
    clean=re.sub(r"\s+"," ",clean).strip()
    if not clean:return []
    pieces=[]
    for sentence in CLAUSE_PUNCT.split(clean):
        for transition in TRANSITION.split(sentence):
            for part in NEW_SUBJECT.split(transition):
                value=part.strip(" ,؛;:।")
                if value and HEBREW_WORDS.search(value):
                    pieces.append(value)
    return pieces


def _words_count(text):
    return max(1,len(HEBREW_WORDS.findall(text)))


def plan_narration(transcript,max_scenes=MAX_SCENES):
    """Chronological, source-exact scene units, up to the supported clip quota.

    Returns {spoken, weight, continuity, original_parts}. Chronological cuts
    favor a genuine change of actor over an arbitrary equal number of words.
    Unknown/ambiguous pronouns stay unchanged; none are resolved by guessing.
    """
    if not 1<=max_scenes<=2:
        raise ValueError("supported video budget is one or two original shots")
    clauses=_clauses(transcript)
    if not clauses:return []
    if len(clauses)<=max_scenes:
        groups=[[value] for value in clauses]
    else:
        # A cut between intact spoken clauses, never in the middle of speech.
        weights=[_words_count(s) for s in clauses]
        total=sum(weights)
        cuts=[]
        previous_actors=[]
        for i in range(1,len(clauses)):
            left=sum(weights[:i]);right=total-left
            named=_actors_in(clauses[i])
            new_actor=bool(named and (not previous_actors or
                                      not set(named).issubset(set(previous_actors))))
            # A new named subject is a sensible fresh shot, provided both
            # resulting scenes keep a reasonable amount of spoken material.
            balance=1-abs(left-right)/max(1,total)
            quality=balance+(0.26 if new_actor and min(left,right)>=2 else 0)
            cuts.append((quality,i))
            previous_actors+=_actors_in(clauses[i-1])
        cut=max(cuts,key=lambda x:(x[0],-x[1]))[1]
        groups=[clauses[:cut],clauses[cut:]]
    result=[]
    previous_names=[]
    for group in groups:
        spoken=" ".join(group).strip()
        present=_actors_in(spoken)
        continuity=[name for name in previous_names if name not in present]
        # An already-named actor should only be reused for explicit pronouns.
        # If several actors could be 'he', never assert which one it is.
        pronouns=set(HEBREW_WORDS.findall(spoken)) & {
            "הוא","היא","אותו","אותה","לו","לה","שלו","שלה","עליו","עליה"}
        if len(previous_names)!=1 or not pronouns:
            continuity=[]
        result.append({"spoken":spoken,"weight":_words_count(spoken),
                       "continuity":continuity,"original_parts":len(group)})
        for name in present:
            if name not in previous_names:
                previous_names.append(name)
    return result


def scene_durations(audio_length,scenes):
    """Word-proportional fallback until vocal-activity alignment is available."""
    if not 1<=len(scenes)<=2:raise ValueError("invalid scene count")
    total=float(audio_length)
    if not 1<=total<=360:raise ValueError("invalid audio duration")
    weights=[max(1,int(s.get("weight",1))) for s in scenes]
    count=sum(weights)
    durations=[total*w/count for w in weights[:-1]]
    durations.append(total-sum(durations))
    return durations
