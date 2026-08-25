"""Launch qrcode_detector node."""

import os
import math

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.actions import OpaqueFunction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def parse_bool(value, name):
    normalized = str(value).strip().lower()
    if normalized not in ('true', 'false'):
        raise RuntimeError(f'Invalid {name}={value!r}; expected true or false.')
    return normalized == 'true'


def parse_positive_float(value, name):
    try:
        parsed = float(value)
    except (TypeError, ValueError) as error:
        raise RuntimeError(f'Invalid {name}={value!r}; expected a finite value > 0.') from error
    if not math.isfinite(parsed) or parsed <= 0.0:
        raise RuntimeError(f'Invalid {name}={value!r}; expected a finite value > 0.')
    return parsed


def parse_nonnegative_float(value, name):
    try:
        parsed = float(value)
    except (TypeError, ValueError) as error:
        raise RuntimeError(f'Invalid {name}={value!r}; expected a finite value >= 0.') from error
    if not math.isfinite(parsed) or parsed < 0.0:
        raise RuntimeError(f'Invalid {name}={value!r}; expected a finite value >= 0.')
    return parsed


def launch_qrcode_node(context):
    image_topic = LaunchConfiguration('image_topic').perform(context)
    model_dir = LaunchConfiguration('model_dir').perform(context)
    prefer_wechat_qr = LaunchConfiguration('prefer_wechat_qr').perform(context)
    use_camera_info = LaunchConfiguration('use_camera_info').perform(context)
    camera_info_topic = LaunchConfiguration('camera_info_topic').perform(context)
    qr_size_m = LaunchConfiguration('qr_size_m').perform(context)
    deduplicate_window_s = LaunchConfiguration('deduplicate_window_s').perform(context)
    min_detect_interval_s = LaunchConfiguration('min_detect_interval_s').perform(context)
    use_compressed = LaunchConfiguration('use_compressed').perform(context)
    queue_size = LaunchConfiguration('queue_size').perform(context)
    try:
        queue_size_value = int(queue_size)
    except (TypeError, ValueError) as error:
        raise RuntimeError(
            f'Invalid queue_size={queue_size!r}; expected a positive integer.'
        ) from error
    if queue_size_value < 1:
        raise RuntimeError(
            f'Invalid queue_size={queue_size!r}; expected a positive integer.'
        )
    parameters = [{
        'image_topic': image_topic,
        'queue_size': queue_size_value,
        'prefer_wechat_qr': parse_bool(prefer_wechat_qr, 'prefer_wechat_qr'),
        'use_camera_info': parse_bool(use_camera_info, 'use_camera_info'),
        'camera_info_topic': camera_info_topic,
        'qr_size_m': parse_positive_float(qr_size_m, 'qr_size_m'),
        'deduplicate_window_s': parse_nonnegative_float(
            deduplicate_window_s, 'deduplicate_window_s'
        ),
        'min_detect_interval_s': parse_nonnegative_float(
            min_detect_interval_s, 'min_detect_interval_s'
        ),
        'use_compressed': parse_bool(use_compressed, 'use_compressed'),
    }]
    if model_dir:
        parameters[0]['model_dir'] = model_dir

    return [
        Node(
            package='qrcode_detector',
            executable='qrcode_node',
            name='wechat_qr_node',
            parameters=parameters,
            output='screen',
        )
    ]


def generate_launch_description():
    # ---------- 可配置参数 ----------
    image_topic_arg = DeclareLaunchArgument(
        'image_topic',
        default_value=os.environ.get(
            'IMAGE_TOPIC',
            '/my_camera/pylon_ros2_camera_node/image_raw',
        ),
        description='Basler 相机发布的图像话题名称',
    )

    model_dir_arg = DeclareLaunchArgument(
        'model_dir',
        default_value=os.environ.get('MODEL_DIR', ''),
        description='WeChatQR 模型文件目录（留空使用包内默认路径）',
    )

    prefer_wechat_qr_arg = DeclareLaunchArgument(
        'prefer_wechat_qr',
        default_value=os.environ.get('PREFER_WECHAT_QR', 'true'),
        description='是否优先使用 WeChatQR 模型（对模糊/小尺寸/遮挡 QR 码更鲁棒）',
    )

    use_camera_info_arg = DeclareLaunchArgument(
        'use_camera_info',
        default_value='true',
        description='是否使用相机内参做 QR 码位姿估计（需先完成相机标定）',
    )

    camera_info_topic_arg = DeclareLaunchArgument(
        'camera_info_topic',
        default_value='/my_camera/pylon_ros2_camera_node/camera_info',
        description='相机标定信息话题名',
    )

    qr_size_m_arg = DeclareLaunchArgument(
        'qr_size_m',
        default_value='0.10',
        description='QR 码物理边长（米），用于 solvePnP 位姿估计',
    )

    deduplicate_window_arg = DeclareLaunchArgument(
        'deduplicate_window_s',
        default_value='0.5',
        description='同一 QR 结果的重复发布抑制时间（秒）',
    )

    queue_size_arg = DeclareLaunchArgument(
        'queue_size',
        default_value=os.environ.get('QUEUE_SIZE', '1'),
        description='图像和结果队列深度，建议工业实时场景使用 1',
    )

    min_detect_interval_arg = DeclareLaunchArgument(
        'min_detect_interval_s',
        default_value=os.environ.get('MIN_DETECT_INTERVAL_S', '0.2'),
        description='Minimum interval between detector runs in seconds',
    )

    use_compressed_arg = DeclareLaunchArgument(
        'use_compressed',
        default_value=os.environ.get('USE_COMPRESSED', 'false'),
        description='Subscribe to the image transport compressed topic',
    )

    return LaunchDescription([
        image_topic_arg,
        model_dir_arg,
        prefer_wechat_qr_arg,
        use_camera_info_arg,
        camera_info_topic_arg,
        qr_size_m_arg,
        deduplicate_window_arg,
        queue_size_arg,
        min_detect_interval_arg,
        use_compressed_arg,
        OpaqueFunction(function=launch_qrcode_node),
    ])
