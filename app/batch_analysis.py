"""A single resumable matching worker; completed jobs survive UI closure."""
import threading

class BatchAnalysis:
    def start_batch_analysis(self,ident):
        with self.lock,self.db:
            if self._closed:raise ValueError('服务正在停止')
            if any(t.is_alive() for t in self._workers):raise ValueError('已有批次正在匹配，请等待完成或先停止')
            b=self.get_batch(ident)
            if b['status']=='collecting':raise ValueError('请完成或暂停导入后再匹配')
            if not b['count']:raise ValueError('这个批次没有岗位')
            if not self._profile()['facts'] or not self._config()['api_key']:raise ValueError('请先配置简历和模型')
            version=self._profile()['version']
            jobs=[j for j in self._jobs() if j.get('batch_id')==ident]
            done=sum(self._current_match(j,version) for j in jobs)
            b['matching']={'status':'running','done':done,'profile_version':version,'message':''};self._put_batch(b)
            event=threading.Event();self._match_cancel=event
            worker=threading.Thread(target=self._match_batch,args=(ident,version,event),daemon=True)
            self._workers=[worker];worker.start();return b
    @staticmethod
    def _current_match(j,version):return bool(j.get('analysis') and j['analysis'].get('scoring_version')==2 and j['analysis'].get('profile_version')==version)
    def cancel_batch_analysis(self,ident):
        with self.lock,self.db:
            b=self.get_batch(ident)
            if b['matching']['status']=='running':
                self._match_cancel.set();b['matching'].update(status='stopping',message='当前请求结束后停止');self._put_batch(b)
            return b
    def _match_batch(self,ident,version,event):
        message=''
        try:
            with self.lock:ids=[j['id'] for j in self._jobs() if j.get('batch_id')==ident and not self._current_match(j,version)]
            for jid in ids:
                if event.is_set():break
                with self.lock:
                    if self._profile()['version']!=version:message='简历已更新，请重新匹配';break
                try:self.analyze_job(jid,'model')
                except Exception as e:
                    with self.lock,self.db:
                        if self._closed:return
                        j=self.get_job(jid);j['match_error']=str(e)[:200] if isinstance(e,ValueError) else '匹配请求未完成，请重试';self._put(j)
                with self.lock,self.db:
                    if self._closed:return
                    b=self.get_batch(ident);b['matching']['done']=sum(self._current_match(j,version) for j in self._jobs() if j.get('batch_id')==ident);self._put_batch(b)
        finally:
            with self.lock:
                if not self._closed:
                  with self.db:
                    b=self.get_batch(ident);complete=b['matching']['done']==b['count']
                    b['matching'].update(status='completed' if complete else 'paused',message=message or ('匹配完成' if complete else '已保留完成结果，可点击匹配验证继续'))
                    self._put_batch(b)
