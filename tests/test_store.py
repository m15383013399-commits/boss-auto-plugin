import tempfile,unittest
from unittest.mock import patch
from app.store import Store

class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.s=Store(self.tmp.name)
        self.s.set_profile('技能特长\n熟悉数据治理、指标体系与 SQL 数据分析。','test.txt')
        self.raw={'job_id':'abc','title':'数据产品经理','company':'公司','city':'北京','salary':'20-30K','description':'负责数据治理及指标体系建设，需要SQL数据分析能力，熟悉B端产品设计。','source_url':'https://www.zhipin.com/job_detail/abc.html'}
        self.s.import_jobs([self.raw]);self.id=self.s.snapshot()['jobs'][0]['id']
    def tearDown(self):self.s.close();self.tmp.cleanup()
    def prepare(self):
        self.s.analyze_job(self.id,'rules');self.s.save_draft(self.id,'您好，希望沟通数据产品经理岗位。',True)
    def test_unreviewed_cannot_queue(self):
        self.s.analyze_job(self.id,'rules')
        with self.assertRaises(ValueError): self.s.queue(self.id)
    def test_duplicate_url_preserves_existing_queue_and_content(self):
        self.prepare();self.s.queue(self.id);self.s.import_jobs([self.raw]);self.assertEqual(self.s.get_job(self.id)['status'],'queued')
        self.s.import_jobs([{**self.raw,'description':self.raw['description']+'需要Spark。'}])
        j=self.s.get_job(self.id);self.assertEqual(j['status'],'queued');self.assertIsNotNone(j['analysis']);self.assertEqual(j['draft'],'您好，希望沟通数据产品经理岗位。')
    def test_new_resume_invalidates_queue(self):
        self.prepare();self.s.queue(self.id);self.s.set_profile('工作经验\n负责产品规划与原型设计，完成需求调研和客户沟通。','new')
        self.assertEqual(self.s.get_job(self.id)['status'],'new')
    def test_excluded_cannot_queue(self):
        self.s.set_preferences({'city':'上海','min_salary':20,'exclude_words':[]});self.prepare()
        with self.assertRaises(ValueError):self.s.queue(self.id)
    def test_same_url_different_recruiter_is_duplicate(self):
        self.s.import_jobs([{**self.raw,'recruiter_id':'other'}]);self.assertEqual(len(self.s.snapshot()['jobs']),1)
    def test_model_failure_preserves_reviewed_draft(self):
        self.prepare();before=self.s.get_job(self.id)
        with patch('app.store.evaluate_job',side_effect=ValueError('invalid model quote')):
            with self.assertRaises(ValueError):self.s.analyze_job(self.id,'model')
        self.assertEqual(self.s.get_job(self.id),before)
    def test_resume_changed_during_model_call_rejects_stale_result(self):
        def result(*args):
            self.s.set_profile('工作经验\n负责产品规划、需求调研与客户沟通，推进产品交付。','changed')
            return {'score':0,'gaps':[]}
        with patch('app.store.evaluate_job',side_effect=result):
            with self.assertRaises(ValueError):self.s.analyze_job(self.id,'model')
        self.assertIsNone(self.s.get_job(self.id)['analysis'])
    def test_key_is_never_returned_in_snapshot(self):
        self.s.set_model({'base_url':'https://example.com/v1','model':'x','api_key':'secret-private'})
        self.assertNotIn('secret-private',str(self.s.snapshot()))
        self.assertTrue(self.s.snapshot()['model']['configured'])
        self.assertEqual((self.s.path/'model.json').stat().st_mode&0o777,0o600)
    def test_changing_provider_does_not_reuse_old_secret(self):
        self.s.set_model({'base_url':'https://first.example/v1','model':'x','api_key':'secret-private'})
        with self.assertRaises(ValueError):self.s.set_model({'base_url':'https://second.example/v1','model':'y','api_key':''})
        self.assertEqual(self.s.snapshot()['model']['base_url'],'https://first.example/v1')
