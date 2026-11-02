"""Grounded, sequential story beats for Hebrew WhatsApp narration.

This is a deliberately conservative lexical bridge, *not* a general Hebrew
translator. Its subject/action hints are only emitted for words explicitly
present in the original ASR. Unknown dialogue remains quoted in Hebrew for
the model instead of being silently substituted with an invented storyline.

The existing free AI-video providers can create only short clips. We retain
chronological clauses and proportional word-count timing; the result is still
labelled approximate and NEVER presented as a verbatim filmed reconstruction.
"""
from __future__ import annotations

import re
import math
from dataclasses import dataclass

HEBREW_WORD = re.compile(r"[א-ת]{2,}")
BOUNDARY = re.compile(
    r"(?<=[.!?;,])\s+|\b(?:ואז|לאחר\s+מכן|ואחר\s+כך|אחר\s+כך|ופתאום|פתאום)\b"
)
MAX_STORY_SCENES = 6
MAX_DURATION_SCENES = 24  # 5-second unique scenes can cover a 120s voice message

# All English hints below require explicit matching Hebrew action in the
# original clause. No background character/object is added without evidence.
ACTIONS = (
    (r"נ[וֹ]?ע[רׇ]|נוער|נוערת|נעירה|נָעַר", "a donkey brays with its mouth visibly opening"),
    (r"נובח|נובחת|נבח|נביחה", "a dog barks with visible mouth movement"),
    (r"מגיש|מגישה|הגיש|נותן|נותנת|מביא|מביאה", "offers or hands over an object"),
    (r"אוכל|אוכלת|אכל|אכלה|לועס|לועסת", "eats and chews"),
    (r"מ[שׂ]?ליך|משליכה|זורק|זורקת|זרק|זורקת", "throws an object with a visible arm motion"),
    (r"נשבר[הת]?|נשברת|שבר|מתנפץ|מתנפצת|נופצ[הת]?|רסיסים", "an object shatters into fragments"),
    (r"נופל|נופלת|נפל|נפלה|נופלים", "falls to the ground"),
    (r"מרים|מרימה|הרים|הרימה|מגביה", "lifts an object up"),
    (r"נוסע[הת]?|נסע[הת]?|נוהג|נוהגת", "drives along a road"),
    (r"רץ|רצה|רצים|רצות|ברח|בורח", "runs with real leg movement"),
    (r"הולך|הולכת|צועד|צועדת|צעד", "walks"),
    (r"צוחק|צוחקת|צחק|צחקה|צוחקים|מתפקע", "laughs visibly"),
    (r"בוכה|בוכים|בכה|בכתה|בכיתי", "cries visibly"),
    (r"רוקד|רוקדת|רוקדים|רקד|רקדה", "dances with body movement"),
    (r"שר|שרה|שרים|שרות|לשיר", "sings"),
    (r"נרגע|נרגעה|רגוע|רגועה", "becomes calm and relaxed"),
    (r"מכה|הכה|חובט|חובטת", "strikes an object"),
    (r"עף|עפה|עפים|טס|טסה", "flies through the air"),
    (r"מתפוצץ|התפוצץ|פיצוץ|מתפוצצת", "an explosion occurs"),
    (r"משפריץ|מתיז|מתיזה|התיז|שופך|שופכת|נשפך", "liquid splashes and flows"),
)
ACTORS = (
    (r"חמור|חמורה|חמורים", "a donkey"),
    (r"כלב|כלבה|כלבים", "a dog"),
    (r"חתול|חתולה|חתולים", "a cat"),
    (r"חקלאי|חקלאית|איכר|איכרה", "a farmer"),
    (r"ילד|ילדה|ילדים", "a child"),
    (r"תינוק|תינוקת", "a baby"),
    (r"איש|אישה|אדם|גבר|בחור|בחורה", "a person"),
    (r"משאית|משאיות|מסעית", "a truck"),
    (r"מכונית|אוטו|רכב", "a car"),
    (r"סוס|סוסה", "a horse"),
    (r"ציפור|יונה|עורב", "a bird"),
    (r"כוס|קוס", "a glass cup"),
)
OBJECTS = (
    (r"כוס|קוס", "a drinking glass"),
    (r"זכוכית|זחוכית", "glass"),
    (r"קש|חציר", "hay"),
    (r"קלשון|קילשון", "a pitchfork"),
    (r"רצפה|אדמה", "the ground"),
    (r"כביש|דרך", "a road"),
    (r"מים", "water"),
    (r"שמן", "oil"),
    (r"עץ|עצים", "a tree"),
    (r"דלת|שער", "a door or gate"),
    (r"בית|חדר", "a room or house"),
)
NEGATION = re.compile(r"(?:^|\s)(?:לא|בלי|אינו|אינה|אסור|לעולם\s+לא)\s*$")


@dataclass(frozen=True)
class StoryBeat:
    spoken_text: str
    english_hints: tuple[str, ...]
    word_count: int
    explicit_action: bool
    shot_index: int = 1
    shot_total: int = 1

    def as_dict(self):
        return {
            "spoken_text": self.spoken_text,
            "action_hints": list(self.english_hints),
            "spoken_words": self.word_count,
            "explicit_action": self.explicit_action,
        }


def _matches(pattern, text):
    """Match whole Hebrew words; allow the definite article and leading ו."""
    return re.search(r"(?<![א-ת])(?:ו?ה?)(?:" + pattern + r")(?![א-ת])", text) is not None


def _clause_hints(clause):
    actors = [english for word, english in ACTORS if _matches(word, clause)]
    objects = [english for word, english in OBJECTS if _matches(word, clause)]
    verbs = []
    for word,english in ACTIONS:
        # Find visible verbs only; a negated event must not become an imagined
        # depiction of the event. The Hebrew sentence itself is still included
        # so the model can respect the negation.
        match = re.search(r"(?<![א-ת])(?:ו?)(?:" + word + r")(?![א-ת])",clause)
        if match and not NEGATION.search(clause[max(0, match.start()-16):match.start()]):
            verbs.append(english)
    # Do not invent a performer from the previous scene when it is unclear
    # who "he"/"she" means.
    items = actors[:2] + verbs[:2] + objects[:3]
    return tuple(dict.fromkeys(items)),bool(verbs)


def _raw_clauses(transcript):
    clean=re.sub(r"[\x00-\x1f\x7f]", " ", str(transcript or ""))
    clean=re.sub(r"\s+", " ", clean).strip()[:4000]
    return [s.strip(" .,!?:;") for s in BOUNDARY.split(clean)
            if len(HEBREW_WORD.findall(s))>=2]


def narrative_beats(transcript, *, max_scenes=MAX_STORY_SCENES):
    """Chronologically group up to max_scenes without losing speech clauses.

    We never group clauses by keyword similarity (which would reorder events).
    If more clauses than public free-clip quota, consecutive clauses are
    combined in adjacent chronological chunks.
    """
    if not 1<=max_scenes<=MAX_DURATION_SCENES:
        raise ValueError("max_scenes must be 1..24")
    clauses=_raw_clauses(transcript)
    if not clauses:
        return []
    groups=[]
    if len(clauses)<=max_scenes:
        groups=[[clause] for clause in clauses]
    else:
        # Balanced contiguous groups, never discard the middle/last event.
        n=len(clauses)
        edges=[(i*n)//max_scenes for i in range(max_scenes+1)]
        groups=[clauses[edges[i]:edges[i+1]] for i in range(max_scenes)]
    result=[]
    for group in groups:
        phrase=". ".join(group)
        hints=[]
        has_action=False
        for clause in group:
            extra,action=_clause_hints(clause)
            hints.extend(extra)
            has_action=has_action or action
        result.append(StoryBeat(
            spoken_text=phrase,
            english_hints=tuple(dict.fromkeys(hints))[:7],
            word_count=max(1,len(HEBREW_WORD.findall(phrase))),
            explicit_action=has_action
        ))
    return result



def duration_beats(transcript, duration_seconds, *, max_scenes=MAX_DURATION_SCENES):
    """Allocate up to 24 genuinely new shots across the whole spoken duration.

    A long single clause can need multiple moving camera shots to fill its
    spoken time, but no new spoken event is invented: each shot stays on that
    SAME clause, using a different explicit camera perspective. This changes
    video generation prompts, not the original transcript or audio order.
    """
    beats=narrative_beats(transcript,max_scenes=max_scenes)
    if not beats:
        return []
    if not math.isfinite(float(duration_seconds)) or duration_seconds<=0:
        return beats
    desired=min(max_scenes,max(len(beats),int(math.ceil(duration_seconds/5.0))))
    if desired<=len(beats):
        return beats
    slots=[1]*len(beats)
    for _ in range(desired-len(beats)):
        index=max(range(len(beats)),
                  key=lambda i:(beats[i].word_count/slots[i],-i))
        slots[index]+=1
    expanded=[]
    for beat,count in zip(beats,slots):
        for index in range(count):
            expanded.append(StoryBeat(
                spoken_text=beat.spoken_text,
                english_hints=beat.english_hints,
                word_count=max(1,round(beat.word_count/count)),
                explicit_action=beat.explicit_action,
                shot_index=index+1,shot_total=count))
    return expanded

def scene_prompt(beat):
    """Give AI English grounding AND the actual Hebrew words in the same shot.

    Short, clear prompts perform better on tiny public inference quotas than
    a 1000+ character prompt to "make any event realistic".
    """
    if not isinstance(beat,StoryBeat):
        raise TypeError("scene_prompt expects a StoryBeat")
    contextual="; ".join(beat.english_hints)
    if not contextual:
        contextual="interpret only the following original Hebrew clause"
    # Same spoken moment may need multiple UNIQUE AI shots when narrated for
    # much longer than a single free GPU clip. Never create a new event.
    angles=(
        "Wide establishing live-action view of the stated actors and action",
        "Distinct medium tracking view with continuous visible physical movement",
        "Close-up moving view of the named actor and named physical action",
        "Different side angle, same event, visible physical progression",
        "Moving over-shoulder or ground-level camera, same action",
        "Distinct final reaction shot of only the named actors and action"
    )
    view=angles[(beat.shot_index-1)%len(angles)]
    continuity=(" This is camera view "+str(beat.shot_index)+
       " of "+str(beat.shot_total)+
       " for the SAME SPOKEN MOMENT, NOT a replay of existing video. "
       "Generate completely new footage with changed camera position. "
       if beat.shot_total>1 else " ")
    return (
        "Photorealistic moving live-action video, continuous physical action, "
        "realistic people and objects, natural motion. "
        "Camera direction: " + view + ". " + continuity +
        "Depict THIS ONE moment in the original Hebrew narration: "
        + beat.spoken_text + ". "
        "Verified words for context: " + contextual + ". "
        "Preserve who does what; respect negations. "
        "No unrelated events, on-screen text, subtitles, stills or waveforms."
    )[:1450]


def scene_prompts(transcript, *, max_scenes=None, duration=None):
    limit=max_scenes if max_scenes is not None else (
        MAX_DURATION_SCENES if duration is not None else MAX_STORY_SCENES)
    beats=(duration_beats(transcript,duration,max_scenes=limit)
           if duration is not None else narrative_beats(transcript,max_scenes=limit))
    return [scene_prompt(b) for b in beats]


def scene_weights(transcript, *, max_scenes=None, duration=None):
    limit=max_scenes if max_scenes is not None else (
        MAX_DURATION_SCENES if duration is not None else MAX_STORY_SCENES)
    beats=(duration_beats(transcript,duration,max_scenes=limit)
           if duration is not None else narrative_beats(transcript,max_scenes=limit))
    return [beat.word_count for beat in beats]
