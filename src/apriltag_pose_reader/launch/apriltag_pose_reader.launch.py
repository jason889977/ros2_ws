"""Launch official apriltag_ros and the local AprilTag pose reader."""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.actions import OpaqueFunction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def _launch(context):
    image_topic = LaunchConfiguration('image_topic').perform(context)
    camera_info_topic = LaunchConfiguration('camera_info_topic').perform(context)
    detector_params_file = LaunchConfiguration('detector_params_file').perform(context)
    start_detector = LaunchConfiguration('start_detector').perform(context).lower() == 'true'
    tag_frame_id = LaunchConfiguration('tag_frame_id').perform(context)
    tag_family = LaunchConfiguration('tag_family').perform(context)
    tag_id = LaunchConfiguration('tag_id').perform(context)
    lookup_parent_frame = LaunchConfiguration('lookup_parent_frame').perform(context)
    lookup_rate_hz = LaunchConfiguration('lookup_rate_hz').perform(context)
    health_log_interval_s = LaunchConfiguration('health_log_interval_s').perform(context)

    actions = []

    if start_detector:
        actions.append(
            Node(
                package='apriltag_ros',
                executable='apriltag_node',
                name='apriltag',
                output='screen',
                remappings=[
                    ('image_rect', image_topic),
                    ('camera_info', camera_info_topic),
                ],
                parameters=[detector_params_file],
            )
        )

    actions.append(
        Node(
            package='apriltag_pose_reader',
            executable='apriltag_pose_reader',
            name='apriltag_pose_reader',
            output='screen',
            parameters=[{
                'detections_topic': '/detections',
                'tf_topic': '/tf',
                'tag_frame_id': tag_frame_id,
                'tag_family': tag_family,
                'tag_id': int(tag_id),
                'lookup_parent_frame': lookup_parent_frame,
                'lookup_rate_hz': float(lookup_rate_hz),
                'health_log_interval_s': float(health_log_interval_s),
                'output_pose_topic': '/apriltag/pose',
                'output_transform_topic': '/apriltag/transform',
                'subscribe_detections': True,
                'publish_detection_logs': True,
            }],
        )
    )

    return actions


def generate_launch_description():
    default_params = os.path.join(
        get_package_share_directory('apriltag_pose_reader'),
        'config',
        'apriltag_36h11.yaml',
    )

    return LaunchDescription([
        DeclareLaunchArgument(
            'image_topic',
            default_value='/my_camera/pylon_ros2_camera_node/image_raw',
            description='Basler 相机的图像话题。',
        ),
        DeclareLaunchArgument(
            'camera_info_topic',
            default_value='/my_camera/pylon_ros2_camera_node/camera_info',
            description='Basler 相机的 camera_info 话题。',
        ),
        DeclareLaunchArgument(
            'detector_params_file',
            default_value=default_params,
            description='apriltag_ros 的参数文件。',
        ),
        DeclareLaunchArgument(
            'start_detector',
            default_value='true',
            description='是否同时启动官方 apriltag_ros 检测节点。',
        ),
        DeclareLaunchArgument(
            'tag_frame_id',
            default_value='',
            description='如果已知，直接指定目标 AprilTag frame。',
        ),
        DeclareLaunchArgument(
            'tag_family',
            default_value='36h11',
            description='当 tag_frame_id 未指定时，用于拼接默认 frame 的 family。',
        ),
        DeclareLaunchArgument(
            'tag_id',
            default_value='-1',
            description='当 tag_frame_id 未指定时，用于拼接默认 frame 的 id。',
        ),
        DeclareLaunchArgument(
            'lookup_parent_frame',
            default_value='',
            description='可选: TF lookup 的父坐标系；为空时自动使用最近一次 TF 消息的父坐标系。',
        ),
        DeclareLaunchArgument(
            'lookup_rate_hz',
            default_value='0.0',
            description='大于 0 时启用 TF buffer 周期性回查发布。',
        ),
        DeclareLaunchArgument(
            'health_log_interval_s',
            default_value='10.0',
            description='健康状态日志周期（秒），小于等于 0 表示关闭。',
        ),
        OpaqueFunction(function=_launch),
    ])
