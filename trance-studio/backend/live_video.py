"""Grounded action-to-live-footage engine.

Unlike the legacy emoji/cartoon renderer, this exporter accepts only *actual*
motion video from a licensed source. It never overlays subtitles and does
not invent a scene when a spoken action can't be matched safely.
"""
from __future__ import annotations
import json
import os
import re
import subprocess
import tempfile
import urllib.parse
import urllib.request
import urllib.error
from pathlib import Path

COMMONS_API="https://commons.wikimedia.org/w/api.php"
# Resource budget for the free worker, not a cap on spoken sentences.
MAX_VISUAL_BEATS=18
MAX_BYTES=22*1024*1024
USER_AGENT="KolboTranceStudio/1.9 (personal noncommercial story builder; contact https://kolbomusic.com)"
# Explicit conjunctions of a subject and action, not substring matches.
# "לבוא" must NEVER be treated as "לב"/love. Unknown scenes fail closed.
ACTIONS=(
    ("donkey_bray",("חמור","חמורה"),("נוער","נעירה","צורח","צועק","צועקת"),"donkey braying"),
    ("dog_bark",("כלב","כלבה"),("נובח","נביחות","נובחת"),"dog barking"),
    ("cat_eat",("חתול","חתולה"),("אוכל","אוכלת","אכלה"),"cat eating"),
    ("car_drive",("אוטו","מכונית","רכב"),("נסעתי","נוסע","נוסעת","נסיעה","נוסעים","נוהג","נהג"),"car driving"),
    ("truck_drive",("משאית","מנוף"),("נוסע","נוסעת","נהג","נוהג","נסעתי"),"truck driving"),
    ("horse_run",("סוס","סוסים"),("רץ","רצים","רצה","דהר","דוהר"),"horse running"),
    ("farmer_feed",("חקלאי","חקלאית"),("מאכיל","מאכילה","מגיש","מגישה","נותן","נותנת"),"farmer feeding animals"),
    ("person_run",("איש","אישה","בחור","ילד","אני"),("רצתי","רץ","רצה","רצים","רצה"),"person running"),
    ("person_dance",("רוקד","רוקדת","רקדנו","ריקוד","רוקדים"),("מסיבה","רוקד","רוקדת","רקדנו","ריקוד","רוקדים"),"people dancing"),
    ("swim",("שוחה","שוחים","שחיתי","שוחה"),("ים","בריכה","מים","שחיתי","שוחים"),"people swimming"),
    ("rain",("גשם","גשמים"),("יורד","ירד","מטפטף","גשם"),"rain falling"),
    ("pizza_eat",("פיצה",),("אכלתי","אוכל","אוכלת","לאכול","אכלה","אכלנו"),"person eating pizza"),
    ("beach_walk",("ים","חוף"),("הלכתי","הולך","הולכים","טיילתי","מטייל"),"person walking beach"),
    ("hug",("חיבוק","חיבק","חיבקתי","מחבק","מחבקת"),("חיבוק","חיבק","חיבקתי","מחבק","מחבקת"),"people hugging"),
    ("donkey_eat",("חמור","חמורה","חמורים"),("אוכל","אוכלת","אכל","אכלה","לועס","לועסת"),"donkey eating"),
    ("dog_run",("כלב","כלבה","כלבים"),("רץ","רצה","רצים","רצות"),"dog running"),
    ("bird_fly",("ציפור","ציפורים","יונה","עורב"),("עפה","עף","עפים","עפות","עופפת","טסה"),"bird flying"),
    ("baby_cry",("תינוק","תינוקת","פעוט","פעוטה"),("בוכה","בוכים","בכיתי","בכה","בכתה"),"baby crying"),
    ("person_laugh",("איש","אישה","בחור","בחורה","ילד","ילדה","אני","אנחנו"),("צוחק","צוחקת","צחק","צחקה","צחקתי","צוחקים"),"person laughing"),
    ("person_cry",("איש","אישה","בחור","בחורה","ילד","ילדה","אני"),("בוכה","בוכים","בכיתי","בכה","בכתה"),"person crying"),
    ("person_sing",("איש","אישה","בחור","בחורה","ילד","ילדה","אני","אנחנו"),("שר","שרה","שרים","שרות","לשיר","שרתי","שרנו"),"person singing"),
    ("person_cook",("טבח","טבחית","איש","אישה","אמא","אבא","אני"),("מבשל","מבשלת","בישל","בישלה","אופה","מטגן"),"person cooking"),
)
# Explicit subject-only visuals: only if the utterance names an actual place
# and no distinct unsupported action. Avoid interpreting "לבוא" as "love".
VISUAL_LOCATIONS=(
    ("sea",("ים","חוף"),"ocean waves"),
    ("house",("בית","הביתה"),"house exterior"),
    ("forest",("יער","עצים"),"forest trees moving"),
)
# When no visible action is named, prepare a real moving shot of an
# EXPLICITLY mentioned subject. This is thematic coverage, not an invented
# action, and must be labeled partial in the finished movie.
SUBJECT_VISUALS=(
    ("donkey",("חמור","חמורה","חמורים"),"donkey"),
    ("dog",("כלב","כלבה","כלבים"),"dog"),
    ("cat",("חתול","חתולה","חתולים"),"cat"),
    ("car",("רכב","מכונית","אוטו","מכוניות"),"car"),
    ("truck",("משאית","מנוף","משאיות"),"truck"),
    ("horse",("סוס","סוסים"),"horse"),
    ("farmer",("חקלאי","חקלאית"),"farmer"),
    ("cow",("פרה","פרות"),"cow"),
    ("bird",("ציפור","ציפורים","יונה","עורב"),"bird"),
    ("baby",("תינוק","תינוקת","פעוט","פעוטה"),"baby"),
    ("police",("שוטר","שוטרים","משטרה"),"police"),
    ("fire",("אש","שריפה","להבות"),"fire"),
    ("food",("פיצה","אוכל","ארוחה"),"food"),
    ("water",("מים","נהר","נחל"),"river"),
    ("city",("רחוב","עיר","כביש"),"street"),
    ("house",("בית","דירה"),"house"),
    ("beach",("ים","חוף"),"beach"),
)
CLAUSE_SPLIT=re.compile(
    r"[.!?;,]+|\b(?:ואז|ואחר כך|אחר כך|לאחר מכן|אחרי זה|פתאום|ולפתע|בינתיים)\b"
    r"|\s+(?=(?:ו)?(?:החקלאי|החמור|הכלב|החתול|המשאית|הסוס|האישה|האיש|האוטו|הילד|התינוק|התינוקת|הציפור|הטבח)\b)"
)
HEBREW_TOKEN=re.compile(r"[א-ת]+")
NEGATIONS={"לא","בלי","אינו","אינה","אינם","אין"}
class UnavailableVideo(RuntimeError):pass

def _words(sentence):
    raw=HEBREW_TOKEN.findall(sentence)
    # Hebrew attached prepositions/articles: "בים" means "ים", but do not
    # run fuzzy substring matching (e.g. "לבוא" != "לב"/love).
    known=set()
    for _,subjects,verbs,_ in ACTIONS:
        known.update(subjects);known.update(verbs)
    for _,items,_ in VISUAL_LOCATIONS:known.update(items)
    for _,items,_ in SUBJECT_VISUALS:known.update(items)
    normalized=[]
    for token in raw:
        normalized.append(token)
        if len(token)>=3 and token[0] in "ובלהמכ" and token[1:] in known:
            normalized.append(token[1:])
        if len(token)>=4 and token[:2] in ("וב","וה","ול","מה","בה","לה"):
            if token[2:] in known:normalized.append(token[2:])
    return normalized

def _positive_clause(tokens):
    # Doesn't visualize negated actions as if they occurred.
    return not any(t in NEGATIONS for t in tokens)

def _asr_spelling_neighbor(token, expected):
    """Bounded Hebrew spelling tolerance ONLY alongside an exact spoken verb.

    This does not replace or rewrite the transcript. A base-sized Whisper
    frequently returns e.g. "המסעית נוסעת" for "המשאית נוסעת". Only
    longer, near-identical actor nouns are considered; no generic topic guess.
    """
    if len(expected)<5 or len(token)<5:
        return False
    variants=(expected, "ה"+expected, "ו"+expected, "וה"+expected)
    for variant in variants:
        if abs(len(token)-len(variant))>2:
            continue
        distance=list(range(len(variant)+1))
        for i,left in enumerate(token,1):
            next_distance=[i]
            for j,right in enumerate(variant,1):
                next_distance.append(min(
                    next_distance[-1]+1, distance[j]+1,
                    distance[j-1]+(left!=right)))
            distance=next_distance
        if distance[-1]<=2 and min(len(token),len(variant))>=6:
            return True
    return False

def action_for_clause(sentence):
    words=_words(sentence)
    if not words or not _positive_clause(words):return None
    tokens=set(words)
    candidates=[]
    for name,subjects,verbs,query in ACTIONS:
        if tokens.intersection(subjects) and tokens.intersection(verbs):
            candidates.append({"action":name,"query":query,"basis":"subject_and_action"})
    if len(candidates)>1:
        # The sentence contains multiple physical actions. Guessing just the
        # first one creates a false story for everything else. Surface this
        # as ambiguous until a real semantic planner can split it reliably.
        raise UnavailableVideo(
            "במשפט זוהו כמה פעולות שלא ניתן להפריד ביניהן באופן אמין. "
            "לא ייווצר סרטון לא תואם.")
    if candidates:return candidates[0]
    # Whisper base struggles with Hebrew actor nouns (e.g. משאית/מסעית).
    # Only use phonetic spelling recovery when the VERB is exact and one
    # unambiguous named physical actor is near the original recognized token.
    repaired=[]
    for name,subjects,verbs,query in ACTIONS:
        if not tokens.intersection(verbs):
            continue
        if any(_asr_spelling_neighbor(token,actor)
               for token in words for actor in subjects):
            repaired.append({"action":name,"query":query,
                             "basis":"asr_spelling_approximation"})
    if len(repaired)==1:
        return repaired[0]
    for name,terms,query in VISUAL_LOCATIONS:
        if tokens.intersection(terms) and len(tokens)<=6:
            return {"action":name,"query":query,"basis":"explicit_location"}
    # No hallucinated action: we may show a named animal/object as motion
    # footage, but its presence alone does not prove what it was doing.
    for name,terms,query in SUBJECT_VISUALS:
        if tokens.intersection(terms):
            return {"action":"subject_"+name,"query":query,
                    "basis":"explicit_subject_only"}
    return None

def visual_plan(transcript,duration):
    """Extract grounded visual beats from the FULL speech transcript.

    Long Hebrew recordings may have dozens of Whisper punctuation segments.
    Sentence count is never a reason to reject the entire video.
    Unsupported speech is retained in transcript/timing and counted honestly.
    Nearby identical actions are merged to avoid repeatedly downloading clips.
    A strictly bounded number of independent footage requests protects the
    free worker, while the complete speech audio always remains intact.
    """
    transcript=str(transcript or "").strip()
    clauses=[x.strip() for x in CLAUSE_SPLIT.split(transcript) if x.strip()]
    if not clauses:
        raise UnavailableVideo("לא זוהו משפטים בדיבור לצורך התאמת הסרטון")
    duration=float(duration)
    if not 0.5<=duration<=360:
        raise UnavailableVideo("משך הווידאו אינו תקין")
    # Retain the complete transcript. Every clause contributes time. Only
    # actual named actions may determine a source video.
    beats=[]
    unmatched=0
    pending=[]
    for clause in clauses:
        try:
            found=action_for_clause(clause)
        except UnavailableVideo:
            # An ambiguous phrase must not cancel clear events later in the
            # same original recording. Retain its words and flag partial coverage.
            found=None
        if not found:
            unmatched+=1
            if beats:
                beats[-1]["spoken"].append(clause)
            else:
                pending.append(clause)
            continue
        if beats and beats[-1]["action"]==found["action"]:
            beats[-1]["spoken"].append(clause)
        else:
            spoken=pending+[clause]
            pending=[]
            beats.append({**found,"spoken":spoken})
    if not beats:
        raise UnavailableVideo(
            "לא נמצאה בהקלטה פעולה שאפשר להציג בווידאו מצולם שתואם לדיבור.")
    # The ASR may return dozens of separate phrases. Coalesce to a bounded
    # number of visual beats instead of rejecting everything after five.
    original_beats=len(beats)
    if len(beats)>MAX_VISUAL_BEATS:
        groups=[]
        for idx,beat in enumerate(beats):
            pos=min(MAX_VISUAL_BEATS-1,idx*MAX_VISUAL_BEATS//len(beats))
            if pos==len(groups):
                groups.append({**beat,"spoken":list(beat["spoken"])})
            else:
                # Keep representative matching footage but include all the
                # skipped speech in the timeline and report partial coverage.
                groups[pos]["spoken"].extend(beat["spoken"])
        beats=groups
    lengths=[max(1,sum(len(_words(t)) for t in beat["spoken"]))
             for beat in beats]
    total=sum(lengths)
    cumulative=0.
    scenes=[]
    for i,(beat,length) in enumerate(zip(beats,lengths)):
        start=cumulative
        cumulative+=duration*length/total
        scenes.append({"start":round(start,3),
                       "end":round(duration if i==len(beats)-1 else cumulative,3),
                       "action":beat["action"],
                       "query":beat["query"],
                       "basis":beat["basis"],
                       "caption":"",
                       "spoken":" ".join(beat["spoken"])})
    return {
        "source":"automatic_transcript_grounded_longform",
        "transcript":transcript,
        "total_clauses":len(clauses),
        "unmatched_clauses":unmatched,
        "recognized_action_beats":original_beats,
        "visual_beats":len(scenes),
        "visual_coverage":"partial" if (unmatched or original_beats>len(scenes)
                         or any(sc["basis"] in ("explicit_subject_only",
                                              "asr_spelling_approximation") for sc in scenes))
                         else "matched",
        "scenes":scenes
    }

def _json_api(params):
    url=COMMONS_API+"?"+urllib.parse.urlencode(params)
    request=urllib.request.Request(url,headers={"User-Agent":USER_AGENT,
                                                  "Accept":"application/json"})
    with urllib.request.urlopen(request,timeout=16) as response:
        raw=response.read(180000)
    return json.loads(raw)

def _valid_license(metadata):
    values=metadata or {}
    license_code=str(values.get("LicenseShortName",{}).get("value","")).lower()
    # Only unambiguously reusable CC0 / public domain / CC-BY / CC-BY-SA.
    return (license_code in {"cc0","public domain","pd","cc by 4.0",
             "cc by-sa 4.0","cc by 3.0","cc by-sa 3.0","cc by 2.0",
             "cc by-sa 2.0","cc-by-4.0","cc-by-sa-4.0",
             "cc-by-3.0","cc-by-sa-3.0","cc-by-2.0","cc-by-sa-2.0"})

def _matches_metadata(title,query):
    title=title.lower().replace("_"," ").replace("-"," ")
    # A motion clip must depict an actual event. Reject animated mockups,
    # stock intros, gameplay, incorrect scene specifics and diagrams.
    forbidden=("animation","cartoon","simulator","simulation","gameplay",
               "computer generated","cgi","3d model","slideshow",
               "wrong side","wrong way")
    if any(x in title for x in forbidden):return False
    keywords=query.lower().split()
    # Preserve the actor and the action without depending on word order
    # or inflection ("braying donkey" is valid for "donkey braying").
    aliases={"braying":("braying","bray","brays","brayed"),
             "driving":("driving","drives","drive"),
             "dancing":("dancing","dance","dances"),
             "falling":("falling","falls","fall"),
             "eating":("eating","eats","eat"),
             "walking":("walking","walks","walk"),
             "barking":("barking","barks","bark"),
             "feeding":("feeding","feeds","feed"),
             "swimming":("swimming","swims","swim"),
             "laughing":("laughing","laughs","laugh","laughed"),
             "crying":("crying","cries","cry","cried"),
             "singing":("singing","sings","sing","sang"),
             "cooking":("cooking","cooks","cook"),
             "flying":("flying","flies","fly"),
             "running":("running","runs","run")}
    return all(any(word in title for word in aliases.get(token,(token,)))
               for token in keywords)

def commons_candidates(query):
    # A narrow, title-validated search is deliberately preferred over generic
    # relevant-looking footage that does not show the *spoken action*.
    terms=query.lower().split()
    searches=[query]
    if len(terms)==2:
        searches.append(" ".join(reversed(terms)))
    if query=="donkey braying":
        searches.append("braying donkey")
    matches=[]
    seen=set()
    for search_text in dict.fromkeys(searches):
        data=_json_api({"action":"query","generator":"search",
                        "gsrsearch":'filetype:video '+search_text,
                        "gsrnamespace":6,"gsrlimit":30,
                        "prop":"imageinfo","iiprop":"url|mime|size|extmetadata",
                        "format":"json","formatversion":2})
        for page in data.get("query",{}).get("pages",[]):
            if not _matches_metadata(page.get("title",""),query):continue
            info=(page.get("imageinfo") or [{}])[0]
            mime=str(info.get("mime",""))
            size=int(info.get("size",0))
            url=str(info.get("url",""))
            if mime not in ("video/webm","video/ogg","application/ogg"):continue
            if size<10000 or size>MAX_BYTES:continue
            if not _valid_license(info.get("extmetadata",{})):continue
            parsed=urllib.parse.urlparse(url)
            if parsed.scheme!="https" or parsed.netloc not in (
                "upload.wikimedia.org","commons.wikimedia.org"):continue
            if url in seen:continue
            seen.add(url)
            matches.append({"url":url,"title":page["title"],"bytes":size,
                            "page":"https://commons.wikimedia.org/wiki/"+
                                urllib.parse.quote(page["title"].replace(" ","_")),
                            "license":info["extmetadata"].get("LicenseShortName",{}).get("value","")})
    return matches

def _candidate_urls(item):
    original=item["url"]
    parsed=urllib.parse.urlparse(original)
    if (parsed.scheme=="https" and parsed.netloc=="upload.wikimedia.org"
        and "/wikipedia/commons/" in parsed.path and
        parsed.path.lower().endswith(".webm")):
        # Wikimedia already publishes low-bitrate VP9 360p transcodes for
        # many files. Using one avoids exhausting Render's tiny CPU by
        # decoding an original 1080p upload, and limits outgoing MP4 size.
        fragment=parsed.path.split("/wikipedia/commons/",1)[1]
        name=fragment.rsplit("/",1)[-1]
        base="https://upload.wikimedia.org/wikipedia/commons/transcoded/"
        yield base+fragment+"/"+name+".360p.vp9.webm"
    yield original

def download_video(item,dest):
    errors=[]
    for source_url in _candidate_urls(item):
        request=urllib.request.Request(source_url,headers={"User-Agent":USER_AGENT})
        try:
            count=0
            with urllib.request.urlopen(request,timeout=22) as response,open(dest,"wb") as file:
                url=urllib.parse.urlparse(response.geturl())
                if url.scheme!="https" or url.hostname not in (
                    "upload.wikimedia.org","commons.wikimedia.org"):
                    raise UnavailableVideo("מקור וידאו לא מורשה")
                while True:
                    data=response.read(65536)
                    if not data:break
                    count+=len(data)
                    if count>MAX_BYTES:raise UnavailableVideo("סרטון המקור גדול מדי")
                    file.write(data)
            if count<10000:raise UnavailableVideo("סרטון המקור חסר")
            return
        except (OSError,urllib.error.URLError,UnavailableVideo) as err:
            Path(dest).unlink(missing_ok=True)
            errors.append(type(err).__name__)
    raise UnavailableVideo("לא ניתן להוריד וידאו מתאים ממקור חופשי: "+";".join(errors[:2]))

def _duration(path):
    proc=subprocess.run(["ffprobe","-v","quiet","-show_entries",
                         "format=duration","-of","default=noprint_wrappers=1:nokey=1",
                         str(path)],check=True,capture_output=True,text=True,timeout=20)
    return float(proc.stdout.strip())

def _video_profile(path):
    result=subprocess.run(["ffprobe","-v","error","-select_streams","v:0",
        "-show_entries","stream=codec_name,width,height",
        "-of","json",str(path)],capture_output=True,text=True,check=True,timeout=15)
    tracks=json.loads(result.stdout).get("streams",[])
    if not tracks:raise UnavailableVideo("המקור אינו כולל תמונה נעה")
    stream=tracks[0]
    return stream.get("codec_name"),stream.get("width"),stream.get("height")

def _make_segment(src,output,length):
    if length<=0:raise UnavailableVideo("קטע וידאו ריק")
    source_length=_duration(src)
    if source_length<min(.7,length*.4):
        raise UnavailableVideo("קטע המקור קצר מדי")
    codec,_,_=_video_profile(src)
    # Zero-reencoding fast path. Wikimedia supplied VP9 clips can be remuxed
    # into MP4 without scaling or H.264 CPU-intensive work. The low-power
    # free Render instance previously timed out after 100 seconds on 30s
    # of H.264 encoding, silently discarding the otherwise valid MP3.
    if codec in ("vp9","h264","hevc","av1"):
        command=["ffmpeg","-nostdin","-hide_banner","-loglevel","error","-y",
                 "-stream_loop","-1","-i",str(src),"-t",f"{length:.3f}",
                 "-map","0:v:0","-an","-c:v","copy",
                 "-movflags","+faststart",str(output)]
        subprocess.run(command,capture_output=True,check=True,timeout=35)
        return
    # For VP8 / Theora transcode ONLY a brief source clip once, then repeat
    # the completed H.264 segment by stream copy. Do not reencode every repeat.
    short=Path(output).with_name("encoded-"+Path(output).name)
    source_duration=min(source_length,6.0)
    command=["ffmpeg","-nostdin","-hide_banner","-loglevel","error","-y",
             "-i",str(src),"-t",f"{source_duration:.3f}","-an",
             "-vf","fps=10,scale=360:-2,format=yuv420p",
             "-c:v","libx264","-preset","ultrafast","-crf","30",str(short)]
    subprocess.run(command,capture_output=True,check=True,timeout=70)
    command=["ffmpeg","-nostdin","-hide_banner","-loglevel","error","-y",
             "-stream_loop","-1","-i",str(short),"-t",f"{length:.3f}",
             "-map","0:v:0","-an","-c:v","copy",
             "-movflags","+faststart",str(output)]
    subprocess.run(command,capture_output=True,check=True,timeout=30)

# When an exact action clip cannot be found, an explicitly named
# physical subject may still be shown as relevant footage. This is thematic
# matching only, NEVER a claim that the subject visibly performed the verb.
# The user interface must report this downgraded visual coverage.
SUBJECT_FALLBACK_QUERIES={
    "donkey_bray":"donkey",
    "dog_bark":"dog",
    "dog_run":"dog",
    "donkey_eat":"donkey",
    "bird_fly":"bird",
    "baby_cry":"baby",
    "person_laugh":"person",
    "person_cry":"person",
    "person_sing":"person",
    "person_cook":"person",
    "cat_eat":"cat",
    "car_drive":"car",
    "truck_drive":"truck",
    "horse_run":"horse",
    "farmer_feed":"farmer",
    "pizza_eat":"pizza",
    "rain":"rain",
    "beach_walk":"beach",
}

def export_live_story(audio_mp3,video_mp4,plan,work_dir,progress=None,
                      search=commons_candidates,download=download_video):
    scenes=plan["scenes"]
    if not scenes:raise UnavailableVideo("אין פעולות ליצירה")
    work=Path(work_dir)
    work.mkdir(parents=True,exist_ok=True)
    # Preparation must search every known event before deciding whether an
    # actual motion picture can be assembled. Missing one archive clip may not
    # discard every other verified scene or the whole 50-second soundtrack.
    cached={}
    prepared=[]
    missing=[]
    for i,scene in enumerate(scenes):
        if progress:progress(88+int(6*i/len(scenes)),
            "בודק צילומים לאירוע "+str(i+1)+" מתוך "+str(len(scenes)))
        query=scene["query"]
        if query not in cached:
            selected=None
            source=work/f"source-{len(cached)}.webm"
            match_level="exact_action"
            queries=[query]
            fallback=SUBJECT_FALLBACK_QUERIES.get(scene["action"])
            if fallback and fallback!=query:
                queries.append(fallback)
            for candidate_query in queries:
                try:
                    choices=search(candidate_query)
                except Exception:
                    choices=[]
                for item in choices[:4]:
                    try:
                        download(item,source)
                        if _duration(source)>=.7:
                            selected=item
                            match_level=("exact_action" if candidate_query==query
                                         else "explicit_subject_only")
                            break
                    except (OSError,subprocess.SubprocessError,ValueError,UnavailableVideo):
                        continue
                if selected is not None:break
            cached[query]=(source,selected,match_level)
        source,selected,match_level=cached[query]
        if selected is None:
            missing.append({"action":scene["action"],"spoken":scene.get("spoken","")[:180]})
            continue
        if match_level=="explicit_subject_only":
            plan["visual_coverage"]="partial"
            plan.setdefault("thematic_clips",[]).append(scene["action"])
        prepared.append((scene,source,selected,match_level))
    if not prepared:
        raise UnavailableVideo(
            "חיפשתי צילומים לכל הפעולות שזוהו, אבל לא נמצא אף קטע וידאו מורשה שתואם להן.")
    sources=[]
    audio_duration=float(scenes[-1]["end"])
    matched_seconds=sum(max(.1,scene["end"]-scene["start"]) for scene,_,_,_ in prepared)
    for i,(scene,source,selected,match_level) in enumerate(prepared):
        # Preserve the entire audio; extend only known matching footage for
        # unsupported phrases. The API/UI explicitly disclose partial visual
        # coverage, never claim every utterance was depicted.
        length=audio_duration*max(.1,scene["end"]-scene["start"])/matched_seconds
        segment=work/f"scene-{i}.mp4"
        _make_segment(source,segment,max(.6,length))
        sources.append({"action":scene["action"],"file":str(segment),
                        "page":selected["page"],"license":selected["license"],
                        "match_level":match_level})
    plan["missing_footage"]=missing
    if missing:
        plan["visual_coverage"]="partial"
        plan["unmatched_clauses"]=plan.get("unmatched_clauses",0)+len(missing)
    concat=work/"manifest.txt"
    concat.write_text("".join("file '"+Path(src["file"]).name+"'\n"
                              for src in sources),encoding="utf-8")
    silent=work/"silent.mp4"
    subprocess.run(["ffmpeg","-nostdin","-loglevel","error","-y",
                    "-f","concat","-safe","0","-i",str(concat),
                    "-c","copy",str(silent)],cwd=work,capture_output=True,
                   check=True,timeout=55)
    attribution=" | ".join(src['page']+" ("+src["license"]+")" for src in sources)
    subprocess.run(["ffmpeg","-nostdin","-loglevel","error","-y",
                    "-i",str(silent),"-i",str(audio_mp3),
                    "-map","0:v:0","-map","1:a:0","-c:v","copy",
                    "-c:a","aac","-b:a","160k","-shortest",
                    "-metadata","comment=Video sources: "+attribution[:2700],
                    "-movflags","+faststart",str(video_mp4)],
                   capture_output=True,check=True,timeout=70)
    if Path(video_mp4).stat().st_size<12000:
        raise UnavailableVideo("סרטון MP4 ריק או פגום")
    return sources
