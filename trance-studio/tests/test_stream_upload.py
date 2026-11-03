"""Regression for disk-spooled WhatsApp uploads on a 512 MiB Render worker."""
import hashlib
import io
import pathlib
import sys
import tempfile
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from app import _save_upload_stream

class TrackingBytes(io.BytesIO):
    def __init__(self,data):
        super().__init__(data)
        self.maximum_requested=0
    def read(self,size=-1):
        self.maximum_requested=max(self.maximum_requested,size)
        if size<0:
            raise AssertionError('Never read entire user video into RAM')
        return super().read(size)

class StreamingUploadTests(unittest.TestCase):
    def test_large_original_video_hash_is_verified_without_large_ram_copy(self):
        payload=b'authentic-whatsapp-moving-file-source'*180_000
        stream=TrackingBytes(payload)
        with tempfile.TemporaryDirectory() as folder:
            dest=pathlib.Path(folder)/'0.mp4'
            size=_save_upload_stream(
                stream,dest,45*1048576,60*1048576,
                expected_sha256=hashlib.sha256(payload).hexdigest())
            self.assertEqual(size,len(payload))
            self.assertEqual(dest.read_bytes(),payload)
            self.assertLessEqual(stream.maximum_requested,256*1024)

    def test_reject_oversized_and_mismatched_sources_without_extra_allocation(self):
        with tempfile.TemporaryDirectory() as folder:
            path=pathlib.Path(folder)/'media.opus'
            stream=TrackingBytes(b'm'*1024)
            with self.assertRaisesRegex(ValueError,'upload_limit'):
                _save_upload_stream(stream,path,512,2000)
            self.assertLessEqual(stream.maximum_requested,256*1024)
            with self.assertRaisesRegex(ValueError,'source_fingerprint_mismatch'):
                _save_upload_stream(io.BytesIO(b'voice'),path,100,100,
                                    expected_sha256='0'*64)

    def test_total_limit_with_one_existing_upload(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(ValueError,'upload_limit'):
                _save_upload_stream(io.BytesIO(b'x'*100),pathlib.Path(folder)/'a.wav',
                                    200,1000,already_saved=950)

if __name__=='__main__':
    unittest.main()
