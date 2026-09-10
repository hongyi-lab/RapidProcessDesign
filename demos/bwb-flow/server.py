"""Local-only API for the standalone BWB demo. Does not serve arbitrary files."""
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
from pathlib import Path
import sys
from engine import analyze,DEFAULTS,BOUNDS,ASSUMPTIONS

class Handler(BaseHTTPRequestHandler):
    def send_json(self,value,code=200):
        blob=json.dumps(value,ensure_ascii=False,allow_nan=False).encode('utf-8')
        self.send_response(code)
        if self.headers.get('Origin') in ('http://localhost:3981','http://127.0.0.1:3981'):
            self.send_header('Access-Control-Allow-Origin',self.headers['Origin'])
        self.send_header('Access-Control-Allow-Headers','Content-Type')
        self.send_header('Access-Control-Allow-Methods','GET,POST,OPTIONS')
        self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Content-Length',str(len(blob)))
        self.end_headers(); self.wfile.write(blob)
    def do_OPTIONS(self): self.send_json({})
    def do_GET(self):
        if self.path=='/health': self.send_json({'service':'bwb-flow-demo','status':'ready'})
        elif self.path=='/defaults': self.send_json({'inputs':DEFAULTS,'bounds':BOUNDS,'assumptions':ASSUMPTIONS})
        else: self.send_json({'error':'not_found'},404)
    def do_POST(self):
        if self.path!='/analyze': return self.send_json({'error':'not_found'},404)
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<12000: return self.send_json({'error':'invalid_length'},400)
            data=json.loads(self.rfile.read(length))
            self.send_json(analyze(data))
        except (ValueError,TypeError) as exc: self.send_json({'error':str(exc)},400)
        except Exception as exc:
            print(type(exc).__name__,str(exc),file=sys.stderr)
            self.send_json({'error':'calculation_error'},500)

if __name__=='__main__':
    print('BWB calculation API: http://127.0.0.1:8842',flush=True)
    ThreadingHTTPServer(('127.0.0.1',8842),Handler).serve_forever()
