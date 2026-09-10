import json, tempfile, threading, unittest
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from app.server import make_server

class ServerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.server=make_server(self.temp.name,0)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.base='http://127.0.0.1:'+str(self.server.server_port)
        self.key=self.server.store.key
    def tearDown(self):self.server.shutdown();self.server.server_close();self.thread.join();self.server.store.close();self.temp.cleanup()
    def request(self,path,body=None,headers=None):
        h={'X-Local-Key':self.key,'Content-Type':'application/json'};h.update(headers or {})
        req=Request(self.base+path,data=json.dumps(body).encode() if body is not None else None,headers=h)
        try:r=urlopen(req)
        except HTTPError as e:r=e
        with r:return r.status,r.read()
    def test_auth_and_origin(self):
        self.assertEqual(self.request('/api/state',headers={'X-Local-Key':''})[0],403)
        self.assertEqual(self.request('/api/state',headers={'Origin':'https://evil.example'})[0],403)
        self.assertEqual(self.request('/api/state')[0],200)
    def test_no_send_route(self):self.assertEqual(self.request('/api/send',{})[0],404)
    def test_bad_json_and_rebinding_host_rejected(self):
        req=Request(self.base+'/api/import',data=b'{broken',headers={'X-Local-Key':self.key,'Content-Type':'application/json'})
        with self.assertRaises(HTTPError) as caught:urlopen(req)
        self.assertEqual(caught.exception.code,400)
        caught.exception.close()
        self.assertEqual(self.request('/',headers={'Host':'attacker.example'})[0],403)
    def test_html_injects_key_and_has_restrictive_csp(self):
        with urlopen(self.base+'/') as response:
            self.assertIn(self.key.encode(),response.read())
            self.assertIn("frame-ancestors 'none'",response.headers['Content-Security-Policy'])
    def test_flow(self):
        self.assertEqual(self.request('/api/profile',{'text':'技能特长\n负责数据治理、指标体系与 SQL 数据分析。','filename':'test'})[0],200)
        raw={'title':'数据产品经理','company':'测试公司','city':'北京','salary':'20-30K','description':'负责数据治理及指标体系建设，需要SQL数据分析能力，熟悉B端产品设计。'}
        self.assertEqual(self.request('/api/import',{'jobs':[raw]})[0],200)
        state=json.loads(self.request('/api/state')[1]);ident=state['jobs'][0]['id']
        self.assertEqual(self.request('/api/jobs/'+ident+'/analyze',{'engine':'rules'})[0],200)
        self.assertEqual(self.request('/api/jobs/'+ident+'/queue',{})[0],400)
        self.assertEqual(self.request('/api/jobs/'+ident+'/draft',{'draft':'您好，希望沟通数据产品经理岗位。','reviewed':True})[0],200)
        self.assertEqual(self.request('/api/jobs/'+ident+'/queue',{})[0],200)
    def test_batch_api_counts_new_jobs_and_protects_known_urls(self):
        status,body=self.request('/api/batches',{'target':1,'name':'API 验证'})
        self.assertEqual(status,200);b=json.loads(body)
        raw={'title':'数据产品经理','company':'测试公司','source_url':'https://www.zhipin.com/job_detail/test1.html?securityId=secret','description':'负责数据治理及指标体系建设，需要SQL数据分析能力，熟悉B端产品设计。'}
        status,body=self.request('/api/import',{'jobs':[raw],'batch_id':b['id']});self.assertEqual(status,200);self.assertEqual(json.loads(body)['batch']['count'],1)
        self.assertEqual(json.loads(self.request('/api/import',{'jobs':[raw],'batch_id':b['id']})[1])['count'],0)
        self.assertEqual(self.request('/api/known',headers={'X-Local-Key':''})[0],403)
        known=json.loads(self.request('/api/known')[1]);self.assertEqual(known['urls'],['https://www.zhipin.com/job_detail/test1.html'])
        self.assertEqual(self.request('/api/batches/analyze',{'id':b['id']})[0],400)
