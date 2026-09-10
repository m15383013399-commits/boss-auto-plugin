import tempfile,unittest
from app.store import Store

def job(i='a',**kw):
    return dict(title='产品经理',company='公司',description='负责数据治理及指标体系建设，需要SQL数据分析能力，熟悉B端产品设计。',source_url=f'https://www.zhipin.com/job_detail/{i}.html',**kw)

class BatchTests(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.s=Store(self.tmp.name)
    def tearDown(self):self.s.close();self.tmp.cleanup()
    def test_success_target_counts_only_new_urls(self):
        self.assertTrue(hasattr(self.s,'create_batch'))
        b=self.s.create_batch(2,'第一批')
        self.s.import_jobs([job()],b['id'])
        self.s.import_jobs([job(recruiter_id='different')],b['id'])
        self.assertEqual(self.s.get_batch(b['id'])['count'],1)
        self.s.import_jobs([job('b'),job('c')],b['id'])
        self.assertEqual(self.s.get_batch(b['id'])['count'],2)
        self.assertEqual(len(self.s.snapshot()['jobs']),2)
        self.assertEqual(self.s.get_batch(b['id'])['status'],'completed')
    def test_url_variants_do_not_reset_existing_draft(self):
        self.s.import_jobs([job()]);j=self.s.snapshot()['jobs'][0]
        self.s.save_draft(j['id'],'已经审核过的招呼',True)
        r=self.s.import_jobs([{**job(),'source_url':'https://zhipin.com/job_detail/a.html?securityId=x#fragment','description':'变更的岗位正文。'*10}])
        self.assertEqual(r['count'],0)
        self.assertEqual(self.s.get_job(j['id'])['draft'],'已经审核过的招呼')
    def test_batch_continues_after_reopen(self):
        self.assertTrue(hasattr(self.s,'create_batch'))
        b=self.s.create_batch(2);self.s.import_jobs([job()],b['id']);self.s.close();self.s=Store(self.tmp.name)
        self.s.set_batch_status(b['id'],'collecting');self.s.import_jobs([job('b')],b['id'])
        self.assertEqual(self.s.get_batch(b['id'])['count'],2)
    def test_invalid_capture_does_not_consume_target(self):
        self.assertTrue(hasattr(self.s,'create_batch'))
        b=self.s.create_batch(1)
        with self.assertRaises(ValueError):self.s.import_jobs([{'title':'bad'}],b['id'])
        self.assertEqual(self.s.get_batch(b['id'])['count'],0)
    def test_parallel_import_cannot_exceed_target(self):
        from concurrent.futures import ThreadPoolExecutor
        b=self.s.create_batch(2)
        with ThreadPoolExecutor(max_workers=4) as pool:list(pool.map(lambda i:self.s.import_jobs([job(str(i))],b['id']),range(8)))
        self.assertEqual(self.s.get_batch(b['id'])['count'],2)
        self.assertEqual(len(self.s.snapshot()['jobs']),2)
    def test_batch_model_worker_finishes_without_creating_drafts(self):
        from unittest.mock import patch
        self.s.set_profile('工作经验\n负责数据治理平台及SQL产品的需求设计。','test')
        self.s.set_model({'base_url':'https://example.com','model':'test','api_key':'local-test'})
        b=self.s.create_batch(2);self.s.import_jobs([job('a'),job('b')],b['id'])
        with patch('app.store.evaluate_job',return_value={'score':80,'gaps':[],'scoring_version':2,'engine':'model'}):
            self.s.start_batch_analysis(b['id']);self.s._workers[0].join(2)
        self.assertEqual(self.s.get_batch(b['id'])['matching']['done'],2)
        self.assertEqual(self.s.get_batch(b['id'])['matching']['status'],'completed')
        self.assertTrue(all(j['draft']=='' for j in self.s.snapshot()['jobs']))
    def test_restart_recovers_stopping_match(self):
        b=self.s.create_batch(1);b['matching']={'status':'stopping','done':0}
        with self.s.db:self.s._put_batch(b)
        self.s.close();self.s=Store(self.tmp.name)
        self.assertEqual(self.s.get_batch(b['id'])['matching']['status'],'paused')
