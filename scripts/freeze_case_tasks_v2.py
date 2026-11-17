"""Create a separate immutable v2; preserve all v1 requests and history."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'data/evaluation'

def main():
    original=DATA/'case_tasks_v1.json';raw=original.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=original.with_suffix('.sha256').read_text().strip():raise ValueError('v1 hash mismatch')
    payload=deepcopy(json.loads(raw));payload['version']='case-tasks-v2'
    payload['previous_dataset_sha256']=hashlib.sha256(raw).hexdigest()
    payload['changes_from_previous']=[]
    for task in payload['tasks']:
        if task['id'] not in ('W05','W06','W07'): continue
        before=deepcopy(task['expected'])
        task['expected'].update(status='no_supported_claim',no_conditional_claims=True)
        payload['changes_from_previous'].append({'id':task['id'],'before':before,'after':deepcopy(task['expected']),'reason':'所填工资没有欠付余额，应保留零余额核算结果，但不允许确认追讨零元的草稿。原输入和金额预期未改变。'})
    encoded=json.dumps(payload,ensure_ascii=False,sort_keys=True,indent=2).encode()
    target=DATA/'case_tasks_v2.json'
    if target.exists() and target.read_bytes()!=encoded:raise ValueError('v2 already frozen; use a new version')
    target.write_bytes(encoded);target.with_suffix('.sha256').write_text(hashlib.sha256(encoded).hexdigest()+'\n',encoding='ascii')
    print('Frozen v2:',len(payload['tasks']),'tasks; corrected expectations:',len(payload['changes_from_previous']))

if __name__=='__main__':main()
