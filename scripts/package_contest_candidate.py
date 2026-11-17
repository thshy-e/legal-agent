"""Create and verify a candidate source snapshot; never declares final release."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import subprocess
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
ROOT_FILES = ('README.md', '.env.example', '.gitignore', '.gitattributes', 'requirements.txt',
              'requirements-win-py312.snapshot.txt', 'app.py', 'start_server.py', 'build_db.py')
DIRECTORIES = ('legal_ai_agent', 'frontend', 'tests', 'scripts', 'data/legal_sources',
               'data/evaluation', 'data/law', 'data/case', 'data/raw', 'docs/evaluation/casework_v1',
               'docs/evaluation/casework_v2', 'docs/evaluation/conversation_v16', 'docs/evaluation/frontend_v17')
DOCS = ('API.md', 'ARCHITECTURE.md', 'DEMO_SCRIPT.md', 'GBA_CASEWORK_IMPLEMENTATION.md',
        'COMPETITION_TECHNICAL_REPORT.md', 'CONTEST_DELIVERY_STATUS.md', 'CANDIDATE_SNAPSHOT.md',
        'GITHUB_CHECKLIST.md', 'PROJECT_REASSESSMENT_2026-10-25.md', 'ROLE_CONTEXT_CONTRACT.md',
        'PROJECT_HANDOFF.md')
MEDIA = ('README.md', 'contest-casework-demo.webm', 'contest-confirmed-draft.png',
         'contest-revised-draft.png', 'contest-law-identity.png', 'casework-zero-balance.png',
         'citation-revision-v14-history.png', 'conversation-v16-desktop.png',
         'conversation-v16-mobile.png', 'frontend-v17-home-desktop.png',
         'frontend-v17-source-desktop.png', 'frontend-v17-draft-desktop.png',
         'frontend-v17-revised-desktop.png', 'frontend-v17-tablet.png',
         'frontend-v17-mobile-draft.png', 'frontend-v17-mobile-home.png',
         'frontend-v17-conversation.png', 'frontend-v17-demo.webm')
EXTENSIONS = {'.py', '.js', '.html', '.css', '.json', '.md', '.txt', '.csv', '.sha256', '.docx', '.cjs'}
FORBIDDEN = {'.git', 'venv', '.venv', '__pycache__', 'db', 'chroma_db', '.playwright-cli', 'legacy'}
MANIFEST = 'CANDIDATE_MANIFEST.json'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def safe_name(name):
    parts = PurePosixPath(name).parts
    if not parts or PurePosixPath(name).is_absolute() or '\\' in name or ':' in name:
        return False
    return not any(part in FORBIDDEN or part in ('.', '..') or
                   (part.startswith('.env') and part != '.env.example') for part in parts)


def collect(root):
    root = Path(root).resolve()
    paths = [root / name for name in ROOT_FILES]
    paths += [root / 'docs' / name for name in DOCS]
    paths += [root / 'output/playwright' / name for name in MEDIA]
    for directory in DIRECTORIES:
        paths += [p for p in (root / directory).rglob('*') if p.is_file() and p.suffix in EXTENSIONS]
    result = {}
    for path in paths:
        if not path.is_file():
            raise ValueError('Required snapshot file is missing: ' + str(path.relative_to(root)))
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise ValueError('Snapshot file leaves the workspace')
        name = path.relative_to(root).as_posix()
        if safe_name(name):
            result[name] = path
    return dict(sorted(result.items()))


def credential(root):
    secret = os.getenv('DASHSCOPE_API_KEY', '').strip()
    env = Path(root) / '.env'
    if not secret and env.is_file():
        for line in env.read_text(encoding='utf-8').splitlines():
            if line.strip().startswith('DASHSCOPE_API_KEY='):
                secret = line.split('=', 1)[1].strip().strip('\"\'')
    return secret.encode() if secret else None


def create(root, output):
    root, output = Path(root).resolve(), Path(output).resolve()
    paths = collect(root)
    secret = credential(root)
    content = {}
    for name, path in paths.items():
        raw = path.read_bytes()
        if secret and secret in raw:
            raise ValueError('Credential found in selected snapshot file: ' + name)
        content[name] = raw
    validation = json.loads(content['docs/evaluation/casework_v2/validation.json'])
    revision = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=root, capture_output=True, text=True)
    manifest = {
        'kind': 'candidate_source_snapshot', 'final_release': False,
        'created_at': datetime.now(timezone.utc).isoformat(),
        'git_base_revision': revision.stdout.strip() if revision.returncode == 0 else None,
        'source_identity': 'Hashes below identify the working files, including uncommitted changes.',
        'python': platform.python_version(), 'platform': platform.system(),
        'knowledge_digest': validation['knowledge_digest'],
        'unresolved': validation['remaining'],
        'tests_recorded': validation['unittest'],
        'model_validation': validation['model_ablation'],
        'expert_reviewed': validation['expert_reviewed'],
        'frontend_version': validation.get('frontend_version'),
        'frontend_validation': validation.get('frontend_validation'),
        'excluded': ['credentials', 'private sessions', 'generated indexes', 'virtual environment',
                     'git history', 'legacy scripts', 'unselected old documents'],
        'files': [{'path': name, 'size': len(raw), 'sha256': sha(raw)} for name, raw in content.items()],
    }
    content[MANIFEST] = (json.dumps(manifest, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('xb') as stream:
        with ZipFile(stream, 'w', compression=ZIP_DEFLATED) as archive:
            for name, raw in content.items():
                info = ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                archive.writestr(info, raw)
    result = verify(output)
    output.with_suffix(output.suffix + '.sha256').write_text(result['archive_sha256'] + '\n', encoding='ascii')
    return result


def verify(path):
    path = Path(path)
    with ZipFile(path) as archive:
        names = archive.namelist()
        if len(set(names)) != len(names) or any(not safe_name(name) for name in names):
            raise ValueError('Unsafe or duplicate archive path')
        manifest = json.loads(archive.read(MANIFEST))
        files = manifest['files']
        if len({f['path'] for f in files}) != len(files) or set(names) != {MANIFEST, *(f['path'] for f in files)}:
            raise ValueError('Archive file inventory differs from manifest')
        for entry in files:
            raw = archive.read(entry['path'])
            if len(raw) != entry['size'] or sha(raw) != entry['sha256']:
                raise ValueError('Snapshot hash mismatch: ' + entry['path'])
        if manifest.get('final_release') is not False:
            raise ValueError('Candidate cannot claim final release')
    return {'archive': str(path), 'archive_sha256': sha(path.read_bytes()), 'files': len(files),
            'verified': True, 'final_release': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('create', 'verify'))
    parser.add_argument('archive', type=Path)
    args = parser.parse_args()
    result = create(ROOT, args.archive) if args.command == 'create' else verify(args.archive)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
