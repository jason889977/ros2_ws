"""Launch the camera, AprilTag and QR nodes in one container."""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.actions import OpaqueFunction
from launch_ros.actions import Node


def launch_pipeline(context):
    camera_id = context.launch_configurations['camera_id']
    camera_config = context.launch_configurations['camera_config']
    camera_frame = context.launch_configurations['camera_frame']
    startup_user_set = context.launch_configurations['startup_user_set']
    scanner_ip = context.launch_configurations['scanner_ip']
    scanner_port = context.launch_configurations['scanner_port']
    reconnect_interval_s = context.launch_configurations['reconnect_interval_s']
    camera_info_topic = f'/{camera_id}/pylon_ros2_camera_node/camera_info'
    image_topic = f'/{camera_id}/pylon_ros2_camera_node/image_raw'
    detector_config = os.path.join(
        get_package_share_directory('apriltag_pose_reader'),
        'config',
        'apriltag_36h11.yaml',
    )

    return [
        Node(
            package='pylon_ros2_camera_wrapper',
            namespace=camera_id,
            executable='pylon_ros2_camera_wrapper',
            name='pylon_ros2_camera_node',
            output='screen',
            respawn=True,
            parameters=[
                camera_config,
                {
                    'startup_user_set': startup_user_set,
                    'binning_x': 2,
                    'binning_y': 2,
                    'enable_status_publisher': True,
                    'enable_current_params_publisher': True,
                },
            ],
        ),
        Node(
            package='apriltag_ros',
            executable='apriltag_node',
            name='apriltag',
            output='screen',
            remappings=[
                ('image_rect', image_topic),
                ('camera_info', camera_info_topic),
            ],
            parameters=[detector_config],
        ),
        Node(
            package='apriltag_pose_reader',
            executable='apriltag_pose_reader',
            name='apriltag_pose_reader',
            output='screen',
            parameters=[{
                'detections_topic': '/detections',
                'tf_topic': '/tf',
                'lookup_parent_frame': camera_frame,
                'lookup_rate_hz': 0.0,
                'publish_all_tags': True,
                'output_pose_topic': '/apriltag/pose',
                'output_transform_topic': '/apriltag/transform',
                'subscribe_detections': True,
                'publish_detection_logs': False,
            }],
        ),
        Node(
            package='qrcode_detector',
            executable='qrcode_node',
            name='wechat_qr_node',
            output='screen',
            parameters=[{
                'image_topic': image_topic,
                'camera_info_topic': camera_info_topic,
                'prefer_wechat_qr': True,
                'use_camera_info': True,
                'deduplicate_window_s': 0.5,
            }],
        ),
        Node(
            package='keyence_sr_wrapper',
            executable='keyence_sr_node',
            name='keyence_sr_node',
            output='screen',
            parameters=[{
                'scanner_ip': scanner_ip,
                'scanner_port': int(scanner_port),
                'reconnect_interval_s': float(reconnect_interval_s),
            }],
        ),
    ]


def generate_launch_description():
    default_config = os.path.join(
        get_package_share_directory('pylon_ros2_camera_wrapper'),
        'config',
        'aca2500_106611_18.yaml',
    )
    return LaunchDescription([
        DeclareLaunchArgument('camera_id', default_value='my_camera'),
        DeclareLaunchArgument('camera_config', default_value=default_config),
        DeclareLaunchArgument(
            'camera_frame',
            default_value='basler_aca2500_106611_18',
        ),
        DeclareLaunchArgument('startup_user_set', default_value='Default'),
        DeclareLaunchArgument(
            'scanner_ip',
            default_value=os.environ.get('SCANNER_IP', '172.31.0.91'),
        ),
        DeclareLaunchArgument(
            'scanner_port',
            default_value=os.environ.get('SCANNER_PORT', '9004'),
        ),
        DeclareLaunchArgument(
            'reconnect_interval_s',
            default_value=os.environ.get('RECONNECT_INTERVAL_S', '5.0'),
        ),
        OpaqueFunction(function=launch_pipeline),
    ])
