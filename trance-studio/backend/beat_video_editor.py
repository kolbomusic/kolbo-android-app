"""Beat-aligned live-action EDITING of a user's existing WhatsApp video.

Creates a visibly re-edited MP4: true shot cuts, restrained punch-in reframes,
and story-cued speed changes. Never fabricates people/events and never overlays
lyrics or substitutes a static picture. The source soundtrack is replaced by
the independently rendered user-voice trance mix. FFmpeg is fully offline.
"""
import json
import math
import subprocess
from pathlib import Path

from live_video import _duration, _video_profile, UnavailableVideo
from motion_quality import require_visible_motion_somewhere, NoVisibleMotion


def edit_decisions(duration, bpm, source_duration, transcript=""):
    """A deterministic shot list with cuts on musical bar boundaries."""
    if not 120<=bpm<=165 or duration<=.5 or source_duration<.75:
        raise UnavailableVideo("נתוני הסרטון או הקצב אינם תקינים")
    beat=60.0/bpm
    bar=4*beat
    # Aim at ~6 edited shots for a typical 30s WhatsApp mix, not 30
    # random half-second cuts. Longer clips cap at eight passes.
    bars_per_shot=max(1,round(duration/(6*bar)))
    base=bar*bars_per_shot
    shots=[]
    t=0.
    max_shots=8
    patterns=(1.,1.,.75,1.25,1.,1.15,.85,1.)
    speeds=(1.,1.10,.92,1.08,1.,.86,1.12,1.)
    framing=(1.,1.085,1.14,1.045,1.10,1.17,1.06,1.0)
    # Never decide a word-aligned cut from an unaligned Hebrew transcript.
    # Semantic cue affects editing *style*, not the claimed actual event.
    drama=any(w in (transcript or "") for w in ("צעק","נפל","חמור","פיצו","בום"))
    while t<duration-.06 and len(shots)<max_shots:
        idx=len(shots)
        if idx==max_shots-1:
            length=duration-t
        else:
            # Quantize cut to a complete musical bar.
            bars=max(1,round(bars_per_shot*patterns[idx]))
            next_cut=min(duration,round((t+bars*bar)/bar)*bar)
            length=max(.18,next_cut-t)
        length=min(length,duration-t)
        if length<.12:break
        speed=speeds[idx]
        zoom=framing[idx]
        if drama and idx in (2,5):
            speed=.83
            zoom=max(zoom,1.16)
        # Follow time in original film where possible, rather than always
        # restarting at frame zero. Short footage is reused truthfully.
        max_seek=max(0.,source_duration-.25)
        seek=(t*.91)%max_seek if max_seek>.3 else 0.
        shots.append({"start":round(t,3),"duration":round(length,3),
                      "source_seek":round(seek,3),"speed":speed,"zoom":zoom,
                      "crop_bias":(.50,.46,.54,.5,.48,.52,.5,.5)[idx]})
        t+=length
    return shots



def _video_effect_parameters(kind, effect, intensity):
    """Respeed and geometrically warp real captured frames at audible FX cues.

    This is not facial reenactment/lip synthesis; the visible deformation,
    movement speed, punch-in and color are real MP4 pixel transforms.
    """
    intensity=max(1,min(3,int(intensity)))
    if kind=="voice_fx":
        if effect in ("stretch","tape","monster","rewind","yo_yo"):
            return (.62 if intensity>=2 else .78,
                    1.12+.04*intensity,"stretch")
        if effect in ("pitch","helium","robot","ring"):
            return (1.28+.07*(intensity-1),
                    1.12+.035*intensity,"pitch")
        return (1.10 if intensity>=2 else 1.02,
                1.09+.05*intensity,"glitch")
    # A pitch/monster mode changes the actual spoken samples as well as
    # highlights. Distort the *spoken person*, not only inserted jokes.
    if kind=="voice" and effect in ("pitch","helium","monster","robot","flanger","ring"):
        return (1.,1.04+.025*intensity,
                "pitch" if effect in ("pitch","helium") else "stretch")
    return 1.,1.035, "normal"


def sync_edit_decisions(duration,bpm,source_duration,events,
                        humor="auto",fx_intensity=2,source_file_index=0):
    """Map audible original words 1:1 to video time, with FX inserts at
    the exact sample-derived position. Never guess word boundaries from text.
    """
    if not 120<=bpm<=165 or duration<=.5 or source_duration<.75:
        raise UnavailableVideo("נתוני הסרטון או הקצב אינם תקינים")
    selected=[]
    for e in events or []:
        if not isinstance(e,dict) or e.get("source_file")!=source_file_index:
            continue
        try:
            start=float(e["start"]);end=float(e["end"]);seek=float(e["source_seek"])
        except (ValueError,TypeError,KeyError):
            continue
        if not all(math.isfinite(v) for v in (start,end,seek)):
            continue
        if start<0 or end<=start or seek<0:
            continue
        selected.append({**e,"start":start,"end":end,"source_seek":seek})
    selected.sort(key=lambda e:(e["start"],e["kind"]!="voice"))
    if not any(e["kind"]=="voice" for e in selected):
        return []
    shots=[]
    cursor=0.
    source_cursor=0.
    def push(start,end,source_seek,kind,effect):
        if end-start<.085:return
        speed,zoom,look=_video_effect_parameters(kind,effect,fx_intensity)
        time_left=end-start
        elapsed=0.
        # Keep individual MP4 passes bounded on Render Free and avoid dozens
        # of unrelated cuts; consecutive long words remain chronological.
        while time_left>.085:
            length=min(14.,time_left)
            # Exact source mapping for unmodified spoken voice (1:1).
            seek=(source_seek+elapsed if kind=="voice" else source_seek)
            if source_duration>.3:
                seek=seek%source_duration
            else:
                seek=0.
            shots.append({"start":round(start+elapsed,4),
                          "duration":round(length,4),
                          "source_seek":round(max(0.,seek),4),
                          "speed":speed,"zoom":zoom,"look":look,
                          "kind":kind,"crop_bias":.50})
            time_left-=length
            elapsed+=length
    for e in selected:
        start=max(cursor,min(duration,e["start"]))
        end=min(duration,e["end"])
        if end<=start:
            continue
        if start>cursor+.085:
            push(cursor,start,source_cursor,"music","off")
        kind="voice_fx" if e["kind"]=="voice_fx" else "voice"
        push(start,end,e["source_seek"]+max(0.,start-e["start"]) if kind=="voice"
             else e["source_seek"],kind,e.get("effect",humor))
        cursor=end
        if kind=="voice":
            source_cursor=e["source_seek"]+(end-e["start"])
        else:
            source_cursor=e["source_seek"]
    if duration-cursor>.085:
        push(cursor,duration,source_cursor,"music","off")
    # Protect the free 1-worker service against pathological 5m sources with
    # many hundreds of cuts. The caller falls back to the older 8-shot mode.
    return shots if 1<=len(shots)<=70 else []


def _visual_filter(shot):
    speed=shot["speed"];zoom=shot["zoom"];bias=shot["crop_bias"]
    look=shot.get("look","normal")
    parts=[
        "setpts=(PTS-STARTPTS)/%.4f"%speed,"fps=12",
        "scale=360:640:force_original_aspect_ratio=increase:force_divisible_by=2",
        "scale=ceil(iw*%.4f/2)*2:ceil(ih*%.4f/2)*2"%(zoom,zoom)]
    # Barrel/pincushion distortion is applied to the *actual moving frames*
    # before center cropping, which avoids dark warped borders.
    if look=="stretch":
        parts.append("lenscorrection=cx=0.5:cy=0.46:k1=-0.20:k2=0.025")
    elif look=="pitch":
        parts.append("lenscorrection=cx=0.5:cy=0.46:k1=0.16:k2=-0.04")
        parts.append("hue=s=1.18")
    elif look=="glitch":
        parts.append("lenscorrection=cx=0.5:cy=0.46:k1=-0.11:k2=0.015")
        parts.append("eq=contrast=1.17:saturation=1.15")
    parts.extend([
        "crop=360:640:(in_w-out_w)*%.3f:(in_h-out_h)/2"%bias,
        "setsar=1","eq=contrast=1.035:saturation=1.045",
        "format=yuv420p"])
    return ",".join(parts)


def compose_simple_original_video_fallback(source,music_mp3,output_mp4,
                                            work_dir,*,bpm=145):
    """Single-pass REAL video rescue if multi-shot FX rendering failed.

    Never turn an audio file or static slide into fabricated action footage.
    Uses only the user's moving original video and the finished vocal mix.
    Slow the source moderately if needed, instead of repeating a short loop.
    A single modest moving-video color/crop transform is deliberately labeled
    less sophisticated than sample-timed original-voice FX.
    """
    src=Path(source);work=Path(work_dir)
    work.mkdir(parents=True,exist_ok=True)
    mix_duration=_duration(music_mp3)
    src_duration=_duration(src)
    if not (.5<=mix_duration<=360. and .8<=src_duration<=600.):
        raise UnavailableVideo("משך הסרטון אינו מתאים למסלול העריכה החלופי")
    _video_profile(src)
    require_visible_motion_somewhere(src,duration=src_duration,threshold=.15)
    # An original 30-second movie with a 39-second remix can be stretched
    # ~1.3x to fill the soundtrack without making a 9-second repeated loop.
    # Never stretch 5 seconds into 40 seconds and call it a new scene.
    speed=min(1.0,src_duration/mix_duration)
    if speed<.55:
        raise UnavailableVideo("אין מספיק תנועה מצולמת ביחס לאורך המיקס")
    transform=(
        "setpts=(PTS-STARTPTS)/%.6f,fps=12,"
        "scale=360:640:force_original_aspect_ratio=increase:"
        "force_divisible_by=2,"
        "scale=ceil(iw*1.08/2)*2:ceil(ih*1.08/2)*2,"
        "crop=360:640:(in_w-out_w)/2:(in_h-out_h)/2,"
        "eq=contrast=1.10:saturation=1.13,"
        "setsar=1,format=yuv420p"
    )%speed
    output=Path(output_mp4)
    cmd=["ffmpeg","-nostdin","-v","error","-y",
         "-i",str(src),"-i",str(music_mp3),
         "-map","0:v:0","-map","1:a:0","-vf",transform,
         "-c:v","libx264","-threads:v","1","-profile:v","baseline","-level","3.0",
         "-preset","ultrafast","-crf","30","-r","12","-g","24",
         "-c:a","aac","-b:a","144k",
         "-t","%.3f"%mix_duration,"-movflags","+faststart",
         str(output)]
    try:
        subprocess.run(cmd,check=True,capture_output=True,timeout=120)
    except (OSError,subprocess.SubprocessError) as exc:
        output.unlink(missing_ok=True)
        raise UnavailableVideo("קידוד סרטון הגיבוי נכשל") from exc
    if not output.exists() or output.stat().st_size<15000:
        output.unlink(missing_ok=True)
        raise UnavailableVideo("לא נוצר סרטון גיבוי תקין")
    codec,width,height=_video_profile(output)
    if (codec,width,height)!=("h264",360,640) or abs(_duration(output)-mix_duration)>.85:
        output.unlink(missing_ok=True)
        raise UnavailableVideo("סרטון הגיבוי אינו תואם את משך המיקס או פורמט אנדרואיד")
    return {
        "video_status":"done",
        "video_mode":"original_input_video",
        "video_edit_style":"single_pass_source_rescue",
        "video_edit_audio_synced":False,
        "video_edit_fx_cues":0,
        "video_edit_shots":1,
        "visual_coverage":"original_video_not_scene_generated",
        "source":"user_original_real_moving_video",
        "video_note":(
            "סרטון המקור עבר עריכת גיבוי עם האטה, חיתוך וזום מתון כדי להתאים "
            "לאורך המיקס. המסלול אינו מסנכרן כל אפקט קולי לתנועה, "
            "ואינו יוצר סצנות חדשות או שינויי שפתיים ב־AI."
        )
    }


def compose_edited_original_video(source, music_mp3, output_mp4, work_dir,
                                  bpm=145, transcript_hint="",
                                  fx_timeline=None,humor="auto",fx_intensity=2,
                                  source_file_index=0,progress=None):
    src=Path(source)
    work=Path(work_dir)
    work.mkdir(parents=True,exist_ok=True)
    duration=_duration(music_mp3)
    src_duration=_duration(src)
    if not .5<=duration<=360.:
        raise UnavailableVideo("אורך המיקס אינו מתאים לעריכת וידאו")
    _video_profile(src)
    require_visible_motion_somewhere(src,duration=src_duration,threshold=.15)
    synced=sync_edit_decisions(duration,bpm,src_duration,fx_timeline,
                  humor=humor,fx_intensity=fx_intensity,
                  source_file_index=source_file_index)
    shots=synced if synced else edit_decisions(duration,bpm,src_duration,transcript_hint)
    if not shots:raise UnavailableVideo("לא נמצאו קטעי צילום לעריכה")
    files=[]
    # The audio timeline is authoritative. An FFmpeg setpts slow-motion
    # effect changes *output* duration; passing the unadjusted requested
    # seconds to -t used to create longer/slower shots, pushing every later
    # vocal effect out of sync before the final MP4 was cut to audio length.
    # Reserve exact, non-overlapping 12-fps frame budgets at the FINAL
    # timeline positions, then read enough input for the chosen speed.
    fps=12
    expected_frames=max(1,round(duration*fps))
    exported_frames=0
    for idx,shot in enumerate(shots):
        start_frame=round(shot["start"]*fps)
        end_frame=round((shot["start"]+shot["duration"])*fps)
        frames=max(0,end_frame-start_frame)
        if not frames:
            continue  # Sub-frame FX are audible but cannot be seen at 12fps.
        clip=work/("shot-%02d.mp4"%idx)
        speed=shot["speed"]
        # Reserve a little source decoding beyond the last required frame;
        # -frames:v is the exact final-length cap, independent of setpts.
        input_seconds=max(.25,frames/fps*speed+.25)
        vf=_visual_filter(shot)
        cmd=[
            "ffmpeg","-nostdin","-v","error","-y",
            "-stream_loop","-1","-ss",str(shot["source_seek"]),
            "-t","%.5f"%input_seconds,"-i",str(src),
            "-vf",vf,"-map","0:v:0","-an",
            "-c:v","libx264","-threads:v","1","-profile:v","baseline","-level","3.0",
            "-preset","ultrafast","-crf","29","-r",str(fps),"-g","24",
            "-frames:v",str(frames),
            "-movflags","+faststart",str(clip)
        ]
        try:
            subprocess.run(cmd,capture_output=True,check=True,timeout=65)
        except (OSError,subprocess.SubprocessError) as exc:
            raise UnavailableVideo("העריכה החזותית נכשלה בעת הכנת צילום המקור") from exc
        if not clip.is_file() or clip.stat().st_size<2048:
            raise UnavailableVideo("לא הופק קטע צילום מעובד")
        files.append(clip)
        exported_frames+=frames
        if progress:
            progress(88+min(7,round(7*(idx+1)/max(1,len(shots)))),
                     "מסנכרן תנועה ומראה עם אפקטי הקול: "+
                     str(idx+1)+" מתוך "+str(len(shots)))
    if not files or abs(exported_frames-expected_frames)>1:
        raise UnavailableVideo("תזמון פריימי הווידאו אינו תואם את המיקס")
    concat_list=work/"shots.txt"
    concat_list.write_text("".join("file '%s'\n"%p.name for p in files),
                           encoding="utf-8")
    joined=work/"edited-no-audio.mp4"
    try:
        subprocess.run(["ffmpeg","-nostdin","-v","error","-y",
                        "-f","concat","-safe","0","-i",str(concat_list),
                        "-c:v","copy","-an","-movflags","+faststart",
                        str(joined)],capture_output=True,check=True,timeout=35)
        subprocess.run(["ffmpeg","-nostdin","-v","error","-y",
                        "-i",str(joined),"-i",str(music_mp3),
                        "-map","0:v:0","-map","1:a:0",
                        "-c:v","copy","-c:a","aac","-b:a","160k",
                        "-t","%.3f"%duration,"-movflags","+faststart",
                        str(output_mp4)],capture_output=True,check=True,timeout=45)
    except (OSError,subprocess.SubprocessError) as exc:
        raise UnavailableVideo("חיבור חיתוכי הווידאו למיקס נכשל") from exc
    output=Path(output_mp4)
    if not output.is_file() or output.stat().st_size<15000:
        raise UnavailableVideo("קובץ MP4 הערוך לא נוצר")
    codec,width,height=_video_profile(output)
    if (codec,width,height)!=("h264",360,640):
        raise UnavailableVideo("קידוד הווידאו הערוך אינו תואם אנדרואיד")
    if abs(_duration(output)-duration)>.8:
        raise UnavailableVideo("אורך הווידאו אינו תואם את המיקס")
    return {"video_mode":"original_input_video",
            "video_edit_fps":fps,
            "video_edit_frames":exported_frames,
            "video_edit_style":("voice_fx_synced_motion_warp" if synced
                                else "beat_cut_punch_in_speed_ramp"),
            "video_edit_fx_cues":sum(1 for shot in shots
                                        if shot.get("kind")=="voice_fx"),
            "video_edit_audio_synced":bool(synced),
            "video_edit_shots":len(shots),
            "video_status":"done",
            "source":"user_original_real_moving_video",
            "visual_coverage":"original_video_not_scene_generated",
            "video_note":(
                "צילום המקור נערך לפי ציר הזמן האמיתי של הקול: תנועת האדם "
                "והתמונה משתנות בהאטה, האצה, עיוות גיאומטרי והדגשות בקצב "
                "האפקטים. לא בוצעו שינויי הבעות פנים או סנכרון שפתיים ב־AI."
                if synced else
                "צילום המקור עבר עריכת קליפ: חיתוכים לפי תיבות, "
                "שינויי מהירות והדגשות צילום מתונות, יחד עם מיקס הקול. "
                "האירועים המצולמים לא נוצרו מחדש ב־AI.")}
