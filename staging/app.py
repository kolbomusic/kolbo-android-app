"""Kolbo Video HTTPS preflight only. Never ingest private media or spawn GPUs."""
import json, os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

CONFIG = {
 "service":"kolbo-volunteer-mesh","api_contract":449,"minimum_android_client":449,
 "owner_auth_required":True,"max_seconds":15,"max_reference_images":2,
 "native_mp4_export_supported":True,"preview_only":True,
 "gpu_guaranteed":False,"gpu_ready":False,"persistent_storage_ready":False,
 "private_media_upload_enabled":False,"hybrid_plan_execution_enabled":False,
 "paid_gpu_fallback_enabled":False,"real_video_generation_verified":False
}
PAGE="""<!doctype html><html lang="he" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Kolbo Video — חיבור בדיקה</title>
<style>:root{color-scheme:dark}body{font-family:system-ui,Arial,sans-serif;background:#181326;color:#f5f1ff;margin:0;padding:20px}main{max-width:520px;margin:8vh auto;background:#241c39;border:1px solid #4a3867;padding:28px;border-radius:20px}h1{color:#e6d7ff}p{line-height:1.8}strong{color:#ffbd59}.status{padding:18px;background:#38294c;border-radius:12px;line-height:2}small{color:#c9bcdb}</style>
</head><body><main><h1>Kolbo Video 4.4.9</h1>
<p>✓ חיבור HTTPS לאפליקציה אומת. <strong>זו סביבת בדיקת חיבור, לא מנוע הפקת AI.</strong></p>
<div class="status">✓ API תואם לאפליקציה<br>⏳ אחסון מתמשך טרם חובר<br>⏳ GPU מאומת טרם חובר<br>🔒 העלאת תמונות ובקשות הפקה חסומות</div>
<p><strong>אין להעלות לכאן תמונות, סרטונים או פרטי התחברות.</strong> לא מופעלת יצירת וידאו.</p>
<small>מצב ההפקה ייפתח רק לאחר אחסון עמיד, חיבור GPU מורשה ובדיקת וידאו אמיתי עם שמע.</small></main></body></html>"""
class Handler(BaseHTTPRequestHandler):
 protocol_version="HTTP/1.1"
 def log_message(self, fmt, *args):pass
 def send(self,code,data,mime):
  self.send_response(code)
  for k,v in (
   ("Content-Type",mime),("Cache-Control","no-store"),
   ("X-Content-Type-Options","nosniff"),("X-Frame-Options","DENY"),
   ("Referrer-Policy","no-referrer"),
   ("Content-Security-Policy","default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"),
   ("Content-Length",str(len(data))),("Connection","close")):self.send_header(k,v)
  self.end_headers()
  if self.command!="HEAD":self.wfile.write(data)
  self.close_connection=True
 def do_GET(self):
  route=urlsplit(self.path).path
  if route in ("/","/studio"):return self.send(200,PAGE.encode(),"text/html; charset=utf-8")
  if route=="/v1/app-config":return self.send(200,json.dumps(CONFIG,ensure_ascii=False).encode(),"application/json")
  if route=="/healthz":return self.send(200,json.dumps({"alive":True,"preview_only":True,"gpu_ready":False,"storage_ready":False,"accepts_media":False}).encode(),"application/json")
  return self.send(404,b"Not found","text/plain")
 def do_HEAD(self):self.do_GET()
 def reject(self):
  self.send(503,json.dumps({"error":"NOT_ACTIVE_FOR_GENERATION","accepted":False,"charged_usd":0,"detail":"No verified GPU or durable media storage"}).encode(),"application/json")
 do_POST=do_PUT=do_PATCH=do_DELETE=reject
if __name__=="__main__":
 ThreadingHTTPServer(("0.0.0.0",int(os.getenv("PORT","8000"))),Handler).serve_forever()
