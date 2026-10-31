"""Bounded, temporary audio jobs. Run one WSGI worker; threads share admission state."""
import os, time, secrets, shutil, threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from flask import Flask, request, jsonify, send_file, send_from_directory
from werkzeug.exceptions import RequestEntityTooLarge
from itsdangerous import URLSafeTimedSerializer, BadSignature
from engine import load_audio, render_mix, export_mp3

ALLOWED={'.opus','.ogg','.oga','.mp3','.wav','.m4a','.aac','.mp4','.webm','.flac'}

def create_app(config=None):
    app=Flask(__name__,static_folder=None)
    app.config.update(MAX_CONTENT_LENGTH=64*1024*1024,JOB_DIR=os.environ.get('JOB_DIR','/tmp/kolbo-trance-jobs'),API_TOKEN=os.environ.get('API_TOKEN',''),ALLOWED_ORIGINS=os.environ.get('ALLOWED_ORIGINS','https://kolbo-trance-studio.happyblimp1.chatgpt.site'),JOB_TTL=3600)
    if config:app.config.update(config)
    root=Path(app.config['JOB_DIR']);root.mkdir(parents=True,exist_ok=True)
    jobs={};lock=threading.Lock();admission=threading.BoundedSemaphore(2);executor=ThreadPoolExecutor(max_workers=1)
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
        try:
            update(job_id,state='processing',percent=4,label='קורא את ההקלטות')
            clips=[load_audio(p) for p in paths]
            audio,vocal=render_mix(clips,**options,return_voice=True,
                                   progress=lambda p,label:update(job_id,percent=p,label=label))
            export_mp3(audio,root/job_id/'mix.mp3')
            export_mp3(vocal,root/job_id/'voice.mp3')
            update(job_id,state='done',percent=100,label='המיקס מוכן',engine='harmonic_quality_v3',audio_seconds=round(len(audio)/32000,2),voice_coverage='full',preset=options.get('style','mixed'),humor=options.get('humor','auto'))
        except Exception:
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
    def health():return jsonify(ok=True,service='kolbo-trance-studio',version='1.2.0',cloud_ready=bool(app.config['API_TOKEN']))

    @app.post('/api/jobs')
    def create_job():
        cleanup()
        files=request.files.getlist('audio')
        if not 1<=len(files)<=4:return jsonify(error='יש לבחור בין הקלטה אחת לארבע הקלטות'),400
        try:
            bpm=int(request.form.get('bpm',145));seconds=int(request.form.get('seconds',0));style=request.form.get('style','mixed');voice_level=float(request.form.get('voice_level',1));melody=request.form.get('melody','auto');humor=request.form.get('humor','auto');fx_intensity=int(request.form.get('fx_intensity',2))
            if not 120<=bpm<=165 or seconds not in (0,30,60,90,120,180) or style not in ('melodic','psy','progressive','goa','acid','uplifting','eurodance','hard','rave','mixed','auto') or humor not in ('auto','classic','cartoon','scratch','robot','chaos','stretch','tape','pitch','glitch','vinyl','dj','off') or melody not in ('auto','1','2','3','4','5','6') or fx_intensity not in (1,2,3) or not .5<=voice_level<=1.5:raise ValueError()
        except (ValueError,TypeError):return jsonify(error='הגדרות המיקס אינן תקינות'),400
        if any(Path(f.filename or '').suffix.lower() not in ALLOWED for f in files):return jsonify(error='סוג הקובץ אינו נתמך'),400
        if not admission.acquire(blocking=False):return jsonify(error='השרת עסוק כרגע. נסו שוב בעוד רגע או בחרו עיבוד במכשיר.'),429
        job_id=secrets.token_hex(24);directory=root/job_id;directory.mkdir(mode=0o700);paths=[]
        try:
            for i,file in enumerate(files):
                content=file.stream.read(15*1024*1024+1)
                if not content or len(content)>15*1024*1024:raise ValueError('גודל הקובץ אינו תקין: עד 15MB')
                path=directory/(str(i)+Path(file.filename).suffix.lower());path.write_bytes(content);paths.append(path)
        except Exception:
            admission.release();shutil.rmtree(directory,ignore_errors=True)
            return jsonify(error='קובץ ריק או גדול מ־15MB'),400
        with lock:jobs[job_id]={'state':'queued','percent':0,'label':'ממתין לעיבוד','created':time.time(),'seconds':seconds,'bpm':bpm}
        executor.submit(work,job_id,paths,{'bpm':bpm,'seconds':seconds,'style':style,'voice_level':voice_level,'melody':melody,'humor':humor,'fx_intensity':fx_intensity})
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
        return jsonify(job)

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
