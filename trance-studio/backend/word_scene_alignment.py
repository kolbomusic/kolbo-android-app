"""Place filmed scene changes on genuinely recognized original Hebrew word times.

Speech word timestamps alone are SOURCE seconds, not mix seconds. Translate
through the same dry-original sample spans exported by the DJ arranger.
Missing/partial ASR never produces fabricated timestamps: the older
vocal-activity approximation remains an explicit fallback.
"""
from __future__ import annotations
import re

HEBREW_WORD=re.compile(r"[\u05d0-\u05ea]+")


def _source_words(timed_groups,source_spans,duration):
    if not isinstance(timed_groups,list) or not isinstance(source_spans,list):
        return []
    mapped=[]
    for file_index,words in enumerate(timed_groups):
        if not isinstance(words,list):return []
        spans=[x for x in source_spans if isinstance(x,dict)
               and x.get("kind")=="voice" and x.get("source_file")==file_index]
        for word in words:
            try:
                src_start=float(word["start"])
                src_end=float(word["end"])
                if not 0<=src_start<src_end<=300:continue
                for span in spans:
                    start=float(span["start"])
                    end=float(span["end"])
                    seek=float(span["source_seek"])
                    if seek-.025<=src_start and src_end<=seek+(end-start)+.025:
                        output=start+max(0,src_start-seek)
                        if 0<=output<duration:
                            mapped.append(output)
                        break
            except (KeyError,TypeError,ValueError,OverflowError):
                continue
    return sorted(mapped)


def align_storyboard_to_source_words(board,timed_groups,source_spans,duration):
    """Return True if scene boundaries are grounded in source word times.

    Word-count alignment chooses each scene's boundary from recognized word
    starts. It does NOT claim a semantic model independently verified every
    event; source captions and approximate scene coverage remain unchanged.
    """
    scenes=board.get("scenes",[]) if isinstance(board,dict) else []
    if len(scenes)<2:return False
    try:
        duration=float(duration)
        if not .5<=duration<=360:return False
        counts=[len(HEBREW_WORD.findall(str(s.get("spoken",""))))
                for s in scenes]
        if any(n<=0 for n in counts):return False
        word_times=_source_words(timed_groups,source_spans,duration)
        # A partial/out-of-order transcript is worse than vocal-energy
        # alignment; be explicit that some words lack authentic timestamps.
        if len(word_times)<max(3,int(sum(counts)*.70)):return False
        if len(word_times)<len(scenes)+1:return False
        cumulative=0
        boundaries=[0.]
        gap=min(.18,duration/(len(scenes)+2)*.3)
        for length in counts[:-1]:
            cumulative+=length
            target=round(cumulative*len(word_times)/sum(counts))
            target=max(1,min(len(word_times)-1,target))
            proposed=word_times[target]
            high=duration-gap*(len(scenes)-len(boundaries))
            boundary=min(high,max(boundaries[-1]+gap,proposed))
            if boundary<=boundaries[-1] or boundary>=duration:
                return False
            boundaries.append(boundary)
        boundaries.append(duration)
        for i,scene in enumerate(scenes):
            scene["start"]=round(boundaries[i],3)
            scene["end"]=round(boundaries[i+1],3)
            scene["alignment"]="word_boundaries_approximate_scene_match"
        board["alignment"]="original_source_word_timestamps"
        return True
    except (KeyError,ValueError,TypeError,OverflowError):
        return False
