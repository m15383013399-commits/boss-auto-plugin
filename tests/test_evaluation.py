import unittest
from app import evaluation

class EvaluationTests(unittest.TestCase):
    def setUp(self):
        self.job={'description':'负责数据治理平台。熟悉SQL。需要金融行业经验。本科。Python优先。'}
        self.profile={'facts':[{'id':'f1','text':'负责数据治理平台，熟悉SQL产品设计。','section':'工作经验'}]}
    def result(self):
        return {'criteria':[{'dimension':d,'requirement':r,'status':s,'reason':'依据简历判断','evidence':[{'fact_id':'f1','quote':'负责数据治理平台'}] if s in ('matched','partial') else []} for d,r,s in [('responsibilities','负责数据治理平台','matched'),('skills','熟悉SQL','partial'),('industry','需要金融行业经验','unknown'),('qualifications','本科','unknown'),('bonus','Python优先','unknown')]]}
    def test_weights_and_unknown_are_not_full_credit(self):
        self.assertTrue(hasattr(evaluation,'validate_evaluation'))
        r=evaluation.validate_evaluation(self.result(),self.job,self.profile)
        self.assertEqual(r['score'],53)
        self.assertEqual(len(r['dimensions']),5)
        self.assertTrue(r['gaps'])
    def test_invented_evidence_rejected(self):
        self.assertTrue(hasattr(evaluation,'validate_evaluation'))
        r=self.result();r['criteria'][0]['evidence'][0]['quote']='管理100人团队'
        with self.assertRaises(ValueError):evaluation.validate_evaluation(r,self.job,self.profile)
    def test_missing_dimension_rejected(self):
        self.assertTrue(hasattr(evaluation,'validate_evaluation'))
        r=self.result();r['criteria'].pop()
        with self.assertRaises(ValueError):evaluation.validate_evaluation(r,self.job,self.profile)
    def test_greeting_rejects_unknown_fact(self):
        self.assertTrue(hasattr(evaluation,'validate_draft'))
        with self.assertRaises(ValueError):evaluation.validate_draft({'sentences':[{'text':'我有8年经验。','fact_ids':['unknown']}]},self.profile,'brief')
    def test_audit_rejection_preserves_existing_draft(self):
        import tempfile
        from unittest.mock import patch
        from app.store import Store
        with tempfile.TemporaryDirectory() as d:
            s=Store(d);s.set_profile('工作经验\n负责数据治理平台及SQL产品的需求设计。','test')
            s.import_jobs([{'title':'产品经理','company':'公司','description':'负责数据治理及指标体系建设，需要SQL数据分析能力，熟悉B端产品设计。'}]);jid=s.snapshot()['jobs'][0]['id'];s.save_draft(jid,'原来的招呼内容',True)
            fid=s.snapshot()['profile']['facts'][0]['id']
            proposed={'sentences':[{'text':'您好，我看到贵司正在招聘数据治理产品经理，与我之前从事的产品方向比较接近。','fact_ids':[]},{'text':'我负责过数据治理平台及SQL产品的需求设计，希望进一步了解团队的情况，方便沟通吗？','fact_ids':[fid]}]}
            with patch('app.evaluation.request_json',side_effect=[proposed,{'supported':False,'issues':['不支持']},proposed,{'supported':False,'issues':['不支持']}]):
                with self.assertRaises(ValueError):s.generate_greeting(jid,'brief')
            self.assertEqual(s.get_job(jid)['draft'],'原来的招呼内容');self.assertTrue(s.get_job(jid)['reviewed']);s.close()
    def test_requirement_can_summarize_saved_jd(self):
        r=self.result();r['criteria'][0]['requirement']='数据治理平台相关职责'
        checked=evaluation.validate_evaluation(r,self.job,self.profile)
        self.assertEqual(checked['score'],53)
        self.assertEqual(checked['criteria'][0]['requirement'],'数据治理平台相关职责')
