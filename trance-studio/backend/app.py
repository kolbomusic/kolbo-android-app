"""Bounded, temporary audio jobs. Run one WSGI worker; threads share admission state."""
import os, time, secrets, shutil, threading, json, subprocess, hashlib, re, tempfile, gc
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from flask import Flask, request, jsonify, send_file, send_from_directory, Response
from werkzeug.exceptions import RequestEntityTooLarge
from itsdangerous import URLSafeTimedSerializer, BadSignature
from engine import load_audio, render_mix, export_mp3, AudioDecodeError
from storyboard import align_storyboard_to_vocal
from live_video import visual_plan, export_live_story, UnavailableVideo


ALLOWED={'.opus','.ogg','.oga','.mp3','.wav','.m4a','.aac','.mp4','.webm','.flac','.3gp','.3gpp','.mov'}
VIDEO_UPLOADS={'.mp4','.webm','.3gp','.3gpp','.mov'}
MAX_AUDIO_UPLOAD=15*1024*1024
MAX_VIDEO_UPLOAD=45*1024*1024
MAX_COMBINED_UPLOAD=60*1024*1024
AUTHORIZED_MUSIC_EXT={'.mp3','.wav','.ogg','.m4a'}
MAX_BACKING_UPLOAD=15*1024*1024

def _save_upload_stream(stream, dest, limit, total_limit, already_saved=0,
                        expected_sha256=None):
    """Store original source on disk in 256-KiB chunks, not a 45-MB RAM blob.

    Waiting jobs can be spooled while the ONE CPU worker is rendering;
    this must not add a 45-MiB in-memory buffer that risks another OOM.
    """
    maximum_chunk=256*1024
    copied=0
    digest=hashlib.sha256() if expected_sha256 is not None else None
    with dest.open('wb') as output:
        while True:
            part=stream.read(maximum_chunk)
            if not part:
                break
            copied+=len(part)
            if copied>limit or already_saved+copied>total_limit:
                raise ValueError('upload_limit')
            output.write(part)
            if digest is not None:
                digest.update(part)
    if copied<1:
        raise ValueError('empty_upload')
    if digest is not None and digest.hexdigest()!=expected_sha256:
        raise ValueError('source_fingerprint_mismatch')
    return copied


def create_app(config=None):
    app=Flask(__name__,static_folder=None)
    app.config.update(MAX_CONTENT_LENGTH=64*1024*1024,JOB_DIR=os.environ.get('JOB_DIR','/tmp/kolbo-trance-jobs'),API_TOKEN=os.environ.get('API_TOKEN',''),ALLOWED_ORIGINS=os.environ.get('ALLOWED_ORIGINS','https://kolbo-trance-studio.happyblimp1.chatgpt.site'),JOB_TTL=3600)
    if config:app.config.update(config)
    root=Path(app.config['JOB_DIR']);root.mkdir(parents=True,exist_ok=True)
    jobs={};lock=threading.Lock();admission=threading.BoundedSemaphore(1);queue_slots=threading.BoundedSemaphore(2);link_admission=threading.BoundedSemaphore(1);executor=ThreadPoolExecutor(max_workers=1)
    static=Path(__file__).resolve().parents[1]/'dist'
    web=Path(__file__).resolve().parents[1]/'web'
    def stream_temporary_media(media_path,mime,folder):
        """Delete the temporary source after actual response consumption.

        Flask send_file(...).call_on_close() is not reliably executed by all
        WSGI response wrappers. This generator ties cleanup to stream close.
        """
        length=media_path.stat().st_size
        def chunks():
            try:
                with media_path.open('rb') as infile:
                    while True:
                        block=infile.read(65536)
                        if not block:break
                        yield block
            finally:
                shutil.rmtree(folder,ignore_errors=True)
        response=Response(chunks(),mimetype=mime,headers={
            'Content-Length':str(length),'Cache-Control':'no-store, private',
            'X-Content-Type-Options':'nosniff'})
        return response

    def session_codec():
        return URLSafeTimedSerializer(app.config['API_TOKEN'],salt='kolbo-studio-web-session')
    def studio_session():
        token=app.config['API_TOKEN']
        if not token:return False
        cookie=request.cookies.get('kolbo_studio','')
        try:return session_codec().loads(cookie,max_age=86400)=='studio'
        except (BadSignature,ValueError):return False

    def cleanup():
        now=time.time()
        with lock:
            expired=[k for k,v in jobs.items() if v['state'] in ('done','error') and now-v['created']>app.config['JOB_TTL']]
            for k in expired:jobs.pop(k,None);shutil.rmtree(root/k,ignore_errors=True)
        # Remove leftovers from a previous process too; opaque names only.
        for p in root.iterdir():
            if p.is_dir() and now-p.stat().st_mtime>app.config['JOB_TTL'] and p.name not in jobs:shutil.rmtree(p,ignore_errors=True)

    def janitor():
        while True:
            time.sleep(60)
            try:cleanup()
            except OSError:pass
    if not app.config.get('TESTING'):threading.Thread(target=janitor,daemon=True).start()

    def update(job_id,**values):
        with lock:jobs[job_id].update(values)

    def work(job_id,paths,options):
        # Exclusive heavy CPU/memory gate shared with phone AI-clip mux.
        # The second mix waits on disk; no simultaneous H264 or DSP render.
        admission.acquire()
        stage='decode'
        try:
            update(job_id,state='processing',percent=4,label='קורא ומאמת את אורך ההקלטות')
            # Accept longer original speech (up to five minutes per job)
            # without silently clipping a WhatsApp message.
            # Validate audio duration before CPU-expensive word-level ASR.
            # Oversized/invalid recordings must fail immediately, never sit
            # for minutes in recognition before a simple decoder check.
            clips=[load_audio(p) for p in paths]
            # Run ASR recovery against the ORIGINAL files before removing them.
            # A failed browser model cannot cancel a user's explicit MP4 request.
            detected_transcript=(options.get('transcript') or '').strip()
            detected_origin='browser_source_asr' if detected_transcript else 'unavailable'
            transcript_complete=True
            asr_recovery_error=''
            # Audio is the primary product, not a silent byproduct of video ASR.
            # Recognize source speech for timestamped music/DJ direction even
            # when MP4 was not requested. If ASR fails, still return audio.
            audio_director=options.get('humor','auto')!='off'
            asr_recovery_attempted=bool(
                (audio_director or options.get('video_requested')) and
                (audio_director or len(detected_transcript.split())<2))
            transcript_timeline=None
            # A decoded 300-second float32 track can hold ~38 MiB (plus
            # Python/NumPy allocator overhead) while multilingual Whisper
            # starts in a child. On a 512-MiB Render container that overlap
            # pushed combined cgroup RSS near 500 MiB and lost the job.
            # Fully validate the original audio above, but drop this decoded
            # copy BEFORE spawning local ASR; reconstruct it after child exit.
            isolated_original_asr=bool(
                asr_recovery_attempted and not app.config.get('TESTING') and
                os.environ.get('KOLBO_ASR_ISOLATED')!='0')
            if isolated_original_asr:
                del clips
                gc.collect()
            if asr_recovery_attempted:
                update(job_id,percent=5,label='מזהה משפטים ותזמון אפקטים מהקלטת המקור')
                try:
                    if app.config.get('TESTING') or os.environ.get('KOLBO_ASR_ISOLATED')=='0':
                        from source_asr import transcribe_original_files
                        asr_result=transcribe_original_files(
                            paths,progress=lambda label:update(job_id,label=label),
                            return_timeline=True)
                    else:
                        from isolated_asr import transcribe_in_child
                        asr_result=transcribe_in_child(paths)
                    # Preserve compatibility with older source-ASR wrappers
                    # which return text+completion but no timestamp metadata.
                    if len(asr_result)==3:
                        spoken,transcript_complete,transcript_timeline=asr_result
                    else:
                        spoken,transcript_complete=asr_result
                        transcript_timeline=None
                    if spoken:
                        detected_transcript=spoken
                        detected_origin='server_original_asr'
                except Exception as exc:
                    # On free CPU, ASR is best-effort: no loss of MP3 jobs.
                    asr_recovery_error=str(exc)[:180]
                    app.logger.warning('Original speech timing unavailable: %s',
                                       type(exc).__name__)
                finally:
                    # The 512 MiB worker must not retain multilingual Whisper
                    # weights while constructing the full stereo DJ mix.
                    # Original source bytes remain on disk; release only the
                    # in-memory ASR inference model before DSP allocations.
                    from source_asr import release_model
                    release_model()
            if isolated_original_asr:
                # Only re-decode after short-lived ASR has COMPLETELY exited.
                # All later mixer stages use the same original bytes on disk.
                update(job_id,percent=9,label='מכין אודיו מקורי למיקס לאחר פינוי זיכרון התמלול')
                clips=[load_audio(p) for p in paths]
            audio_options={k:v for k,v in options.items() if k not in ('make_video','transcript','transcript_origin','video_requested','transcription_failed','source_hashes','ai_video_consent','video_strategy','backing_music_path','music_license_ack')}
            # Make the already recognized Hebrew speech useful for comic
            # timing/preset decisions. Keep it in-process; never transmit
            # private audio or transcript to a new third party.
            audio_options['transcript_hint']=detected_transcript[:4000]
            audio_options['transcript_timeline']=transcript_timeline
            audio_options['source_video_length']=bool(
                options.get('video_requested') and
                options.get('video_strategy') in ('remix_original','auto_legacy') and
                any(Path(p).suffix.lower() in ('.mp4','.webm','.3gp','.3gpp','.mov')
                    for p in paths))
            stage='mix'
            rendered=render_mix(clips,**audio_options,return_voice=True,
                                   return_video_timeline=bool(options.get('video_requested')),
                                   progress=lambda p,label:update(job_id,percent=p,label=label))
            # Older test engines still return (mix,voice). Only the current
            # renderer exports sample-derived original voice/FX timestamps.
            if len(rendered)==3:
                audio,vocal,video_fx_timeline=rendered
            else:
                audio,vocal=rendered
                video_fx_timeline=[]
            if options.get('backing_music_path'):
                stage='licensed_music'
                from licensed_music import mix_licensed_backing
                audio=mix_licensed_backing(
                    options['backing_music_path'],vocal,32000,
                    transcript_hint=detected_transcript,
                    bpm=options.get('bpm',145),
                    humor=options.get('humor','auto'))
            stage='export'
            export_mp3(audio,root/job_id/'mix.mp3')
            export_mp3(vocal,root/job_id/'voice.mp3')
            audio_duration_seconds=len(audio)/32000
            del audio, rendered, clips
            if (not options.get('video_requested') or
                    options.get('video_strategy') in ('remix_original','new_story')):
                del vocal
            gc.collect()
            meta={'video_status':'disabled','storyboard_source':'not_requested'}
            if options.get('video_requested'):
                stage='video'
                update(job_id,percent=87,label='בודק התאמה בין המשפטים לצילומי וידאו',
                       video_status='processing')
                # The USER submitted an actual video, not just a voice
                # message. Edit those real captured frames FIRST rather
                # than replacing them with unrelated stock footage or
                # spending a public AI quota. This is a video remix, not
                # an invented visual reconstruction of the narration.
                from source_video_fallback import VIDEO_TYPES
                original_video_issue=''
                original_video_error_code=''
                if options.get('video_strategy') in ('remix_original','auto_legacy') and any(Path(p).suffix.lower() in VIDEO_TYPES for p in paths):
                    try:
                        from source_video_fallback import compose_original_video_with_mix
                        remixed=compose_original_video_with_mix(
                            paths,root/job_id/'mix.mp3',
                            root/job_id/'story.mp4',root/job_id/'original-video',
                            bpm=options.get('bpm',145),
                            transcript_hint=detected_transcript,
                            fx_timeline=video_fx_timeline,
                            humor=options.get('humor','auto'),
                            fx_intensity=options.get('fx_intensity',2),
                            progress=lambda p,label:update(job_id,percent=p,label=label))
                        meta={**remixed,
                              'storyboard_source':'original_shared_video',
                              'transcript_origin':detected_origin,
                              'visual_beats':remixed.get('video_edit_shots',1)}
                    except (UnavailableVideo,OSError,ValueError,
                            subprocess.SubprocessError) as exc:
                        # Never swallow a video failure and then claim a bad
                        # source was proven: encode errors and absent video
                        # tracks are different problems. Expose only known
                        # fixed Hebrew categories, not private file paths.
                        cause=str(exc) if isinstance(exc,UnavailableVideo) else ''
                        if 'תנועת תמונה מספקת' in cause:
                            original_video_error_code='motion_not_detected'
                            original_video_issue='בסרטון המקור כמעט לא זוהתה תנועה חזותית.'
                        elif 'ערוץ תמונה' in cause or 'ללא ערוץ וידאו' in cause:
                            original_video_error_code='no_video_track'
                            original_video_issue='הקובץ אינו מכיל ערוץ תמונה שניתן לפענוח.'
                        elif 'קצר מדי' in cause:
                            original_video_error_code='source_too_short'
                            original_video_issue='הסרטון קצר מדי ביחס למיקס.'
                        elif 'הגיבוי נכשלו' in cause:
                            original_video_error_code='both_encoders_failed'
                            original_video_issue='זוהה סרטון נע, אך קידוד העריכה והגיבוי נכשל.'
                        else:
                            original_video_error_code='source_video_unavailable'
                            original_video_issue='לא ניתן להשלים את עריכת הסרטון המקורי.'
                        app.logger.warning(
                            'Kolbo real-source MP4 unavailable ref=%s code=%s exc=%s',
                            job_id[:8],original_video_error_code,
                            type(exc).__name__)
                        (root/job_id/'story.mp4').unlink(missing_ok=True)
                if meta.get('video_status')=='done':
                    pass
                elif options.get('video_strategy')=='remix_original':
                    has_video_source=any(
                        Path(p).suffix.lower() in VIDEO_TYPES for p in paths)
                    meta={'video_status':'unavailable',
                          'video_error':(
                              'נבחר מצב עריכת סרטון מקורי, אך התקבל קובץ שמע בלבד. '
                              'כדי לקבל סרטון מהקול בחר ״סרטון AI חדש לפי הדיבור״ '
                              'ואשר שימוש בתמלול.'
                              if not has_video_source else
                              (original_video_issue or
                               'לא ניתן להפיק סרטון MP4 מהמקור.')
                              +' אפשר לבחור סרטון מקור אחר או ליצור סיפור חדש.'
                          ),
                          'video_error_code':(
                              'no_video_file' if not has_video_source
                              else original_video_error_code or 'unknown_video_failure'),
                          'storyboard_source':(
                              'no_video_track' if not has_video_source else
                              'original_video_not_usable'),
                          'visual_coverage':'none'}
                elif not detected_transcript or len(detected_transcript.split())<2:
                    meta={'video_status':'unavailable',
                          'video_error':'נוסו תמלול במכשיר ובשרת, אך לא זוהו מילים מספיק אמינות מההקלטה המקורית. '+asr_recovery_error,
                          'storyboard_source':'original_asr_failed',
                          'visual_coverage':'none'}
                    # Video uploads remain usable even when ASR fails:
                    # reuse ONLY the owner's real moving input footage.
                    # Audio-only files remain audio-only, never fake an MP4.
                    try:
                        if options.get('video_strategy') in ('new_story','illustrated_story'):
                            raise UnavailableVideo('אסור להחליף המחשה חדשה בצילום המקורי')
                        from source_video_fallback import compose_original_video_with_mix
                        original_recovery=compose_original_video_with_mix(
                            paths,root/job_id/'mix.mp3',root/job_id/'story.mp4',
                            root/job_id/'original-video',
                            bpm=options.get('bpm',145),
                            transcript_hint=detected_transcript,
                            fx_timeline=video_fx_timeline,
                            humor=options.get('humor','auto'),
                            fx_intensity=options.get('fx_intensity',2),
                            progress=lambda p,label:update(job_id,percent=p,label=label))
                        meta={**original_recovery,
                              'storyboard_source':'original_shared_video',
                              'transcript_origin':'unavailable',
                              'visual_beats':1}
                    except (UnavailableVideo,OSError,ValueError,
                            subprocess.SubprocessError):
                        pass
                else:
                    ai_generation_error=''
                    if options.get('ai_video_consent') and options.get('video_strategy')!='illustrated_story':
                        # Explicit one-tap consent: a community ZeroGPU Space
                        # receives only recognized TEXT, never private audio.
                        try:
                            from ai_video import generate_ai_story, AIVideoUnavailable
                            board=generate_ai_story(
                                detected_transcript,root/job_id/'mix.mp3',
                                root/job_id/'story.mp4',root/job_id/'generated',
                                progress=lambda p,label:update(job_id,percent=p,label=label))
                            board['transcript_origin']=detected_origin
                            (root/job_id/'storyboard.json').write_text(
                                json.dumps(board,ensure_ascii=False),encoding='utf-8')
                            meta={'video_status':'done',
                                  'video_mode':'ai_generated_experimental',
                                  'storyboard_source':board['source'],
                                  'transcript_origin':detected_origin,
                                  'transcript_complete':transcript_complete,
                                  'visual_coverage':'approximate',
                                  'visual_beats':board.get('ai_clips_generated',1),
                                  'ai_clip_seconds':board['ai_clip_seconds'],
                                  'ai_clips_generated':board.get('ai_clips_generated',1),
                                  'video_note':(
                                      'נוצרו '+str(board.get('ai_clips_generated',1))+
                                      ' סצנות AI עם '+str(board.get('ai_clip_seconds',0))+
                                      ' שניות של תנועה מקורית מתוך '+
                                      str(round(audio_duration_seconds,1))+
                                      ' שניות מיקס, ללא חזרה על קליפ קצר. '+
                                      'התאמה סמנטית מלאה אינה מובטחת.')}
                        except AIVideoUnavailable as err:
                            ai_generation_error=str(err)[:180]
                            app.logger.warning('Free AI video unavailable: %s',
                                               str(err)[:160])
                            (root/job_id/'story.mp4').unlink(missing_ok=True)
                        except Exception:
                            ai_generation_error='שירות יצירת הווידאו הניסיוני לא הצליח'
                            app.logger.exception('Experimental AI video failed')
                            (root/job_id/'story.mp4').unlink(missing_ok=True)
                    # A user selecting NEW AI STORY must never be given
                    # third-party archive footage disguised as AI generation.
                    # Archive shots remain available only in the legacy and
                    # explicitly selected illustration workflows.
                    if (meta.get('video_status')!='done' and
                            options.get('video_strategy')=='new_story'):
                        (root/job_id/'story.mp4').unlink(missing_ok=True)
                        meta={'video_status':'unavailable',
                              'video_error':(
                                  ('יצירת סרטון AI חדש לא הושלמה: '+ai_generation_error)
                                  if options.get('ai_video_consent')
                                  else 'כדי לייצר סרטון AI חדש נדרש אישור לשליחת התמלול לשירות הווידאו החיצוני'
                              )[:350],
                              'storyboard_source':'independent_ai_not_available',
                              'video_mode':'new_story_requested',
                              'visual_coverage':'none'}
                    if (meta.get('video_status')!='done' and
                            options.get('video_strategy')!='new_story'):
                        try:
                            board=visual_plan(detected_transcript,audio_duration_seconds)
                            board['transcript_origin']=detected_origin
                            board['transcript_complete']=transcript_complete
                            # A clip must depict every uttered event; do not hide
                            # unsupported sentences beneath footage from another
                            # sentence. Never swap to a waveform or cartoons.
                            # Continue preparing source footage even if there are
                            # unmatched phrases. Real video may still illustrate
                            # recognized scenes; coverage must be openly partial.
                            board=align_storyboard_to_vocal(board,vocal,sr=32000)
                            video_path=root/job_id/'story.mp4'
                            sources=export_live_story(root/job_id/'mix.mp3',video_path,
                                board,root/job_id/'footage',
                                progress=lambda p,label:update(job_id,percent=p,label=label))
                            board['sources']=[{'action':item['action'],
                                              'page':item['page'],
                                              'license':item['license']} for item in sources]
                            (root/job_id/'storyboard.json').write_text(
                                json.dumps(board,ensure_ascii=False),encoding='utf-8')
                            meta={'video_status':'done','video_mode':'matched_footage',
                                  'storyboard_source':board['source'],
                                  'transcript_origin':board['transcript_origin'],
                                   'transcript_complete':board['transcript_complete'],
                                  'visual_coverage':board.get('visual_coverage','partial'),
                                  'visual_beats':len(sources),
                                  'unmatched_clauses':board.get('unmatched_clauses',0),
                                  'video_note':(
                                      'זהו סרטון מצולם של אירועים שזוהו בהקלטה. '
                                      'בחלק מהמשפטים לא נמצאה המחשה מדויקת.'
                                      if board.get('visual_coverage')=='partial'
                                      else 'הצילומים נבחרו לפי האירועים שזוהו בדיבור המקורי.')}
                        except UnavailableVideo as err:
                            # If the WhatsApp original was VIDEO (not an
                            # audio-only recording), the real original moving
                            # frames offer a deterministic, private last
                            # resort. Never invent footage or imply this is
                            # an AI reconstruction of what was spoken.
                            recovered=None
                            try:
                                if options.get('video_strategy') in ('new_story','illustrated_story'):
                                    raise UnavailableVideo('אסור להחליף המחשה חדשה בצילום המקורי')
                                from source_video_fallback import compose_original_video_with_mix
                                recovered=compose_original_video_with_mix(
                                    paths,root/job_id/'mix.mp3',
                                    root/job_id/'story.mp4',root/job_id/'original-video',
                                    bpm=options.get('bpm',145),
                                    transcript_hint=detected_transcript)
                            except (UnavailableVideo,OSError,ValueError,
                                    subprocess.SubprocessError):
                                pass
                            if recovered is not None:
                                meta={**recovered,
                                      'storyboard_source':'original_shared_video',
                                      'transcript_origin':detected_origin,
                                      'visual_beats':1}
                            else:
                                # Diagnostics exclude private speech, audio and
                                # file names; preserve the successfully made MP3.
                                app.logger.warning('Grounded MP4 unavailable: asr=%s, cause=%s',
                                                   detected_origin, str(err)[:180])
                                (root/job_id/'story.mp4').unlink(missing_ok=True)
                                meta={'video_status':'unavailable',
                                      'video_error':(str(err) + ((' בנוסף, ניסיון וידאו AI נכשל: '+ai_generation_error) if ai_generation_error else ''))[:350],
                                      'storyboard_source':'no_grounded_story',
                                      'visual_coverage':'none'}
                        except (OSError,RuntimeError,ValueError,subprocess.SubprocessError):
                            app.logger.exception('Grounded live footage export failed')
                            (root/job_id/'story.mp4').unlink(missing_ok=True)
                            meta={'video_status':'error',
                                  'video_error':'לא ניתן לייצר סרטון שממחיש את המילים במדויק. המיקס נשמר, ולא ייוצר סרטון גלי קול.',
                                  'storyboard_source':'no_grounded_story',
                                  'visual_coverage':'none'}
            # A Render Free server has one shared anonymous ZeroGPU quota.
            # If it is exhausted, a user who explicitly opted in can try the
            # SAME narration from their own phone's browser quota instead.
            # Save only a bounded text-to-video prompt in this private, expiring
            # job status; NEVER expose the original audio to a third party.
            if (options.get('ai_video_consent') and
                    options.get('video_strategy') != 'remix_original' and
                    meta.get('video_status') != 'done'):
                try:
                    from ai_video import cinematic_prompt, AIVideoUnavailable
                    from narrative_plan import scene_prompts, scene_weights
                    # All prompts are based on the ACTUAL recognized Hebrew,
                    # never on what the application guesses was spoken.
                    beats=scene_prompts(detected_transcript,duration=audio_duration_seconds)
                    if beats:
                        meta['client_ai_prompt']=cinematic_prompt(detected_transcript)
                        meta['client_ai_scene_prompts']=beats
                        meta['client_ai_scene_weights']=scene_weights(detected_transcript,duration=audio_duration_seconds)
                        meta['client_ai_scene_count']=len(beats)
                        meta['client_ai_fallback']=True
                except AIVideoUnavailable:
                    pass
            update(job_id,state='done',percent=100,label='ההפקה מוכנה' if meta['video_status']=='done' else 'המיקס מוכן',engine='semantic_footage_with_original_asr_recovery_v5',asr_recovery_attempted=asr_recovery_attempted,asr_recovery_status=('recognized' if detected_origin=='server_original_asr' else 'unavailable' if asr_recovery_attempted else 'not_needed'),audio_seconds=round(audio_duration_seconds,2),voice_coverage='full',speech_timed=bool(transcript_timeline and any(transcript_timeline)),preset=options.get('style','mixed'),humor=options.get('humor','auto'),mix_variation=options.get('mix_variation',0),**meta)
        except AudioDecodeError as exc:
            # The decoder supplies only vetted Hebrew UI text, never raw
            # FFmpeg stderr or uploaded filenames.
            app.logger.warning('Kolbo processing input failure ref=%s stage=%s code=%s',
                               job_id[:10],stage,exc.code)
            update(job_id,state='error',message=str(exc),error_code=exc.code,
                   error_stage=stage,error_ref=job_id[:10])
        except ValueError as exc:
            # A ValueError may also be an internal DSP error. Never report
            # a 120-second violation unless the actual validation raised it.
            recognized={
                'לא נמצא קול בהקלטה':('no_audible_voice',
                    'לא זוהה קול בעוצמה מספקת בהקלטה. ודא שהקובץ כולל דיבור שניתן לשמוע.'),
                'הקלטה ריקה או לא תקינה':('invalid_audio',
                    'ההקלטה ריקה או מכילה שמע שלא ניתן לעבד.'),
                'סך הקלטות המקור חורג מחמש דקות':('combined_duration_exceeded',
                    'אורך הקלטות המקור יחד עולה על חמש דקות. ניתן לבחור עד ארבע הקלטות שסכומן עד 300 שניות.'),
                'משך ההקלטות הכולל גדול מדי לעיבוד חינמי':('combined_duration_exceeded',
                    'סך ההקלטות והעיבוד ארוך מדי עבור מנוע הענן החינמי.'),
            }
            code,message=recognized.get(str(exc),('mix_validation_error',
                'השרת נתקל בבעיה בבדיקת השמע או בהכנת המיקס. נסה קובץ מקור שניתן לנגן.'))
            app.logger.warning('Kolbo processing validation failure ref=%s stage=%s code=%s',
                               job_id[:10],stage,code)
            update(job_id,state='error',message=message,error_code=code,
                   error_stage=stage,error_ref=job_id[:10])
        except (subprocess.CalledProcessError,subprocess.TimeoutExpired,OSError):
            code='audio_export_failure' if stage=='export' else 'processing_io_failure'
            message=('נוצר המיקס, אך שמירת קובץ השמע נכשלה בשרת.'
                     if stage=='export' else
                     'מנוע העיבוד נתקל בתקלה בקריאת המדיה או בעיבוד השמע.')
            app.logger.exception('Kolbo processing I/O failure ref=%s stage=%s code=%s',
                                 job_id[:10],stage,code)
            update(job_id,state='error',message=message+' מזהה תקלה: '+job_id[:10],
                   error_code=code,error_stage=stage,error_ref=job_id[:10])
        except MemoryError:
            app.logger.exception('Kolbo processing memory failure ref=%s stage=%s',
                                 job_id[:10],stage)
            update(job_id,state='error',
                   message='שרת העיבוד הגיע למגבלת הזיכרון. נסה הקלטה קצרה יותר.',
                   error_code='memory_limit',error_stage=stage,error_ref=job_id[:10])
        except Exception:
            app.logger.exception('Kolbo audio/video worker error ref=%s stage=%s',
                                 job_id[:10],stage)
            update(job_id,state='error',
                   message='אירעה תקלה פנימית בשלב העיבוד ('+stage+'). מזהה תקלה: '+job_id[:10],
                   error_code='internal_processing_error',error_stage=stage,
                   error_ref=job_id[:10])
        finally:
            for p in paths:p.unlink(missing_ok=True)
            admission.release()
            queue_slots.release()

    @app.before_request
    def origin_check():
        if request.path.startswith('/api/'):
            origin=request.headers.get('Origin')
            allowed={v.strip().rstrip('/') for v in app.config['ALLOWED_ORIGINS'].split(',') if v.strip()}
            allowed.add(request.host_url.rstrip('/'))
            allowed.add('https://'+request.host)
            allowed.add('http://'+request.host)
            if origin and origin.rstrip('/') not in allowed:return jsonify(error='מקור הבקשה אינו מורשה'),403
            if request.method=='OPTIONS':return '',204
            if (request.path.startswith('/api/jobs') or request.path=='/api/import-link' or request.path=='/api/audio-tools/render') and not app.config.get('TESTING'):
                token=app.config['API_TOKEN']
                if not token:return jsonify(error='העיבוד בענן טרם הוגדר. ניתן לעבד במכשיר.'),503
                if not studio_session() and not secrets.compare_digest(request.headers.get('Authorization',''),'Bearer '+token):return jsonify(error='קוד הגישה אינו תקין'),401

    @app.after_request
    def headers(response):
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['Referrer-Policy']='no-referrer'
        origin=request.headers.get('Origin')
        if origin:
            response.headers['Access-Control-Allow-Origin']=origin
            response.headers['Vary']='Origin'
            response.headers['Access-Control-Allow-Headers']='Authorization, Content-Type'
            response.headers['Access-Control-Allow-Methods']='GET, POST, OPTIONS'
        if request.path.startswith('/api/'):response.headers['Cache-Control']='no-store'
        return response

    @app.errorhandler(RequestEntityTooLarge)
    def too_large(_):return jsonify(error='קובץ גדול מדי: עד 15MB להקלטת קול, 45MB לסרטון ו־60MB יחד.'),413

    @app.get('/health')
    def health():return jsonify(ok=True,service='kolbo-trance-studio',version='1.16.20',cloud_ready=bool(app.config['API_TOKEN']),asr_preloaded=bool(os.environ.get('KOLBO_ASR_DIR') and (Path(os.environ['KOLBO_ASR_DIR'])/'model.bin').is_file()))

    @app.get('/api/jobs/capacity')
    def job_capacity():
        """Check for one of two disk-spooled job slots, without uploading.

        Exactly one CPU worker runs at a time. A second job may wait on
        disk; this read-only probe avoids consuming mobile bandwidth while
        the one active and one queued slot are occupied. It never reserves
        a slot: the actual POST still atomically acquires admission.
        """
        available=queue_slots.acquire(blocking=False)
        if available:
            queue_slots.release()
        response=jsonify(available=available,maximum_jobs=2,
                         workers=1,queue_enabled=True)
        response.headers['Cache-Control']='no-store'
        if not available:response.headers['Retry-After']='5'
        return response

    @app.get('/api/capabilities')
    def capabilities():
        from engine_registry import catalog
        return jsonify(catalog())

    @app.post('/api/audio-tools/render')
    def audio_tools_render():
        from audio_tools import render_audio_tool, AudioToolError, SUPPORTED
        if not link_admission.acquire(blocking=False):
            return jsonify(error='מנוע האולפן עסוק כעת. ניתן לנסות שוב.'),429
        work=None
        try:
            if request.form.get('rights')!='yes':
                return jsonify(error='נדרש אישור הרשאות שימוש בקבצים.'),400
            mode=request.form.get('mode','master')
            sound=request.form.get('sound','balanced')
            try:
                voice_gain=int(request.form.get('voice_gain','100'))
                backing_gain=int(request.form.get('backing_gain','80'))
            except ValueError:
                return jsonify(error='ערכי עוצמה אינם תקינים.'),400
            first=request.files.get('source')
            second=request.files.get('voice')
            if not first or not first.filename:
                return jsonify(error='יש לבחור קובץ שמע או וידאו מקורי.'),400
            if mode=='mix' and (not second or not second.filename):
                return jsonify(error='למיקס יש לבחור גם קובץ קול שני.'),400
            work=Path(tempfile.mkdtemp(prefix='kolbo-audio-tools-',dir=root))
            files=[]
            for name,item in [('source',first),('voice',second)]:
                if name=='voice' and mode!='mix':continue
                if item is None:continue
                ext=Path(item.filename).suffix.lower()
                if ext not in SUPPORTED:return jsonify(error='פורמט הקובץ אינו נתמך.'),400
                limit=MAX_VIDEO_UPLOAD if ext in VIDEO_UPLOADS else MAX_AUDIO_UPLOAD
                data=item.stream.read(limit+1)
                if not data or len(data)>limit:return jsonify(error='הקובץ חורג ממגבלת הגודל.'),400
                path=work/(name+ext);path.write_bytes(data);files.append(path)
            dest=work/'mastered.mp3'
            render_audio_tool(files[0],dest,mode=mode,
                              voice=files[1] if len(files)>1 else None,
                              sound=sound,voice_gain=voice_gain,backing_gain=backing_gain)
            # send_file may be streamed by WSGI; do not remove it before
            # response close, otherwise the download disappears.
            response=stream_temporary_media(dest,'audio/mpeg',work)
            response.headers['Content-Disposition']='attachment; filename="Kolbo-Studio-Master.mp3"'
            work=None
            return response
        except AudioToolError as exc:
            return jsonify(error=str(exc)),422
        except OSError:
            app.logger.exception('Audio studio filesystem error')
            return jsonify(error='לא ניתן לשמור את קובץ האולפן.'),503
        finally:
            link_admission.release()
            if work:shutil.rmtree(work,ignore_errors=True)

    @app.post('/api/import-link')
    def import_social_link():
        # Triggered ONLY by clicking the explicit 'import link' control.
        # Public HTTPS social hosts only, without browser cookies or login.
        from link_import import fetch_public_social_media, LinkImportError
        raw=request.get_json(silent=True) or {}
        if not isinstance(raw,dict):
            return jsonify(error='בקשת הקישור אינה תקינה.'),400
        link=raw.get('url','')
        if not link_admission.acquire(blocking=False):
            return jsonify(error='ייבוא קישור אחר מתבצע כעת. אפשר לנסות שוב.'),429
        folder=None
        try:
            folder=Path(tempfile.mkdtemp(prefix='kolbo-social-',dir=root))
            output,mime=fetch_public_social_media(link,folder)
            response=stream_temporary_media(output,mime,folder)
            folder=None
            return response
        except LinkImportError as exc:
            # Log only numeric attempt count and fixed codes, NEVER full media
            # URL, cookies, video title, content or private token.
            trace=secrets.token_hex(4)
            app.logger.warning(
                'public_video_import_failed trace=%s code=%s attempts=%s steps=%s',
                trace,exc.code,exc.attempts,exc.steps or 'none')
            return jsonify(error=str(exc),code=exc.code,trace_id=trace),422
        except (OSError,subprocess.SubprocessError):
            app.logger.warning('Public link import failed; no user URL logged')
            return jsonify(error='ייבוא הקישור לא הושלם. אפשר לשתף קובץ מדיה ישירות.'),503
        finally:
            link_admission.release()
            if folder is not None:shutil.rmtree(folder,ignore_errors=True)

    @app.post('/api/jobs')
    def create_job():
        cleanup()
        files=request.files.getlist('audio')
        if not 1<=len(files)<=4:return jsonify(error='יש לבחור בין הקלטה אחת לארבע הקלטות'),400
        try:
            bpm=int(request.form.get('bpm',145));seconds=int(request.form.get('seconds',0));style=request.form.get('style','mixed');voice_level=float(request.form.get('voice_level',1));melody=request.form.get('melody','auto');humor=request.form.get('humor','auto');fx_intensity=int(request.form.get('fx_intensity',2));fx_gain=float(request.form.get('fx_gain',1.15));mix_variation=int(request.form.get('mix_variation',0));make_video=request.form.get('make_video','off')=='on';video_requested=request.form.get('video_requested','on' if make_video else 'off')=='on';transcription_failed=request.form.get('transcription_failed','off')=='on';transcript=request.form.get('transcript','')[:4000].strip();transcript_origin=request.form.get('transcript_origin','manual');source_hashes=request.form.get('source_hashes','');ai_video_consent=request.form.get('ai_video_consent','off')=='on';video_strategy=request.form.get('video_strategy','auto_legacy');music_license_ack=request.form.get('music_license_ack','off')=='on'
            if not 120<=bpm<=165 or seconds not in (0,30,60,90,120,180) or style not in ('melodic','psy','progressive','goa','acid','uplifting','eurodance','hard','rave','mixed','auto','israeli') or humor not in ('auto','classic','cartoon','scratch','robot','chaos','stretch','tape','pitch','glitch','vinyl','dj','helium','monster','yo_yo','comic_roll','rewind','telephone','echo','flanger','gate','ring','off') or melody not in ('auto','1','2','3','4','5','6') or fx_intensity not in (1,2,3) or not .55<=fx_gain<=1.7 or not 0<=mix_variation<=100000 or not .5<=voice_level<=1.5 or video_strategy not in ('new_story','illustrated_story','remix_original','auto_legacy'):raise ValueError()
        except (ValueError,TypeError):return jsonify(error='הגדרות המיקס אינן תקינות'),400
        # Never reject the upload before trying original-file server ASR.
        # If both ASR paths fail, finish the MP3 and report the MP4 limitation.
        if make_video and transcript_origin=='auto' and len(transcript.split())<2:
            transcript=''
        if transcript_origin not in ('auto','manual'):
            return jsonify(error='מקור התמלול אינו תקין'),400
        if any(Path(f.filename or '').suffix.lower() not in ALLOWED for f in files):return jsonify(error='סוג הקובץ אינו נתמך'),400
        backing_file=request.files.get('backing_music')
        if backing_file and backing_file.filename:
            if not music_license_ack:
                return jsonify(error='נדרש אישור זכויות שימוש בקובץ המוזיקה'),400
            if Path(backing_file.filename).suffix.lower() not in AUTHORIZED_MUSIC_EXT:
                return jsonify(error='קובץ מוזיקה אינו בפורמט נתמך'),400
        if not queue_slots.acquire(blocking=False):
            response=jsonify(error='כל מקומות התור תפוסים כרגע. הקובץ לא נקלט; אפשר לנסות שוב כשהתור יתפנה.')
            response.headers['Retry-After']='20'
            return response,429
        job_id=secrets.token_hex(24);directory=root/job_id;directory.mkdir(mode=0o700);paths=[]
        total_bytes=0
        try:
            for i,file in enumerate(files):
                extension=Path(file.filename).suffix.lower()
                size_limit=MAX_VIDEO_UPLOAD if extension in VIDEO_UPLOADS else MAX_AUDIO_UPLOAD
                # Validate the optional WhatsApp source fingerprint first,
                # then hash and spool each chunk as it arrives. A simultaneous
                # heavy mix can be running within the same 512 MiB instance.
                expected_hash=None
                if source_hashes:
                    hashes=source_hashes.split(',')
                    if len(hashes)!=len(files) or not re.fullmatch('[a-f0-9]{64}',hashes[i]):
                        raise ValueError('source_fingerprint_invalid')
                    expected_hash=hashes[i]
                path=directory/(str(i)+extension)
                saved=_save_upload_stream(
                    file.stream,path,size_limit,MAX_COMBINED_UPLOAD,
                    already_saved=total_bytes,expected_sha256=expected_hash)
                total_bytes+=saved
                paths.append(path)
        except ValueError as exc:
            queue_slots.release();shutil.rmtree(directory,ignore_errors=True)
            if str(exc).startswith('source_fingerprint'):
                return jsonify(error='קובץ המקור השתנה בין התמלול להעלאה. יש לשלוח שוב את ההקלטה המקורית.'),409
            return jsonify(error='גודל הקובץ אינו תקין: עד 15MB לשמע, 45MB לסרטון ו־60MB לכל הקבצים יחד'),400
        except Exception:
            queue_slots.release();shutil.rmtree(directory,ignore_errors=True)
            return jsonify(error='לא ניתן לקרוא את הקובץ המקורי'),400
        backing_music_path=None
        if backing_file and backing_file.filename:
            try:
                ext=Path(backing_file.filename).suffix.lower()
                backing_music_path=directory/('licensed-backing'+ext)
                _save_upload_stream(
                    backing_file.stream,backing_music_path,MAX_BACKING_UPLOAD,
                    MAX_COMBINED_UPLOAD,already_saved=total_bytes)
            except (OSError,ValueError):
                queue_slots.release();shutil.rmtree(directory,ignore_errors=True)
                return jsonify(error='המוזיקה או סך הקבצים חורגים ממגבלת ההעלאה המורשית'),400
        with lock:jobs[job_id]={'state':'queued','percent':0,'label':'ממתין לעיבוד','created':time.time(),'seconds':seconds,'bpm':bpm}
        executor.submit(work,job_id,paths,{'bpm':bpm,'seconds':seconds,'style':style,'voice_level':voice_level,'melody':melody,'humor':humor,'fx_intensity':fx_intensity,'fx_gain':fx_gain,'mix_variation':mix_variation,'make_video':make_video,'video_requested':video_requested,'transcription_failed':transcription_failed,'transcript':transcript,'transcript_origin':transcript_origin,'source_hashes':source_hashes,'ai_video_consent':ai_video_consent and video_requested,
             'video_strategy':video_strategy,'backing_music_path':backing_music_path,
             'music_license_ack':music_license_ack})
        return jsonify(id=job_id,status_url='/api/jobs/'+job_id),202

    @app.get('/api/jobs/<job_id>')
    def status(job_id):
        cleanup()
        with lock:job=dict(jobs[job_id]) if job_id in jobs else None
        if not job:return jsonify(error='המיקס לא נמצא או שתוקפו פג'),404
        job.pop('created',None)
        if job['state']=='done':
            job['download_url']='/api/jobs/'+job_id+'/audio'
            job['voice_url']='/api/jobs/'+job_id+'/voice'
            if job.get('video_status')=='done':
                job['video_url']='/api/jobs/'+job_id+'/video'
                job['video_preview_url']='/api/jobs/'+job_id+'/video_preview'
            if (root/job_id/'storyboard.json').exists():
                job['storyboard_url']='/api/jobs/'+job_id+'/storyboard'
        return jsonify(job)

    @app.get('/api/jobs/<job_id>/ai-plan')
    def ai_scene_plan(job_id):
        """Recover the ORIGINAL consented shot plan without re-uploading audio.

        A caller cannot request a plan for an unconsented job, and no remote
        AI provider is contacted by this read-only route. Job IDs are opaque
        high-entropy values, protected by the same session gate as status.
        """
        cleanup()
        if not re.fullmatch(r'[a-f0-9]{48}',job_id):
            return jsonify(error='מזהה המיקס אינו תקין'),404
        with lock:
            job=jobs.get(job_id)
            if not job:return jsonify(error='המיקס לא נמצא או שתוקפו פג'),404
            if job.get('state')!='done':
                return jsonify(error='המיקס עדיין בעיבוד'),409
            if (not job.get('client_ai_fallback') or
                    not job.get('client_ai_prompt') or
                    job.get('video_status')=='done'):
                return jsonify(error='אין תוכנית וידאו בהסכמת המשתמש למשימה זו'),403
            prompts=job.get('client_ai_scene_prompts',[])
            weights=job.get('client_ai_scene_weights',[])
            count=job.get('client_ai_scene_count',0)
        if (not isinstance(prompts,list) or not 1<=len(prompts)<=24 or
                count!=len(prompts) or
                any(not isinstance(p,str) or not 20<len(p)<2000 for p in prompts) or
                not isinstance(weights,list) or len(weights)!=len(prompts)):
            return jsonify(error='תוכנית סצנות מקורית אינה זמינה'),422
        return jsonify(prompts=prompts,scene_count=len(prompts),
                       weights=weights),200

    @app.post('/api/jobs/<job_id>/ai-clips')
    def accept_direct_phone_generated_clips(job_id):
        """Use original AI-video BYTES from the phone, not a remote download URL.

        Render Free may be unable to retrieve a Gradio clip after creation;
        the phone network already fetched the MP4 successfully. Limit bytes,
        codecs, dimensions, clip count, retries and CPU work.
        """
        cleanup()
        if not re.fullmatch(r'[a-f0-9]{48}',job_id):
            return jsonify(error='מזהה המיקס אינו תקין'),404
        with lock:
            job=jobs.get(job_id)
            if not job or job.get('state')!='done':
                return jsonify(error='המיקס אינו זמין או שתוקפו פג'),404
            if not job.get('client_ai_fallback') or not job.get('client_ai_prompt'):
                return jsonify(error='לא ניתנה הסכמה להעברת תמלול לשירות AI'),403
            if job.get('video_status')=='done':
                return jsonify(error='סרטון כבר הוכן למשימה זו'),409
            if job.get('ai_client_busy'):
                return jsonify(error='יצירת הסרטון כבר בתהליך'),409
            if job.get('ai_client_upload_attempts',0)>=3:
                return jsonify(error='הסתיימה מכסת ניסיונות שילוב הווידאו למשימה'),429
            job['ai_client_busy']=True
        if not admission.acquire(blocking=False):
            # A busy server is NOT a failed phone upload. Do not consume a
            # limited video-finalization attempt before any bytes were read.
            with lock:
                if job_id in jobs:jobs[job_id]['ai_client_busy']=False
            response=jsonify(error='השרת עסוק כרגע; קטעי הווידאו שלך לא אבדו, אפשר לנסות שוב')
            response.headers['Retry-After']='6'
            return response,429
        with lock:
            if job_id in jobs:
                jobs[job_id]['ai_client_upload_attempts']=(
                    jobs[job_id].get('ai_client_upload_attempts',0)+1)
        work_dir=root/job_id/'mobile-ai-upload'
        try:
            from client_ai_fallback import (combine_mobile_ai_clips,
                                            MobileClipError,MAX_CLIP_BYTES,
                                            MAX_AI_UPLOAD_BYTES)
            clips=request.files.getlist('clip')
            from client_ai_fallback import MAX_CLIPS
            if not 1<=len(clips)<=MAX_CLIPS:
                return jsonify(error='ניתן להעלות עד 24 קטעי וידאו לסיפור'),400
            work_dir.mkdir(parents=True,exist_ok=True,mode=0o700)
            inputs=[]
            total_uploaded=0
            for i,clip in enumerate(clips):
                data=clip.stream.read(MAX_CLIP_BYTES+1)
                if not 12000<=len(data)<=MAX_CLIP_BYTES or data[4:8]!=b'ftyp':
                    return jsonify(error='הווידאו שהתקבל אינו MP4 אמיתי או גדול מדי'),400
                total_uploaded+=len(data)
                if total_uploaded>MAX_AI_UPLOAD_BYTES:
                    return jsonify(error='סך סצנות הווידאו גדול מ־58MB'),413
                src=work_dir/f'generated-source-{i}.mp4'
                src.write_bytes(data)
                inputs.append(src)
            planned=int(job.get('client_ai_scene_count',0))
            if planned and len(clips)!=planned:
                return jsonify(error='לא הופקו כל הסצנות המקוריות. לא נמחזר קליפ קצר'),422
            output=root/job_id/'story.mp4'
            # Durations reflect relative spoken word counts in each scene,
            # instead of forcing every scene to have the same screen time.
            with lock:
                weights=list(jobs.get(job_id,{}).get('client_ai_scene_weights',[]))
            board=combine_mobile_ai_clips(
                inputs,root/job_id/'mix.mp3',output,work_dir/'encode',
                weights=weights[:len(inputs)] if len(weights)>=len(inputs) else None)
            board['transcript_origin']=job.get('transcript_origin','server_original_asr')
            (root/job_id/'storyboard.json').write_text(
                json.dumps(board,ensure_ascii=False),encoding='utf-8')
            with lock:
                current=jobs.get(job_id)
                if current is None:
                    output.unlink(missing_ok=True)
                    return jsonify(error='תוקף המיקס פג'),404
                current.pop('video_error',None)
                current.pop('client_ai_prompt',None)
                current.pop('client_ai_scene_prompts',None)
                current.pop('client_ai_scene_weights',None)
                current.update(
                    video_status='done',
                    video_mode='ai_generated_client_fallback',
                    storyboard_source=board['source'],
                    visual_coverage='approximate',
                    visual_beats=board['ai_clips_generated'],
                    client_ai_fallback=False,
                    ai_clips_generated=board['ai_clips_generated'],
                    ai_clip_seconds=board['ai_clip_seconds'],
                    video_note=(
                        'נוצרו '+str(board['ai_clips_generated'])+
                        ' סצנות AI עם '+str(board['ai_clip_seconds'])+
                        ' שניות תנועה מקורית ברצף, ללא לולאות. '+
                        'המחשת המילים עדיין משוערת.'),
                    label='סרטון ה־AI והמיקס מוכנים')
            return jsonify(video_url='/api/jobs/'+job_id+'/video',
                           video_preview_url='/api/jobs/'+job_id+'/video_preview',
                           video_status='done',
                           video_mode='ai_generated_client_fallback',
                           visual_coverage='approximate',
                           video_note=(
                               'נוצרו '+str(board['ai_clips_generated'])+
                               ' סצנות AI עם '+str(board['ai_clip_seconds'])+
                               ' שניות תנועה מקורית, ללא חזרת קליפים.'),
                           storyboard_url='/api/jobs/'+job_id+'/storyboard',
                           ai_clips_generated=board['ai_clips_generated']),200
        except MobileClipError as exc:
            return jsonify(error=str(exc)),422
        except Exception:
            app.logger.exception('Direct phone-generated AI video mux failed')
            return jsonify(error='שילוב הווידאו נכשל. המיקס המקורי נשמר.'),500
        finally:
            shutil.rmtree(work_dir,ignore_errors=True)
            with lock:
                if job_id in jobs:jobs[job_id]['ai_client_busy']=False
            admission.release()

    @app.post('/api/jobs/<job_id>/generated-video')
    def finalize_browser_generated_video(job_id):
        """Authenticated, consent-only, bounded upload of a phone-generated shot.

        Rendering is done on the original Render server, but anonymous AI
        compute is requested from the phone's public Gradio quota. MP3/voice
        downloads remain intact if an unsafe or invalid video is supplied.
        """
        cleanup()
        if not re.fullmatch(r'[a-f0-9]{48}',job_id):
            return jsonify(error='המשימה אינה תקינה'),404
        with lock:
            job=jobs.get(job_id)
            if not job or job.get('state')!='done':
                return jsonify(error='המיקס לא נמצא או שתוקפו פג'),404
            if not job.get('client_ai_fallback') or not job.get('client_ai_prompt'):
                return jsonify(error='לא ניתנה הרשאה ליצירת וידאו AI במכשיר'),403
            if job.get('video_status')=='done':
                return jsonify(error='כבר קיים סרטון מוכן'),409
            if job.get('ai_client_busy'):
                return jsonify(error='הסרטון נמצא כעת בעיבוד'),409
            job['ai_client_busy']=True
        workdir=root/job_id
        original=workdir/'device-ai-original.mp4'
        prepared=workdir/'device-ai-prepared.mp4'
        result=workdir/'story.mp4'
        try:
            if request.is_json:
                # Most phones only need to POST the file URL; the Render
                # server downloads bytes from precisely the two verified
                # Gradio hosts. No mobile video bandwidth is wasted.
                supplied=(request.get_json(silent=True) or {}).get('video_url','')
                if not isinstance(supplied,str) or len(supplied)>1200:
                    return jsonify(error='כתובת סרטון אינה תקינה'),400
                from ai_video import _download_public_video, AIVideoUnavailable
                try:
                    _download_public_video(supplied,original)
                except AIVideoUnavailable:
                    return jsonify(error='הקובץ שיצר שירות ה־AI אינו זמין להורדה מאובטחת'),422
            else:
                upload=request.files.get('video')
                if not upload:
                    return jsonify(error='קובץ וידאו לא צורף'),400
                # Optional direct upload is for devices where the provider's
                # file URL has already expired. Never trust client filenames.
                raw=upload.stream.read(14*1024*1024+1)
                if len(raw)<12000 or len(raw)>14*1024*1024 or raw[4:8]!=b'ftyp':
                    return jsonify(error='קובץ הווידאו שנוצר אינו תקין או גדול מדי'),400
                original.write_bytes(raw)
            from live_video import _duration, _video_profile, _make_segment
            try:
                codec,width,height=_video_profile(original)
                clip_seconds=_duration(original)
                if (codec not in ('h264','hevc','vp9','vp8','av1') or
                    not 160<=width<=1536 or not 160<=height<=1536 or
                    not .7<=clip_seconds<=12):
                    raise ValueError('invalid_generated_media')
                audio_seconds=_duration(workdir/'mix.mp3')
                if not 1<=audio_seconds<=360:
                    raise ValueError('invalid_soundtrack_duration')
                if clip_seconds+.12<audio_seconds:
                    return jsonify(error='קליפ AI יחיד קצר מהמיקס. כדי לא לחזור על אותה שנייה, יש ליצור כמה סצנות שונות.'),422
                _make_segment(original,prepared,audio_seconds,allow_loop=False)
                subprocess.run(['ffmpeg','-nostdin','-hide_banner','-loglevel','error',
                    '-y','-i',str(prepared),'-i',str(workdir/'mix.mp3'),
                    '-map','0:v:0','-map','1:a:0','-c:v','copy','-c:a','aac',
                    '-b:a','160k','-shortest','-movflags','+faststart',
                    str(result)],capture_output=True,check=True,timeout=65)
                if (_video_profile(result)!=('h264',360,640) or
                    abs(_duration(result)-audio_seconds)>.8 or
                    result.stat().st_size<25000):
                    raise ValueError('invalid_final_movie')
            except (OSError,ValueError,RuntimeError,subprocess.SubprocessError):
                app.logger.warning('Phone-generated AI clip failed local media validation')
                result.unlink(missing_ok=True)
                return jsonify(error='לא ניתן לשלב את קליפ ה־AI עם המיקס. המוזיקה נשמרה.'),422
            board={
                'source':'ai_generated_from_private_original_narration_on_phone',
                'transcript_origin':job.get('transcript_origin','server_original_asr'),
                'visual_coverage':'approximate',
                'video_mode':'ai_generated_on_device',
                'ai_clips_generated':1,'ai_clip_seconds':round(clip_seconds,2),
                'audio_seconds':round(audio_seconds,2),
                'sources':[],
                'video_note':'קליפ AI חדש נוצר דרך המכשיר מתוך תמלול הדיבור. '
                             'הקטע אינו מורחב בלולאה. אין הבטחה להתאמה סמנטית מושלמת.'
            }
            (workdir/'storyboard.json').write_text(
                json.dumps(board,ensure_ascii=False),encoding='utf-8')
            with lock:
                job.update(video_status='done',video_mode='ai_generated_on_device',
                           visual_coverage='approximate',visual_beats=1,
                           ai_clips_generated=1,ai_clip_seconds=round(clip_seconds,2),
                           video_note=board['video_note'])
                job.pop('client_ai_prompt',None)
                job.pop('client_ai_fallback',None)
            return jsonify(video_status='done',video_mode='ai_generated_on_device',
                visual_coverage='approximate',video_note=board['video_note'],
                video_url='/api/jobs/'+job_id+'/video',
                video_preview_url='/api/jobs/'+job_id+'/video_preview',
                storyboard_url='/api/jobs/'+job_id+'/storyboard'),200
        finally:
            original.unlink(missing_ok=True)
            prepared.unlink(missing_ok=True)
            with lock:
                if job_id in jobs:jobs[job_id]['ai_client_busy']=False

    @app.get('/api/jobs/<job_id>/audio')
    def download(job_id):
        cleanup()
        with lock:ready=jobs.get(job_id,{}).get('state')=='done'
        path=root/job_id/'mix.mp3'
        if not ready or not path.is_file():return jsonify(error='המיקס לא זמין'),404
        return send_file(path,mimetype='audio/mpeg',as_attachment=True,download_name='Kolbo-Trance-Mix.mp3')

    @app.get('/api/jobs/<job_id>/voice')
    def vocal_preview(job_id):
        cleanup()
        with lock:ready=jobs.get(job_id,{}).get('state')=='done'
        path=root/job_id/'voice.mp3'
        if not ready or not path.is_file():
            return jsonify(error='הקול המעובד לא זמין'),404
        return send_file(path,mimetype='audio/mpeg',as_attachment=False,
                         download_name='Kolbo-Voice-Effects.mp3')

    @app.get('/api/jobs/<job_id>/video')
    def video(job_id):
        cleanup()
        with lock:ready=jobs.get(job_id,{}).get('video_status')=='done'
        path=root/job_id/'story.mp4'
        if not ready or not path.is_file():return jsonify(error='סרטון עדיין לא זמין'),404
        return send_file(path,mimetype='video/mp4',as_attachment=True,
                         download_name='Kolbo-Trance-Animated-Story.mp4')

    @app.get('/api/jobs/<job_id>/video_preview')
    def video_preview(job_id):
        cleanup()
        with lock:ready=jobs.get(job_id,{}).get('video_status')=='done'
        path=root/job_id/'story.mp4'
        if not ready or not path.is_file():return jsonify(error='סרטון לא זמין'),404
        return send_file(path,mimetype='video/mp4',as_attachment=False,
                         conditional=True,download_name='Kolbo-Trance-Story.mp4')

    @app.get('/api/jobs/<job_id>/storyboard')
    def story_details(job_id):
        cleanup()
        with lock:exists=job_id in jobs
        path=root/job_id/'storyboard.json'
        if not exists or not path.is_file():return jsonify(error='סטוריבורד לא נמצא'),404
        return send_file(path,mimetype='application/json',as_attachment=False)

    @app.get('/install')
    def install_page():
        response=send_from_directory(web,'install.html')
        response.headers['Cache-Control']='no-store'
        return response

    @app.get('/studio')
    def studio():
        response=send_from_directory(web,'studio.html')
        response.headers['Cache-Control']='no-store'
        if app.config['API_TOKEN']:
            response.set_cookie('kolbo_studio',session_codec().dumps('studio'),max_age=86400,httponly=True,secure=True,samesite='Lax',path='/')
        return response
    @app.get('/studio.webmanifest')
    def studio_manifest():return send_file(web/'studio.webmanifest',mimetype='application/manifest+json')
    @app.get('/studio-sw.js')
    def studio_sw():
        response=send_file(web/'studio-sw.js',mimetype='application/javascript')
        response.headers['Service-Worker-Allowed']='/'
        response.headers['Cache-Control']='no-store'
        return response
    @app.get('/studio-job-recovery.js')
    def studio_job_recovery_script():
        response=send_file(web/'studio-job-recovery.js',mimetype='application/javascript')
        response.headers['Cache-Control']='no-store'
        return response

    @app.get('/studio-ai-fallback.js')
    def studio_ai_fallback_script():
        response=send_file(web/'studio-ai-fallback.js',mimetype='application/javascript')
        response.headers['Cache-Control']='no-store'
        return response
    @app.get('/studio-asr-worker.js')
    def studio_asr_worker():
        response=send_file(web/'studio-asr-worker.js',mimetype='application/javascript')
        response.headers['Cache-Control']='no-store'
        return response
    @app.get('/studio-icon.svg')
    def studio_icon():return send_file(web/'studio-icon.svg',mimetype='image/svg+xml')

    @app.get('/')
    def index():
        if os.environ.get('API_ONLY')=='1':return jsonify(service='kolbo-trance-studio',ok=True)
        return send_from_directory(static,'index.html')
    @app.get('/<path:name>')
    def asset(name):return send_from_directory(static,name)
    return app

app=create_app()
