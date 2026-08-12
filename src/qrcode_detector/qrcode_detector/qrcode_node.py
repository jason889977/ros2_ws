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
# Node 是 ROS 2 节点的基类。
# 节点是 ROS 2 中的最小计算单元，拥有自己的参数、话题、服务等。

from sensor_msgs.msg import Image
# sensor_msgs/Image 是 ROS 2 中图像消息的标准类型。
# 包含字段：
#   header   — 时间戳 + 坐标系
#   height   — 图像高度（像素）
#   width    — 图像宽度（像素）
#   encoding — 像素编码（如 "bgr8", "mono8", "rgb8"）
#   data     — 原始像素数据（一维字节数组）

from std_msgs.msg import String
# std_msgs/String 是最简单的 ROS 2 消息类型之一。
# 只有一个字段 data（字符串），用于传递文本信息。


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

        self.declare_parameter('image_topic', '/camera/image_raw')
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
        # 当前版本未实现此功能，仅为预留参数。

        self.declare_parameter('prefer_wechat_qr', False)
        # 是否优先使用 WeChatQR 深度学习检测器。
        # False（默认）→ 使用 OpenCV 内置的 QRCodeDetector（轻量，无需模型）
        # True → 尝试加载 WeChatQR 模型，加载失败则自动降级为 OpenCV 检测器

        # ==================================================================
        # 读取参数值到局部变量
        # ==================================================================
        # get_parameter() 返回 rclpy.parameter.Parameter 对象，
        # .value 属性取出实际的值（类型在声明时由默认值推断）。
        image_topic = self.get_parameter('image_topic').value
        model_dir = self.get_parameter('model_dir').value
        queue_size = self.get_parameter('queue_size').value
        use_camera_info = self.get_parameter('use_camera_info').value
        prefer_wechat_qr = self.get_parameter('prefer_wechat_qr').value

        # 如果用户启用了 use_camera_info，打印警告（当前未实现）
        if use_camera_info:
            self.get_logger().warn(
                '参数 use_camera_info 当前未启用，将被忽略。'
            )

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
        # create_subscription(消息类型, 话题名, 回调函数, 队列大小)
        # 每当相机发布新图像时，self.image_callback 会被自动调用
        self.subscription = self.create_subscription(
            Image,          # 消息类型：ROS 标准图像消息
            image_topic,    # 话题名（从参数读取）
            self.image_callback,  # 回调函数：收到图像时执行
            queue_size,     # 队列大小（从参数读取）
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
            self.get_logger().warn('OpenCV does not provide wechat_qrcode, fallback to QRCodeDetector.')
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
    # QR 码解码
    # ======================================================================

    def _decode_qr(self, cv_image):
        """
        对一幅 OpenCV 图像进行 QR 码检测与解码。

        根据 self.detector_kind 选择不同的后端：
          - 'wechat' → WeChatQRCode.detectAndDecode()
          - 'opencv' → QRCodeDetector.detectAndDecodeMulti() 或 detectAndDecode()

        参数:
            cv_image: numpy ndarray，BGR 格式的图像（由 CvBridge 转换而来）

        返回:
            list[str] — 解码得到的字符串列表。
                        如果图像中没有 QR 码，返回空列表 []。
        """

        # ---- WeChatQR 后端 ----
        if self.detector_kind == 'wechat':
            # WeChatQRCode.detectAndDecode(image) 返回:
            #   (decoded_info, points)
            #   decoded_info — tuple of str，每个 QR 码的解码文本
            #   points       — numpy array，每个 QR 码的四个角点坐标
            # 我们只需要 decoded_info，不需要角点，所以用 _ 忽略第二个返回值
            decoded_info, _ = self.detector.detectAndDecode(cv_image)

            # WeChatQR 在只检测到一个 QR 码时，可能返回 str 而非 tuple
            if isinstance(decoded_info, str):
                # 如果是字符串且非空，包装成单元素列表返回
                return [decoded_info] if decoded_info else []
            # 如果是 tuple/list，过滤掉空字符串后返回
            return [info for info in decoded_info if info]

        # ---- OpenCV 后端 ----
        # OpenCV 4.5.4+ 的 QRCodeDetector 支持 detectAndDecodeMulti()
        # 可以同时检测和解码图像中的多个 QR 码
        if hasattr(self.detector, 'detectAndDecodeMulti'):
            # detectAndDecodeMulti(image) 返回:
            #   (retval, decoded_info)
            #   retval      — bool，是否成功检测到
            #   decoded_info — tuple of str
            # 有些版本返回 (retval, decoded_info, points) 三元组
            result = self.detector.detectAndDecodeMulti(cv_image)
            if isinstance(result, tuple) and len(result) >= 2:
                decoded_info = result[1]
                return [info for info in decoded_info if info]

        # 旧版 OpenCV 没有 detectAndDecodeMulti，退回单码检测
        # detectAndDecode(image) 返回:
        #   (decoded_info, points, straight_qrcode)
        #   decoded_info     — str，解码文本（无 QR 码时为空字符串）
        #   points           — numpy array，QR 码角点
        #   straight_qrcode  — 矫正后的 QR 码图像
        decoded_info, _, _ = self.detector.detectAndDecode(cv_image)
        return [decoded_info] if decoded_info else []

    # ======================================================================
    # 图像回调函数
    # ======================================================================

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

        # ---- 步骤 1：ROS Image → OpenCV numpy 数组 ----
        # imgmsg_to_cv2() 将序列化的 ROS 图像消息解码为内存中的像素矩阵
        # desired_encoding='bgr8' 指定输出格式为 BGR 8位（OpenCV 默认格式）
        #   B = 蓝通道, G = 绿通道, R = 红通道, 每通道 8 bit (0-255)
        #   如果输入图像的编码不是 bgr8，CvBridge 会自动做色彩空间转换
        try:
            cv_image = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
        except Exception as e:
            # 可能的异常：图像编码不支持、数据损坏等
            self.get_logger().error(f'图像转换失败: {e}')
            return  # 跳过本帧，等待下一帧

        # ---- 步骤 2：QR 码检测与解码 ----
        try:
            decoded_info = self._decode_qr(cv_image)
        except Exception as e:
            # 可能的异常：模型推理错误、内存不足等
            self.get_logger().error(f'二维码检测失败: {e}')
            return

        # ---- 步骤 3：发布解码结果 ----
        if decoded_info:
            for info in decoded_info:
                # 在终端打印识别结果（方便调试）
                self.get_logger().info(f'✅ 识别到二维码: {info}')
                # 构造 ROS String 消息并发布
                str_msg = String()
                str_msg.data = info
                # publish() 将消息发送到 ~/decoded_info 话题
                # 所有订阅了该话题的节点都会收到这条消息
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
