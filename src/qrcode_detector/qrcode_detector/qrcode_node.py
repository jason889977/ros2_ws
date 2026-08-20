"""
QR 码检测节点（ROS 2）

功能概述：
    订阅相机图像话题，对每一帧图像进行 QR 码检测与解码，
    将解码结果以字符串形式发布到输出话题，供下游节点消费。

检测后端（二选一）：
    1. WeChatQRCode（推荐）— 基于深度学习的高鲁棒性 QR 检测器，
       由微信开源，对遮挡、模糊、小尺寸 QR 码表现优异。
       需要 4 个模型文件（detect.prototxt / detect.caffemodel /
       sr.prototxt / sr.caffemodel）。
    2. OpenCV QRCodeDetector（默认）— OpenCV 内置的轻量级检测器，
       无需额外模型文件，适合简单场景。

数据流：
    相机 → /camera/image_raw (sensor_msgs/Image)
               ↓
         本节点订阅并解码
               ↓
         ~/decoded_info (std_msgs/String) — 解码后的文本内容

算法原理（WeChatQRCode）：
    WeChatQRCode 的检测流程分为 4 个阶段：
      1. 检测阶段（detect.prototxt + detect.caffemodel）
         使用 Caffe 深度学习模型定位图像中所有 QR 码区域，
         输出每个 QR 码的四个角点坐标。
      2. 超分辨率阶段（sr.prototxt + sr.caffemodel）
         对小尺寸或模糊的 QR 码做超分辨率重建，提升解码成功率。
      3. 解码阶段
         根据角点做透视变换，将 QR 码矫正为正视图，
         然后按 QR 码标准（Reed-Solomon 纠错）解码数据。
      4. 后处理
         过滤无效结果，返回最终的字符串列表。
"""

# ============================================================================
# 导入部分
# ============================================================================

import os
import time
# Python 标准库：操作系统相关功能（路径拼接、文件存在性检查等）

from ament_index_python.packages import get_package_share_directory
# ament 是 ROS 2 的构建系统。
# get_package_share_directory('包名') 返回该包在 install/ 目录下的共享路径，
# 例如 /home/ubuntu/ros2_ws/install/qrcode_detector/share/qrcode_detector/
# 用于定位模型文件、配置文件等运行时资源。

import cv2 as cv
# OpenCV（cv2）是计算机视觉的核心库。
# 提供图像处理、QR 码检测、深度学习推理等功能。
# 别名 cv 是社区惯例（import cv2 as cv）。

from cv_bridge import CvBridge
# CvBridge 是 ROS 2 图像消息与 OpenCV numpy 数组之间的转换桥梁。
# ROS 话题传输的是 sensor_msgs/Image（序列化格式），
# OpenCV 需要的是 numpy ndarray（内存中的像素矩阵）。
# CvBridge 负责两者之间的双向转换。

import rclpy
# ROS 2 Python 客户端库，提供节点创建、话题发布/订阅、参数管理等核心功能。

from rclpy.executors import ExternalShutdownException
# 当 ROS 2 节点被外部信号（如 SIGTERM、launch 系统关闭）中断时抛出的异常。
# 与 KeyboardInterrupt（Ctrl+C）类似，但覆盖更多优雅退出的场景。

from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
# Node 是 ROS 2 节点的基类。
# 节点是 ROS 2 中的最小计算单元，拥有自己的参数、话题、服务等。

from sensor_msgs.msg import Image, CameraInfo, CompressedImage
# sensor_msgs/Image 是 ROS 2 中图像消息的标准类型。
# 包含字段：
#   header   — 时间戳 + 坐标系
#   height   — 图像高度（像素）
#   width    — 图像宽度（像素）
#   encoding — 像素编码（如 "bgr8", "mono8", "rgb8"）
#   data     — 原始像素数据（一维字节数组）
# sensor_msgs/CompressedImage 是压缩图像消息（JPEG/PNG），带宽更低。
# sensor_msgs/CameraInfo 包含相机内参矩阵和畸变系数。

from std_msgs.msg import String
# std_msgs/String 是最简单的 ROS 2 消息类型之一。
# 只有一个字段 data（字符串），用于传递文本信息。

from geometry_msgs.msg import PoseStamped
# geometry_msgs/PoseStamped 带时间戳和坐标系的位姿消息（位置 xyz + 四元数姿态 xyzw）。
# 用于发布 QR 码的 6D 位姿估计结果。

import numpy as np
# NumPy 用于矩阵运算，solvePnP 需要 numpy 数组作为输入。


# ============================================================================
# 节点类定义
# ============================================================================

class WeChatQRNode(Node):
    """
    QR 码检测 ROS 2 节点。

    工作流程：
      1. 初始化时加载 QR 检测模型（WeChatQR 或 OpenCV 内置）
      2. 订阅相机图像话题
      3. 每收到一帧图像 → 用 CvBridge 转为 numpy 数组 → 调用检测器解码
      4. 如果检测到 QR 码 → 将解码文本发布到 ~/decoded_info 话题
    """

    def __init__(self):
        # 调用父类 Node 的初始化，节点名称为 'wechat_qr_node'
        # 节点名称在 ROS 2 图中必须唯一，用于日志前缀和参数的命名空间
        super().__init__('wechat_qr_node')
        self.get_logger().info('Initializing QR detector node...')

        # ==================================================================
        # 参数声明（declare_parameter）
        # ==================================================================
        # ROS 2 参数机制：
        #   - 声明时指定默认值
        #   - 可在 launch 文件中通过 Parameter() 覆盖
        #   - 也可通过命令行 ros2 run ... --ros-args -p 参数名:=值 覆盖
        #   - 运行时可通过 ros2 param set 动态修改（需节点支持）

        self.declare_parameter(
            'image_topic',
            '/my_camera/pylon_ros2_camera_node/image_raw',
        )
        # 订阅的相机图像话题名。
        # 默认 '/camera/image_raw' 是 Basler 相机驱动发布的原始图像话题。

        self.declare_parameter('model_dir', '')
        # WeChatQR 模型文件所在目录的绝对路径。
        # 留空字符串时，自动使用本功能包 install 目录下的 models/ 子目录。

        self.declare_parameter('queue_size', 10)
        # 订阅器的消息队列长度。
        # 如果处理速度跟不上相机帧率，队列最多缓存 10 帧，
        # 超出后最旧的帧会被丢弃（FIFO 策略）。

        self.declare_parameter('use_camera_info', False)
        # 是否使用相机标定信息（内参矩阵、畸变系数）。
        # 启用后，节点会订阅 camera_info 话题，结合 QR 码角点做 solvePnP
        # 位姿估计，发布 ~/qr_pose (PoseStamped)。

        self.declare_parameter(
            'camera_info_topic',
            '/my_camera/pylon_ros2_camera_node/camera_info',
        )
        # 相机标定信息话题名（sensor_msgs/CameraInfo）。

        self.declare_parameter('qr_size_m', 0.10)
        # QR 码的物理边长（米），用于 solvePnP 的 3D 物体点定义。
        # 默认 0.10m = 10cm，根据实际 QR 码尺寸调整。

        self.declare_parameter('prefer_wechat_qr', False)
        # 是否优先使用 WeChatQR 深度学习检测器。
        # False（默认）→ 使用 OpenCV 内置的 QRCodeDetector（轻量，无需模型）
        # True → 尝试加载 WeChatQR 模型，加载失败则自动降级为 OpenCV 检测器

        self.declare_parameter('deduplicate_window_s', 0.5)

        self.declare_parameter('min_detect_interval_s', 0.2)
        # 两次检测之间的最小间隔（秒）。
        # 默认 0.2s 即最高 5Hz 检测频率。工业场景中二维码不会每帧变化，
        # 降低检测频率可显著减少 CPU 占用。设为 0 表示不限制（每帧都检测）。

        self.declare_parameter('use_compressed', False)
        # 是否订阅压缩图像话题（CompressedImage）而非原始图像（Image）。
        # 启用后话题名自动追加 /compressed 后缀。
        # 压缩传输可显著降低内存拷贝和 DDS 带宽占用，适合 GigE 相机场景。
        # 需要上游有 image_transport republish 节点提供压缩流。

        # ==================================================================
        # 读取参数值到局部变量
        # ==================================================================
        # get_parameter() 返回 rclpy.parameter.Parameter 对象，
        # .value 属性取出实际的值（类型在声明时由默认值推断）。
        image_topic = self.get_parameter('image_topic').value
        model_dir = self.get_parameter('model_dir').value
        self._use_camera_info = self.get_parameter('use_camera_info').value
        camera_info_topic = self.get_parameter('camera_info_topic').value
        self._qr_size_m = self.get_parameter('qr_size_m').value
        prefer_wechat_qr = self.get_parameter('prefer_wechat_qr').value
        self._deduplicate_window_s = float(
            self.get_parameter('deduplicate_window_s').value
        )
        self._min_detect_interval_s = float(
            self.get_parameter('min_detect_interval_s').value
        )
        self._use_compressed = bool(
            self.get_parameter('use_compressed').value
        )
        self._last_published_at = {}
        self._last_detect_time = 0.0

        # 相机内参（从 CameraInfo 消息中填充）
        self._camera_matrix = None   # 3x3 numpy 数组
        self._dist_coeffs = None     # 畸变系数 numpy 数组
        self._camera_frame_id = ''   # 相机坐标系名称

        # ==================================================================
        # 初始化 CvBridge
        # ==================================================================
        # CvBridge 是一个轻量工具类，无需额外配置。
        # 核心方法：
        #   imgmsg_to_cv2(msg, encoding) — ROS Image → numpy ndarray
        #   cv2_to_imgmsg(array, encoding) — numpy ndarray → ROS Image
        self.bridge = CvBridge()

        # ==================================================================
        # 初始化 QR 检测器
        # ==================================================================
        # 如果用户没有指定模型目录，则自动定位到功能包的共享目录
        if not model_dir:
            # get_package_share_directory 返回 install 后的共享路径
            # 例如: /home/ubuntu/ros2_ws/install/qrcode_detector/share/qrcode_detector
            pkg_share = get_package_share_directory('qrcode_detector')
            # 模型文件约定存放在 share/qrcode_detector/models/ 下
            model_dir = os.path.join(pkg_share, 'models')

        # 调用初始化方法，返回 (检测器实例, 检测器类型字符串)
        self.detector, self.detector_kind = self._init_detector(
            model_dir,
            prefer_wechat_qr,
        )
        # self.detector_kind 为 'wechat' 或 'opencv'，
        # 后续 _decode_qr 根据此值选择不同的解码逻辑。

        # ==================================================================
        # 创建发布者（Publisher）
        # ==================================================================
        # create_publisher(消息类型, 话题名, 队列大小)
        # '~/decoded_info' 中 '~' 是私有命名空间缩写，
        # 展开后为 /wechat_qr_node/decoded_info
        self.result_pub = self.create_publisher(String, '~/decoded_info', 10)

        # ==================================================================
        # 创建订阅者（Subscriber）
        # ==================================================================
        # 图像话题使用 BEST_EFFORT + KEEP_LAST(1)：丢弃旧帧而非阻塞相机
        sensor_qos = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            history=HistoryPolicy.KEEP_LAST,
            depth=1,
        )
        if self._use_compressed:
            compressed_topic = image_topic + '/compressed'
            self.subscription = self.create_subscription(
                CompressedImage,
                compressed_topic,
                self.compressed_image_callback,
                sensor_qos,
            )
            self.get_logger().info(
                f'已启用压缩图像订阅: {compressed_topic}'
            )
        else:
            self.subscription = self.create_subscription(
                Image,
                image_topic,
                self.image_callback,
                sensor_qos,
            )

        # ==================================================================
        # CameraInfo 订阅 + 位姿发布（use_camera_info 功能）
        # ==================================================================
        self._camera_info_sub = None
        self._pose_pub = None

        if self._use_camera_info:
            self._pose_pub = self.create_publisher(PoseStamped, '~/qr_pose', 10)
            self._camera_info_sub = self.create_subscription(
                CameraInfo,
                camera_info_topic,
                self._camera_info_callback,
                sensor_qos,
            )
            self.get_logger().info(
                f'use_camera_info 已启用，订阅 {camera_info_topic}，'
                f'qr_size_m={self._qr_size_m}'
            )

        # 启动日志
        self.get_logger().info(
            f'WeChatQR 二维码识别节点已启动，订阅话题: {image_topic}'
        )

    # ======================================================================
    # 检测器初始化
    # ======================================================================

    def _init_detector(self, model_dir: str, prefer_wechat_qr: bool):
        """
        初始化 QR 码检测器。

        策略：
          - prefer_wechat_qr=False → 直接使用 OpenCV 内置 QRCodeDetector
          - prefer_wechat_qr=True  → 尝试加载 WeChatQR 模型
            → 如果 OpenCV 编译时未包含 wechat_qrcode 模块 → 降级
            → 如果模型文件缺失 → 降级
            → 全部就绪 → 使用 WeChatQR

        参数:
            model_dir:          模型文件所在目录的绝对路径
            prefer_wechat_qr:   是否优先使用 WeChatQR

        返回:
            (detector, kind) 元组：
              detector — 检测器对象（cv.QRCodeDetector 或 cv.wechat_qrcode.WeChatQRCode）
              kind     — 字符串 'opencv' 或 'wechat'，标识实际使用的后端
        """

        # ---- 路径 1：用户不要求 WeChatQR，直接用 OpenCV 内置检测器 ----
        if not prefer_wechat_qr:
            self.get_logger().info(
                'prefer_wechat_qr is false, using OpenCV QRCodeDetector.'
            )
            # cv.QRCodeDetector() 是 OpenCV 内置的 QR 码检测器
            # 基于传统的图像处理算法（阈值化 + 轮廓检测 + 几何验证）
            # 优点：无需额外依赖，启动快
            # 缺点：对模糊、小尺寸、部分遮挡的 QR 码识别率较低
            return cv.QRCodeDetector(), 'opencv'

        # ---- 路径 2：用户要求 WeChatQR，需要检查前置条件 ----

        # WeChatQR 需要 4 个模型文件：
        #   detect.prototxt   — 检测网络的结构定义（Caffe Protobuf 文本格式）
        #   detect.caffemodel — 检测网络的权重文件（Caffe 二进制格式）
        #   sr.prototxt       — 超分辨率网络的结构定义
        #   sr.caffemodel     — 超分辨率网络的权重文件
        required_files = [
            'detect.prototxt',
            'detect.caffemodel',
            'sr.prototxt',
            'sr.caffemodel',
        ]

        # 检查哪些模型文件不存在
        # os.path.isfile() 检查文件是否存在且是普通文件（非目录）
        # os.path.join() 安全地拼接目录和文件名
        missing = [f for f in required_files
                   if not os.path.isfile(os.path.join(model_dir, f))]
        # 列表推导式：遍历 required_files，保留不存在的文件名

        # 检查当前 OpenCV 是否编译了 wechat_qrcode 模块
        # hasattr() 检查对象是否有某个属性/方法
        # OpenCV 的 Python 绑定中，contrib 模块（如 wechat_qrcode）
        # 只有在编译时启用了 opencv_contrib 才可用
        has_wechat = hasattr(cv, 'wechat_qrcode') and hasattr(cv.wechat_qrcode, 'WeChatQRCode')

        # 前置条件 1：OpenCV 必须包含 wechat_qrcode 模块
        if not has_wechat:
            self.get_logger().warn(
                'OpenCV does not provide wechat_qrcode, fallback to QRCodeDetector.'
            )
            return cv.QRCodeDetector(), 'opencv'

        # 前置条件 2：模型文件必须齐全
        if missing:
            self.get_logger().warn(
                f'模型文件缺失: {missing}，fallback to QRCodeDetector。'
            )
            return cv.QRCodeDetector(), 'opencv'

        # ---- 所有条件满足，加载 WeChatQR 模型 ----
        # 构造 4 个模型文件的完整路径列表
        paths = [os.path.join(model_dir, f) for f in required_files]
        self.get_logger().info(f'加载 WeChatQR 模型: {model_dir}')

        # cv.wechat_qrcode.WeChatQRCode 构造函数接受 4 个路径参数：
        #   WeChatQRCode(detect_proto, detect_model, sr_proto, sr_model)
        # *paths 是 Python 的解包语法，将列表 [a, b, c, d] 展开为 4 个独立参数
        # 加载过程会读取模型文件到内存，初始化神经网络推理引擎
        return cv.wechat_qrcode.WeChatQRCode(*paths), 'wechat'

    # ======================================================================
    # CameraInfo 回调
    # ======================================================================

    def _camera_info_callback(self, msg: CameraInfo):
        """
        接收相机标定信息，提取内参矩阵和畸变系数。

        CameraInfo 消息中的 K 字段是 3x3 内参矩阵（行优先 9 元素），
        D 字段是畸变系数。只需接收一次即可（相机内参不会动态变化）。
        """
        if self._camera_matrix is not None:
            return
        self._camera_matrix = np.array(msg.k, dtype=np.float64).reshape(3, 3)
        self._dist_coeffs = np.array(msg.d, dtype=np.float64)
        self._camera_frame_id = msg.header.frame_id
        self.get_logger().info(
            f'相机内参已加载 (frame={self._camera_frame_id}): '
            f'fx={self._camera_matrix[0,0]:.1f}, fy={self._camera_matrix[1,1]:.1f}, '
            f'cx={self._camera_matrix[0,2]:.1f}, cy={self._camera_matrix[1,2]:.1f}'
        )

    # ======================================================================
    # 位姿估计（solvePnP）
    # ======================================================================

    def _estimate_pose(self, corners_2d, header):
        """
        用 QR 码的 4 个像素角点 + 已知物理尺寸，通过 solvePnP 计算 6D 位姿。

        参数:
            corners_2d: numpy array，形状 (4, 2)，QR 码四个角点的像素坐标
            header:     ROS 标准 header（用于时间戳和坐标系）

        返回:
            PoseStamped 消息，或 None（内参未就绪时）
        """
        if self._camera_matrix is None:
            return None

        s = self._qr_size_m
        # QR 码 3D 物体点（以 QR 码中心为原点，Z 轴朝上）
        # 角点顺序：左上、右上、右下、左下（与 QR 码检测器输出一致）
        object_points = np.array([
            [-s / 2, s / 2, 0.0],
            [s / 2, s / 2, 0.0],
            [s / 2, -s / 2, 0.0],
            [-s / 2, -s / 2, 0.0],
        ], dtype=np.float64)

        image_points = corners_2d.reshape(4, 2).astype(np.float64)

        success, rvec, tvec = cv.solvePnP(
            object_points, image_points,
            self._camera_matrix, self._dist_coeffs,
        )

        if not success:
            self.get_logger().warn('solvePnP 未收敛，跳过本帧位姿估计')
            return None

        # 将旋转向量转换为四元数
        rotation_matrix, _ = cv.Rodrigues(rvec)
        quat = self._rotation_matrix_to_quaternion(rotation_matrix)

        pose = PoseStamped()
        pose.header.stamp = header.stamp
        pose.header.frame_id = self._camera_frame_id or header.frame_id
        pose.pose.position.x = float(tvec[0])
        pose.pose.position.y = float(tvec[1])
        pose.pose.position.z = float(tvec[2])
        pose.pose.orientation.x = quat[0]
        pose.pose.orientation.y = quat[1]
        pose.pose.orientation.z = quat[2]
        pose.pose.orientation.w = quat[3]

        return pose

    @staticmethod
    def _rotation_matrix_to_quaternion(R):
        """将 3x3 旋转矩阵转换为四元数 (x, y, z, w)。"""
        trace = R[0, 0] + R[1, 1] + R[2, 2]
        if trace > 0:
            s = 0.5 / np.sqrt(trace + 1.0)
            w = 0.25 / s
            x = (R[2, 1] - R[1, 2]) * s
            y = (R[0, 2] - R[2, 0]) * s
            z = (R[1, 0] - R[0, 1]) * s
        elif R[0, 0] > R[1, 1] and R[0, 0] > R[2, 2]:
            s = 2.0 * np.sqrt(1.0 + R[0, 0] - R[1, 1] - R[2, 2])
            w = (R[2, 1] - R[1, 2]) / s
            x = 0.25 * s
            y = (R[0, 1] + R[1, 0]) / s
            z = (R[0, 2] + R[2, 0]) / s
        elif R[1, 1] > R[2, 2]:
            s = 2.0 * np.sqrt(1.0 + R[1, 1] - R[0, 0] - R[2, 2])
            w = (R[0, 2] - R[2, 0]) / s
            x = (R[0, 1] + R[1, 0]) / s
            y = 0.25 * s
            z = (R[1, 2] + R[2, 1]) / s
        else:
            s = 2.0 * np.sqrt(1.0 + R[2, 2] - R[0, 0] - R[1, 1])
            w = (R[1, 0] - R[0, 1]) / s
            x = (R[0, 2] + R[2, 0]) / s
            y = (R[1, 2] + R[2, 1]) / s
            z = 0.25 * s
        return (x, y, z, w)

    # ======================================================================
    # QR 码解码
    # ======================================================================

    @staticmethod
    def _normalize_corners(points):
        """Return finite QR corners in the canonical (4, 2) shape."""
        if points is None:
            return None
        corners = np.asarray(points, dtype=np.float64).squeeze()
        if corners.shape != (4, 2) or not np.isfinite(corners).all():
            return None
        return corners

    def _decode_qr(self, cv_image):
        """
        对一幅 OpenCV 图像进行 QR 码检测与解码。

        根据 self.detector_kind 选择不同的后端：
          - 'wechat' → WeChatQRCode.detectAndDecode()
          - 'opencv' → QRCodeDetector.detectAndDecodeMulti() 或 detectAndDecode()

        参数:
            cv_image: numpy ndarray，BGR 格式的图像（由 CvBridge 转换而来）

        返回:
            (decoded_info, points_list) 元组：
              decoded_info — list[str]，解码得到的字符串列表
              points_list  — list[numpy array]，每个 QR 码的四个角点坐标 (4,2)
                             如果检测器不提供角点，对应位置为 None
        """

        # ---- WeChatQR 后端 ----
        if self.detector_kind == 'wechat':
            decoded_info, points = self.detector.detectAndDecode(cv_image)

            if isinstance(decoded_info, str):
                decoded_list = [decoded_info] if decoded_info else []
                pts_list = [self._normalize_corners(points)] if decoded_info else []
                return decoded_list, pts_list

            decoded_list = []
            pts_list = []
            for i, info in enumerate(decoded_info):
                if info:
                    decoded_list.append(info)
                    point_set = points[i] if points is not None and i < len(points) else None
                    pts_list.append(self._normalize_corners(point_set))
            return decoded_list, pts_list

        # ---- OpenCV 后端 ----
        # 工业场景通常只有一个 QR 码，优先用 detectAndDecode（更快）
        # 如果未检测到且 detectAndDecodeMulti 可用，再尝试多码检测
        decoded_info, pts, _ = self.detector.detectAndDecode(cv_image)
        if decoded_info:
            pts_list = [self._normalize_corners(pts)]
            return [decoded_info], pts_list

        if hasattr(self.detector, 'detectAndDecodeMulti'):
            result = self.detector.detectAndDecodeMulti(cv_image)
            if isinstance(result, tuple) and len(result) >= 2:
                decoded_info = result[1]
                decoded_list = []
                pts_list = []
                raw_pts = result[2] if len(result) >= 3 else None
                for i, info in enumerate(decoded_info):
                    if info:
                        decoded_list.append(info)
                        point_set = (
                            raw_pts[i]
                            if raw_pts is not None and i < len(raw_pts)
                            else None
                        )
                        pts_list.append(self._normalize_corners(point_set))
                return decoded_list, pts_list

        return [], []

    # ======================================================================
    # 图像回调函数
    # ======================================================================

    def _should_publish(self, info: str) -> bool:
        if self._deduplicate_window_s <= 0.0:
            return True
        now = time.monotonic()
        previous = self._last_published_at.get(info)
        should_publish = (
            previous is None
            or now - previous >= self._deduplicate_window_s
        )
        if should_publish:
            self._last_published_at[info] = now
        # 定期清理过期条目，防止字典无限增长
        if len(self._last_published_at) > 100:
            cutoff = now - self._deduplicate_window_s * 10
            self._last_published_at = {
                k: v for k, v in self._last_published_at.items() if v > cutoff
            }
        return should_publish

    def compressed_image_callback(self, msg: CompressedImage):
        """压缩图像回调：从 CompressedImage 解码后复用检测逻辑。"""
        if self._min_detect_interval_s > 0.0:
            now = time.monotonic()
            if now - self._last_detect_time < self._min_detect_interval_s:
                return
            self._last_detect_time = now

        try:
            np_arr = np.frombuffer(msg.data, np.uint8)
            cv_image = cv.imdecode(np_arr, cv.IMREAD_GRAYSCALE)
            if cv_image is None:
                self.get_logger().error('压缩图像解码失败')
                return
        except Exception as e:
            self.get_logger().error(f'压缩图像解码异常: {e}')
            return

        try:
            decoded_info, points_list = self._decode_qr(cv_image)
        except Exception as e:
            self.get_logger().error(f'二维码检测失败: {e}')
            return

        if decoded_info:
            for i, info in enumerate(decoded_info):
                if self._pose_pub is not None and i < len(points_list):
                    corners = points_list[i]
                    if corners is not None and corners.shape == (4, 2):
                        pose = self._estimate_pose(corners, msg.header)
                        if pose is not None:
                            self._pose_pub.publish(pose)

                if not self._should_publish(info):
                    continue
                self.get_logger().info(f'✅ 识别到二维码: {info}')
                str_msg = String()
                str_msg.data = info
                self.result_pub.publish(str_msg)

    def image_callback(self, msg: Image):
        """
        图像回调：每收到一帧相机图像时自动调用。

        处理流程：
          1. CvBridge 将 ROS Image 消息转为 OpenCV numpy 数组（BGR 格式）
          2. 调用 _decode_qr() 检测并解码 QR 码
          3. 如果检测到内容，逐条发布到 ~/decoded_info 话题

        参数:
            msg: sensor_msgs/Image 消息，包含一帧相机图像
        """

        # ---- 帧率控制：跳过过于密集的检测请求 ----
        if self._min_detect_interval_s > 0.0:
            now = time.monotonic()
            if now - self._last_detect_time < self._min_detect_interval_s:
                return
            self._last_detect_time = now

        # ---- 步骤 1：ROS Image → OpenCV numpy 数组 ----
        # 使用 passthrough 保持原始编码（相机输出 mono8，无需转 bgr8）
        # QR 检测算法基于灰度边缘/对比度，不需要彩色信息
        try:
            cv_image = self.bridge.imgmsg_to_cv2(msg, desired_encoding='passthrough')
        except Exception as e:
            # 可能的异常：图像编码不支持、数据损坏等
            self.get_logger().error(f'图像转换失败: {e}')
            return  # 跳过本帧，等待下一帧

        # ---- 步骤 2：QR 码检测与解码 ----
        try:
            decoded_info, points_list = self._decode_qr(cv_image)
        except Exception as e:
            self.get_logger().error(f'二维码检测失败: {e}')
            return

        # ---- 步骤 3：发布解码结果 ----
        if decoded_info:
            for i, info in enumerate(decoded_info):
                # 位姿估计（use_camera_info 启用时）
                if self._pose_pub is not None and i < len(points_list):
                    corners = points_list[i]
                    if corners is not None and corners.shape == (4, 2):
                        pose = self._estimate_pose(corners, msg.header)
                        if pose is not None:
                            self._pose_pub.publish(pose)
                            self.get_logger().info(
                                f'📐 QR 位姿: x={pose.pose.position.x:.3f} '
                                f'y={pose.pose.position.y:.3f} '
                                f'z={pose.pose.position.z:.3f}'
                            )

                if not self._should_publish(info):
                    continue
                self.get_logger().info(f'✅ 识别到二维码: {info}')
                str_msg = String()
                str_msg.data = info
                self.result_pub.publish(str_msg)


# ============================================================================
# 节点入口函数
# ============================================================================

def main(args=None):
    """
    节点主入口。

    执行流程：
      1. rclpy.init()       — 初始化 ROS 2 通信中间件（DDS）
      2. WeChatQRNode()     — 实例化节点（触发 __init__ 中的所有初始化）
      3. rclpy.spin(node)   — 进入事件循环，阻塞等待回调
      4. destroy_node()     — 清理资源
      5. rclpy.shutdown()   — 关闭 ROS 2 通信
    """
    # 初始化 ROS 2 客户端库，必须在使用任何 ROS 功能前调用
    # args 参数用于接收命令行参数（如 --ros-args -p 参数:=值）
    rclpy.init(args=args)

    # 创建节点实例
    node = WeChatQRNode()

    try:
        # spin() 进入事件循环：
        #   - 检查是否有新消息到达 → 调用对应的回调函数
        #   - 检查是否有定时器到期 → 调用定时器回调
        #   - 循环直到节点被关闭
        # 这是一个阻塞调用，会一直运行直到退出
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        # KeyboardInterrupt:  用户按 Ctrl+C
        # ExternalShutdownException: launch 系统或外部信号要求关闭
        # 两种情况都属于正常退出，不需要报错
        pass
    finally:
        # 无论是否发生异常，finally 块都会执行
        node.destroy_node()
        # destroy_node() 释放节点占用的资源：
        #   - 取消所有订阅
        #   - 销毁所有发布者和定时器
        #   - 从 ROS 图中注销节点

        # rclpy.ok() 检查 ROS 2 通信系统是否仍在运行
        # 如果已经被外部关闭（如 SIGTERM），则不需要再次 shutdown
        if rclpy.ok():
            rclpy.shutdown()


# Python 标准入口点判断：
# 当文件被直接执行（python3 qrcode_node.py）时 __name__ == '__main__'
# 当文件被 import 时 __name__ == 模块名，不会执行 main()
if __name__ == '__main__':
    main()
