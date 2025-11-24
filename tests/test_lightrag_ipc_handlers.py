import unittest
from unittest.mock import MagicMock, patch
import sys
import os

# 添加项目根目录到 path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gui.ipc.types import IPCRequest
from gui.ipc.w2p_handlers import lightrag_handler

class TestLightRAGIPCHandlers(unittest.TestCase):
    def setUp(self):
        self.mock_request = {
            'id': 'test-id-123',
            'type': 'request',
            'method': 'test.method',
            'params': {},
            'timestamp': 1234567890
        }
        self.mock_client = MagicMock()
        
        # Patch get_client to return our mock
        self.patcher = patch('gui.ipc.w2p_handlers.lightrag_handler.get_client', return_value=self.mock_client)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()

    def test_handle_ingest_files(self):
        """测试文件导入接口"""
        # 1. 测试正常情况
        params = {'paths': ['/tmp/test.txt']}
        self.mock_client.ingest_files.return_value = {'status': 'success', 'data': {'track_id': '123'}}
        
        response = lightrag_handler.handle_ingest_files(self.mock_request, params)
        
        self.assertEqual(response['status'], 'success')
        self.assertEqual(response['result']['data']['track_id'], '123')
        self.mock_client.ingest_files.assert_called_with(['/tmp/test.txt'], {})

        # 2. 测试参数缺失
        response = lightrag_handler.handle_ingest_files(self.mock_request, {})
        self.assertEqual(response['status'], 'error')
        self.assertEqual(response['error']['code'], 'INVALID_PARAMS')

    def test_handle_query(self):
        """测试查询接口"""
        # 1. 测试正常查询
        params = {'text': 'hello', 'options': {'mode': 'local'}}
        self.mock_client.query.return_value = {'status': 'success', 'data': 'answer'}
        
        response = lightrag_handler.handle_query(self.mock_request, params)
        
        self.assertEqual(response['status'], 'success')
        self.mock_client.query.assert_called_with('hello', {'mode': 'local'})

        # 2. 测试空查询
        response = lightrag_handler.handle_query(self.mock_request, {'text': ''})
        self.assertEqual(response['status'], 'error')

    def test_handle_query_graphs(self):
        """测试图查询接口 (前端可视化核心)"""
        params = {'label': '*', 'maxDepth': 2, 'maxNodes': 100}
        mock_graph_data = {'nodes': [{'id': 'A'}], 'edges': []}
        self.mock_client.query_graphs.return_value = mock_graph_data
        
        response = lightrag_handler.handle_query_graphs(self.mock_request, params)
        
        self.assertEqual(response['status'], 'success')
        self.assertEqual(response['result'], mock_graph_data)
        self.mock_client.query_graphs.assert_called_with('*', 2, 100)

    def test_handle_get_graph_label_list(self):
        """测试获取标签列表"""
        mock_labels = ['Person', 'Organization']
        self.mock_client.get_graph_label_list.return_value = {'status': 'success', 'data': mock_labels}
        
        response = lightrag_handler.handle_get_graph_label_list(self.mock_request, {})
        
        self.assertEqual(response['status'], 'success')
        self.assertEqual(response['result']['data'], mock_labels)

    def test_handle_insert_text(self):
        """测试文本插入"""
        params = {'text': 'Sample content', 'metadata': {'source': 'test'}}
        self.mock_client.insert_text.return_value = {'status': 'success'}
        
        response = lightrag_handler.handle_insert_text(self.mock_request, params)
        
        self.assertEqual(response['status'], 'success')
        self.mock_client.insert_text.assert_called_with('Sample content', {'source': 'test'})

    def test_handle_delete_document(self):
        """测试文档删除"""
        params = {'filePath': '/path/to/doc'}
        self.mock_client.delete_document.return_value = {'status': 'success'}
        
        response = lightrag_handler.handle_delete_document(self.mock_request, params)
        
        self.assertEqual(response['status'], 'success')
        self.mock_client.delete_document.assert_called_with('/path/to/doc')

    def test_handle_update_entity(self):
        """测试实体更新"""
        params = {
            'entity_name': 'Entity1', 
            'updated_data': {'prop': 'val'},
            'allow_rename': True
        }
        self.mock_client.update_entity.return_value = {'status': 'success'}
        
        response = lightrag_handler.handle_update_entity(self.mock_request, params)
        
        self.assertEqual(response['status'], 'success')
        self.mock_client.update_entity.assert_called_with('Entity1', {'prop': 'val'}, True, False)

if __name__ == '__main__':
    unittest.main()
