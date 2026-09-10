"""Resume evidence and deterministic, explainable job screening."""
import hashlib
import io
import re
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit
from xml.etree import ElementTree
from zipfile import ZipFile, BadZipFile

THEMES = {
    '数据治理': ('数据治理', '数据质量', '血缘', '资产目录', '元数据'),
    '数据中台': ('数据中台', '数仓', '数据仓库', '数据建模', 'ods', 'dwd'),
    '指标体系': ('指标体系', '指标字典', '口径', '指标管理'),
    'SQL': ('sql',),
    'Python': ('python',),
    'B端产品': ('b端', '2b', '政企', '企业级', '业务系统'),
    'C端产品': ('c端', '2c', '消费者', '用户增长'),
    'AI产品': ('ai', '人工智能', '大模型'),
    '大模型应用': ('大模型', 'llm', 'prompt', '提示词', '结构化抽取'),
    'Agent': ('agent', '智能体', '工具调用', '多智能体'),
    'RAG': ('rag', '检索增强', '向量检索'),
    '产品设计': ('prd', '原型', '产品设计', '需求调研', '需求分析'),
    '项目交付': ('项目管理', '交付', '验收', '跨团队', '协调'),
    '数据分析': ('数据分析', 'bi', 'tableau', 'power bi', '看板'),
    '金融业务': ('金融', '银行', '证券', 'esg'),
}
HEADINGS = {'个人概述','技能特长','工作经验','教育背景','项目经历','专业技能'}


def compact(text):
    return re.sub(r'\s+', '', text).lower()

def contains(text, term):
    text,term=compact(text),compact(term)
    return bool(re.search(r'(?<![a-z])'+re.escape(term)+r'(?![a-z])',text)) if term.isascii() else term in text


def extract_docx(data):
    try:
        with ZipFile(io.BytesIO(data)) as z:
            info = z.getinfo('word/document.xml')
            if info.file_size > 4_000_000:
                raise ValueError('简历文档过大')
            root = ElementTree.fromstring(z.read(info))
        ns = {'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
        return '\n'.join(''.join(t.text or '' for t in p.findall('.//w:t', ns)) for p in root.findall('.//w:p', ns))
    except (BadZipFile, KeyError, ElementTree.ParseError) as e:
        raise ValueError('无法读取 DOCX，请上传未加密的 Word 文档或粘贴文本') from e


def profile_from_text(text, filename):
    if not isinstance(text, str) or not 20 <= len(text) <= 100_000:
        raise ValueError('简历文本需为 20–100000 字符')
    facts, section, cleaned = [], '简历', []
    for line in text.splitlines():
        line = line.strip()
        if not line or '@' in line or re.search(r'(?<!\d)1[3-9]\d{9}(?!\d)', line):
            continue
        if any(k in line for k in ['手机：', '电话：', '邮箱：']):
            continue
        cleaned.append(line)
        if line in HEADINGS or line.startswith('▍'):
            section = line
            continue
        if len(line) < 8:
            continue
        if line.startswith(('期望岗位','求职意向','期望薪资')):
            continue
        ident = 'f_' + hashlib.sha256((section+'\n'+line).encode()).hexdigest()[:14]
        if not any(f['id'] == ident for f in facts):
            facts.append({'id': ident, 'text': line, 'section': section})
    if not facts:
        raise ValueError('没有可用简历事实，请补充经历或技能原文')
    return {'filename': str(filename)[:200], 'text': '\n'.join(cleaned), 'facts': facts, 'version': 0}


def normalize_job(raw):
    if not isinstance(raw, dict):
        raise ValueError('岗位格式必须为对象')
    j = {k: str(raw.get(k, '') or '').strip() for k in ('job_id','recruiter_id','title','company','city','salary','recruiter','description','source_url','source')}
    if not j['title'] or not j['company'] or len(j['description']) < 30:
        raise ValueError('请提供岗位名、公司及至少 30 字的完整 JD')
    if len(j['description']) > 60000 or any(len(j[k]) > 500 for k in ('title','company','city','salary','recruiter','job_id','recruiter_id')):
        raise ValueError('岗位字段过长')
    if j['source_url']:
        u = urlsplit(j['source_url'])
        if u.scheme != 'https' or not (u.hostname == 'zhipin.com' or (u.hostname or '').endswith('.zhipin.com')) or u.username or u.password:
            raise ValueError('岗位链接必须为 HTTPS BOSS 直聘链接')
        j['source_url'] = urlunsplit(('https','www.zhipin.com',u.path.rstrip('/'),'',''))
    if not j['job_id']:
        j['job_id'] = 'manual_' + hashlib.sha256((j['title']+'|'+j['company']+'|'+j['source_url']).encode()).hexdigest()[:20]
    j['id'] = hashlib.sha256((j['job_id']+'|'+j['recruiter_id']).encode()).hexdigest()[:24]
    j['source'] = j['source'] or 'manual'
    j['captured_at'] = datetime.now(timezone.utc).isoformat()
    return j


def salary_bounds(value):
    m = re.search(r'(\d+(?:\.\d+)?)\s*[-~–]\s*(\d+(?:\.\d+)?)\s*[kK]', value)
    if m:
        return float(m[1]), float(m[2])
    m = re.search(r'(\d+(?:\.\d+)?)\s*[kK]', value)
    return (float(m[1]),float(m[1])) if m else None


def brief_quote(text, terms, limit=82):
    # Keep a literal substring; no paraphrasing or newly invented numbers.
    parts = re.split(r'[；;。\n]',text)
    selected = next((p.strip() for p in parts if any(compact(t) in compact(p) for t in terms) and len(p.strip()) >= 8),text)
    return selected[:limit]


def greeting(job, matches, focus=''):
    intro = '您好，关注到贵司的「'+job['title'][:40]+'」岗位。'
    if not matches:
        return intro + '希望进一步了解岗位职责及团队对相关经验的要求，方便沟通吗？'
    evidence = '；'.join(m['quote'].rstrip('。；') for m in matches[:2])
    focus_line = '看到 JD 中提到“'+focus+'”。' if focus else ''
    return intro + focus_line + '我的相关经历：' + evidence + '。希望结合这些经验进一步交流，方便沟通吗？'


def analyze(job, profile, prefs):
    facts = profile.get('facts', [])
    if not facts:
        raise ValueError('请先导入简历')
    jd = compact(job['title']+' '+job['description'])
    matches, gaps, blockers, covered, requested = [], [], [], 0, 0
    for name, terms in THEMES.items():
        requested_terms=[t for t in terms if contains(jd,t)]
        if not requested_terms:
            continue
        requested += 1
        candidates = [f for f in facts if any(contains(f['text'],t) for t in terms)]
        if candidates:
            covered += 1
            # A certificate or career wish cannot stand in for delivery experience.
            f = min(candidates,key=lambda f:(f['section']=='教育背景' or '认证' in f['text'],
                -sum(contains(f['text'],t) for t in requested_terms),
                f['section'] in ('个人概述','技能特长','简历'),
                not f['text'].startswith('职责'),-sum(contains(f['text'],t) for t in terms),len(f['text'])))
            matches.append({'requirement':name,'fact_id':f['id'],'quote':brief_quote(f['text'],terms)})
        else:
            gaps.append(name+'：简历未找到直接依据，需确认')
    city = prefs.get('city','').strip()
    if city and job.get('city') and city not in job['city']:
        blockers.append('城市不符：期望'+city+'，岗位为'+job['city'])
    elif city and not job.get('city'):
        gaps.append('岗位城市未知，需确认')
    minimum = float(prefs.get('min_salary',0) or 0)
    bounds = salary_bounds(job.get('salary',''))
    if minimum and not bounds:
        gaps.append('薪资无法可靠解析，需确认')
    elif minimum and bounds[1] < minimum:
        blockers.append('薪资上限低于期望最低月薪 '+str(minimum)+'K')
    for word in prefs.get('exclude_words',[]):
        if word and compact(word) in compact(job['company']+' '+job['description']):
            blockers.append('命中排除词：'+word)
    score = round(covered / requested * 100) if requested else 0
    if not requested:
        gaps.append('JD 缺少明确技能主题，需要人工判断')
    decision = 'exclude' if blockers else ('review' if gaps or score < 65 else 'match')
    unique = []
    for m in matches:
        if not any(x['fact_id']==m['fact_id'] for x in unique): unique.append(m)
    return {'score':score,'decision':decision,'engine':'rules','matches':matches,'gaps':gaps,'blockers':blockers,'greeting':greeting(job,unique),'profile_version':profile.get('version',0)}


def validate_selection(selection, job, profile):
    if not isinstance(selection, dict): raise ValueError('模型返回格式错误')
    focus = selection.get('jd_focus','')
    if not isinstance(focus,str) or not 2 <= len(focus) <= 32 or focus not in job['description']:
        raise ValueError('模型的岗位需求摘录必须逐字来自 JD（2–32 字）')
    highlights = selection.get('highlights')
    if not isinstance(highlights,list) or not 1 <= len(highlights) <= 2:
        raise ValueError('模型必须选择 1–2 条简历证据')
    facts = {f['id']: f['text'] for f in profile['facts']}
    result = []
    for h in highlights:
        if not isinstance(h,dict): raise ValueError('模型证据格式错误')
        fid, quote = h.get('fact_id'),h.get('quote')
        if not isinstance(fid,str) or fid not in facts or not isinstance(quote,str) or not 8 <= len(quote) <= 82 or quote not in facts[fid]:
            raise ValueError('模型引用了不存在或非原文的简历证据，已阻止生成')
        result.append({'requirement':focus,'fact_id':fid,'quote':quote})
    return result
