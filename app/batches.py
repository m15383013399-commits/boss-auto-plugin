"""Atomic batch accounting; only newly persisted jobs consume the target."""
import json
import secrets
from datetime import datetime, timezone
from .domain import normalize_job

def now():return datetime.now(timezone.utc).isoformat()
def job_key(j):return j['source_url'] or 'manual:'+j['id']

class BatchStore:
    def init_batches(self):
        self.db.execute('CREATE TABLE IF NOT EXISTS batches (id TEXT PRIMARY KEY,value TEXT NOT NULL)')
        self.db.execute('CREATE TABLE IF NOT EXISTS job_keys (key TEXT PRIMARY KEY,job_id TEXT NOT NULL)')
        with self.db:
            legacy=[j for j in self._jobs() if not j.get('batch_id')]
            if legacy:
                b=self._new_batch(len(legacy),'历史导入','')
                b.update(count=len(legacy),status='completed')
                for j in legacy:j['batch_id']=b['id'];self._put(j)
                self._put_batch(b)
            for j in self._jobs():
                normalized=normalize_job(j)
                self.db.execute('INSERT OR IGNORE INTO job_keys VALUES (?,?)',(job_key(normalized),j['id']))
            for b in self._batches():
                if b['status']=='collecting':b.update(status='paused',message='服务已重启，可在插件中继续采集')
                if b.get('matching',{}).get('status') in ('running','stopping'):b['matching'].update(status='paused',message='服务已重启，点击匹配验证继续')
                self._put_batch(b)
    def _batches(self):return [json.loads(r[0]) for r in self.db.execute('SELECT value FROM batches ORDER BY rowid DESC')]
    def _put_batch(self,b):self.db.execute('INSERT INTO batches VALUES (?,?) ON CONFLICT(id) DO UPDATE SET value=excluded.value',(b['id'],json.dumps(b,ensure_ascii=False)))
    def get_batch(self,ident):
        with self.lock:
            row=self.db.execute('SELECT value FROM batches WHERE id=?',(ident,)).fetchone()
            if not row:raise ValueError('导入批次不存在')
            return json.loads(row[0])
    def _new_batch(self,target,name,source_url):
        b={'id':secrets.token_hex(12),'name':name or '岗位导入','target':target,'count':0,'created_at':now(),'source_url':source_url,'status':'collecting','message':'','matching':{'status':'idle','done':0}}
        self._put_batch(b);return b
    def create_batch(self,target,name='',source_url=''):
        if isinstance(target,bool) or not isinstance(target,int) or not 1<=target<=200:raise ValueError('成功新增目标需为 1–200 个岗位')
        if not isinstance(name,str) or len(name)>100 or not isinstance(source_url,str) or len(source_url)>2000:raise ValueError('批次名称或筛选来源过长')
        # Search URL contains only user-selected filters; never retain session parameters.
        from urllib.parse import urlsplit,parse_qsl,urlencode
        u=urlsplit(source_url)
        if source_url and (u.scheme!='https' or u.hostname!='www.zhipin.com' or u.path!='/web/geek/jobs'):raise ValueError('批量导入需从 BOSS 职位搜索页开始')
        source_url=('https://www.zhipin.com/web/geek/jobs?'+urlencode([(k,v) for k,v in parse_qsl(u.query) if k in ('query','city','position','experience','degree','salary','industry','scale','stage','jobType')])) if source_url else ''
        with self.lock,self.db:return self._new_batch(target,name.strip(),source_url)
    def set_batch_status(self,ident,status,message=''):
        if status not in ('collecting','paused','stopped','exhausted'):raise ValueError('无效的批次状态')
        with self.lock,self.db:
            b=self.get_batch(ident)
            if b['count']<b['target']:b.update(status=status,message=str(message)[:250])
            self._put_batch(b);return b
    def known_urls(self):
        with self.lock:return [r[0] for r in self.db.execute('SELECT key FROM job_keys WHERE key LIKE ?',('https://%',))]
    def import_jobs(self,raw,batch_id=None):
        if not isinstance(raw,list) or not 1<=len(raw)<=50:raise ValueError('每次导入 1–50 个岗位')
        jobs=[normalize_job(j) for j in raw]
        with self.lock,self.db:
            b=self.get_batch(batch_id) if batch_id else None
            added=[]
            for j in jobs:
                if b and b['status']!='collecting':break
                if self.db.execute('SELECT 1 FROM job_keys WHERE key=?',(job_key(j),)).fetchone():continue
                if b is None:b=self._new_batch(len(jobs),'手动导入' if j['source']=='manual' else '单岗位导入','')
                if b['count']>=b['target']:break
                # URL-backed identities are independent of recruiter and capture route.
                if j['source_url']:
                    import hashlib
                    j['id']=hashlib.sha256(j['source_url'].encode()).hexdigest()[:24]
                j['batch_id']=b['id'];self._reset(j);self._put(j)
                self.db.execute('INSERT INTO job_keys VALUES (?,?)',(job_key(j),j['id']))
                added.append(j['id']);b['count']+=1
                if b['count']>=b['target']:b.update(status='completed',message='已达到成功新增目标')
            if b:
                if not batch_id and b['status']=='collecting':b.update(status='completed',target=b['count'])
                self._put_batch(b)
            return {'ok':True,'count':len(added),'added_ids':added,'batch':b}
