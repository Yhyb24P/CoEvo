"""Scoped experience/skill retrieval in an explicitly isolated experiment State.

Administrative registration is outside the evaluated Agent. These records are
observations and experience, never runtime authorization or Instructions.
"""
import json
import time


def matches(conditions, context):
    return all(context.get(key)==value for key,value in conditions.items())


class Memory:
    def __init__(self,state):
        if not getattr(state,'namespace',None):
            raise ValueError('Experience pool requires an isolated experiment state')
        self.state=state
        state.db.execute('''CREATE TABLE IF NOT EXISTS memory_objects (
            id TEXT PRIMARY KEY, kind TEXT NOT NULL, source TEXT NOT NULL,
            body TEXT NOT NULL, conditions TEXT NOT NULL, origins TEXT NOT NULL,
            parents TEXT NOT NULL, status TEXT NOT NULL, created REAL NOT NULL)''')
        state.db.commit()

    def register(self,identity,kind,source,body,conditions,origins,parents=()):
        if kind not in ('instance','skill') or not source or not origins:
            raise ValueError('Experience requires its own kind, source and evidence origins')
        if not isinstance(conditions,dict) or any(not isinstance(k,str) or not isinstance(v,(str,int,bool)) for k,v in conditions.items()):
            raise ValueError('First pilot supports explicit scalar equality conditions')
        for parent in parents:
            row=self.state.db.execute('SELECT source FROM memory_objects WHERE id=?',(parent,)).fetchone()
            if row is None or row[0]!=source:
                raise ValueError('Derived experience must retain its original source')
        with self.state.db:
            self.state.db.execute('INSERT INTO memory_objects VALUES (?,?,?,?,?,?,?,?,?)',(
                identity,kind,source,body,json.dumps(conditions),json.dumps(origins),json.dumps(list(parents)),
                'active',time.time()))
            self.state.db.execute('INSERT INTO events(timestamp,kind,payload) VALUES (?,?,?)',(
                time.time(),'memory-register',json.dumps({'id':identity,'source':source,'parents':list(parents),'actor':'external-controller'})))

    def revoke(self,identity,reason):
        with self.state.db:
            if not self.state.db.execute('SELECT 1 FROM memory_objects WHERE id=?',(identity,)).fetchone():
                raise ValueError('Unknown experience')
            self.state.db.execute("UPDATE memory_objects SET status='revoked' WHERE id=?",(identity,))
            self.state.db.execute('INSERT INTO events(timestamp,kind,payload) VALUES (?,?,?)',(
                time.time(),'memory-revoke',json.dumps({'id':identity,'reason':reason,'actor':'external-controller'})))

    def _records(self):
        rows=self.state.db.execute('SELECT id,kind,source,body,conditions,origins,parents,status FROM memory_objects ORDER BY created,id').fetchall()
        return [{'id':r[0],'kind':r[1],'source_cluster_id':r[2],'body':r[3],
                 'conditions':json.loads(r[4]),'origins':json.loads(r[5]),'parents':json.loads(r[6]),'status':r[7]}
                for r in rows]

    def retrieve(self,context,mode,max_items=1,max_chars=1000):
        if mode not in ('M0','M1','M2','M3'):raise ValueError('Unknown memory intervention')
        records=self._records();by_id={r['id']:r for r in records}
        def valid(identity,seen=()):
            if identity in seen:return False
            r=by_id.get(identity)
            return bool(r and r['status']=='active' and all(valid(p,(*seen,identity)) for p in r['parents']))
        selected=[]
        for record in reversed(records):
            if mode=='M0':break
            if mode=='M1' and record['kind']!='instance':continue
            if mode in ('M2','M3') and (record['kind']!='skill' or not matches(record['conditions'],context)):continue
            if mode=='M3' and not valid(record['id']):continue
            # Status is deliberately not shown to M1/M2: invalidation is the M3
            # intervention. Original status and ancestry remain in the run record.
            visible={k:record[k] for k in ('id','kind','source_cluster_id','body')}
            text=json.dumps(visible,ensure_ascii=False)
            if sum(len(json.dumps(r,ensure_ascii=False)) for r in selected)+len(text)>max_chars:continue
            selected.append(visible)
            if len(selected)>=max_items:break
        return {'mode':mode,'selected':selected,'selected_ids':[r['id'] for r in selected],
                'context':context,'max_items':max_items,'max_chars':max_chars,
                'text':json.dumps(selected,ensure_ascii=False) if selected else '',
                'source_kind':'Experience, not Instruction','conditions_checked':mode in ('M2','M3'),
                'invalidation_checked':mode=='M3'}
