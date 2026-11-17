"""Bounded synthetic conversation smoke; real calls, not legal accuracy scoring."""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    if args.output.exists(): parser.error('Choose a new output; previous evidence is preserved')
    from legal_ai_agent.api import server
    from legal_ai_agent.agents.qa_agent import QAAgent
    from legal_ai_agent.memory.memory_manager import ConversationStateStore
    from legal_ai_agent.casework.model_observation import observe_response, observe_exception
    from legal_ai_agent.conversation import VERSION
    report = {'version':VERSION,'created_at':datetime.now(timezone.utc).isoformat(),
              'scope':'Public synthetic conversational engineering smoke, not blind or legal accuracy.',
              'expert_reviewed':False,'cases':[],'calls':[]}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    def save():
        temporary = args.output.with_suffix('.json.tmp')
        with temporary.open('w',encoding='utf-8') as stream:
            stream.write(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary,args.output)
    agent = QAAgent()
    real = agent._get_balanced_llm()
    class ObservedModel:
        def invoke(self,messages):
            call = {'status':'failed','actual_model':'unknown','usage':None,
                    'messages':[{'role':m.type,'content':m.content} for m in messages]}
            report['calls'].append(call)
            started = time.monotonic()
            try:
                response = real.invoke(messages)
                observe_response(call,response)
                call['status']='response_received'
                return response
            except Exception as exc:
                observe_exception(call,exc)
                call['error_type']=type(exc).__name__
                raise
            finally:
                call['seconds']=round(time.monotonic()-started,3)
                save()
    agent.balanced_llm = ObservedModel()
    started = time.monotonic()
    with tempfile.TemporaryDirectory() as directory:
        store = ConversationStateStore(Path(directory)/'sessions.json')
        with patch.object(server,'conversation_store',store),patch.object(server,'qa',agent),patch.dict(os.environ,{'CASE_MODEL_ENABLED':'0'}):
            def ask(label,query,sid='probation',**extra):
                before = len(report['calls'])
                result = server._build_chat_payload({'query':query,'session_id':sid,**extra})
                entry = {'id':label,'query':query,'response':result,'model_calls':len(report['calls'])-before}
                entry['engineering_checks']={'conversation':result['structured']['presentation']['kind']=='conversation',
                    'completed':result['structured'].get('status') in ('completed','clarification'),
                    'no_legacy_report':not any(k in result['structured'] for k in ('metrics','risk','timeline'))}
                if label == 'C10':
                    entry['engineering_checks']['second_point_has_requested_topic'] = any(word in result['answer'] for word in ('催款','延期','欠条','沟通','拖欠的通知','欠薪的直接证据','银行流水','工资条','转账记录','个税'))
                report['cases'].append(entry)
                save()
                print(label+': '+result['structured']['status'],flush=True)
                return result
            for label,query in [('C01','试用期也要签劳动合同吗？'),('C02','公司说转正才签呢？'),
                                ('C03','为什么？'),('C04','该怎么办？'),('C05','我有点担心')]:
                ask(label,query)
            ask('C06','劳动法第47条是什么',sid='article')
            ask('C07','这一条是什么意思？',sid='article')
            ask('C08','N+1是什么意思？',sid='concept')
            ask('C09','请分两点告诉我，发生欠薪时可以先保存哪些材料？',sid='points')
            ask('C10','第二点是什么意思？',sid='points')
            ask('C11','这一条是什么意思？',sid='empty')
            server._build_chat_payload({'workflow':'case','session_id':'case','facts':{
                'workplace':'广州','employer_city':'广州','dispute_date':'2026-10-01',
                'wages':[{'start':'2026-09-01','end':'2026-09-30','due':'8000.10','paid':'1000'}]}})
            before = deepcopy(store.get('case')['case'])
            ask('C12','为什么需要工资流水？',sid='case')
            report['case_explanation_read_only']=store.get('case')['case']==before
            ask('C13','工资改成9000元，重新算',sid='case')
            report['ambiguous_revision_read_only']=store.get('case')['case']==before
    report['seconds']=round(time.monotonic()-started,3)
    report['all_engineering_checks_passed']=all(all(c['engineering_checks'].values()) for c in report['cases']) and report['case_explanation_read_only'] and report['ambiguous_revision_read_only']
    report['source_sha256']={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in
        [ROOT/'legal_ai_agent/conversation.py',ROOT/'legal_ai_agent/agents/qa_agent.py',ROOT/'legal_ai_agent/api/server.py',ROOT/'legal_ai_agent/memory/memory_manager.py',ROOT/'legal_ai_agent/casework/workflow.py']}
    report['missing_usage_calls']=sum(c['usage'] is None for c in report['calls'])
    report['recorded_input_tokens']=sum((c['usage'] or {}).get('input_tokens',0) for c in report['calls'])
    report['recorded_output_tokens']=sum((c['usage'] or {}).get('output_tokens',0) for c in report['calls'])
    save()
    print(json.dumps({k:report[k] for k in ('version','seconds','all_engineering_checks_passed','missing_usage_calls','recorded_input_tokens','recorded_output_tokens')},ensure_ascii=False),flush=True)
    if not report['all_engineering_checks_passed']: raise SystemExit(1)


if __name__=='__main__': main()
