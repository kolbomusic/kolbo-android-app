"""Bounded, temporary audio jobs. Run one WSGI worker; threads share admission state."""
import os, time, secrets, shutil, threading, json, subprocess, hashlib, re
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from flask import Flask, request, jsonify, send_file, send_from_directory
from werkzeug.exceptions import RequestEntityTooLarge
from itsdangerous import URLSafeTimedSerializer, BadSignature
from engine import load_audio, render_mix, export_mp3
from storyboard import align_storyboard_to_vocal
from live_video import visual_plan, export_live_story, UnavailableVideo


ALLOWED={'.opus','.ogg','.oga','.mp3','.wav','.m4a','.aac','.mp4','.webm','.flac'}

def create_app(config=None):
    app=Flask(__name__,static_folder=None)
    app.config.update(MAX_CONTENT_LENGTH=64*1024*1024,JOB_DIR=os.environ.get('JOB_DIR','/tmp/kolbo-trance-jobs'),API_TOKEN=os.environ.get('API_TOKEN',''),ALLOWED_ORIGINS=os.environ.get('ALLOWED_ORIGINS','https://kolbo-trance-studio.happyblimp1.chatgpt.site'),JOB_TTL=3600)
    if config:app.config.update(config)
    root=Path(app.config['JOB_DIR']);root.mkdir(parents=True,exist_ok=True)
    jobs={};private_ai_plans={};lock=threading.Lock();admission=threading.BoundedSemaphore(2);executor=ThreadPoolExecutor(max_workers=1)
    static=Path(__file__).resolve().parents[1]/'dist'
    web=Path(__file__).resolve().parents[1]/'web'
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
            for k in expired:
                jobs.pop(k,None);private_ai_plans.pop(k,None)
                shutil.rmtree(root/k,ignore_errors=True)
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
        try:
            update(job_id,state='processing',percent=4,label='קורא את ההקלטות')
            # Run ASR recovery against the ORIGINAL files before removing them.
            # A failed browser model cannot cancel a user's explicit MP4 request.
            detected_transcript=(options.get('transcript') or '').strip()
            detected_origin='browser_source_asr' if detected_transcript else 'unavailable'
            transcript_complete=True
            asr_recovery_error=''
            asr_recovery_attempted=bool(options.get('video_requested') and len(detected_transcript.split())<2)
            if asr_recovery_attempted:
                update(job_id,percent=5,label='מנסה תמלול נוסף מההקלטה המקורית בשרת')
                try:
                    from source_asr import transcribe_original_files, SourceTranscriptionUnavailable
                    detected_transcript,transcript_complete=transcribe_original_files(
                        paths,progress=lambda label:update(job_id,label=label))
                    detected_origin='server_original_asr'
                except Exception as exc:
                    # Transcription is a best-effort subtask. A decoder/library
                    # incompatibility must NEVER destroy the finished MP3.
                    asr_recovery_error=str(exc)[:180]
                    app.logger.exception('Original-file ASR failed; keeping the requested audio job alive')
            clips=[load_audio(p) for p in paths]
            audio_options={k:v for k,v in options.items() if k not in ('make_video','transcript','transcript_origin','video_requested','transcription_failed','source_hashes','ai_video_consent')}
            audio,vocal=render_mix(clips,**audio_options,return_voice=True,
                                   progress=lambda p,label:update(job_id,percent=p,label=label))
            export_mp3(audio,root/job_id/'mix.mp3')
            export_mp3(vocal,root/job_id/'voice.mp3')
            meta={'video_status':'disabled','storyboard_source':'not_requested'}
            if options.get('video_requested'):
                update(job_id,percent=87,label='בודק התאמה בין המשפטים לצילומי וידאו',
                       video_status='processing')
                if not detected_transcript or len(detected_transcript.split())<2:
                    meta={'video_status':'unavailable',
                          'video_error':'נוסו תמלול במכשיר ובשרת, אך לא זוהו מילים מספיק אמינות מההקלטה המקורית. '+asr_recovery_error,
                          'storyboard_source':'original_asr_failed',
                          'visual_coverage':'none'}
                else:
                    ai_generation_error=''
                    if options.get('ai_video_consent'):
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
                                      'הקטע נוצר באמצעות AI מתוך תמלול ההקלטה. '
                                      'זו המחשה משוערת, לא שחזור מדויק של כל משפט. '
                                      'סצנות AI קצרות עשויות לחזור לאורך המיקס; '
                                      'השירות החינמי מוגבל.')}
                        except AIVideoUnavailable as err:
                            ai_generation_error=str(err)[:180]
                            app.logger.warning('Free AI video unavailable: %s',
                                               type(err).__name__)
                            (root/job_id/'story.mp4').unlink(missing_ok=True)
                        except Exception:
                            ai_generation_error='שירות יצירת הווידאו הניסיוני לא הצליח'
                            app.logger.exception('Experimental AI video failed')
                            (root/job_id/'story.mp4').unlink(missing_ok=True)
                    if meta.get('video_status')!='done':
                        try:
                            board=visual_plan(detected_transcript,len(audio)/32000)
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
                            # Job diagnostics without storing user speech, audio, or file names.
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
            # If server-originated free GPU calls were rejected, the user's
            # *consented* Android WebView can request public AI clips directly
            # over CORS and upload ONLY generated video here for soundtrack mux.
            # Store prompt privately in memory, NEVER in the public job status.
            if (options.get('ai_video_consent') and options.get('video_requested')
                    and meta['video_status']!='done' and detected_transcript):
                try:
                    from ai_video import _narrative_shots, cinematic_prompt
                    prompts=[cinematic_prompt(s) for s in
                             _narrative_shots(detected_transcript)[:2]]
                    if prompts:
                        with lock:
                            private_ai_plans[job_id]={'prompts':prompts,
                                'consented':True,'uploading':False,
                                'upload_attempts':0}
                        meta['client_ai_fallback_available']=True
                except (ValueError,RuntimeError):
                    pass
            update(job_id,state='done',percent=100,label='ההפקה מוכנה' if meta['video_status']=='done' else 'המיקס מוכן',engine='semantic_footage_with_original_asr_recovery_v5',asr_recovery_attempted=asr_recovery_attempted,asr_recovery_status=('recognized' if detected_origin=='server_original_asr' else 'unavailable' if asr_recovery_attempted else 'not_needed'),audio_seconds=round(len(audio)/32000,2),voice_coverage='full',preset=options.get('style','mixed'),humor=options.get('humor','auto'),mix_variation=options.get('mix_variation',0),**meta)
        except Exception:
            app.logger.exception('Kolbo audio/video worker error')
            update(job_id,state='error',message='לא ניתן לעבד את הקובץ. הקלטה אחת עד 120 שניות, ועד ארבע הקלטות יחד.')
        finally:
            for p in paths:p.unlink(missing_ok=True)
            admission.release()

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
            if request.path.startswith('/api/jobs') and not app.config.get('TESTING'):
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
    def too_large(_):return jsonify(error='הקבצים גדולים מדי. עד 15MB לכל הקלטה.'),413

    @app.get('/health')
    def health():return jsonify(ok=True,service='kolbo-trance-studio',version='1.14.0',cloud_ready=bool(app.config['API_TOKEN']),asr_preloaded=bool(os.environ.get('KOLBO_ASR_DIR') and (Path(os.environ['KOLBO_ASR_DIR'])/'model.bin').is_file()))

    @app.post('/api/jobs')
    def create_job():
        cleanup()
        files=request.files.getlist('audio')
        if not 1<=len(files)<=4:return jsonify(error='יש לבחור בין הקלטה אחת לארבע הקלטות'),400
        try:
            bpm=int(request.form.get('bpm',145));seconds=int(request.form.get('seconds',0));style=request.form.get('style','mixed');voice_level=float(request.form.get('voice_level',1));melody=request.form.get('melody','auto');humor=request.form.get('humor','auto');fx_intensity=int(request.form.get('fx_intensity',2));fx_gain=float(request.form.get('fx_gain',1.15));mix_variation=int(request.form.get('mix_variation',0));make_video=request.form.get('make_video','off')=='on';video_requested=request.form.get('video_requested','on' if make_video else 'off')=='on';transcription_failed=request.form.get('transcription_failed','off')=='on';transcript=request.form.get('transcript','')[:4000].strip();transcript_origin=request.form.get('transcript_origin','manual');source_hashes=request.form.get('source_hashes','');ai_video_consent=request.form.get('ai_video_consent','off')=='on'
            if not 120<=bpm<=165 or seconds not in (0,30,60,90,120,180) or style not in ('melodic','psy','progressive','goa','acid','uplifting','eurodance','hard','rave','mixed','auto') or humor not in ('auto','classic','cartoon','scratch','robot','chaos','stretch','tape','pitch','glitch','vinyl','dj','helium','monster','yo_yo','comic_roll','rewind','off') or melody not in ('auto','1','2','3','4','5','6') or fx_intensity not in (1,2,3) or not .55<=fx_gain<=1.7 or not 0<=mix_variation<=100000 or not .5<=voice_level<=1.5:raise ValueError()
        except (ValueError,TypeError):return jsonify(error='הגדרות המיקס אינן תקינות'),400
        # Never reject the upload before trying original-file server ASR.
        # If both ASR paths fail, finish the MP3 and report the MP4 limitation.
        if make_video and transcript_origin=='auto' and len(transcript.split())<2:
            transcript=''
        if transcript_origin not in ('auto','manual'):
            return jsonify(error='מקור התמלול אינו תקין'),400
        if any(Path(f.filename or '').suffix.lower() not in ALLOWED for f in files):return jsonify(error='סוג הקובץ אינו נתמך'),400
        if not admission.acquire(blocking=False):return jsonify(error='השרת עסוק כרגע. נסו שוב בעוד רגע או בחרו עיבוד במכשיר.'),429
        job_id=secrets.token_hex(24);directory=root/job_id;directory.mkdir(mode=0o700);paths=[]
        try:
            for i,file in enumerate(files):
                content=file.stream.read(15*1024*1024+1)
                if not content or len(content)>15*1024*1024:raise ValueError('גודל הקובץ אינו תקין: עד 15MB')
                # Fingerprint the exact original file received from WhatsApp
                # or device storage. This is used to check that the voice ASR
                # and mixing pipeline operate on the SAME uploaded bytes.
                if source_hashes:
                    hashes=source_hashes.split(',')
                    if len(hashes)!=len(files) or not re.fullmatch('[a-f0-9]{64}',hashes[i]):
                        raise ValueError('source_fingerprint_invalid')
                    if hashlib.sha256(content).hexdigest()!=hashes[i]:
                        raise ValueError('source_fingerprint_mismatch')
                path=directory/(str(i)+Path(file.filename).suffix.lower());path.write_bytes(content);paths.append(path)
        except ValueError as exc:
            admission.release();shutil.rmtree(directory,ignore_errors=True)
            if str(exc).startswith('source_fingerprint'):
                return jsonify(error='קובץ המקור השתנה בין התמלול להעלאה. יש לשלוח שוב את ההקלטה המקורית.'),409
            return jsonify(error='קובץ ריק או גדול מ־15MB'),400
        except Exception:
            admission.release();shutil.rmtree(directory,ignore_errors=True)
            return jsonify(error='לא ניתן לקרוא את הקובץ המקורי'),400
        with lock:jobs[job_id]={'state':'queued','percent':0,'label':'ממתין לעיבוד','created':time.time(),'seconds':seconds,'bpm':bpm}
        executor.submit(work,job_id,paths,{'bpm':bpm,'seconds':seconds,'style':style,'voice_level':voice_level,'melody':melody,'humor':humor,'fx_intensity':fx_intensity,'fx_gain':fx_gain,'mix_variation':mix_variation,'make_video':make_video,'video_requested':video_requested,'transcription_failed':transcription_failed,'transcript':transcript,'transcript_origin':transcript_origin,'source_hashes':source_hashes,'ai_video_consent':ai_video_consent and video_requested})
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
    def mobile_ai_plan(job_id):
        """Only the holder of the original studio session can request prompts.

        This does not expose speech content in the ordinary status endpoint,
        logs or storyboard. The consent checkbox was submitted with the
        original job; a caller cannot switch it on after uploading the voice.
        """
        cleanup()
        if not re.fullmatch(r'[a-f0-9]{48}',job_id):
            return jsonify(error='מזהה המשימה אינו תקין'),404
        with lock:
            job=jobs.get(job_id,{})
            private=private_ai_plans.get(job_id)
            ready=(job.get('state')=='done' and
                   job.get('video_status')!='done' and private is not None and
                   private.get('consented'))
            prompts=list(private.get('prompts',[])) if ready else []
            duration=job.get('audio_seconds',0)
        if not ready:return jsonify(error='השלמת סרטון AI אינה זמינה למשימה זו או שלא ניתנה הסכמה'),403
        return jsonify(prompts=prompts,seconds=duration,
                       external_provider_notice='רק טקסט התמלול מועבר לשירות AI ציבורי',
                       max_clips=2)

    @app.post('/api/jobs/<job_id>/ai-clips')
    def upload_mobile_ai_clips(job_id):
        """Receive generated MP4 *bytes*, never arbitrary URLs.

        Same-origin studio session/API key required by before_request.
        Clip bodies and FFmpeg work are bounded; only jobs with prior
        explicit third-party AI consent are eligible.
        """
        cleanup()
        if not re.fullmatch(r'[a-f0-9]{48}',job_id):
            return jsonify(error='מזהה המשימה אינו תקין'),404
        with lock:
            job=jobs.get(job_id,{})
            private=private_ai_plans.get(job_id)
            if not (job.get('state')=='done' and private and
                    private.get('consented') and job.get('video_status')!='done'):
                return jsonify(error='המשימה אינה זמינה להשלמת וידאו או שלא ניתנה הסכמה'),403
            if private['uploading'] or private['upload_attempts']>=3:
                return jsonify(error='ניסיון העלאת הווידאו כבר מתבצע או שהמכסה הסתיימה'),429
            private['uploading']=True
            private['upload_attempts']+=1
        if not admission.acquire(blocking=False):
            with lock:
                if job_id in private_ai_plans:
                    private_ai_plans[job_id]['uploading']=False
            return jsonify(error='השרת עסוק, ניתן לנסות שוב'),429
        work_dir=root/job_id/'mobile-ai-upload'
        try:
            from client_ai_fallback import (combine_mobile_ai_clips,
                                            MobileClipError,MAX_CLIP_BYTES)
            clips=request.files.getlist('clip')
            if not 1<=len(clips)<=2:
                return jsonify(error='יש להעלות קטע וידאו אחד או שניים'),400
            work_dir.mkdir(parents=True,exist_ok=True,mode=0o700)
            input_paths=[]
            for i,clip in enumerate(clips):
                raw=clip.stream.read(MAX_CLIP_BYTES+1)
                if not 12000<=len(raw)<=MAX_CLIP_BYTES or raw[4:8]!=b'ftyp':
                    return jsonify(error='הווידאו שהתקבל ממנוע ה־AI אינו MP4 תקין או גדול מדי'),400
                source=work_dir/f'original-generated-{i}.mp4'
                source.write_bytes(raw)
                input_paths.append(source)
            out=root/job_id/'story.mp4'
            board=combine_mobile_ai_clips(input_paths,
                                          root/job_id/'mix.mp3',
                                          out,work_dir/'encoding')
            (root/job_id/'storyboard.json').write_text(
                json.dumps(board,ensure_ascii=False),encoding='utf-8')
            with lock:
                if job_id not in jobs:
                    out.unlink(missing_ok=True)
                    return jsonify(error='תוקף משימת המיקס פג'),404
                jobs[job_id].pop('video_error',None)
                jobs[job_id].update(
                    video_status='done',
                    video_mode='ai_generated_client_fallback',
                    storyboard_source=board['source'],
                    visual_coverage='approximate',
                    visual_beats=board['ai_clips_generated'],
                    client_ai_fallback_available=False,
                    ai_clips_generated=board['ai_clips_generated'],
                    ai_clip_seconds=board['ai_clip_seconds'],
                    video_note='סצנות AI חדשות נוצרו מהתמלול בהסכמה. זו המחשה משוערת; קטעים קצרים עשויים לחזור לאורך המיקס.',
                    label='הסרטון והמיקס מוכנים')
                private_ai_plans.pop(job_id,None)
            return jsonify(video_url='/api/jobs/'+job_id+'/video',
                           video_preview_url='/api/jobs/'+job_id+'/video_preview',
                           video_status='done',
                           video_mode='ai_generated_client_fallback',
                           visual_coverage='approximate',
                           video_note='סרטון AI שנוצר מהתמלול; המחשה משוערת, לא שחזור מדויק של כל המשפטים.',
                           storyboard_url='/api/jobs/'+job_id+'/storyboard',
                           ai_clips_generated=board['ai_clips_generated']),200
        except MobileClipError as exc:
            return jsonify(error=str(exc)),422
        except Exception:
            app.logger.exception('Browser-produced AI clip assembly failed')
            return jsonify(error='שילוב סרטון ה־AI והמיקס נכשל, אך קובץ המיקס נשמר'),500
        finally:
            shutil.rmtree(work_dir,ignore_errors=True)
            with lock:
                if job_id in private_ai_plans:
                    private_ai_plans[job_id]['uploading']=False
            admission.release()

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
