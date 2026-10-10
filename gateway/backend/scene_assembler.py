"""Deterministic assembly of ALREADY-GENERATED scene clips, with real FFmpeg QA.

STAGING: Does not produce AI footage, lip-sync or face identity consistency.
It normalizes video/audio codecs before joining, then rejects silent, short or
corrupt output. Never claims semantic audiovisual continuity from a container
probe. The only sources allowed are private local MP4s within an allowed folder.
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import json,os,subprocess,tempfile

class AssemblyError(RuntimeError): pass

@dataclass(frozen=True)
class SourceClip:
    index:int
    path:Path
    expected_ms:int

@dataclass(frozen=True)
class Assembled:
    path:Path
    clip_count:int
    expected_ms:int
    measured_ms:int
    audio_present:bool
    identity_verified:bool=False
    lipsync_verified:bool=False
    cross_scene_continuity_verified:bool=False

def _ffprobe(source:Path)->dict:
    args=['ffprobe','-v','error','-show_entries',
          'format=duration:stream=index,codec_type,width,height',
          '-of','json',str(source)]
    try:
        p=subprocess.run(args,check=True,capture_output=True,
                         text=True,timeout=25)
        return json.loads(p.stdout)
    except (ValueError,subprocess.SubprocessError,OSError) as error:
        raise AssemblyError('Invalid or unreadable video media') from error

def _probe_audio_video(source:Path)->tuple[int,bool]:
    info=_ffprobe(source)
    streams=info.get('streams',[])
    if not any(x.get('codec_type')=='video' for x in streams):
        raise AssemblyError('Video stream missing')
    has_audio=any(x.get('codec_type')=='audio' for x in streams)
    try: duration=float(info['format']['duration'])
    except (KeyError,TypeError,ValueError) as e:
        raise AssemblyError('Video duration unavailable') from e
    if not 0.02<duration<=360:
        raise AssemblyError('Media duration out of bounds')
    return round(duration*1000),has_audio

def join(source_directory:Path,clips:list[SourceClip],output_directory:Path,
         *,require_audio:bool=True,
         output_basename:str='finished_video.mp4',
         size:tuple[int,int]=(640,360),fps:int=24)->Assembled:
    """Render a single MP4 from sequential clips. Audio normalization ensures
    one continuous audio track but *does not* guarantee voice/timing correctness.
    Caller separately approves identity/lip-sync via execution_guard.
    """
    if not 1<=len(clips)<=12:raise AssemblyError('Unsupported clip count')
    if len(set(c.index for c in clips))!=len(clips):
        raise AssemblyError('Duplicate clip index')
    if [c.index for c in clips]!=list(range(len(clips))):
        raise AssemblyError('Scenes must be contiguous and in order')
    if size[0]%2 or size[1]%2 or not 144<=size[1]<=1080:
        raise AssemblyError('Invalid target video dimensions')
    if not 12<=fps<=30:raise AssemblyError('Invalid output frame rate')
    if not output_basename.endswith('.mp4') or '/' in output_basename or '..' in output_basename:
        raise AssemblyError('Invalid output filename')
    allowed=source_directory.resolve(strict=True)
    inputs=[]
    expected=0
    for clip in clips:
        path=clip.path.resolve(strict=True)
        if not path.is_relative_to(allowed) or path==allowed:
            raise AssemblyError('Source file outside private staging directory')
        if path.suffix.lower()!='.mp4' or not path.is_file():
            raise AssemblyError('Source must be a local MP4')
        if path.stat().st_size<1000 or path.stat().st_size>300*1024*1024:
            raise AssemblyError('Source size out of bounds')
        with path.open('rb') as f:magic=f.read(12)
        if magic[4:8]!=b'ftyp':raise AssemblyError('Invalid MP4 signature')
        if not 100<=clip.expected_ms<=120000:
            raise AssemblyError('Expected scene duration invalid')
        actual,has_audio=_probe_audio_video(path)
        if abs(actual-clip.expected_ms)>500:
            raise AssemblyError('Source length differs from storyboarding target')
        if require_audio and not has_audio:
            raise AssemblyError('Requested audio is missing in a scene')
        inputs.append((path,has_audio))
        expected+=clip.expected_ms
    output_directory.mkdir(parents=True,exist_ok=True,mode=0o700)
    directory=output_directory.resolve(strict=True)
    fd,temporary=tempfile.mkstemp(prefix='.kolbo-assembling-',
                                  suffix='.mp4',dir=directory)
    os.close(fd)
    try:
        command=['ffmpeg','-nostdin','-hide_banner','-loglevel','error','-y']
        for path,_ in inputs:command.extend(['-i',str(path)])
        filters=[]
        concat_parts=[]
        width,height=size
        for i,(path,has_audio) in enumerate(inputs):
            filters.append(
                f'[{i}:v:0]scale={width}:{height}:force_original_aspect_ratio=decrease,'
                f'pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black,'
                f'fps={fps},setsar=1,format=yuv420p[v{i}]')
            concat_parts.append(f'[v{i}]')
            if require_audio:
                filters.append(
                    f'[{i}:a:0]aresample=48000,'
                    'aformat=sample_fmts=fltp:channel_layouts=stereo'
                    f'[a{i}]')
                concat_parts.append(f'[a{i}]')
        audio_flag=1 if require_audio else 0
        filters.append(''.join(concat_parts)+
               f'concat=n={len(inputs)}:v=1:a={audio_flag}[outv]'+
               ('[outa]' if require_audio else ''))
        command.extend(['-filter_complex',';'.join(filters),
                        '-map','[outv]'])
        if require_audio:command.extend(['-map','[outa]'])
        command.extend(['-c:v','libx264','-preset','veryfast','-crf','23',
                        '-threads','2','-pix_fmt','yuv420p','-movflags','+faststart'])
        if require_audio:command.extend(['-c:a','aac','-b:a','160k'])
        else:command.append('-an')
        command.extend([temporary])
        try:
            subprocess.run(command,check=True,capture_output=True,
                           timeout=min(900,90+expected//1000*3))
        except (OSError,subprocess.SubprocessError) as error:
            raise AssemblyError('FFmpeg could not join the supplied scenes') from error
        actual,has_audio=_probe_audio_video(Path(temporary))
        if abs(actual-expected)>500:
            raise AssemblyError('Final assembled duration does not match planned length')
        if require_audio and not has_audio:
            raise AssemblyError('Final output unexpectedly has no audio')
        target=directory/output_basename
        os.replace(temporary,target)
        return Assembled(target,len(clips),expected,actual,has_audio)
    finally:
        Path(temporary).unlink(missing_ok=True)
