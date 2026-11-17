import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from legal_ai_agent.config.settings import embedding_base_url
from legal_ai_agent.llm.qwen_llm import get_embedding
from legal_ai_agent.casework.knowledge import build_embeddings


class WorkspaceEmbeddingTest(unittest.TestCase):
    def test_workspace_url_is_derived_without_switching_region(self):
        self.assertEqual(embedding_base_url('https://workspace.invalid/compatible-mode/v1'),'https://workspace.invalid/api/v1')
        self.assertEqual(embedding_base_url('https://custom.invalid/v2','https://native.invalid/api/v1/'),'https://native.invalid/api/v1')
        with self.assertRaises(ValueError):embedding_base_url('https://custom.invalid/v2')

    def test_document_and_query_use_scoped_endpoint_and_bounded_timeout(self):
        import dashscope
        previous=dashscope.base_http_api_url
        response=SimpleNamespace(status_code=200,output={'embeddings':[{'embedding':[0.1,0.2]}]})
        with patch('legal_ai_agent.llm.qwen_llm.get_dashscope_api_key',return_value='SYNTHETIC_KEY'), patch('dashscope.TextEmbedding.call',return_value=response) as call:
            embedding=get_embedding(base_url='https://workspace.invalid/api/v1',timeout=7)
            self.assertEqual(embedding.embed_documents(['example']),[[0.1,0.2]])
            self.assertEqual(embedding.embed_query('query'),[0.1,0.2])
        self.assertEqual(dashscope.base_http_api_url,previous)
        for request in call.call_args_list:
            self.assertEqual(request.kwargs['base_address'],'https://workspace.invalid/api/v1')
            self.assertEqual(request.kwargs['api_key'],'SYNTHETIC_KEY')
            self.assertEqual(request.kwargs['request_timeout'],7)

    def test_bad_vectors_do_not_replace_previous_index(self):
        with tempfile.TemporaryDirectory() as folder:
            index=Path(folder)/'index.json';target=index.with_name('vectors.json')
            index.write_text(json.dumps({'digest':'test','documents':[{'id':'a'},{'id':'b'}]}),encoding='utf-8')
            target.write_text('previous-valid-index',encoding='utf-8')
            for values in ([[1.0]],[[1.0],[1.0,2.0]],[[1.0],[float('nan')]],[[1.0],[]]):
                with self.subTest(values=values):
                    with self.assertRaises(ValueError):build_embeddings(index,SimpleNamespace(embed_documents=lambda texts:values))
                    self.assertEqual(target.read_text(encoding='utf-8'),'previous-valid-index')


if __name__=='__main__':unittest.main()
