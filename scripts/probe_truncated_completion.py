"""One deliberately truncated, non-legal Qwen request to verify SDK telemetry."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from legal_ai_agent.casework.model_observation import observe_response,observe_exception,correction_error
from legal_ai_agent.llm.qwen_llm import get_llm
from legal_ai_agent.config.settings import QWEN_API_KEY


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():parser.error('Existing evidence is never overwritten')
    if not QWEN_API_KEY:parser.error('DASHSCOPE_API_KEY is not configured')
    prompt='接口诊断任务，无需法律分析。请输出一个JSON对象，numbers字段为从1到1000的全部整数数组，不省略任何数字。'
    record={'requested_model':'qwen-plus','max_tokens':16,'max_retries':0,'timeout':30,
            'actual_model':'unknown','usage':None,'finish_reason':None,
            'context_sha256':hashlib.sha256(prompt.encode()).hexdigest()}
    report={'scope':'One intentionally truncated non-legal diagnostic; not a case test or success-rate observation.',
            'expert_reviewed':False,'diagnostic_only':True,
            'implementation_sha256':{p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
                for p in [Path(__file__).resolve(),ROOT/'legal_ai_agent/casework/model_observation.py']}}
    started=time.monotonic()
    try:
        llm=get_llm(model_name='qwen-plus',temperature=.1,timeout=30,max_retries=0,max_tokens=16).bind(
            response_format={'type':'json_object'},extra_body={'enable_thinking':False})
        response=llm.invoke(prompt)
        observe_response(record,response)
        record['status']='ok'
    except Exception as exc:
        observe_exception(record,exc)
        record.update(status='failed',error=correction_error(exc).replace(QWEN_API_KEY,'[redacted]'))
    record['seconds']=round(time.monotonic()-started,3)
    passed=record['status']=='failed' and record['finish_reason']=='length' and record['actual_model']=='qwen-plus' and bool(record['usage'])
    report.update(status='observed_expected_rejection' if passed else 'unexpected_result',call=record)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'status':report['status'],'metadata_source':record.get('metadata_source'),'usage_reported':bool(record['usage'])}))
    if not passed:raise SystemExit(1)


if __name__=='__main__':main()
