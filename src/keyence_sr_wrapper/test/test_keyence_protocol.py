"""Unit tests for Keyence SR node protocol logic."""

import socket
import threading
import unittest
from unittest.mock import MagicMock

import rclpy
from rclpy.node import Node
from rclpy.parameter import Parameter

from keyence_sr_wrapper.keyence_sr_node import KeyenceSRNode


class TestKeyenceProtocol(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        rclpy.init()

    @classmethod
    def tearDownClass(cls):
        rclpy.shutdown()

    def _make_node(self):
        node = KeyenceSRNode.__new__(KeyenceSRNode)
        Node.__init__(node, '_test_keyence')
        node.client_socket = None
        node._receive_buffer = b''
        node._socket_lock = threading.RLock()
        node.scanner_ip = '127.0.0.1'
        node.scanner_port = 9999
        node._scan_count = 0
        node._error_count = 0
        node.publisher_ = node.create_publisher(
            __import__('std_msgs.msg', fromlist=['String']).String,
            '/test_barcode', 10,
        )
        node.reconnect_interval_s = 0.0
        return node

    def test_connect_failure_sets_socket_none(self):
        node = self._make_node()
        node.scanner_ip = '192.0.2.1'
        node.scanner_port = 1
        node.connect_to_scanner()
        self.assertIsNone(node.client_socket)
        node.destroy_node()

    def test_parameter_update_keeps_existing_connection_on_failure(self):
        node = self._make_node()
        existing_socket = MagicMock()
        node.client_socket = existing_socket
        node.connect_to_scanner = MagicMock(return_value=False)

        result = node._on_parameter_changed([
            Parameter('scanner_ip', Parameter.Type.STRING, '192.0.2.1'),
        ])

        self.assertFalse(result.successful)
        self.assertEqual(node.scanner_ip, '127.0.0.1')
        self.assertEqual(node.scanner_port, 9999)
        self.assertIs(node.client_socket, existing_socket)
        node.connect_to_scanner.assert_called_once_with('192.0.2.1', 9999)
        node.destroy_node()

    def test_trigger_returns_failure_when_disconnected(self):
        node = self._make_node()
        node.scanner_ip = '192.0.2.1'
        node.scanner_port = 1
        from std_srvs.srv import Trigger
        response = Trigger.Response()
        result = node.trigger_scan_callback(Trigger.Request(), response)
        self.assertFalse(result.success)
        node.destroy_node()

    def test_trigger_parses_error_response(self):
        node = self._make_node()
        mock_sock = MagicMock()
        mock_sock.recv.return_value = b'ER001\r\n'
        node.client_socket = mock_sock
        from std_srvs.srv import Trigger
        response = Trigger.Response()
        result = node.trigger_scan_callback(Trigger.Request(), response)
        self.assertFalse(result.success)
        self.assertIn('ER001', result.message)
        node.destroy_node()

    def test_trigger_parses_success_response(self):
        node = self._make_node()
        mock_sock = MagicMock()
        mock_sock.recv.return_value = b'ABC123\r\n'
        node.client_socket = mock_sock
        from std_srvs.srv import Trigger
        response = Trigger.Response()
        result = node.trigger_scan_callback(Trigger.Request(), response)
        self.assertTrue(result.success)
        self.assertEqual(result.message, 'ABC123')
        node.destroy_node()

    def test_trigger_reassembles_fragmented_response(self):
        node = self._make_node()
        mock_sock = MagicMock()
        mock_sock.recv.side_effect = [b'ABC', b'123\r']
        node.client_socket = mock_sock
        from std_srvs.srv import Trigger
        response = Trigger.Response()
        result = node.trigger_scan_callback(Trigger.Request(), response)
        self.assertTrue(result.success)
        self.assertEqual(result.message, 'ABC123')
        node.destroy_node()

    def test_trigger_preserves_buffered_next_response(self):
        node = self._make_node()
        mock_sock = MagicMock()
        mock_sock.recv.return_value = b'FIRST\rSECOND\r'
        node.client_socket = mock_sock
        from std_srvs.srv import Trigger

        first = node.trigger_scan_callback(Trigger.Request(), Trigger.Response())
        second = node.trigger_scan_callback(Trigger.Request(), Trigger.Response())

        self.assertEqual(first.message, 'FIRST')
        self.assertEqual(second.message, 'SECOND')
        self.assertEqual(mock_sock.recv.call_count, 1)
        node.destroy_node()

    def test_trigger_treats_eof_as_disconnect(self):
        node = self._make_node()
        mock_sock = MagicMock()
        mock_sock.recv.return_value = b''
        node.client_socket = mock_sock
        node.connect_to_scanner = MagicMock(return_value=False)
        from std_srvs.srv import Trigger

        result = node.trigger_scan_callback(Trigger.Request(), Trigger.Response())

        self.assertFalse(result.success)
        self.assertIn('Communication Error', result.message)
        self.assertIsNone(node.client_socket)
        mock_sock.close.assert_called_once()
        node.destroy_node()

    def test_trigger_handles_timeout(self):
        node = self._make_node()
        mock_sock = MagicMock()
        mock_sock.recv.side_effect = socket.timeout('timed out')
        node.client_socket = mock_sock
        from std_srvs.srv import Trigger
        response = Trigger.Response()
        result = node.trigger_scan_callback(Trigger.Request(), response)
        self.assertFalse(result.success)
        self.assertIn('Timeout', result.message)
        self.assertIsNone(node.client_socket)
        node.destroy_node()


if __name__ == '__main__':
    unittest.main()
