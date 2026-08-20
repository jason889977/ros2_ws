"""Launch the vision pipeline with per-module enable flags and namespaced outputs.

Supports multi-camera by namespacing all output topics under /{camera_id}/.
Each detection module (AprilTag, QR, Keyence) can be independently enabled/disabled.
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.actions import OpaqueFunction
from launch.conditions import IfCondition
from launch_ros.actions import ComposableNodeContainer, Node
from launch_ros.descriptions import ComposableNode


def launch_pipeline(context):
    camera_id = context.launch_configurations['camera_id']
    camera_config = context.launch_configurations['camera_config']
    camera_frame = context.launch_configurations['camera_frame']
    startup_user_set = context.launch_configurations['startup_user_set']
    scanner_ip = context.launch_configurations['scanner_ip']
    scanner_port = context.launch_configurations['scanner_port']
    reconnect_interval_s = context.launch_configurations['reconnect_interval_s']
    enable_apriltag = context.launch_configurations['enable_apriltag']
    enable_qrcode = context.launch_configurations['enable_qrcode']
    enable_keyence = context.launch_configurations['enable_keyence']

    camera_info_topic = f'/{camera_id}/pylon_ros2_camera_node/camera_info'
    image_topic = f'/{camera_id}/pylon_ros2_camera_node/image_raw'

    # Namespaced output topics
    apriltag_pose_topic = f'/{camera_id}/apriltag/pose'
    apriltag_transform_topic = f'/{camera_id}/apriltag/transform'
    detections_topic = f'/{camera_id}/detections'
    qr_decoded_topic = f'/{camera_id}/qr/decoded_info'
    scanner_barcode_topic = f'/{camera_id}/scanner/barcode'
    scanner_trigger_topic = f'/{camera_id}/scanner/trigger'

    detector_config = os.path.join(
        get_package_share_directory('apriltag_pose_reader'),
        'config',
        'apriltag_36h11.yaml',
    )

    nodes = []

    # ------------------------------------------------------------------
    # Camera always runs in a component container (zero-copy image pub)
    # ------------------------------------------------------------------
    container = ComposableNodeContainer(
        name=f'vision_container_{camera_id}',
        namespace='',
        package='rclcpp_components',
        executable='component_container_mt',
        composable_node_descriptions=[
            ComposableNode(
                package='pylon_ros2_camera_component',
                plugin='pylon_ros2_camera::PylonROS2CameraNode',
                name='pylon_ros2_camera_node',
                namespace=camera_id,
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
                extra_arguments=[{'use_intra_process_comms': True}],
            ),
        ],
    )
    nodes.append(container)

    # ------------------------------------------------------------------
    # AprilTag chain (conditional)
    # ------------------------------------------------------------------
    nodes.append(Node(
        package='apriltag_ros',
        executable='apriltag_node',
        name='apriltag',
        namespace=camera_id,
        output='screen',
        respawn=True,
        respawn_delay=3.0,
        condition=IfCondition(enable_apriltag),
        remappings=[
            ('image_rect', image_topic),
            ('camera_info', camera_info_topic),
        ],
        parameters=[detector_config],
    ))

    nodes.append(Node(
        package='apriltag_pose_reader',
        executable='apriltag_pose_reader',
        name='apriltag_pose_reader',
        namespace=camera_id,
        output='screen',
        respawn=True,
        respawn_delay=3.0,
        condition=IfCondition(enable_apriltag),
        parameters=[{
            'detections_topic': detections_topic,
            'tf_topic': '/tf',
            'lookup_parent_frame': camera_frame,
            'lookup_rate_hz': 0.0,
            'publish_all_tags': True,
            'output_pose_topic': apriltag_pose_topic,
            'output_transform_topic': apriltag_transform_topic,
            'subscribe_detections': True,
            'publish_detection_logs': False,
        }],
    ))

    # ------------------------------------------------------------------
    # QR detection chain (conditional) — subscribes to raw image directly
    # ------------------------------------------------------------------
    nodes.append(Node(
        package='qrcode_detector',
        executable='qrcode_node',
        name='wechat_qr_node',
        namespace=camera_id,
        output='screen',
        respawn=True,
        respawn_delay=3.0,
        condition=IfCondition(enable_qrcode),
        parameters=[{
            'image_topic': image_topic,
            'camera_info_topic': camera_info_topic,
            'prefer_wechat_qr': True,
            'use_camera_info': True,
            'deduplicate_window_s': 0.5,
            'min_detect_interval_s': 0.2,
            'use_compressed': False,
        }],
        remappings=[
            ('~/decoded_info', qr_decoded_topic),
        ],
    ))

    # ------------------------------------------------------------------
    # Keyence scanner (conditional)
    # ------------------------------------------------------------------
    nodes.append(Node(
        package='keyence_sr_wrapper',
        executable='keyence_sr_node',
        name='keyence_sr_node',
        namespace=camera_id,
        output='screen',
        respawn=True,
        respawn_delay=3.0,
        condition=IfCondition(enable_keyence),
        parameters=[{
            'scanner_ip': scanner_ip,
            'scanner_port': int(scanner_port),
            'reconnect_interval_s': float(reconnect_interval_s),
        }],
        remappings=[
            ('~/barcode', scanner_barcode_topic),
            ('~/trigger', scanner_trigger_topic),
        ],
    ))

    return nodes


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
        DeclareLaunchArgument('enable_apriltag', default_value='true',
                              description='Enable AprilTag detection chain'),
        DeclareLaunchArgument('enable_qrcode', default_value='true',
                              description='Enable QR code detection chain'),
        DeclareLaunchArgument('enable_keyence', default_value='true',
                              description='Enable Keyence scanner node'),
        OpaqueFunction(function=launch_pipeline),
    ])
