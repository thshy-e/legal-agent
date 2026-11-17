"""A contest snapshot must exclude private state and verify its actual bytes."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from scripts.package_contest_candidate import ROOT_FILES, DOCS, MEDIA, create, safe_name, verify


class CandidateSnapshotTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / 'source'; self.root.mkdir()
        self.archive = Path(self.tmp.name) / 'candidate.zip'
        for name in (*ROOT_FILES, *(str(Path('docs') / n) for n in DOCS),
                     *(str(Path('output/playwright') / n) for n in MEDIA)):
            path = self.root / name; path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('synthetic fixture', encoding='utf-8')
        for name in ('legal_ai_agent/public.py', 'scripts/legacy/private.py', 'db/conversation_state.json'):
            path = self.root / name; path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('synthetic fixture', encoding='utf-8')
        path = self.root / 'docs/evaluation/casework_v2/validation.json'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({'knowledge_digest': 'synthetic', 'remaining': ['external validation'],
                                   'unittest': {}, 'model_ablation': {}, 'expert_reviewed': False}), encoding='utf-8')

    def tearDown(self):
        self.tmp.cleanup()

    @patch.dict('os.environ', {'DASHSCOPE_API_KEY': ''})
    def test_private_files_are_excluded_and_existing_archive_is_preserved(self):
        (self.root / '.env').write_text('DASHSCOPE_API_KEY=SYNTHETIC_PRIVATE_KEY', encoding='utf-8')
        result = create(self.root, self.archive)
        self.assertTrue(result['verified']); self.assertFalse(result['final_release'])
        with ZipFile(self.archive) as archive:
            names = archive.namelist()
            self.assertNotIn('.env', names); self.assertNotIn('db/conversation_state.json', names)
            self.assertNotIn('scripts/legacy/private.py', names)
        raw = self.archive.read_bytes()
        with self.assertRaises(FileExistsError): create(self.root, self.archive)
        self.assertEqual(self.archive.read_bytes(), raw)

    @patch.dict('os.environ', {'DASHSCOPE_API_KEY': 'SYNTHETIC_PRIVATE_KEY'})
    def test_credential_in_public_source_prevents_package_creation(self):
        (self.root / 'legal_ai_agent/public.py').write_text('SYNTHETIC_PRIVATE_KEY', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'Credential found'):
            create(self.root, self.archive)
        self.assertFalse(self.archive.exists())

    def test_tampered_bytes_and_unsafe_paths_fail_verification(self):
        create(self.root, self.archive)
        changed = self.archive.with_name('tampered.zip')
        with ZipFile(self.archive) as source, ZipFile(changed, 'w') as target:
            for name in source.namelist():
                raw = source.read(name)
                target.writestr(name, raw + b'changed' if name == 'README.md' else raw)
        with self.assertRaisesRegex(ValueError, 'hash mismatch'): verify(changed)
        for name in ('../escape', '/absolute', 'D:/drive', 'a\\b', '.env', 'db/state.json'):
            self.assertFalse(safe_name(name), name)
        self.assertTrue(safe_name('.env.example'))


if __name__ == '__main__': unittest.main()
