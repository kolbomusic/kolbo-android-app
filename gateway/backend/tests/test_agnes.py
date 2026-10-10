"""Mock-API integration checks; NO REAL AGNES GENERATION IS CLAIMED."""
import base64
import json
import pathlib
import sys
import subprocess
import time
from urllib.parse import urlsplit
import pytest
from fastapi.testclient import TestClient
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import server
import agnes_adapter as agnes
client=TestClient(server.app)
AUTH='a_private_kolbo_token_longer_than_24_chars'

@pytest.fixture(autouse=True)
def config(tmp_path,monkeypatch):
    monkeypatch.setattr(server,'TOKEN',AUTH)
    monkeypatch.setattr(server,'RENDER_PROVIDER','agnes')
    monkeypatch.setattr(server,'AGNES_KEY','agnes-demo-test-credential-long-enough')
    monkeypatch.setattr(server,'AGNES_PROMO_ACK',True)
    monkeypatch.setattr(server,'PUBLIC_BASE','https://video.example.com')
    monkeypatch.setattr(server,'WORK_DIR',tmp_path)
    server.jobs.clear()
    server.refs.clear()
    yield
    server.refs.clear()
    server.jobs.clear()

def headers():return {'Authorization':'Bearer '+AUTH}
def pictures():
    photo_a=base64.b64encode(b'\xff\xd8\xff'+b'A'*500).decode()
    photo_b=base64.b64encode(b'\xff\xd8\xff'+b'B'*700).decode()
    return [{'mime_type':'image/jpeg','data_base64':photo_a},
            {'mime_type':'image/jpeg','data_base64':photo_b}]

def test_gateway_not_ready_with_missing_key(monkeypatch):
    monkeypatch.setattr(server,'AGNES_KEY','')
    ready=client.get('/v1/health',headers=headers()).json()
    assert ready['status']=='not_ready'
    assert 'מפתח Agnes' in ready['detail']
    r=client.post('/v1/jobs',headers=headers(),json={'prompt':'Two singers on stage','seconds':10})
    assert r.status_code==503


def test_gateway_honest_provenance():
    ready=client.get('/v1/health',headers=headers()).json()
    assert ready['status']=='ready'
    assert ready['provider']=='agnes-video-2.5-flash'
    assert ready['unlimited_credits'] is False
    assert ready['unlimited_compute'] is False
    assert ready['price_promotion_verified_live'] is False
    assert ready['min_seconds']==4 and ready['max_seconds']==12


def test_duration_guard_and_token_route():
    for seconds in (1,3,13,60):
        resp=client.post('/v1/jobs',json={'prompt':'Two people singing','seconds':seconds},headers=headers())
        assert resp.status_code==422, resp.text
    assert client.get('/v1/media/not-a-valid-token').status_code==404
    assert client.get('/v1/health').status_code==401


def test_agnes_request_includes_flash_reference_urls_with_distinct_slots():
    a=agnes.video_payload('sing together',10,['https://video.example.com/v1/media/a',
                                              'https://video.example.com/v1/media/b'])
    assert a['model']=='agnes-video-2.5-flash'
    assert a['mode']=='reference'
    assert a['seconds']=='10' and a['size']=='720P'
    assert a['images'][0]!=a['images'][1]
    assert '<Picture 1>' in a['prompt'] and '<Picture 2>' in a['prompt']
    assert 'agnes-video-2.5' not in (a['model'],)
    b=agnes.video_payload('cat in forest',8,[])
    assert b['mode']=='text' and 'images' not in b
    for bad in (1,2,3,13,60):
        with pytest.raises(ValueError):agnes.video_payload('good prompt',bad,[])


def make_video(path, seconds):
    subprocess.run(['ffmpeg','-hide_banner','-nostdin','-loglevel','error','-y',
        '-f','lavfi','-i','testsrc2=size=320x192:rate=24','-t',str(seconds),
        '-pix_fmt','yuv420p','-an','-movflags','+faststart',str(path)],check=True)


def test_mocked_ten_second_reference_request_cleanup_and_ffprobe(tmp_path,monkeypatch):
    video=tmp_path/'fixture.mp4'
    make_video(video,10)
    calls=[]
    def fake_submit(prompt,seconds,urls,key):
        calls.append(('submit',seconds,list(urls)))
        assert seconds==10
        assert len(urls)==2 and urls[0]!=urls[1]
        assert key.startswith('agnes-demo-test')
        assert len(server.refs)==2
        image_bytes=[]
        for index,url in enumerate(urls):
            parts=urlsplit(url)
            assert parts.scheme=='https' and parts.netloc=='video.example.com'
            route=parts.path
            response=client.get(route)  # Provider fetch needs no phone bearer token.
            assert response.status_code==200
            assert response.headers['cache-control'].startswith('no-store')
            image_bytes.append(response.content)
        assert image_bytes[0]!=image_bytes[1]
        return 'video_123456'
    def fake_poll(video_id,key,deadline,progress):
        calls.append(('poll',video_id))
        progress('מפיק סרטון דרך Agnes · 30%')
        return 'https://cdn.example.com/result.mp4'
    def fake_download(url):
        calls.append(('download',url))
        return video.read_bytes()
    monkeypatch.setattr(agnes,'submit',fake_submit)
    monkeypatch.setattr(agnes,'poll',fake_poll)
    monkeypatch.setattr(agnes,'download_mp4',fake_download)
    payload={'prompt':'Two reference people sing together on Caesarea stage',
             'seconds':10,'images':pictures()}
    response=client.post('/v1/jobs',json=payload,headers=headers())
    assert response.status_code==202,response.text
    job_id=response.json()['job_id']
    for _ in range(100):
        state=client.get('/v1/jobs/'+job_id,headers=headers()).json()
        if state['state'] in ('completed','failed'):break
        time.sleep(.02)
    assert state['state']=='completed', state
    downloaded=client.get('/v1/jobs/'+job_id+'/result',headers=headers())
    assert downloaded.status_code==200 and downloaded.content[4:8]==b'ftyp'
    assert [p[0] for p in calls]==['submit','poll','download']
    assert not server.refs
    assert not list((tmp_path/'refs').glob('*'))


def test_short_video_is_never_accepted(tmp_path,monkeypatch):
    short=tmp_path/'short.mp4';make_video(short,3)
    monkeypatch.setattr(agnes,'submit',lambda *a:'video_valid')
    monkeypatch.setattr(agnes,'poll',lambda *a:'https://cdn.example.com/demo.mp4')
    monkeypatch.setattr(agnes,'download_mp4',lambda *a:short.read_bytes())
    response=client.post('/v1/jobs',json={'prompt':'two singers','seconds':10,'images':pictures()},headers=headers())
    jobid=response.json()['job_id']
    for _ in range(100):
        state=client.get('/v1/jobs/'+jobid,headers=headers()).json()
        if state['state'] in ('failed','completed'):break
        time.sleep(.02)
    assert state['state']=='failed',state
    assert '3.00' in state['error'] and '10' in state['error']
    assert client.get('/v1/jobs/'+jobid+'/result',headers=headers()).status_code==409
    assert not server.refs


def test_quota_rejection_visible_and_no_provider_fallback(monkeypatch):
    monkeypatch.setattr(agnes,'submit',lambda *a:(_ for _ in ()).throw(agnes.AgnesError('video_queue_full · תור מלא')))
    response=client.post('/v1/jobs',json={'prompt':'two people sing on stage','seconds':10},headers=headers())
    jobid=response.json()['job_id']
    for _ in range(100):
        state=client.get('/v1/jobs/'+jobid,headers=headers()).json()
        if state['state'] in ('failed','completed'):break
        time.sleep(.02)
    assert state['state']=='failed'
    assert 'תור מלא' in state['error']
    assert not server.refs


def test_public_ref_expires(tmp_path,monkeypatch):
    token,url=server.stage_reference('abcd',1,b'\xff\xd8\xffabc','image/jpeg')
    assert client.get('/v1/media/'+token).status_code==200
    server.refs[token].expires=time.monotonic()-1
    assert client.get('/v1/media/'+token).status_code==404
    server.prune_expired_jobs()
    assert token not in server.refs and not list((tmp_path/'refs').glob('*'))


def test_block_private_result_urls(monkeypatch):
    for url in ('http://example.com/abc.mp4','https://127.0.0.1/a.mp4',
                'https://169.254.169.254/latest/meta-data',
                'https://localhost/result.mp4','https://user:pwd@example.com/a.mp4'):
        with pytest.raises(agnes.AgnesError):agnes.validate_download_url(url)
