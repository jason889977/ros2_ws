"""ROS 2 QR code detector node."""

import os

from ament_index_python.packages import get_package_share_directory
import cv2 as cv
from cv_bridge import CvBridge
import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from sensor_msgs.msg import Image
from std_msgs.msg import String


class WeChatQRNode(Node):
    def __init__(self):
        super().__init__('wechat_qr_node')
        self.get_logger().info('Initializing QR detector node...')

        # ---------- 参数声明 ----------
        self.declare_parameter('image_topic', '/camera/image_raw')
        self.declare_parameter('model_dir', '')          # 留空则使用包内默认 models/
        self.declare_parameter('queue_size', 10)
        self.declare_parameter('use_camera_info', False)
        self.declare_parameter('prefer_wechat_qr', False)

        # ---------- 读取参数 ----------
        image_topic = self.get_parameter('image_topic').value
        model_dir = self.get_parameter('model_dir').value
        queue_size = self.get_parameter('queue_size').value
        use_camera_info = self.get_parameter('use_camera_info').value
        prefer_wechat_qr = self.get_parameter('prefer_wechat_qr').value

        if use_camera_info:
            self.get_logger().warn(
                '参数 use_camera_info 当前未启用，将被忽略。'
            )

        # ---------- 初始化 CvBridge ----------
        self.bridge = CvBridge()

        # ---------- 初始化 WeChatQRCode 检测器 ----------
        if not model_dir:
            pkg_share = get_package_share_directory('qrcode_detector')
            model_dir = os.path.join(pkg_share, 'models')

        self.detector, self.detector_kind = self._init_detector(
            model_dir,
            prefer_wechat_qr,
        )

        # ---------- 发布者：识别结果（字符串） ----------
        self.result_pub = self.create_publisher(String, '~/decoded_info', 10)

        # ---------- 订阅相机图像 ----------
        self.subscription = self.create_subscription(
            Image,
            image_topic,
            self.image_callback,
            queue_size,
        )

        self.get_logger().info(
            f'WeChatQR 二维码识别节点已启动，订阅话题: {image_topic}'
        )

    # ------------------------------------------------------------------
    def _init_detector(self, model_dir: str, prefer_wechat_qr: bool):
        """Initialize QR detector with WeChat model, fallback to OpenCV QRCodeDetector."""
        if not prefer_wechat_qr:
            self.get_logger().info(
                'prefer_wechat_qr is false, using OpenCV QRCodeDetector.'
            )
            return cv.QRCodeDetector(), 'opencv'

        required_files = [
            'detect.prototxt',
            'detect.caffemodel',
            'sr.prototxt',
            'sr.caffemodel',
        ]
        missing = [f for f in required_files
                   if not os.path.isfile(os.path.join(model_dir, f))]

        has_wechat = hasattr(cv, 'wechat_qrcode') and hasattr(cv.wechat_qrcode, 'WeChatQRCode')

        if not has_wechat:
            self.get_logger().warn('OpenCV does not provide wechat_qrcode, fallback to QRCodeDetector.')
            return cv.QRCodeDetector(), 'opencv'

        if missing:
            self.get_logger().warn(
                f'模型文件缺失: {missing}，fallback to QRCodeDetector。'
            )
            return cv.QRCodeDetector(), 'opencv'

        paths = [os.path.join(model_dir, f) for f in required_files]
        self.get_logger().info(f'加载 WeChatQR 模型: {model_dir}')
        return cv.wechat_qrcode.WeChatQRCode(*paths), 'wechat'

    def _decode_qr(self, cv_image):
        """Decode one or multiple QR codes using the selected backend."""
        if self.detector_kind == 'wechat':
            decoded_info, _ = self.detector.detectAndDecode(cv_image)
            if isinstance(decoded_info, str):
                return [decoded_info] if decoded_info else []
            return [info for info in decoded_info if info]

        if hasattr(self.detector, 'detectAndDecodeMulti'):
            result = self.detector.detectAndDecodeMulti(cv_image)
            if isinstance(result, tuple) and len(result) >= 2:
                decoded_info = result[1]
                return [info for info in decoded_info if info]

        decoded_info, _, _ = self.detector.detectAndDecode(cv_image)
        return [decoded_info] if decoded_info else []

    # ------------------------------------------------------------------
    def image_callback(self, msg: Image):
        """Decode QR data from each incoming image and publish results."""
        try:
            cv_image = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
        except Exception as e:
            self.get_logger().error(f'图像转换失败: {e}')
            return

        try:
            decoded_info = self._decode_qr(cv_image)
        except Exception as e:
            self.get_logger().error(f'二维码检测失败: {e}')
            return

        if decoded_info:
            for info in decoded_info:
                self.get_logger().info(f'✅ 识别到二维码: {info}')
                # 同时发布到话题，供下游节点使用
                str_msg = String()
                str_msg.data = info
                self.result_pub.publish(str_msg)


def main(args=None):
    rclpy.init(args=args)
    node = WeChatQRNode()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
