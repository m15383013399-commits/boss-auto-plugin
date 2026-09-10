import json, unittest
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch
from app.model import select_evidence, validate_config, evidence_options

class ModelTests(unittest.TestCase):
    def call_fixture(self,result,config=None):
        class Response:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,n):return json.dumps(result).encode()
        with patch('app.model.urlopen',return_value=Response()) as request:
            value=select_evidence(config or {'base_url':'https://example.com/v1','model':'example','api_key':'secret'},
                {'title':'数据产品经理','description':'负责数据治理及指标体系'}, {'facts':[{'id':'f1','text':'负责数据治理与数据质量体系建设。'}]})
        return value,json.loads(request.call_args.args[0].data)
    def valid_response(self,finish='stop'):
        return {'choices':[{'finish_reason':finish,'message':{'content':json.dumps({'jd_focus':'数据治理','highlights':[{'fact_id':'f1','quote':'负责数据治理与数据质量体系建设'}]})}}]}
    def test_deepseek_v4_uses_json_and_non_thinking_for_short_evidence(self):
        _,payload=self.call_fixture(self.valid_response(),{'base_url':'https://api.deepseek.com','model':'deepseek-v4-flash','api_key':'secret'})
        self.assertEqual(payload.get('thinking'),{'type':'disabled'})
        self.assertEqual(payload.get('response_format'),{'type':'json_object'})
        self.assertGreaterEqual(payload['max_tokens'],4096)
    def test_generic_provider_does_not_receive_deepseek_specific_options(self):
        _,payload=self.call_fixture(self.valid_response())
        self.assertNotIn('thinking',payload)
        self.assertNotIn('response_format',payload)
    def test_reasoning_only_truncation_reports_token_limit(self):
        with self.assertRaisesRegex(ValueError,'长度上限'):
            self.call_fixture({'choices':[{'finish_reason':'length','message':{'content':'','reasoning_content':'private reasoning'}}]})
    def test_even_valid_json_is_rejected_if_provider_reports_truncated(self):
        with self.assertRaisesRegex(ValueError,'长度上限'):self.call_fixture(self.valid_response('length'))
    def test_empty_final_answer_is_not_parsed_as_json(self):
        with self.assertRaisesRegex(ValueError,'最终答案为空'):
            self.call_fixture({'choices':[{'finish_reason':'stop','message':{'content':None,'reasoning_content':'private reasoning'}}]})
    def test_selected_ids_are_resolved_to_source_text(self):
        result={'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'jd_focus_id':'j1','evidence_ids':['e1']})}}]}
        (focus,matches),_=self.call_fixture(result)
        self.assertEqual(focus,'负责数据治理及指标体系')
        self.assertEqual(matches[0]['quote'],'负责数据治理与数据质量体系建设。')
        self.assertEqual(matches[0]['fact_id'],'f1')
    def test_unknown_selected_evidence_id_is_rejected(self):
        result={'choices':[{'message':{'content':json.dumps({'jd_focus_id':'j1','evidence_ids':['invented']})}}]}
        with self.assertRaisesRegex(ValueError,'不存在'):self.call_fixture(result)
    def test_candidate_chunks_are_bounded_verbatim_source_spans(self):
        fact='负责数据产品规划，协同研发推进落地，'*20+'完成验收。'
        jd='理解大模型与智能体的基本工作原理及能力边界，具备产品设计能力。'*6
        focuses,evidence=evidence_options({'description':jd},{'facts':[{'id':'real','section':'项目','text':fact}]})
        self.assertGreater(len(evidence),1)
        for item in evidence.values():
            self.assertIn(item['quote'],fact);self.assertTrue(8<=len(item['quote'])<=82)
        for item in focuses.values():self.assertIn(item,jd);self.assertTrue(2<=len(item)<=32)
    def test_jd_focus_uses_clause_boundaries_before_cutting_words(self):
        jd='2、可熟练使用 Agent Harness、Axure、墨刀等工具快速输出产品原型，能独立编写产品需求文档（PRD）'
        focuses,_=evidence_options({'description':jd},{'facts':[{'id':'f1','text':'负责数据治理与数据质量体系建设。'}]})
        self.assertIn('可熟练使用 Agent Harness',focuses.values())
        self.assertFalse(any(q.endswith('等工') for q in focuses.values()))
    def test_rejects_insecure_remote(self):
        with self.assertRaises(ValueError): validate_config({'base_url':'http://example.com/v1','model':'x','api_key':'secret'})
    def test_compatible_chat_response_is_validated(self):
        profile={'facts':[{'id':'f1','text':'负责数据治理与数据质量体系建设。'}]}
        job={'title':'产品经理','description':'岗位要求：负责数据治理与指标体系。'}
        selection={'jd_focus':'负责数据治理','highlights':[{'fact_id':'f1','quote':'负责数据治理与数据质量体系建设'}]}
        class Response:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,n):return json.dumps({'choices':[{'message':{'content':json.dumps(selection)}}]}).encode()
        with patch('app.model.urlopen',return_value=Response()) as request:
            focus,matches=select_evidence({'base_url':'https://example.com/v1','model':'example','api_key':'secret'},job,profile)
        self.assertEqual(focus,'负责数据治理');self.assertEqual(matches[0]['fact_id'],'f1')
        req=request.call_args.args[0]
        self.assertEqual(req.full_url,'https://example.com/v1/chat/completions')
        self.assertEqual(req.get_header('Authorization'),'Bearer secret')

    def test_real_local_http_provider(self):
        captured=[]
        class Fixture(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_POST(self):
                body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                captured.append((self.path,self.headers.get('Authorization'),body))
                content={'jd_focus':'数据治理','highlights':[{'fact_id':'f1','quote':'负责数据治理与数据质量体系建设'}]}
                payload=json.dumps({'choices':[{'message':{'content':json.dumps(content)}}]}).encode()
                self.send_response(200);self.send_header('Content-Length',str(len(payload)));self.end_headers();self.wfile.write(payload)
        server=ThreadingHTTPServer(('127.0.0.1',0),Fixture)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            focus,matches=select_evidence({'base_url':'http://127.0.0.1:'+str(server.server_port)+'/v1','model':'fixture-model','api_key':'fixture-key'},
                {'title':'数据产品经理','description':'负责数据治理及指标体系'}, {'facts':[{'id':'f1','text':'负责数据治理与数据质量体系建设。'}]})
            self.assertEqual(focus,'数据治理');self.assertEqual(len(matches),1)
            self.assertEqual(captured[0][0],'/v1/chat/completions');self.assertEqual(captured[0][2]['model'],'fixture-model')
        finally:server.shutdown();server.server_close();thread.join()
