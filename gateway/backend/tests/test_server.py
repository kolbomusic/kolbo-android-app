import base64, json, os, pathlib, sys, tempfile
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import server
from fastapi.testclient import TestClient

client=TestClient(server.app)


def setup_module():
    server.TOKEN='supersecretlongerthan24characters123456789'
    server.jobs.clear()


def headers():return {'Authorization':'Bearer '+server.TOKEN}


def workflow(tmp):
    p=tmp/'workflow_api.json'
    p.write_text(json.dumps({'1':{'class_type':'CLIPTextEncode','inputs':{'text':'__KOLBO_PROMPT__'}},
      '2':{'class_type':'LoadImage','inputs':{'image':'__KOLBO_IMAGE1__'}},
      '3':{'class_type':'LoadImage','inputs':{'image':'__KOLBO_IMAGE2__'}},
      '4':{'class_type':'TemporalNode','inputs':{'frames':'__KOLBO_FRAMES__','fps':'__KOLBO_FPS__'}}}))
    return p


def test_auth_is_required():
    assert client.get('/v1/health').status_code==401
    assert client.get('/v1/health',headers={'Authorization':'Bearer wrong'}).status_code==401


def test_health_truthfully_not_ready(monkeypatch):
    monkeypatch.setattr(server,'template_available',lambda n=0:False)
    monkeypatch.setattr(server,'gpu_available',lambda:False)
    r=client.get('/v1/health',headers=headers())
    assert r.status_code==200
    assert r.json()['status']=='not_ready'
    assert r.json()['unlimited_compute'] is False
    q=client.post('/v1/jobs',json={'prompt':'שתי דמויות רוקדות','seconds':10},headers=headers())
    assert q.status_code==503


def test_template_binds_two_distinct_images_and_requested_duration(tmp_path,monkeypatch):
    monkeypatch.setitem(server.WORKFLOW_BY_IMAGE_COUNT,2,workflow(tmp_path))
    spec=server.JobSpec(prompt='two people sing onstage',seconds=10,images=[],fps=24)
    w=server.prepare_workflow(spec,['first.png','second.png'])
    assert w['2']['inputs']['image']=='first.png'
    assert w['3']['inputs']['image']=='second.png'
    assert w['4']['inputs']['frames']==server.frame_count(10,24)
    assert w['4']['inputs']['fps']==24
    assert w['1']['inputs']['text']=='two people sing onstage'


def test_missing_reference_slot_rejected(tmp_path,monkeypatch):
    p=tmp_path/'workflow.json'
    p.write_text(json.dumps({'a':{'inputs':{'prompt':'__KOLBO_PROMPT__','length':'__KOLBO_FRAMES__'}}}))
    monkeypatch.setitem(server.WORKFLOW_BY_IMAGE_COUNT,2,p)
    try:
        server.prepare_workflow(server.JobSpec(prompt='people on stage',seconds=10),['img1.jpg','img2.jpg'])
    except ValueError as e:
        assert '__KOLBO_IMAGE2__' in str(e)
    else:raise AssertionError('missing second image slot was accepted')


def test_binary_magic_not_mime_claim():
    good=server.Picture(mime_type='image/jpeg',data_base64=base64.b64encode(b'\xff\xd8\xff'+b'x'*150).decode())
    assert server.validate_image(good).startswith(b'\xff\xd8\xff')
    bad=server.Picture(mime_type='image/jpeg',data_base64=base64.b64encode(b'NOT_A_JPEG'+b'x'*150).decode())
    try:server.validate_image(bad)
    except ValueError:pass
    else:raise AssertionError('invalid image accepted')


def test_result_missing_video_is_rejected():
    try:server.get_video({'foo':{'outputs':{'9':{'images':[{'filename':'x.png'}]}}}},'foo')
    except ValueError:pass
    else:raise AssertionError('image-only result was accepted as video')


def test_end_to_end_mocked_comfyui_uses_real_ffprobe(tmp_path,monkeypatch):
    import subprocess, time
    video=tmp_path/'sample.mp4'
    subprocess.run(['ffmpeg','-nostdin','-hide_banner','-loglevel','error','-y',
      '-f','lavfi','-i','testsrc2=size=320x192:rate=24',
      '-t','2','-pix_fmt','yuv420p','-an','-movflags','+faststart',str(video)],check=True)
    monkeypatch.setitem(server.WORKFLOW_BY_IMAGE_COUNT,2,workflow(tmp_path))
    monkeypatch.setattr(server,'WORK_DIR',tmp_path/'results')
    monkeypatch.setattr(server,'gpu_available',lambda:True)
    def mock_request(method,path,data=None,ctype=None,timeout=25):
        if path=='/prompt':
            payload=json.loads(data)
            assert payload['prompt']['4']['inputs']['frames']==server.frame_count(2,24)
            assert payload['prompt']['2']['inputs']['image']=='im1.png'
            assert payload['prompt']['3']['inputs']['image']=='im2.png'
            return b'{"prompt_id":"pid-12"}'
        if path.startswith('/upload/image'):
            calls=mock_request.__dict__.setdefault('calls',0)
            mock_request.calls=calls+1
            return json.dumps({'name':'im1.png' if calls==0 else 'im2.png'}).encode()
        if path.startswith('/history/'):
            return json.dumps({'pid-12':{'outputs':{'27':{'videos':[{'filename':'sample.mp4','type':'output','subfolder':''}]}}}}).encode()
        if path.startswith('/view?'):return video.read_bytes()
        raise AssertionError(path)
    monkeypatch.setattr(server,'comfy_request',mock_request)
    # An authentic test MP4 is used to validate the byte and duration paths,
    # not to claim actual AI image/video inference.
    photo=base64.b64encode(b'\xff\xd8\xff'+b'X'*150).decode()
    req={'prompt':'two people singing on the stage','seconds':2,'images':[
        {'mime_type':'image/jpeg','data_base64':photo},
        {'mime_type':'image/jpeg','data_base64':photo}]}
    response=client.post('/v1/jobs',json=req,headers=headers())
    assert response.status_code==202,response.text
    job_id=response.json()['job_id']
    for _ in range(60):
        data=client.get('/v1/jobs/'+job_id,headers=headers()).json()
        if data['state'] in ('completed','failed'):break
        time.sleep(.05)
    assert data['state']=='completed',data
    reply=client.get('/v1/jobs/'+job_id+'/result',headers=headers())
    assert reply.status_code==200 and reply.content[4:8]==b'ftyp'
