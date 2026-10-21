"""Functional tests for the shared server. python -m unittest discover -s server -v"""
import base64, json, os, tempfile, threading, unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from http.server import ThreadingHTTPServer
import app

class TestSharedServer(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory()
  app.BASE=Path(cls.tmp.name);app.DB_PATH=app.BASE/"test.sqlite3";app.FILES=app.BASE/"attachments"
  os.environ["PERMIT_ADMIN_EMAIL"]="minjeong.kang@hdc-resort.com"
  os.environ["PERMIT_ADMIN_PASSWORD"]="test-only-strong-password-123"
  app.boot()
  cls.server=ThreadingHTTPServer(("127.0.0.1",0),app.Handler)
  cls.host="http://127.0.0.1:"+str(cls.server.server_port)
  cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
 @classmethod
 def tearDownClass(cls):
  cls.server.shutdown();cls.server.server_close();cls.thread.join(timeout=3);cls.tmp.cleanup()
 def call(self,route,body=None,token=None,origin=None):
  headers={}
  if token:headers["Authorization"]="Bearer "+token
  if origin:headers["Origin"]=origin
  if body is not None:headers["Content-Type"]="application/json"
  req=Request(self.host+route,data=json.dumps(body).encode() if body is not None else None,headers=headers)
  try:
   with urlopen(req,timeout=5) as r:
    raw=r.read()
    try:raw=json.loads(raw)
    except ValueError:pass
    return r.status,raw
  except HTTPError as ex:
   return ex.code,json.loads(ex.read())
 def test_staff_share_access_and_images(self):
  code,_=self.call("/api/tickets");self.assertEqual(code,401)
  code,a=self.call("/api/login",{"email":"minjeong.kang@hdc-resort.com","password":"test-only-strong-password-123"})
  self.assertEqual(code,200);admin=a["token"]
  for email,role in [("worker.a@hdc-resort.com","requester"),("worker.b@hdc-resort.com","requester"),("reviewer@hdc-resort.com","reviewer")]:
   code,_=self.call("/api/users",{"email":email,"password":"unique-password-12345","role":role},admin)
   self.assertEqual(code,201)
  def login(email):
   code,out=self.call("/api/login",{"email":email,"password":"unique-password-12345"})
   self.assertEqual(code,200);return out["token"]
  ta,tb,tr=login("worker.a@hdc-resort.com"),login("worker.b@hdc-resort.com"),login("reviewer@hdc-resort.com")
  form={"department":"시설팀","requester":"직원A","date":"2026-10-21","title":"건축물 변경","site":"A현장","category":"건축","question":"검토요청","current":"현황","purpose":"사유"}
  code,res=self.call("/api/tickets",form,ta);self.assertEqual(code,201)
  tid=res["ticket"]["id"]
  self.assertEqual(res["ticket"]["email"],"worker.a@hdc-resort.com")
  code,res=self.call("/api/tickets",token=tb);self.assertEqual(code,200);self.assertFalse(res["tickets"])
  code,res=self.call("/api/tickets",token=tr);self.assertEqual(code,200);self.assertEqual(res["tickets"][0]["id"],tid)
  code,_=self.call("/api/tickets/"+tid,token=tb);self.assertEqual(code,404)
  code,_=self.call("/api/tickets/"+tid+"/review",{"assigned":"검토자","result":"승인","complete":True},ta);self.assertEqual(code,403)
  photo=b"\x89PNG\r\n\x1a\n"+b"\0"*30
  code,res=self.call("/api/tickets/"+tid+"/attachments",{"name":"drawing.png","data":base64.b64encode(photo).decode()},ta)
  self.assertEqual(code,201)
  aid=res["ticket"]["attachments"][0]["id"]
  code,got=self.call("/api/tickets/"+tid+"/attachments/"+str(aid),token=tr);self.assertEqual(code,200);self.assertEqual(got,photo)
  code,_=self.call("/api/tickets/"+tid+"/attachments/"+str(aid),token=tb);self.assertEqual(code,404)
  code,out=self.call("/api/tickets/"+tid+"/review",{"assigned":"팀원","result":"검토 중","law":"","action":"","period":"","complete":False},tr)
  self.assertEqual(code,200);self.assertEqual(out["ticket"]["status"],"검토중")
  code,out=self.call("/api/tickets/"+tid+"/review",{"assigned":"팀원","result":"검토 완료","law":"법령","action":"","period":"","complete":True},tr)
  self.assertEqual(code,200);self.assertEqual(out["ticket"]["status"],"회신완료")
  code,_=self.call("/api/tickets/"+tid+"/review",{"assigned":"팀원","result":"덮어쓰기","complete":True},tr);self.assertEqual(code,409)
  code,out=self.call("/api/tickets/"+tid,token=ta);self.assertEqual(code,200);self.assertEqual(out["ticket"]["review"]["result"],"검토 완료")
  code,out=self.call("/api/audit",token=tr);self.assertEqual(code,200);self.assertTrue(any(e["action"]=="회신확정" for e in out["changes"]))
  code,_=self.call("/api/audit",token=ta);self.assertEqual(code,403)
  code,_=self.call("/api/tickets",{"title":"bad"},ta,origin="https://untrusted.invalid");self.assertEqual(code,403)

if __name__=="__main__": unittest.main()
