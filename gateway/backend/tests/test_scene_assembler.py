"""Real FFmpeg assembly of fixture videos; NOT real AI model generation."""
from pathlib import Path
import shutil,subprocess
import pytest
import scene_assembler as assembly

pytestmark=pytest.mark.skipif(
    not shutil.which('ffmpeg') or not shutil.which('ffprobe'),
    reason='FFmpeg required for media integration tests')

def create_clip(target:Path,sec:float,freq:int,audio=True):
    target.parent.mkdir(parents=True,exist_ok=True)
    cmd=['ffmpeg','-nostdin','-hide_banner','-loglevel','error','-y',
         '-f','lavfi','-i','testsrc2=size=256x144:rate=24']
    if audio:
        cmd+=['-f','lavfi','-i',f'sine=frequency={freq}:sample_rate=48000']
    cmd+=['-t',str(sec),'-c:v','libx264','-preset','ultrafast',
           '-threads','2','-pix_fmt','yuv420p']
    if audio:cmd+=['-c:a','aac','-b:a','96k']
    else:cmd+=['-an']
    cmd+=['-movflags','+faststart',str(target)]
    subprocess.run(cmd,check=True,capture_output=True,timeout=45)
    return target

def test_two_separate_scenes_have_one_continuous_audio_video_file(tmp_path):
    source=tmp_path/'sources'
    first=create_clip(source/'scene_1.mp4',1.5,440)
    second=create_clip(source/'scene_2.mp4',1.5,660)
    result=assembly.join(source,[
       assembly.SourceClip(0,first,1500),
       assembly.SourceClip(1,second,1500),
    ],tmp_path/'finished',size=(320,180))
    assert result.path.exists()
    assert result.clip_count==2
    assert result.expected_ms==3000
    assert abs(result.measured_ms-3000)<=500
    assert result.audio_present is True
    assert result.identity_verified is False
    assert result.lipsync_verified is False
    assert result.cross_scene_continuity_verified is False
    data=result.path.read_bytes()
    assert data[4:8]==b'ftyp'

def test_missing_audio_is_rejected_before_output(tmp_path):
    source=tmp_path/'sources'
    silent=create_clip(source/'silent.mp4',1.0,440,audio=False)
    with pytest.raises(assembly.AssemblyError,match='audio is missing'):
        assembly.join(source,[assembly.SourceClip(0,silent,1000)],
                      tmp_path/'done',size=(320,180))
    assert not list((tmp_path/'done').glob('*.mp4')) if (tmp_path/'done').exists() else True

def test_scene_shorter_than_requested_never_accepted(tmp_path):
    source=tmp_path/'sources'
    short=create_clip(source/'three_seconds.mp4',1.0,440)
    with pytest.raises(assembly.AssemblyError,match='length differs'):
        assembly.join(source,[assembly.SourceClip(0,short,3000)],
                      tmp_path/'finished',size=(320,180))

def test_malicious_path_outside_private_workspace_is_rejected(tmp_path):
    private=tmp_path/'private'
    private.mkdir()
    outside=create_clip(tmp_path/'other.mp4',1.0,440)
    with pytest.raises(assembly.AssemblyError,match='outside private staging'):
        assembly.join(private,[assembly.SourceClip(0,outside,1000)],
                      tmp_path/'done',size=(320,180))

def test_order_or_duplicate_scenes_rejected(tmp_path):
    private=tmp_path/'private'
    first=create_clip(private/'scene.mp4',1.0,440)
    with pytest.raises(assembly.AssemblyError,match='Duplicate'):
        assembly.join(private,[assembly.SourceClip(0,first,1000),
                               assembly.SourceClip(0,first,1000)],
                      tmp_path/'done',size=(320,180))
    with pytest.raises(assembly.AssemblyError,match='contiguous'):
        assembly.join(private,[assembly.SourceClip(1,first,1000)],
                      tmp_path/'done',size=(320,180))


def test_assembly_cannot_overwrite_existing_customer_delivery(tmp_path):
    source=tmp_path/'sources'
    a=create_clip(source/'a.mp4',1.0,440)
    destination=tmp_path/'done'
    first=assembly.join(source,[assembly.SourceClip(0,a,1000)],
       destination,size=(320,180),output_basename='job_a.mp4')
    original=first.path.read_bytes()
    with pytest.raises(assembly.AssemblyError,match='already exists'):
        assembly.join(source,[assembly.SourceClip(0,a,1000)],
          destination,size=(320,180),output_basename='job_a.mp4')
    assert first.path.read_bytes()==original
