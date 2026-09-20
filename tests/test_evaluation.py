import unittest
from unittest.mock import patch
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
        proposed=self.draft_of_length(200)
        proposed['sentences'][0]['fact_ids']=['unknown']
        with patch('app.evaluation.request_json',return_value=proposed) as request:
            with self.assertRaisesRegex(ValueError,'不存在的简历事实'):
                evaluation.compose_greeting({},self.job,self.profile,'brief')
        self.assertEqual(request.call_count,1)
    def draft_of_length(self,length,fid='f1'):
        invitation='希望进一步沟通。'
        return {'sentences':[{'text':'经'*(length-len(invitation)-1),'fact_ids':[fid]},
                             {'text':invitation,'fact_ids':[]}]}
    def test_greeting_length_counts_joined_text_and_reports_limits(self):
        for style,maximum in [('brief',360),('detailed',850)]:
            with self.subTest(style=style):
                for length in (40,maximum):
                    text,_=evaluation.validate_draft(self.draft_of_length(length),self.profile,style)
                    self.assertEqual(len(text),length)
                for length,direction in [(39,'过短'),(maximum+1,'过长')]:
                    with self.assertRaisesRegex(ValueError,rf'{direction}.*{length}.*40–{maximum}'):
                        evaluation.validate_draft(self.draft_of_length(length),self.profile,style)
    def test_length_correction_is_audited_before_returning(self):
        for style,invalid_length in [('brief',361),('brief',39),('detailed',851)]:
            with self.subTest(style=style,length=invalid_length):
                proposed=self.draft_of_length(invalid_length)
                corrected=self.draft_of_length(200 if style=='brief' else 400)
                expected='\n'.join(row['text'] for row in corrected['sentences'])
                with patch('app.evaluation.request_json',side_effect=[proposed,corrected,{'supported':True,'issues':[]}]) as request:
                    result=evaluation.compose_greeting({},self.job,self.profile,style)
                self.assertEqual(result['text'],expected)
                self.assertEqual(result['style'],style)
                self.assertEqual(result['citations'][0]['facts'][0]['fact_id'],'f1')
                self.assertEqual(request.call_count,3)
                rewrite_data=request.call_args_list[1].args[2]
                self.assertEqual(rewrite_data['previous_draft'],proposed)
                self.assertIn(str(invalid_length),' '.join(rewrite_data['corrections_required']))
                self.assertEqual(request.call_args_list[2].args[2]['sentences'],result['citations'])
    def test_length_correction_cannot_bypass_fact_audit(self):
        with patch('app.evaluation.request_json',side_effect=[self.draft_of_length(361),self.draft_of_length(200),{'supported':False,'issues':['项目经历没有简历依据']}]) as request:
            with self.assertRaisesRegex(ValueError,'事实核验未通过'):
                evaluation.compose_greeting({},self.job,self.profile,'brief')
        self.assertEqual(request.call_count,3)
    def test_audit_correction_still_checks_length(self):
        with patch('app.evaluation.request_json',side_effect=[self.draft_of_length(200),{'supported':False,'issues':['项目经历没有简历依据']},self.draft_of_length(361)]) as request:
            with self.assertRaisesRegex(ValueError,'过长.*361.*360.*已保留原草稿'):
                evaluation.compose_greeting({},self.job,self.profile,'brief')
        self.assertEqual(request.call_count,3)
    def test_repeated_length_failure_preserves_existing_draft(self):
        import tempfile
        from app.store import Store
        with tempfile.TemporaryDirectory() as d:
            s=Store(d)
            try:
                s.set_profile('工作经验\n负责数据治理平台及SQL产品的需求设计。','test')
                s.import_jobs([{'title':'产品经理','company':'公司','description':'负责数据治理及指标体系建设，需要SQL数据分析能力，熟悉B端产品设计。'}])
                jid=s.snapshot()['jobs'][0]['id'];s.save_draft(jid,'原来的招呼内容',True)
                previous=s.get_job(jid)
                fid=s.snapshot()['profile']['facts'][0]['id']
                proposed=self.draft_of_length(361,fid)
                with patch('app.evaluation.request_json',side_effect=[proposed,proposed]) as request:
                    with self.assertRaisesRegex(ValueError,'过长.*361.*360.*已保留原草稿'):
                        s.generate_greeting(jid,'brief')
                self.assertEqual(request.call_count,2)
                self.assertEqual(s.get_job(jid),previous)
            finally:s.close()
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
