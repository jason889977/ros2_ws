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
    package_prefix = get_package_prefix('qrcode_detector')
    executable = os.path.join(package_prefix, 'lib', 'qrcode_detector', 'qrcode_node')

    cmd = [
        executable,
        '--ros-args',
        '-r', '__node:=wechat_qr_node',
        '-p', f'image_topic:={image_topic}',
        '-p', 'queue_size:=10',
        '-p', f'prefer_wechat_qr:={prefer_wechat_qr}',
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
        default_value='/my_camera/pylon_ros2_camera_node/image_raw',
        description='Basler 相机发布的图像话题名称',
    )

    model_dir_arg = DeclareLaunchArgument(
        'model_dir',
        default_value='',
        description='WeChatQR 模型文件目录（留空使用包内默认路径）',
    )

    prefer_wechat_qr_arg = DeclareLaunchArgument(
        'prefer_wechat_qr',
        default_value='false',
        description='是否优先使用 WeChatQR 模型，默认关闭以走稳定的 OpenCV fallback',
    )

    return LaunchDescription([
        image_topic_arg,
        model_dir_arg,
        prefer_wechat_qr_arg,
        OpaqueFunction(function=launch_qrcode_node),
    ])
