"""Unit tests for Keyence SR node protocol logic."""

import socket
import threading
import time
import unittest
from unittest.mock import MagicMock, patch

import rclpy
from rclpy.parameter import Parameter

from keyence_sr_wrapper.keyence_sr_node import KeyenceSRNode


class TestKeyenceProtocol(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        rclpy.init()

    @classmethod
    def tearDownClass(cls):
        rclpy.shutdown()

    def _make_node(self, scanner_port=9999):
        return KeyenceSRNode(parameter_overrides=[
            Parameter('scanner_ip', value='127.0.0.1'),
            Parameter('scanner_port', value=scanner_port),
            Parameter('reconnect_interval_s', value=0.0),
        ])

    def test_connect_failure_sets_socket_none(self):
        node = self._make_node()
        node._scanner_ip = '192.0.2.1'
        node._scanner_port = 1
        node.connect_to_scanner()
        self.assertIsNone(node._client_socket)
        node.destroy_node()

    def test_connect_does_not_hold_socket_state_lock_during_network_io(self):
        node = self._make_node()
        connect_started = threading.Event()
        release_connect = threading.Event()
        candidate_socket = MagicMock()

        def block_connect(endpoint):
            connect_started.set()
            release_connect.wait(timeout=2.0)

        candidate_socket.connect.side_effect = block_connect
        with patch(
            'keyence_sr_wrapper.keyence_sr_node.socket.socket',
            return_value=candidate_socket,
        ):
            thread = threading.Thread(target=node.connect_to_scanner)
            thread.start()
            self.assertTrue(connect_started.wait(timeout=1.0))
            self.assertTrue(node._socket_lock.acquire(timeout=0.2))
            node._socket_lock.release()
            release_connect.set()
            thread.join(timeout=2.0)

        self.assertFalse(thread.is_alive())
        self.assertIs(node._client_socket, candidate_socket)
        node.destroy_node()

    def test_parameter_update_keeps_existing_connection_on_failure(self):
        node = self._make_node()
        existing_socket = MagicMock()
        node._client_socket = existing_socket
        node.connect_to_scanner = MagicMock(return_value=False)

        result = node._on_parameter_changed([
            Parameter('scanner_ip', Parameter.Type.STRING, '192.0.2.1'),
        ])

        self.assertFalse(result.successful)
        self.assertEqual(node._scanner_ip, '127.0.0.1')
        self.assertEqual(node._scanner_port, 9999)
        self.assertIs(node._client_socket, existing_socket)
        node.connect_to_scanner.assert_called_once_with('192.0.2.1', 9999)
        node.destroy_node()

    def test_trigger_returns_failure_when_disconnected(self):
        node = self._make_node()
        node._scanner_ip = '192.0.2.1'
        node._scanner_port = 1
        from std_srvs.srv import Trigger
        response = Trigger.Response()
        result = node.trigger_scan_callback(Trigger.Request(), response)
        self.assertFalse(result.success)
        node.destroy_node()

    def test_trigger_parses_error_response(self):
        node = self._make_node()
        mock_sock = MagicMock()
        mock_sock.recv.return_value = b'ER001\r\n'
        node._client_socket = mock_sock
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
        node._client_socket = mock_sock
        from std_srvs.srv import Trigger
        response = Trigger.Response()
        result = node.trigger_scan_callback(Trigger.Request(), response)
        self.assertTrue(result.success)
        self.assertEqual(result.message, 'ABC123')
        node.destroy_node()

    def test_trigger_parses_utf8_response(self):
        node = self._make_node()
        mock_sock = MagicMock()
        mock_sock.recv.return_value = '物料批次-20260825\r'.encode('utf-8')
        node._client_socket = mock_sock
        from std_srvs.srv import Trigger
        response = Trigger.Response()
        result = node.trigger_scan_callback(Trigger.Request(), response)
        self.assertTrue(result.success)
        self.assertEqual(result.message, '物料批次-20260825')
        node.destroy_node()

    def test_trigger_reassembles_fragmented_response(self):
        node = self._make_node()
        mock_sock = MagicMock()
        mock_sock.recv.side_effect = [b'ABC', b'123\r']
        node._client_socket = mock_sock
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
        node._client_socket = mock_sock
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
        node._client_socket = mock_sock
        node.connect_to_scanner = MagicMock(return_value=False)
        from std_srvs.srv import Trigger

        result = node.trigger_scan_callback(Trigger.Request(), Trigger.Response())

        self.assertFalse(result.success)
        self.assertIn('Communication Error', result.message)
        self.assertIsNone(node._client_socket)
        mock_sock.close.assert_called_once()
        node.destroy_node()

    def test_trigger_handles_timeout(self):
        node = self._make_node()
        mock_sock = MagicMock()
        mock_sock.recv.side_effect = socket.timeout('timed out')
        node._client_socket = mock_sock
        from std_srvs.srv import Trigger
        response = Trigger.Response()
        result = node.trigger_scan_callback(Trigger.Request(), response)
        self.assertFalse(result.success)
        self.assertIn('Timeout', result.message)
        self.assertIsNone(node._client_socket)
        node.destroy_node()

    def test_trigger_tolerates_slow_scanner_response(self):
        """Responses slower than the 3 s connect timeout must still work.

        Regression test: connect_to_scanner() leaves a 3 s socket timeout on
        the socket; _receive_response_from() must honor response_timeout_s
        instead, or every slow physical scan (>3 s) would tear down the
        connection.
        """
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.bind(('127.0.0.1', 0))
        server.listen(1)
        port = server.getsockname()[1]

        def serve_slow():
            connection, _ = server.accept()
            with connection:
                self.assertEqual(connection.recv(16), b'LON\r')
                time.sleep(3.5)  # slower than the 3 s connect timeout
                connection.sendall(b'SLOW123\r')

        thread = threading.Thread(target=serve_slow)
        thread.start()
        node = self._make_node(port)
        node.response_timeout_s = 10.0
        from std_srvs.srv import Trigger

        try:
            result = node.trigger_scan_callback(
                Trigger.Request(), Trigger.Response(),
            )
            self.assertTrue(result.success)
            self.assertEqual(result.message, 'SLOW123')
            self.assertIsNotNone(node._client_socket)
        finally:
            node.destroy_node()
            server.close()
            thread.join(timeout=5)

    def test_response_deadline_shorter_than_connect_timeout(self):
        """The response deadline, not the socket timeout, bounds a read."""
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.bind(('127.0.0.1', 0))
        server.listen(1)
        port = server.getsockname()[1]

        def serve_silent():
            connection, _ = server.accept()
            with connection:
                connection.recv(16)
                time.sleep(10.0)  # never responds within the test window

        thread = threading.Thread(target=serve_silent, daemon=True)
        thread.start()
        node = self._make_node(port)
        node.response_timeout_s = 1.0  # shorter than the 3 s socket timeout
        from std_srvs.srv import Trigger

        try:
            started = time.monotonic()
            result = node.trigger_scan_callback(
                Trigger.Request(), Trigger.Response(),
            )
            elapsed = time.monotonic() - started
            self.assertFalse(result.success)
            self.assertLess(elapsed, 2.5)
            self.assertIsNone(node._client_socket)
        finally:
            node.destroy_node()
            server.close()
            thread.join(timeout=12)

    def test_connection_alive_detects_peer_close(self):
        """Half-open TCP must be detected instead of reporting OK."""
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.bind(('127.0.0.1', 0))
        server.listen(1)
        port = server.getsockname()[1]

        def serve_and_close():
            connection, _ = server.accept()
            connection.close()

        thread = threading.Thread(target=serve_and_close)
        thread.start()
        node = self._make_node(port)
        try:
            self.assertTrue(node.connect_to_scanner('127.0.0.1', port))
            self.assertIsNotNone(node._client_socket)
            # Peer closed; recv(MSG_PEEK) must return b'' promptly.
            deadline = time.monotonic() + 2.0
            while time.monotonic() < deadline:
                if not node._connection_alive():
                    break
                time.sleep(0.05)
            self.assertFalse(node._connection_alive())
        finally:
            node.destroy_node()
            server.close()
            thread.join(timeout=2)


if __name__ == '__main__':
    unittest.main()
