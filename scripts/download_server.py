import time
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
class Handler(BaseHTTPRequestHandler):
 def do_GET(self):
  if self.path == "/health":
   self.send_response(200);self.end_headers();self.wfile.write(b"audit-target-download-server-v1\n");return
  if self.path not in ('/10','/100','/1000'):
   self.send_error(404); return
  remaining=int(self.path[1:])*1000000
  self.send_response(200);self.send_header('Content-Length',str(remaining));self.send_header('Content-Type','application/octet-stream');self.end_headers()
  block=bytes(range(256))*4096
  try:
   while remaining:
    n=min(remaining,len(block));self.wfile.write(block[:n]);remaining-=n;time.sleep(.02)
  except (BrokenPipeError,ConnectionResetError):pass
ThreadingHTTPServer(('127.0.0.1',8765),Handler).serve_forever()
