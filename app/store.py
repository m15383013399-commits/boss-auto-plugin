"""Local SQLite persistence with evidence/review invalidation."""
import json
import math
import os
import secrets
import sqlite3
import threading
from pathlib import Path
from urllib.parse import urlsplit
from .domain import profile_from_text, normalize_job, analyze, greeting
from .model import validate_config, select_evidence
from .batches import BatchStore
from .batch_analysis import BatchAnalysis
from .evaluation import evaluate_job, compose_greeting

class Store(BatchStore,BatchAnalysis):
    def __init__(self, path):
        self.path=Path(path);self.path.mkdir(parents=True,exist_ok=True);self.path.chmod(0o700)
        self.lock=threading.RLock()
        self._workers=[];self._match_cancel=threading.Event();self._closed=False
        keyfile=self.path/'local-key'
        if not keyfile.exists(): self._private_write(keyfile,secrets.token_urlsafe(32))
        self.key=keyfile.read_text().strip();keyfile.chmod(0o600)
        self.db=sqlite3.connect(self.path/'workspace.sqlite3',check_same_thread=False)
        (self.path/'workspace.sqlite3').chmod(0o600)
        self.db.execute('CREATE TABLE IF NOT EXISTS settings (name TEXT PRIMARY KEY, value TEXT NOT NULL)')
        self.db.execute('CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, value TEXT NOT NULL)');self.db.commit()
        self.init_batches()

    def _private_write(self,path,text):
        tmp=path.with_suffix('.tmp')
        fd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
        with os.fdopen(fd,'w') as f:f.write(text)
        tmp.chmod(0o600);os.replace(tmp,path)

    def _setting(self,name,default):
        row=self.db.execute('SELECT value FROM settings WHERE name=?',(name,)).fetchone()
        return json.loads(row[0]) if row else default
    def _set(self,name,value):
        self.db.execute('INSERT OR REPLACE INTO settings VALUES (?,?)',(name,json.dumps(value,ensure_ascii=False)))
    def _jobs(self):return [json.loads(r[0]) for r in self.db.execute('SELECT value FROM jobs ORDER BY rowid DESC')]
    def _put(self,j):self.db.execute('INSERT INTO jobs VALUES (?,?) ON CONFLICT(id) DO UPDATE SET value=excluded.value',(j['id'],json.dumps(j,ensure_ascii=False)))
    def _profile(self):return self._setting('profile',{'text':'','filename':'','facts':[],'version':0})
    def _prefs(self):return self._setting('preferences',{'city':'北京','min_salary':20,'exclude_words':[]})
    def _config(self):
        p=self.path/'model.json'
        return json.loads(p.read_text()) if p.exists() else {'base_url':'','model':'','api_key':''}
    def snapshot(self):
        with self.lock:
            c=self._config()
            return {'profile':self._profile(),'preferences':self._prefs(),'model':{'base_url':c['base_url'],'model':c['model'],'configured':bool(c['api_key'] and c['base_url'] and c['model'])},'pairing_key':self.key,'jobs':self._jobs(),'batches':self._batches(),'mode':'draft_only'}
    def get_job(self,ident):
        with self.lock:
            row=self.db.execute('SELECT value FROM jobs WHERE id=?',(ident,)).fetchone()
            if not row:raise ValueError('岗位不存在')
            return json.loads(row[0])
    @staticmethod
    def _reset(j):j.update(analysis=None,draft='',reviewed=False,status='new',draft_citations=[],match_error='')
    def _invalidate(self):
        for j in self._jobs():self._reset(j);self._put(j)
    def set_profile(self,text,filename):
        p=profile_from_text(text,filename)
        with self.lock,self.db:
            p['version']=self._profile()['version']+1;self._set('profile',p);self._invalidate()
    def set_preferences(self,prefs):
        city=str(prefs.get('city','')).strip()
        try:salary=float(prefs.get('min_salary',0) or 0)
        except (ValueError,TypeError):raise ValueError('最低月薪格式不正确') from None
        words=prefs.get('exclude_words',[])
        if not math.isfinite(salary) or not 0<=salary<=1000 or len(city)>100 or not isinstance(words,list) or len(words)>50 or any(not isinstance(w,str) or len(w)>100 for w in words):
            raise ValueError('求职偏好格式不正确')
        p={'city':city,'min_salary':salary,'exclude_words':[w.strip() for w in words if w.strip()]}
        with self.lock,self.db:
            if p!=self._prefs():self._set('preferences',p);self._invalidate()
    def set_model(self,raw):
        with self.lock:
            old=self._config()
            c={**old,'api_key':''} if raw.get('clear') is True else validate_config({'base_url':raw.get('base_url',''),'model':raw.get('model',''),'api_key':raw.get('api_key') or old['api_key']})
            before,after=urlsplit(old['base_url']),urlsplit(c['base_url'])
            if old['api_key'] and not raw.get('api_key') and raw.get('clear') is not True and (before.scheme,before.netloc)!=(after.scheme,after.netloc):
                raise ValueError('更换模型服务地址时请重新填写该服务的 API Key，避免沿用其他服务的凭据')
            self._private_write(self.path/'model.json',json.dumps(c,ensure_ascii=False))
    def analyze_job(self,ident,engine):
        if engine not in ('rules','model'):raise ValueError('请选择规则分析或模型分析')
        with self.lock:
            j=self.get_job(ident);p=self._profile();prefs=self._prefs();config=self._config()
        result=analyze(j,p,prefs)
        if engine=='model':
            graded=evaluate_job(config,j,p)
            result.update(graded)
            result['decision']='exclude' if result['blockers'] else ('review' if graded['gaps'] or graded['score']<65 else 'match')
            result.pop('greeting',None)
        with self.lock,self.db:
            if self._closed or self._profile()!=p or self._prefs()!=prefs or self.get_job(ident)!=j:
                raise ValueError('分析期间简历、偏好或岗位已变更，请重新分析')
            j.update(analysis=result,match_error='')
            if engine=='model' and j['status']=='new':j['status']='matched'
            if engine=='rules':j.update(draft=result['greeting'],reviewed=False,status='draft',draft_citations=[])
            self._put(j)
        return result
    def generate_greeting(self,ident,style):
        with self.lock:
            j=self.get_job(ident);p=self._profile();config=self._config()
            if not p['facts']:raise ValueError('请先导入简历')
        result=compose_greeting(config,j,p,style)
        with self.lock,self.db:
            if self._closed or self._profile()!=p or self.get_job(ident)!=j:raise ValueError('生成期间简历或岗位已变更，请重试')
            j.update(draft=result['text'],draft_citations=result['citations'],draft_style=style,reviewed=False,status='draft');self._put(j)
        return result
    def save_draft(self,ident,text,reviewed):
        if not isinstance(text,str) or not 1<=len(text.strip())<=2000 or not isinstance(reviewed,bool):raise ValueError('草稿需为 1–2000 字符，并明确审核状态')
        with self.lock,self.db:
            j=self.get_job(ident)
            if j['draft']!=text.strip():j['draft_citations']=[]
            j.update(draft=text.strip(),reviewed=reviewed,status='draft');self._put(j)
    def queue(self,ident):
        with self.lock,self.db:
            j=self.get_job(ident);a=j['analysis']
            if not a or a['profile_version']!=self._profile()['version'] or a['decision']=='exclude' or not j['reviewed'] or not j['draft'].strip():
                raise ValueError('请先完成当前简历的岗位分析，并保存审核后的草稿；排除岗位不能加入队列')
            j['status']='queued';self._put(j)
    def set_status(self,ident,status):
        if status not in ('new','skipped'):raise ValueError('不支持该状态')
        with self.lock,self.db:
            j=self.get_job(ident);j['status']=status;self._put(j)
    def close(self):
        with self.lock:
            self._closed=True;self._match_cancel.set();self.db.close()
