"""Single manifest build entry; old Chroma directories are never overwritten."""
import argparse
import json
from pathlib import Path
from legal_ai_agent.casework.knowledge import build_index, INDEX_DIR

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--activate',action='store_true',help='accept candidate and atomically switch active pointer')
    parser.add_argument('--rollback',action='store_true',help='switch to the retained previous manifest index')
    parser.add_argument('--embeddings',action='store_true',help='build optional DashScope vectors for the filtered hybrid retriever')
    args=parser.parse_args()
    if args.rollback:
        import os
        previous=INDEX_DIR/'previous.json';active=INDEX_DIR/'active.json'
        if not previous.exists(): parser.error('no previous index available')
        old=active.read_text(encoding='utf-8') if active.exists() else None
        candidate=INDEX_DIR/'active.json.tmp';candidate.write_text(previous.read_text(encoding='utf-8'),encoding='utf-8');os.replace(candidate,active)
        if old: previous.write_text(old,encoding='utf-8')
        print('rolled back');return
    result=build_index(activate=False)
    if args.embeddings:
        from legal_ai_agent.llm.qwen_llm import get_embedding
        from legal_ai_agent.casework.knowledge import build_embeddings
        build_embeddings(Path(result['path'])/'index.json',get_embedding())
    if args.activate: result=build_index(activate=True)
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__': main()
