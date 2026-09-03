from __future__ import annotations

import socket
import threading
import time

from rclpy.callback_groups import MutuallyExclusiveCallbackGroup
from rclpy.node import Node
from rclpy.parameter import Parameter
from std_msgs.msg import String
from diagnostic_msgs.msg import DiagnosticStatus
from std_srvs.srv import Trigger
from diagnostic_updater import DiagnosticStatusWrapper, Updater
from rcl_interfaces.msg import SetParametersResult
from vision_core import run_node


class KeyenceSRNode(Node):

    def __init__(self, parameter_overrides=None) -> None:
        super().__init__(
            'keyence_sr_node', parameter_overrides=parameter_overrides or [],
        )

        self.declare_parameter('scanner_ip', '172.31.0.91')
        self.declare_parameter('scanner_port', 9004)
        self.declare_parameter('reconnect_interval_s', 5.0)
        self.declare_parameter('response_timeout_s', 30.0)

        self._scanner_ip = self.get_parameter('scanner_ip').value

        self._scanner_port = self.get_parameter('scanner_port').value
        self.reconnect_interval_s = float(
            self.get_parameter('reconnect_interval_s').value
        )
        self.response_timeout_s = float(
            self.get_parameter('response_timeout_s').value
        )

        self._client_socket = None
        self._receive_buffer = b''
        self._socket_lock = threading.RLock()
        self._connect_lock = threading.Lock()

        self._barcode_pub = self.create_publisher(String, '~/barcode', 10)

        self._service_cb_group = MutuallyExclusiveCallbackGroup()
        self._trigger_srv = self.create_service(
            Trigger, '~/trigger', self.trigger_scan_callback,
            callback_group=self._service_cb_group)

        self._pending_reconnect = True
        self.add_on_set_parameters_callback(self._on_parameter_changed)
        if self.reconnect_interval_s > 0.0:
            self.create_timer(
                self.reconnect_interval_s,
                self._reconnect_if_needed,
                callback_group=self._service_cb_group,
            )

        self._diag_updater = Updater(self)
        self._diag_updater.setHardwareID('keyence_sr')
        self._diag_updater.add('Scanner Connection', self._diag_connection)
        self._scan_count = 0
        self._error_count = 0
        self._request_count = 0
        self._consecutive_failures = 0
        self._last_request_ms = 0.0
        self._total_request_time_s = 0.0

        self.get_logger().info(
            f'Keyence SR Wrapper started. Target: {self._scanner_ip}:{self._scanner_port}'
        )

    def connect_to_scanner(
        self,
        scanner_ip: str | None = None,
        scanner_port: int | None = None,
    ) -> bool:
        """Establishes the TCP connection to scanner."""
        target_ip = scanner_ip if scanner_ip is not None else self._scanner_ip
        target_port = (
            scanner_port if scanner_port is not None else self._scanner_port
        )
        with self._connect_lock:
            candidate_socket = None
            try:
                candidate_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                candidate_socket.setsockopt(
                    socket.SOL_SOCKET,
                    socket.SO_KEEPALIVE,
                    1,
                )
                candidate_socket.settimeout(3.0)
                candidate_socket.connect((target_ip, target_port))
                with self._socket_lock:
                    previous_socket = self._client_socket
                    self._client_socket = candidate_socket
                    self._receive_buffer = b''
                if previous_socket:
                    previous_socket.close()
                self.get_logger().info('Successfully connected to Keyence SR-1000.')
                return True

            except (OSError, socket.timeout, ConnectionError) as exc:
                self.get_logger().error(f'Failed to connect to scanner: {exc}')
                if candidate_socket:
                    candidate_socket.close()
                return False

    def _disconnect_scanner(self) -> None:
        """Closes the current scanner connection and discards partial data."""
        if self._client_socket:
            try:
                self._client_socket.close()
            except OSError:
                pass
        self._client_socket = None
        self._receive_buffer = b''

    def _receive_response_from(self, sock: socket.socket, timeout_s: float = 30.0) -> str:
        """Read one CR-terminated response from *sock* without holding the lock.

        Data beyond the first CR is preserved in ``self._receive_buffer`` for
        the next call (under the lock).
        """
        deadline = time.monotonic() + timeout_s
        max_buffer_size = 64 * 1024

        with self._socket_lock:
            buf = self._receive_buffer
            self._receive_buffer = b''

        while b'\r' not in buf:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                with self._socket_lock:
                    self._receive_buffer = buf
                raise TimeoutError(f'Response incomplete after {timeout_s:.0f} seconds')
            if len(buf) >= max_buffer_size:
                with self._socket_lock:
                    self._receive_buffer = buf
                raise ValueError('Response buffer exceeded 64 KiB')
            # The socket-level timeout set in connect_to_scanner() only guards
            # the handshake; reads here honor the response deadline instead.
            sock.settimeout(remaining)
            chunk = sock.recv(1024)
            if not chunk:
                raise ConnectionError('Scanner closed the connection')
            buf += chunk

        raw_response, remainder = buf.split(b'\r', 1)
        with self._socket_lock:
            self._receive_buffer = remainder

        try:
            response = raw_response.decode('utf-8')
        except UnicodeDecodeError:
            response = raw_response.decode('latin-1')
        return response.strip('\r\n')

    def _on_parameter_changed(self, params: list[Parameter]) -> SetParametersResult:
        """Apply scanner endpoint changes only after a successful reconnect."""
        old_ip = self._scanner_ip
        old_port = self._scanner_port
        next_ip = self._scanner_ip
        next_port = self._scanner_port
        for param in params:
            if param.name == 'scanner_ip':
                next_ip = param.value
            elif param.name == 'scanner_port':
                next_port = param.value

        if next_ip != old_ip or next_port != old_port:
            if not self.connect_to_scanner(next_ip, next_port):
                return SetParametersResult(successful=False)

            self._scanner_ip = next_ip
            self._scanner_port = next_port
            self._pending_reconnect = False
            self.get_logger().info(
                f'Scanner endpoint updated to {self._scanner_ip}:{self._scanner_port}.'
            )

        return SetParametersResult(successful=True)

    def _reconnect_if_needed(self) -> None:
        """Retry the connection when the scanner is currently unavailable or parameters changed."""
        if self._pending_reconnect:
            self._pending_reconnect = False
            self.get_logger().info('Attempting to reconnect to the scanner...')
            if not self.connect_to_scanner():
                self._pending_reconnect = True
        elif self._client_socket is None:
            self.connect_to_scanner()

    def _connection_alive(self) -> bool:
        """Non-blocking probe: False once the peer has closed the TCP stream."""
        with self._socket_lock:
            sock = self._client_socket
        if sock is None:
            return False
        try:
            data = sock.recv(1, socket.MSG_PEEK | socket.MSG_DONTWAIT)
        except BlockingIOError:
            return True  # no data pending and connection still open
        except (ConnectionResetError, OSError):
            return False
        return data != b''

    def _diag_connection(self, stat: DiagnosticStatusWrapper) -> DiagnosticStatusWrapper:
        """Diagnostic task: report scanner connection and scan statistics."""
        if self._connection_alive():
            stat.summary(
                DiagnosticStatus.OK,
                f'Connected to {self._scanner_ip}:{self._scanner_port}'
            )
        else:
            # Peer closed or socket gone: force a reconnect attempt soon.
            with self._socket_lock:
                self._disconnect_scanner()
            self._pending_reconnect = True
            stat.summary(DiagnosticStatus.ERROR, 'Disconnected')
        stat.add('scanner_ip', self._scanner_ip)
        stat.add('scanner_port', str(self._scanner_port))
        stat.add('scan_count', str(self._scan_count))
        stat.add('error_count', str(self._error_count))
        stat.add('request_count', str(self._request_count))
        stat.add('consecutive_failures', str(self._consecutive_failures))
        stat.add('last_request_ms', f'{self._last_request_ms:.3f}')
        average_ms = (
            self._total_request_time_s * 1000.0 / self._request_count
            if self._request_count else 0.0
        )
        stat.add('average_request_ms', f'{average_ms:.3f}')
        return stat

    def trigger_scan_callback(
        self, request: Trigger.Request, response: Trigger.Response,
    ) -> Trigger.Response:
        """Handles one-shot external scan trigger requests."""
        del request
        request_started_at = time.monotonic()
        self._request_count += 1

        with self._socket_lock:
            sock = self._client_socket

        if sock is None:
            self.connect_to_scanner()
            with self._socket_lock:
                sock = self._client_socket

        if sock is None:
            response.success = False
            response.message = 'Scanner not connected.'
            return response

        try:
            sock.sendall(b'LON\r')
            data = self._receive_response_from(sock, self.response_timeout_s)

            no_read_tokens = {'', 'NO READ', 'NOR', 'NG', 'OVER', 'TIME OUT', 'LON'}
            if data.startswith('ER') or data in no_read_tokens:
                with self._socket_lock:
                    self._error_count += 1
                    self._consecutive_failures += 1
                response.success = False
                response.message = f'Scanner Error: {data}' if data.startswith('ER') else 'No-Read'
            else:
                with self._socket_lock:
                    self._scan_count += 1
                    self._consecutive_failures = 0
                msg = String()
                msg.data = data
                self._barcode_pub.publish(msg)
                response.success = True
                response.message = data

        except socket.timeout:
            with self._socket_lock:
                self._error_count += 1
                self._consecutive_failures += 1
                self._disconnect_scanner()
            response.success = False
            response.message = 'Timeout: Scanner did not respond in time.'

        except (ConnectionError, OSError, ValueError) as exc:
            with self._socket_lock:
                self._error_count += 1
                self._consecutive_failures += 1
                self._disconnect_scanner()
            response.success = False
            response.message = f'Communication Error: {exc}'
            self.get_logger().warning('Connection lost; reconnect timer will retry.')

        elapsed = max(0.0, time.monotonic() - request_started_at)
        with self._socket_lock:
            self._total_request_time_s += elapsed
            self._last_request_ms = elapsed * 1000.0
        return response

    def destroy_node(self) -> None:
        """Closes the TCP connection on shutdown."""
        with self._socket_lock:
            self._disconnect_scanner()
        super().destroy_node()


def main(args: list[str] | None = None) -> None:
    run_node(KeyenceSRNode, args=args)


if __name__ == '__main__':
    main()
