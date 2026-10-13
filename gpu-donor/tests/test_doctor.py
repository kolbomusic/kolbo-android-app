import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from doctor import check,RECOMMENDED_DISK_BYTES

class DoctorTests(unittest.TestCase):
 def test_eligible_means_review_only(self):
  result=check(lambda:'NVIDIA H100, 81920',lambda:True,lambda:RECOMMENDED_DISK_BYTES)
  self.assertTrue(result['eligible_for_operator_review'])
  self.assertFalse(result['gpu_generation_proven'])
  self.assertFalse(result['worker_registered'])
  self.assertFalse(result['user_media_transferred'])
 def test_weak_gpu(self):
  self.assertFalse(check(lambda:'NVIDIA GT 630, 1024',lambda:True,lambda:RECOMMENDED_DISK_BYTES)['recommended_gpu_detected'])
 def test_no_gpu(self):
  self.assertFalse(check(lambda:'',lambda:True,lambda:RECOMMENDED_DISK_BYTES)['eligible_for_operator_review'])
 def test_no_docker(self):
  self.assertFalse(check(lambda:'NVIDIA A100, 40960',lambda:False,lambda:RECOMMENDED_DISK_BYTES)['eligible_for_operator_review'])
 def test_no_disk(self):
  self.assertFalse(check(lambda:'NVIDIA A100, 40960',lambda:True,lambda:0)['eligible_for_operator_review'])
 def test_driver_error(self):
  def missing():raise FileNotFoundError()
  self.assertFalse(check(missing,lambda:True,lambda:RECOMMENDED_DISK_BYTES)['eligible_for_operator_review'])
 def test_bad_device_rows(self):
  r=check(lambda:'bad\nRTX A6000, nope\nRTX A6000, 49152',lambda:True,lambda:RECOMMENDED_DISK_BYTES)
  self.assertEqual(r['gpu_count'],1)
 def test_never_enrolls_or_spends(self):
  r=check(lambda:'RTX A6000, 49152',lambda:True,lambda:RECOMMENDED_DISK_BYTES)
  self.assertFalse(r['payments_started'])
  self.assertFalse(r['user_media_transferred'])

if __name__=='__main__':unittest.main()
