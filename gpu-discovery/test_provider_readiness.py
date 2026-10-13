import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from provider_readiness import inspect,ORIGIN
class Reply:
    status_code=200
    headers={"Content-Type":"application/json"}
    def __init__(self,value,code=200,mime="application/json"):
        self.value=value;self.status_code=code;self.headers={"Content-Type":mime};self.content=value.encode()
    def json(self):return {"components":[{"type":"markdown","props":{"value":self.value}}]}
class Session:
    def __init__(self,r):self.r=r;self.urls=[]
    def get(self,url,**kw):self.urls.append(url);assert not kw["allow_redirects"];return self.r
class GateTests(unittest.TestCase):
    def test_ready_declared(self):
        c=Session(Reply("Model access configured"))
        self.assertTrue(inspect(c).eligible_for_job_lease)
        self.assertEqual(c.urls,[ORIGIN+"/config"])
    def test_setup_required(self):self.assertFalse(inspect(Session(Reply("Setup required"))).eligible_for_job_lease)
    def test_conflict(self):self.assertFalse(inspect(Session(Reply("Model access configured, Setup required"))).eligible_for_job_lease)
    def test_unknown(self):self.assertFalse(inspect(Session(Reply("GPU demo"))).eligible_for_job_lease)
    def test_redirect(self):self.assertFalse(inspect(Session(Reply("Model access configured",302))).eligible_for_job_lease)
    def test_html(self):self.assertFalse(inspect(Session(Reply("Model access configured",200,"text/html"))).eligible_for_job_lease)
    def test_oversized(self):self.assertFalse(inspect(Session(Reply("X"*700001))).eligible_for_job_lease)
if __name__=="__main__":unittest.main()
