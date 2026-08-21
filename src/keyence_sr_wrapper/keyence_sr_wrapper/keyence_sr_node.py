from __future__ import annotations

import socket
import threading
from typing import Any

import rclpy
from rclpy.callback_groups import MutuallyExclusiveCallbackGroup
from rclpy.executors import ExternalShutdownException, MultiThreadedExecutor
from rclpy.node import Node
from rclpy.parameter import Parameter
from std_msgs.msg import String
from diagnostic_msgs.msg import DiagnosticStatus
from std_srvs.srv import Trigger
from diagnostic_updater import DiagnosticStatusWrapper, Updater
from rcl_interfaces.msg import SetParametersResult


# 定义基恩士扫码器 ROS 2 节点类，继承自 rclpy.node.Node
# 该节点封装了与基恩士 SR 系列扫码器的 TCP 通信逻辑，对外提供话题发布和服务触发两种接口
class KeyenceSRNode(Node):

    # 构造函数：节点初始化时调用，完成参数声明、TCP 连接建立、话题和服务的创建
    def __init__(self) -> None:
        # 调用父类 Node 的构造函数，将节点名称注册为 'keyence_sr_node'，该名称在 ROS 2 图中必须唯一
        super().__init__('keyence_sr_node')

        # ---- 参数声明与获取 ----

        # 声明一个名为 'scanner_ip' 的 ROS 参数，类型为字符串，默认值为 '172.31.0.91'
        # 用户可在 launch 文件或命令行中覆盖此参数以指向不同扫码器 IP
        self.declare_parameter('scanner_ip', '172.31.0.91')

        # 声明一个名为 'scanner_port' 的 ROS 参数，类型为整数，默认值为 9004
        # 9004 是基恩士 SR 系列扫码器默认的 TCP 通信端口
        self.declare_parameter('scanner_port', 9004)
        self.declare_parameter('reconnect_interval_s', 5.0)

        # 从参数服务器中获取 'scanner_ip' 参数的实际值（可能是默认值，也可能是用户覆盖后的值），赋给实例变量
        self.scanner_ip = self.get_parameter('scanner_ip').value
        
        # 从参数服务器中获取 'scanner_port' 参数的实际值，赋给实例变量
        self.scanner_port = self.get_parameter('scanner_port').value
        self.reconnect_interval_s = float(
            self.get_parameter('reconnect_interval_s').value
        )

        # ---- TCP 连接初始化 ----

        # 初始化 TCP 套接字变量为 None，表示尚未建立连接；后续 connect_to_scanner() 会为其赋值
        self.client_socket = None
        self._receive_buffer = b''
        # 保护 socket 操作的互斥锁（RLock 允许同一线程重入，因为 trigger 回调内部会调用 connect）
        self._socket_lock = threading.RLock()
        # 立即调用连接方法，尝试与扫码器建立 TCP 连接；如果失败，client_socket 仍为 None，后续触发时会报错
        self.connect_to_scanner()

        # ---- ROS 话题 & 服务创建 ----

        # 创建一个 ROS 2 话题发布者：
        #   - 话题名称: '/scanner/barcode'，扫码结果将发布到此话题
        #   - 消息类型: String，即标准字符串消息
        #   - 队列大小: 10，表示发布者内部消息队列的最大长度，超出时旧消息会被丢弃
        self.publisher_ = self.create_publisher(String, '~/barcode', 10)

        # 创建一个 ROS 2 服务：
        #   - 服务名称: '~/trigger'，外部节点可通过调用此服务触发一次扫码
        #   - 服务类型: Trigger，请求为空，响应包含 success(bool) 和 message(string)
        #   - 回调函数: trigger_scan_callback，当有客户端调用此服务时自动执行
        self._service_cb_group = MutuallyExclusiveCallbackGroup()
        self.srv = self.create_service(Trigger, '~/trigger', self.trigger_scan_callback, callback_group=self._service_cb_group)

        # 注册参数变更回调，支持运行时修改 scanner_ip / scanner_port 后自动重连
        self.add_on_set_parameters_callback(self._on_parameter_changed)
        if self.reconnect_interval_s > 0.0:
            self.create_timer(
                self.reconnect_interval_s,
                self._reconnect_if_needed,
            )

        # ---- Diagnostics ----
        self._diag_updater = Updater(self)
        self._diag_updater.setHardwareID('keyence_sr')
        self._diag_updater.add('Scanner Connection', self._diag_connection)
        self._scan_count = 0
        self._error_count = 0

        # 在终端输出启动日志信息，包含扫码器的 IP 地址和端口号，方便调试和确认配置是否正确
        self.get_logger().info(
            f'Keyence SR Wrapper started. Target: {self.scanner_ip}:{self.scanner_port}'
        )

    # 定义连接到扫码器的方法，负责建立 TCP 套接字连接
    def connect_to_scanner(
        self,
        scanner_ip: str | None = None,
        scanner_port: int | None = None,
    ) -> bool:
        """Establishes the TCP connection to scanner."""
        target_ip = scanner_ip if scanner_ip is not None else self.scanner_ip
        target_port = (
            scanner_port if scanner_port is not None else self.scanner_port
        )
        with self._socket_lock:
            candidate_socket = None
            try:
                # 创建一个新的 TCP 套接字：
                #   socket.AF_INET 表示使用 IPv4 地址族
                #   socket.SOCK_STREAM 表示使用 TCP 协议（面向连接、可靠传输）
                candidate_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                candidate_socket.setsockopt(
                    socket.SOL_SOCKET,
                    socket.SO_KEEPALIVE,
                    1,
                )

                # 设置套接字的超时时间为 3.0 秒
                # 后续所有阻塞操作（如 connect、recv）如果在 3 秒内未完成，将抛出 socket.timeout 异常
                # 这可以防止节点在扫码器无响应时无限阻塞
                candidate_socket.settimeout(3.0)

                # 发起 TCP 连接请求，目标地址为 (scanner_ip, scanner_port)
                # 如果连接成功，套接字进入已连接状态；如果失败（如网络不通、端口未开放），将抛出异常
                candidate_socket.connect((target_ip, target_port))
                previous_socket = self.client_socket
                self.client_socket = candidate_socket
                self._receive_buffer = b''
                if previous_socket:
                    previous_socket.close()
                self.get_logger().info('Successfully connected to Keyence SR-1000.')
                return True

            except Exception as e:
                # 捕获所有异常（包括网络不可达、连接被拒绝、超时等），记录错误日志
                # 使用通用 Exception 而非具体异常类型，是为了在连接阶段尽可能容错
                self.get_logger().error(f'Failed to connect to scanner: {e}')
                if candidate_socket:
                    candidate_socket.close()
                return False

    def _disconnect_scanner(self) -> None:
        """Closes the current scanner connection and discards partial data."""
        if self.client_socket:
            try:
                self.client_socket.close()
            except OSError:
                pass
        self.client_socket = None
        self._receive_buffer = b''

    def _receive_response(self) -> str:
        """Reads exactly one CR-terminated scanner response from the TCP stream."""
        while b'\r' not in self._receive_buffer:
            chunk = self.client_socket.recv(1024)
            if not chunk:
                raise ConnectionError('Scanner closed the connection')
            self._receive_buffer += chunk

        raw_response, self._receive_buffer = self._receive_buffer.split(b'\r', 1)
        return raw_response.decode('ascii').strip()

    def _on_parameter_changed(self, params: list[Parameter]) -> SetParametersResult:
        """参数变更回调：检测 scanner_ip / scanner_port 变化后自动重连。"""
        next_ip = self.scanner_ip
        next_port = self.scanner_port
        for param in params:
            if param.name == 'scanner_ip':
                next_ip = param.value
            elif param.name == 'scanner_port':
                next_port = param.value

        if next_ip != self.scanner_ip or next_port != self.scanner_port:
            self.get_logger().info('正在重新连接扫码器...')
            if not self.connect_to_scanner(next_ip, next_port):
                return SetParametersResult(successful=False, reason='Reconnection failed')
            self.scanner_ip = next_ip
            self.scanner_port = next_port
            self.get_logger().info(
                f'参数 scanner_ip/scanner_port 已更新为: '
                f'{self.scanner_ip}:{self.scanner_port}'
            )

        return SetParametersResult(successful=True)

    def _reconnect_if_needed(self) -> None:
        """Retry the connection when the scanner is currently unavailable."""
        if self.client_socket is None:
            self.connect_to_scanner()

    def _diag_connection(self, stat: DiagnosticStatusWrapper) -> DiagnosticStatusWrapper:
        """Diagnostic task: report scanner connection and scan statistics."""
        if self.client_socket is not None:
            stat.summary(
                DiagnosticStatus.OK,
                f'Connected to {self.scanner_ip}:{self.scanner_port}'
            )
        else:
            stat.summary(DiagnosticStatus.ERROR, 'Disconnected')
        stat.add('scanner_ip', self.scanner_ip)
        stat.add('scanner_port', str(self.scanner_port))
        stat.add('scan_count', str(self._scan_count))
        stat.add('error_count', str(self._error_count))
        return stat

    # 定义服务回调函数：当外部节点调用 '/scanner/trigger' 服务时，此方法被自动调用
    # request: Trigger 服务的请求对象（此处为空，无字段）
    # response: Trigger 服务的响应对象，需要填充 success 和 message 字段后返回
    def trigger_scan_callback(self, request: Trigger.Request, response: Trigger.Response) -> Trigger.Response:
        """Handles one-shot external scan trigger requests."""
        # 显式删除 request 参数，因为 Trigger 服务的请求体为空，不使用该变量
        # 这是一种 Python 惯例，表明该参数被有意忽略
        del request

        with self._socket_lock:
            # ---- 前置检查：确认扫码器已连接 ----

            if not self.client_socket:
                self.connect_to_scanner()

            if not self.client_socket:
                response.success = False
                response.message = 'Scanner not connected.'
                return response

            # ---- 发送扫码指令并接收结果 ----

            try:
                # 构造发送给扫码器的 TCP 命令字符串：b'LON\r'
                # 'LON' 是基恩士 SR 系列的通信协议命令，含义为 "Live mode ON"（开启实时读取模式）
                # 在该模式下，扫码器会立即执行一次扫码并返回结果
                # b 前缀表示这是 bytes 类型（字节串），因为 TCP 套接字发送/接收的都是字节数据
                # '\r' 是回车符（ASCII 13），基恩士协议要求每条命令以 \r 结尾作为终止符
                command = b'LON\r'
                # 通过 TCP 套接字将命令字节串发送给扫码器
                # sendall 会确保所有字节都被发送出去（与 send 不同，send 可能只发送部分数据）
                self.client_socket.sendall(command)

                # TCP 是字节流协议，必须读取到 Keyence 规定的 CR 终止符，
                # 以正确处理响应分包和粘包。
                data = self._receive_response()

                # ---- 解析扫码器响应 ----

                # 检查扫码器返回的数据是否以 'ER' 开头
                # 在基恩士通信协议中，以 'ER' 开头的响应表示扫码器返回了错误码
                # 例如 'ER001' 表示某种硬件或通信错误
                if data.startswith('ER'):
                    self._error_count += 1
                    response.success = False
                    response.message = f'Scanner Error: {data}'
                else:
                    self._scan_count += 1
                    msg = String()
                    msg.data = data
                    self.publisher_.publish(msg)

                    response.success = True
                    response.message = data

            # ---- 异常处理 ----

            except socket.timeout:
                # 捕获套接字超时异常：扫码器在 3 秒内未返回任何数据
                # 可能原因：扫码器忙、网络延迟过高、扫码器故障等
                response.success = False
                response.message = 'Timeout: Scanner did not respond in time.'
                self._disconnect_scanner()

            except Exception as e:
                # 捕获所有其他异常（如连接断开、数据解码错误等）
                response.success = False
                response.message = f'Communication Error: {e}'

                self.get_logger().warn('Connection lost. Attempting to reconnect...')
                # 尝试自动重新连接扫码器，以便后续的服务调用可以继续使用
                # 这是一种简单的容错机制：在通信异常时自动恢复连接，而非要求用户手动重启节点
                self._disconnect_scanner()
                self.connect_to_scanner()

        return response

    # 重写父类的 destroy_node 方法，在节点销毁时执行自定义的清理逻辑
    def destroy_node(self) -> None:
        """Closes TCP connection on node shutdown."""
        self._disconnect_scanner()
        super().destroy_node()


# 定义模块入口函数，当此文件作为主程序运行时执行
def main(args: Any = None) -> None:
    rclpy.init(args=args)

    node = KeyenceSRNode()
    executor = MultiThreadedExecutor()
    executor.add_node(node)
    try:
        executor.spin()
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        executor.shutdown()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
