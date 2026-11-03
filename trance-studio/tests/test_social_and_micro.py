"""Social URL import and modular creative engine tests.

No external URL or real user media is ever fetched during CI.
"""
import io
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

import numpy as np
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
import app
import link_import
import engine
from engine_registry import catalog


class SocialImportAndMicroRemixTests(unittest.TestCase):
    def test_public_known_https_social_links_only(self):
        allowed=(
            'https://www.facebook.com/reel/9876',
            'https://vm.tiktok.com/ZMz123/',
            'https://www.instagram.com/reel/example/',
            'https://vimeo.com/123456789',
            'https://www.reddit.com/r/test/comments/123/abc',
        )
        for url in allowed:
            self.assertEqual(link_import.validate_public_link(url),url)
        forbidden=(
            'http://www.facebook.com/reel/123',
            'https://localhost/private',
            'https://127.0.0.1/internal',
            'https://facebook.com.evil.example/video',
            'https://user:secret@tiktok.com/video',
            'https://tiktok.com:8443/video',
            'file:///etc/passwd',
            'https://169.254.169.254/latest/meta-data',
            'https://example.org/stream.mp4',
            'https://youtu.be/dQw4w9WgXcQ',
            'https://vm.tiktok.com/video bad',
            'https://www.facebook.com\\@evil.example/x',
        )
        for url in forbidden:
            with self.subTest(url=url):
                with self.assertRaises(link_import.LinkImportError):
                    link_import.validate_public_link(url)

    def test_tiktok_short_redirect_is_canonicalized_only_on_trusted_hosts(self):
        short='https://vt.tiktok.com/ZDemo2026/'
        canonical='https://www.tiktok.com/@test_news/video/1234567890123456789'
        class PublicRedirect:
            def __enter__(self):return self
            def __exit__(self,*args):return False
            def geturl(self):
                return canonical+'?_r=1&_t=fake'
        opener=mock.Mock()
        opener.open.return_value=PublicRedirect()
        urls=link_import._public_tiktok_candidates(short,opener=opener)
        self.assertEqual(urls,[canonical,short])
        self.assertEqual(opener.open.call_count,1)
        self.assertEqual(opener.open.call_args.args[0].get_method(),'HEAD')
        self.assertIsNone(link_import._canonical_tiktok_video(
            'https://tiktok.com.evil.example/@test/video/1234567890123456789'))
        with self.assertRaises(link_import.LinkImportError) as bad:
            link_import._TikTokOnlyRedirects().redirect_request(
                None,None,302,'Found',{},
                'http://127.0.0.1/private.mp4')
        self.assertEqual(bad.exception.code,'unsafe_redirect')

    def test_successful_ytdlp_exit_with_no_media_is_not_a_success(self):
        class FinishedWithoutFile:
            returncode=0
            def poll(self):return 0
        def test_with_message(message):
            def fake_popen(command,stdout,stderr):
                self.assertIn('--match-filter',command)
                stdout.write(message.encode('utf-8'))
                return FinishedWithoutFile()
            with tempfile.TemporaryDirectory() as folder:
                with mock.patch.object(link_import.subprocess,'Popen',
                                       side_effect=fake_popen):
                    return link_import._try_public_download(
                        'https://www.tiktok.com/@test/video/1234567890123456789',
                        pathlib.Path(folder),deadline=link_import.time.monotonic()+8,
                        format_spec='best')
        self.assertEqual(test_with_message(
            '[download] example does not pass filter (duration > 120)'),
            'duration')
        self.assertEqual(test_with_message(''),'invalid_file')

    def test_verified_tiktok_public_permalink_attempted_first(self):
        short='https://vt.tiktok.com/ZDemo2026/'
        full='https://www.tiktok.com/@test_news/video/1234567890123456789'
        attempted=[]
        def public_video(url, folder, **kwargs):
            attempted.append(url)
            if url!=full:return 'unavailable'
            (pathlib.Path(folder)/'shared.mp4').write_bytes(b'video'*1024)
            return 'ok'
        with tempfile.TemporaryDirectory() as directory:
            with mock.patch.object(link_import,'_public_tiktok_candidates',
                                   return_value=[full,short]),mock.patch.object(
                    link_import,'_try_public_download',
                    side_effect=public_video),mock.patch.object(
                    link_import,'_media_probe',return_value=18.):
                result,mime=link_import.fetch_public_social_media(short,directory)
                self.assertEqual(attempted,[full])
                self.assertEqual(result.name,'shared.mp4')
                self.assertEqual(mime,'video/mp4')

    def test_tiktok_audio_only_is_rejected_as_video(self):
        link='https://www.tiktok.com/@test_news/video/1234567890123456789'
        def incomplete_video(url, folder, **kwargs):
            (pathlib.Path(folder)/'shared.m4a').write_bytes(b'audio'*1024)
            return 'ok'
        with tempfile.TemporaryDirectory() as directory:
            with mock.patch.object(link_import,'_try_public_download',
                                   side_effect=incomplete_video):
                with self.assertRaises(link_import.LinkImportError) as error:
                    link_import.fetch_public_social_media(link,directory)
                self.assertEqual(error.exception.code,'no_public_media')
                self.assertIn('tiktok:audio_only',error.exception.steps)

    def test_import_endpoint_authenticated_and_never_generates(self):
        with tempfile.TemporaryDirectory() as folder:
            instance=app.create_app({'TESTING':True,'JOB_DIR':folder,'API_TOKEN':'test-secret'})
            client=instance.test_client()
            with mock.patch.object(link_import,'fetch_public_social_media',
                                   side_effect=link_import.LinkImportError('פרטי')):
                response=client.post('/api/import-link',json={'url':'https://www.facebook.com/reel/12'})
                self.assertEqual(response.status_code,422,response.json)
            self.assertEqual(list(pathlib.Path(folder).glob('*')),[])
            capabilities=client.get('/api/capabilities')
            self.assertEqual(capabilities.status_code,200)
            self.assertEqual(capabilities.json['api_version'],1)
            self.assertFalse(capabilities.json['promises_unlimited_public_gpu'])

    def test_mock_public_download_is_returned_not_auto_processed(self):
        with tempfile.TemporaryDirectory() as folder:
            instance=app.create_app({'TESTING':True,'JOB_DIR':folder})
            client=instance.test_client()
            def fake_download(url,path):
                video=pathlib.Path(path)/'shared.mp4'
                video.write_bytes(b'verified-test-media-not-real-mp4')
                return video,'video/mp4'
            with mock.patch.object(link_import,'fetch_public_social_media',
                                   side_effect=fake_download):
                response=client.post('/api/import-link',json={'url':'https://www.tiktok.com/@example/video/123'})
                self.assertEqual(response.status_code,200)
                self.assertEqual(response.mimetype,'video/mp4')
                self.assertEqual(response.data,b'verified-test-media-not-real-mp4')
                response.close()
            self.assertEqual(list(pathlib.Path(folder).glob('kolbo-social-*')),[])

    def test_engine_catalog_explicitly_avoids_unlimited_gpu_claims(self):
        result=catalog()
        self.assertEqual(result['selection_policy'],
                         'local-dsp-first-public-ai-when-user-consents')
        self.assertTrue(any(v['kind']=='local-dsp' for v in result['music']))
        self.assertTrue(all(v['needs_consent'] for v in result['video']
                            if v['kind']=='external-public-ai'))
        self.assertTrue(all(v['quota_limited'] for v in result['video']
                            if v['kind']=='external-public-ai'))

    def test_one_word_automatic_remix_is_short_and_contains_original_voice(self):
        sr=8000
        t=np.arange(int(1.15*sr),dtype=np.float32)/sr
        voice=(.27*np.sin(2*np.pi*205*t)+.08*np.sin(2*np.pi*415*t)).astype(np.float32)
        full,wet=engine.render_mix(
            [voice],sample_rate=sr,seconds=0,humor='auto',style='mixed',
            transcript_hint='חמור',fx_intensity=3,return_voice=True)
        duration=len(wet)/sr
        self.assertGreaterEqual(duration,14)
        self.assertLess(duration,30)
        self.assertGreater(np.max(np.abs(wet)),.02)
        self.assertTrue(np.isfinite(full).all())
        self.assertEqual(len(full),len(wet))
        # A single short source is arranged in a multi-stage sound design.
        tail=wet[int(4*sr):]
        self.assertGreater(float(np.sqrt(np.mean(tail**2))),.001)

    def test_manual_trance_off_still_preserves_short_recording(self):
        sr=8000
        t=np.arange(int(1*sr))/sr
        voice=(.25*np.sin(2*np.pi*210*t)).astype(np.float32)
        full,raw=engine.render_mix([voice],sample_rate=sr,seconds=0,
                                   humor='off',return_voice=True)
        self.assertGreaterEqual(len(full)/sr,30)
        self.assertEqual(len(full),len(raw))


if __name__=='__main__':
    unittest.main()
