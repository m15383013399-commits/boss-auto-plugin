"""Loopback-only workbench. No BOSS network client or sending route."""
import base64
import binascii
import hmac
import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from .domain import extract_docx
from .store import Store

WEB=Path(__file__).resolve().parent.parent/'web'

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def _origin(self):
        origin=self.headers.get('Origin','')
        local='http://127.0.0.1:'+str(self.server.server_port)
        return not origin or origin==local or bool(re.fullmatch(r'chrome-extension://[a-p]{32}',origin))
    def _guard(self,auth=True):
        if self.headers.get('Host')!='127.0.0.1:'+str(self.server.server_port) or not self._origin():
            self._json(403,{'error':'只允许本机工作台或已配对扩展访问'});return False
        token=self.headers.get('X-Local-Key','')
        if auth and not hmac.compare_digest(token.encode(),self.server.store.key.encode()):
            self._json(403,{'error':'本机连接密钥不正确，请刷新页面或重新配置扩展'});return False
        return True
    def _respond(self,status,body,content_type):
        self.send_response(status);self.send_header('Content-Type',content_type);self.send_header('Content-Length',str(len(body)))
        self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        origin=self.headers.get('Origin','')
        if origin and self._origin():self.send_header('Access-Control-Allow-Origin',origin);self.send_header('Vary','Origin')
        self.end_headers();self.wfile.write(body)
    def _json(self,status,obj):self._respond(status,json.dumps(obj,ensure_ascii=False).encode(),'application/json; charset=utf-8')
    def do_OPTIONS(self):
        if not self._guard(False):return
        self.send_response(204);self.send_header('Access-Control-Allow-Origin',self.headers.get('Origin',''))
        self.send_header('Access-Control-Allow-Methods','GET, POST, OPTIONS');self.send_header('Access-Control-Allow-Headers','Content-Type, X-Local-Key');self.end_headers()
    def do_GET(self):
        if not self._guard(self.path.startswith('/api')):return
        if self.path=='/api/known':self._json(200,{'urls':self.server.store.known_urls()});return
        if self.path=='/api/state':self._json(200,self.server.store.snapshot());return
        files={'/':('index.html','text/html; charset=utf-8'),'/state.js':('state.js','text/javascript; charset=utf-8'),'/batches.js':('batches.js','text/javascript; charset=utf-8'),'/app.js':('app.js','text/javascript; charset=utf-8'),'/style.css':('style.css','text/css; charset=utf-8')}
        if self.path not in files:self._json(404,{'error':'路径不存在'});return
        name,content_type=files[self.path];body=(WEB/name).read_bytes()
        if name=='index.html':body=body.replace(b'__LOCAL_KEY__',self.server.store.key.encode())
        self._respond(200,body,content_type)
    def do_POST(self):
        if not self._guard():return
        try:
            size=int(self.headers.get('Content-Length','0'))
            if not 0<size<=22_000_000:raise ValueError('请求内容为空或过大')
            if self.headers.get('Content-Type','').split(';')[0]!='application/json':raise ValueError('请使用 JSON 请求')
            obj=json.loads(self.rfile.read(size))
            if not isinstance(obj,dict):raise ValueError('请求格式必须是 JSON 对象')
            s=self.server.store;result={'ok':True}
            if self.path=='/api/profile':
                text=obj.get('text','')
                if 'docx_base64' in obj:
                    text=extract_docx(base64.b64decode(obj['docx_base64'],validate=True))
                s.set_profile(text,obj.get('filename','文本简历'))
            elif self.path=='/api/preferences':s.set_preferences(obj)
            elif self.path=='/api/model':s.set_model(obj)
            elif self.path=='/api/import':result=s.import_jobs(obj.get('jobs'),obj.get('batch_id'))
            elif self.path=='/api/batches':result=s.create_batch(obj.get('target'),obj.get('name',''),obj.get('source_url',''))
            elif self.path=='/api/batches/analyze':result=s.start_batch_analysis(obj.get('id'))
            elif self.path=='/api/batches/cancel-analysis':result=s.cancel_batch_analysis(obj.get('id'))
            elif self.path=='/api/batches/status':result=s.set_batch_status(obj.get('id'),obj.get('status'),obj.get('message',''))
            else:
                m=re.fullmatch(r'/api/jobs/([a-f0-9]{24})/(analyze|generate|draft|queue|status)',self.path)
                if not m:self._json(404,{'error':'路径不存在'});return
                ident,action=m.groups()
                if action=='analyze':result=s.analyze_job(ident,obj.get('engine','rules'))
                elif action=='generate':result=s.generate_greeting(ident,obj.get('style','brief'))
                elif action=='draft':s.save_draft(ident,obj.get('draft'),obj.get('reviewed',False))
                elif action=='queue':s.queue(ident)
                elif action=='status':s.set_status(ident,obj.get('status'))
            self._json(200,result)
        except (ValueError,TypeError,binascii.Error,UnicodeError) as e:self._json(400,{'error':str(e)[:300]})
        except Exception:self._json(500,{'error':'本地服务异常，本次操作未完成'})

def make_server(data_path,port=8765):
    server=ThreadingHTTPServer(('127.0.0.1',port),Handler);server.store=Store(data_path)
    return server
