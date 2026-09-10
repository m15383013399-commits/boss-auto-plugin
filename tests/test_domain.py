import unittest
from app.domain import profile_from_text, analyze, validate_selection, normalize_job

class DomainTests(unittest.TestCase):
    def setUp(self):
        self.profile=profile_from_text('技能特长\n熟悉数据治理和 SQL，负责指标体系与数据质量。\n工作经验\n负责政企 B 端产品设计及大模型报告解析。','resume.txt')
        self.job={'title':'数据产品经理','company':'测试公司','city':'北京','salary':'20-30K','description':'负责数据治理、指标体系与数据质量，需要 SQL 能力及 B端产品经验。'}
    def test_rule_matching_has_real_evidence(self):
        a=analyze(self.job,self.profile,{'city':'北京','min_salary':20})
        self.assertTrue(a['matches'])
        for m in a['matches']:
            self.assertIn(m['quote'],next(f['text'] for f in self.profile['facts'] if f['id']==m['fact_id']))
        self.assertNotIn('exclude',a['decision'])
    def test_city_excludes(self):
        self.assertEqual(analyze({**self.job,'city':'上海'},self.profile,{'city':'北京'})['decision'],'exclude')
    def test_c_end_gap_not_invented(self):
        a=analyze({**self.job,'description':'要求5年以上 C端产品经验，负责消费者增长。'},self.profile,{})
        self.assertTrue(any('C端' in g for g in a['gaps']))
        self.assertNotEqual(a['decision'],'match')
    def test_unknown_salary_requires_review(self):
        a=analyze({**self.job,'salary':'\ue032\ue039K'},self.profile,{'min_salary':20})
        self.assertTrue(any('薪资' in g for g in a['gaps']))
        self.assertEqual(a['decision'],'review')
    def test_model_fabricated_evidence_rejected(self):
        with self.assertRaises(ValueError):
            validate_selection({'jd_focus':'数据治理','highlights':[{'fact_id':'missing','quote':'经验'}]},self.job,self.profile)
        with self.assertRaises(ValueError):
            validate_selection({'jd_focus':'数据治理','highlights':[{'fact_id':self.profile['facts'][0]['id'],'quote':'带领100人团队'}]},self.job,self.profile)
    def test_model_quote_validated(self):
        f=self.profile['facts'][0]
        quotes=validate_selection({'jd_focus':'数据治理','highlights':[{'fact_id':f['id'],'quote':'熟悉数据治理和 SQL'}]},self.job,self.profile)
        self.assertEqual(quotes[0]['quote'],'熟悉数据治理和 SQL')
    def test_clean_link_and_reject_non_boss(self):
        j=normalize_job({**self.job,'job_id':'a','source_url':'https://www.zhipin.com/job_detail/a.html?securityId=secret'})
        self.assertEqual(j['source_url'],'https://www.zhipin.com/job_detail/a.html')
        with self.assertRaises(ValueError):normalize_job({**self.job,'source_url':'https://evil.com/job_detail/a'})
    def test_profile_ignores_contacts(self):
        p=profile_from_text('手机：13800138000\n邮箱：test@example.com\n技能特长\n熟悉SQL数据分析','x')
        self.assertFalse(any('13800138000' in f['text'] or '@' in f['text'] for f in p['facts']))
    def test_plain_ai_jd_has_evidence(self):
        p=profile_from_text('工作经验\n负责 AI 报告解析产品，构建证据抽取与人工复核流程。','x')
        a=analyze({**self.job,'title':'AI产品经理','description':'整合现有AI使用，形成AI需求方案，落地产品。'},p,{})
        self.assertTrue(any(m['requirement']=='AI产品' for m in a['matches']))
    def test_prefers_actual_cross_team_experience_over_certificate(self):
        p=profile_from_text('技能特长\n以5A成绩通过项目管理专业认证。\n工作经验\n协调跨团队合作推进产品交付，管理需求与验收。','x')
        a=analyze({**self.job,'description':'负责跨团队合作推进产品。'},p,{})
        self.assertIn('跨团队',a['matches'][0]['quote'])
