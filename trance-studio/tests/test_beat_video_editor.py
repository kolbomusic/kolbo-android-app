"""Audio-sync and visible-edit regression tests for user's REAL WhatsApp video."""
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from beat_video_editor import edit_decisions, compose_edited_original_video


class BeatVideoEditTests(unittest.TestCase):
    def test_timeline_has_real_musical_cuts_and_multiple_shot_styles(self):
        bpm=145
        decisions=edit_decisions(30,bpm,9.0,'כולם צוחקים ואז האיש נפל')
        self.assertGreaterEqual(len(decisions),4)
        self.assertLessEqual(len(decisions),8)
        self.assertAlmostEqual(sum(x['duration'] for x in decisions),30,delta=.05)
        self.assertGreater(len(set(x['zoom'] for x in decisions)),2)
        self.assertGreater(len(set(x['speed'] for x in decisions)),2)
        self.assertTrue(all(x['duration']>.1 for x in decisions))
        self.assertTrue(all(.8<=x['speed']<=1.2 for x in decisions))
        # Cuts before the final one should align to bar boundaries.
        bar=240./bpm
        for x in decisions[:-1]:
            end=x['start']+x['duration']
            self.assertLess(abs(end/bar-round(end/bar)),.02)

    def test_real_mp4_contains_multiple_edited_shots_and_original_mix(self):
        with tempfile.TemporaryDirectory() as d:
            root=pathlib.Path(d)
            source=root/'whatsapp-original.mp4'
            music=root/'trance.mp3'
            out=root/'edited-story.mp4'
            subprocess.run([
                'ffmpeg','-nostdin','-v','error','-y','-f','lavfi',
                '-i','testsrc2=size=360x640:rate=12:duration=4',
                '-c:v','libx264','-preset','ultrafast','-pix_fmt','yuv420p',
                str(source)],check=True,timeout=25)
            subprocess.run([
                'ffmpeg','-nostdin','-v','error','-y','-f','lavfi',
                '-i','sine=frequency=250:duration=9',
                '-c:a','libmp3lame',str(music)],check=True,timeout=25)
            meta=compose_edited_original_video(source,music,out,root/'work',
                                                 bpm=145,transcript_hint='החמור נוער ובום')
            self.assertEqual(meta['video_edit_style'],
                             'beat_cut_punch_in_speed_ramp')
            self.assertGreaterEqual(meta['video_edit_shots'],3)
            self.assertGreater(out.stat().st_size,20000)
            probe=json.loads(subprocess.check_output([
                'ffprobe','-v','error','-show_streams','-show_format',
                '-of','json',str(out)],timeout=20))
            tracks={x['codec_type']:x for x in probe['streams']}
            self.assertEqual(set(tracks),{'audio','video'})
            self.assertEqual((tracks['video']['codec_name'],
                              tracks['video']['width'],tracks['video']['height']),
                             ('h264',360,640))
            self.assertGreater(float(probe['format']['duration']),8.5)
            self.assertLess(float(probe['format']['duration']),10.)
            # Decode two shots and show that the generated output was
            # actually spatially reframed, rather than just audio dubbed.
            def frame(movie,seconds):
                return subprocess.check_output([
                    'ffmpeg','-nostdin','-v','error','-ss',str(seconds),
                    '-i',str(movie),'-frames:v','1',
                    '-vf','scale=40:64,format=gray','-f','rawvideo','-'],
                    timeout=15)
            first=frame(out,.6)
            second=frame(out,3.)
            self.assertEqual(len(first),40*64)
            self.assertEqual(len(second),40*64)
            change=sum(abs(x-y) for x,y in zip(first,second))/len(first)
            self.assertGreater(change,1.6)



    def test_fx_video_shots_map_to_actual_voice_and_stretch_cues(self):
        from beat_video_editor import sync_edit_decisions
        cues=[
            {'kind':'voice','source_file':0,'start':1.655,'end':3.2,
             'source_seek':0.0,'effect':'stretch','intensity':3},
            {'kind':'voice_fx','source_file':0,'start':3.2,'end':3.9,
             'source_seek':1.2,'effect':'stretch','intensity':3},
            {'kind':'voice','source_file':0,'start':3.9,'end':6.7,
             'source_seek':1.55,'effect':'stretch','intensity':3},
        ]
        scenes=sync_edit_decisions(8.,145,5.,cues,
                                  humor='stretch',fx_intensity=3)
        self.assertGreaterEqual(len(scenes),5)
        self.assertEqual([s['kind'] for s in scenes[:3]],
                         ['music','voice','voice_fx'])
        slow=next(s for s in scenes if s['kind']=='voice_fx')
        self.assertAlmostEqual(slow['start'],3.2,places=2)
        self.assertAlmostEqual(slow['duration'],.7,places=2)
        self.assertLess(slow['speed'],1)
        self.assertEqual(slow['look'],'stretch')
        self.assertAlmostEqual(sum(s['duration'] for s in scenes),8.,delta=.1)
        self.assertEqual(sync_edit_decisions(8,145,5,cues,
                         source_file_index=1),[])

    def test_real_motion_video_warps_and_slows_at_audio_fx_timestamps(self):
        from beat_video_editor import compose_edited_original_video
        with tempfile.TemporaryDirectory() as d:
            root=pathlib.Path(d)
            source=root/'moving-person-source.mp4'
            music=root/'full-mix.mp3'
            out=root/'synced-effects.mp4'
            subprocess.run(['ffmpeg','-nostdin','-v','error','-y',
                '-f','lavfi','-i','testsrc2=size=360x640:rate=12:duration=5',
                '-c:v','libx264','-preset','ultrafast','-pix_fmt','yuv420p',
                str(source)],check=True,timeout=25)
            subprocess.run(['ffmpeg','-nostdin','-v','error','-y',
                '-f','lavfi','-i','sine=frequency=250:duration=8',
                '-c:a','libmp3lame',str(music)],check=True,timeout=25)
            cues=[
                {'kind':'voice','source_file':0,'start':1.655,'end':3.2,
                 'source_seek':0.,'effect':'stretch','intensity':3},
                {'kind':'voice_fx','source_file':0,'start':3.2,'end':3.9,
                 'source_seek':1.2,'effect':'stretch','intensity':3},
                {'kind':'voice','source_file':0,'start':3.9,'end':6.7,
                 'source_seek':1.55,'effect':'stretch','intensity':3},
            ]
            meta=compose_edited_original_video(source,music,out,root/'work',
                       bpm=145,fx_timeline=cues,humor='stretch',fx_intensity=3)
            self.assertEqual(meta['video_status'],'done')
            self.assertEqual(meta['video_edit_style'],'voice_fx_synced_motion_warp')
            self.assertTrue(meta['video_edit_audio_synced'])
            self.assertEqual(meta['video_edit_fx_cues'],1)
            self.assertTrue(out.stat().st_size>20000)
            probe=json.loads(subprocess.check_output(['ffprobe','-v','error',
                '-show_streams','-show_format','-of','json',str(out)],timeout=20))
            self.assertEqual({s['codec_type'] for s in probe['streams']},
                             {'audio','video'})
            self.assertAlmostEqual(float(probe['format']['duration']),8.,
                                   delta=.8)
            def frame(movie,at):
                return subprocess.check_output(['ffmpeg','-nostdin','-v',
                    'error','-ss',str(at),'-i',str(movie),
                    '-frames:v','1','-vf','scale=48:80,format=gray',
                    '-f','rawvideo','-'],timeout=20)
            # This is changing actual video pixels, not simply substituting
            # an audio track or printing an FX label on static frames.
            normal=frame(out,2.5)
            warped=frame(out,3.55)
            self.assertEqual(len(normal),48*80)
            self.assertEqual(len(warped),48*80)
            delta=sum(abs(x-y) for x,y in zip(normal,warped))/len(normal)
            self.assertGreater(delta,2.)

    def test_render_mix_exports_real_audio_derived_fx_timeline(self):
        from engine import render_mix
        import numpy as np
        sr=8000
        clip=np.zeros(sr*5,dtype=np.float32)
        for left,right,pitch in ((0,.9,310),(1.5,2.35,440),(3,4.8,275)):
            left_index=int(round(sr*left));right_index=int(round(sr*right))
            t=np.arange(right_index-left_index,dtype=np.float32)/sr
            clip[left_index:right_index]=.31*np.sin(2*np.pi*pitch*t)
        music,voice,cues=render_mix([clip],sample_rate=sr,seconds=30,
                        bpm=145,humor='stretch',fx_intensity=3,
                        return_voice=True,return_video_timeline=True)
        self.assertEqual(music.shape[1],2)
        self.assertEqual(len(voice),len(music))
        self.assertTrue(any(e['kind']=='voice' for e in cues))
        self.assertTrue(any(e['kind']=='voice_fx' for e in cues),cues)
        self.assertEqual({e['source_file'] for e in cues},{0})
        self.assertTrue(all(0<=e['start']<e['end']<=len(music)/sr
                            for e in cues),cues)
        self.assertTrue(any(e['effect']=='stretch' and e['kind']=='voice_fx'
                            for e in cues))

if __name__=='__main__':unittest.main()
