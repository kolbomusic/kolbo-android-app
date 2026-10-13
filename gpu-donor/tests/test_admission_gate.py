import json
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from admission_gate import inspect_graph,inspect_receipt,inspect_donor

class AdmissionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)
    def graph(self,kind):
        o={"1":{"class_type":"CLIPTextEncode","inputs":{"text":"__KOLBO_PROMPT__"}},
           "2":{"class_type":"Frames","inputs":{"count":"__KOLBO_FRAMES__"}}}
        if kind==1:o["3"]={"class_type":"LoadImage","inputs":{"image":"__KOLBO_IMAGE1__"}}
        p=self.path/f"workflow_{kind}_images.json";p.write_text(json.dumps(o))
        return p
    def test_zero_workflows_never_approved(self):
        r=inspect_donor(hardware_report={"eligible_for_operator_review":True},workflows=self.path)
        self.assertFalse(r["eligible_for_independent_review"])
        self.assertFalse(r["allowed_to_receive_private_media"])
    def test_structural_both_workflows(self):
        self.assertTrue(inspect_graph(self.graph(0),0)["bindings_ok"])
        self.assertTrue(inspect_graph(self.graph(1),1)["bindings_ok"])
    def test_ui_canvas_not_api(self):
        p=self.path/"a.json";p.write_text(json.dumps({"nodes":[{"id":1}],"links":[]}))
        self.assertFalse(inspect_graph(p,0)["structural_api_graph"])
    def test_wrong_reference_binding(self):
        self.assertFalse(inspect_graph(self.graph(1),0)["bindings_ok"])
    def test_invalid_receipt(self):
        p=self.path/"proof.json";p.write_text('{"verified":true}')
        self.assertFalse(inspect_receipt(p))
    def test_no_real_worker_even_if_local_proof(self):
        self.graph(0);self.graph(1)
        p=self.path/"receipt.json"
        p.write_text(json.dumps({"verified":True,"audio_verified":True,
            "audible_audio_verified":True,"changing_frame_intervals":2,"sha256":"a"*64}))
        r=inspect_donor(hardware_report={"eligible_for_operator_review":True},workflows=self.path,receipt=p)
        self.assertTrue(r["eligible_for_independent_review"])
        self.assertFalse(r["owner_approved"])
        self.assertFalse(r["registered_worker"])
        self.assertFalse(r["allowed_to_receive_private_media"])
        self.assertFalse(r["real_ai_e2e_verified"])
    def test_symlink_refused(self):
        path=self.graph(0)
        other=self.path/"link.json";other.symlink_to(path)
        self.assertFalse(inspect_graph(other,0)["present"])

if __name__=="__main__":unittest.main()
