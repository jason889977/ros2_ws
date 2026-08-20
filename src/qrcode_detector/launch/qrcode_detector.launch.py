"""Launch qrcode_detector node."""

import os

from ament_index_python.packages import get_package_prefix
from launch import LaunchDescription
from launch.actions import ExecuteProcess
from launch.actions import DeclareLaunchArgument
from launch.actions import OpaqueFunction
from launch.substitutions import LaunchConfiguration


def launch_qrcode_node(context):
    image_topic = LaunchConfiguration('image_topic').perform(context)
    model_dir = LaunchConfiguration('model_dir').perform(context)
    prefer_wechat_qr = LaunchConfiguration('prefer_wechat_qr').perform(context)
    use_camera_info = LaunchConfiguration('use_camera_info').perform(context)
    camera_info_topic = LaunchConfiguration('camera_info_topic').perform(context)
    qr_size_m = LaunchConfiguration('qr_size_m').perform(context)
    deduplicate_window_s = LaunchConfiguration('deduplicate_window_s').perform(context)
    package_prefix = get_package_prefix('qrcode_detector')
    executable = os.path.join(package_prefix, 'lib', 'qrcode_detector', 'qrcode_node')

    cmd = [
        executable,
        '--ros-args',
        '-r', '__node:=wechat_qr_node',
        '-p', f'image_topic:={image_topic}',
        '-p', 'queue_size:=10',
        '-p', f'prefer_wechat_qr:={prefer_wechat_qr}',
        '-p', f'use_camera_info:={use_camera_info}',
        '-p', f'camera_info_topic:={camera_info_topic}',
        '-p', f'qr_size_m:={qr_size_m}',
        '-p', f'deduplicate_window_s:={deduplicate_window_s}',
    ]

    if model_dir:
        cmd.extend(['-p', f'model_dir:={model_dir}'])

    return [
        ExecuteProcess(
            cmd=cmd,
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

    return LaunchDescription([
        image_topic_arg,
        model_dir_arg,
        prefer_wechat_qr_arg,
        use_camera_info_arg,
        camera_info_topic_arg,
        qr_size_m_arg,
        deduplicate_window_arg,
        OpaqueFunction(function=launch_qrcode_node),
    ])
