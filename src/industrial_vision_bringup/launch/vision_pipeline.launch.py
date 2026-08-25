"""Launch the vision pipeline with per-module enable flags and namespaced outputs.

Supports multi-camera by namespacing all output topics under /{camera_id}/.
Each detection module (AprilTag, QR, Keyence) can be independently enabled/disabled.
"""

import os
import math
import re

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.actions import OpaqueFunction
from launch.conditions import IfCondition
from launch_ros.actions import ComposableNodeContainer, Node
from launch_ros.descriptions import ComposableNode


def parse_scanner_settings(scanner_port_value, reconnect_interval_value):
    """Parse and validate scanner connection settings from launch arguments."""
    try:
        scanner_port = int(scanner_port_value)
    except ValueError as error:
        raise RuntimeError(
            f'Invalid scanner_port={scanner_port_value!r}; expected an integer from 1 to 65535.'
        ) from error
    if not 1 <= scanner_port <= 65535:
        raise RuntimeError(
            f'Invalid scanner_port={scanner_port_value!r}; expected an integer from 1 to 65535.'
        )

    try:
        reconnect_interval_s = float(reconnect_interval_value)
    except ValueError as error:
        raise RuntimeError(
            f'Invalid reconnect_interval_s={reconnect_interval_value!r}; expected a finite value >= 0.'
        ) from error
    if not math.isfinite(reconnect_interval_s) or reconnect_interval_s < 0.0:
        raise RuntimeError(
            f'Invalid reconnect_interval_s={reconnect_interval_value!r}; expected a finite value >= 0.'
        )
    return scanner_port, reconnect_interval_s


def validate_pipeline_settings(camera_id, camera_frame, mtu_size, respawn,
                                prefer_wechat_qr):
    """Validate launch values before creating any ROS actions."""
    if re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*', str(camera_id)) is None:
        raise RuntimeError(
            f'Invalid camera_id={camera_id!r}; expected a ROS-safe identifier.'
        )
    if not str(camera_frame).strip():
        raise RuntimeError('camera_frame must not be empty.')
    try:
        mtu_size = int(mtu_size)
    except (TypeError, ValueError) as error:
        raise RuntimeError(
            f'Invalid mtu_size={mtu_size!r}; expected an integer from 576 to 9000.'
        ) from error
    if not 576 <= mtu_size <= 9000:
        raise RuntimeError(
            f'Invalid mtu_size={mtu_size!r}; expected an integer from 576 to 9000.'
        )
    for name, value in (('respawn', respawn),
                        ('prefer_wechat_qr', prefer_wechat_qr)):
        if str(value).lower() not in ('true', 'false'):
            raise RuntimeError(
                f'Invalid {name}={value!r}; expected true or false.'
            )


def build_tag_frames(camera_id, tag_count=12):
    """Return unique AprilTag child frames for one camera pipeline."""
    return [f'{camera_id}/tag36h11:{tag_id}' for tag_id in range(tag_count)]


def parse_bool(value, name):
    """Parse a strict boolean launch value."""
    normalized = str(value).strip().lower()
    if normalized not in ('true', 'false'):
        raise RuntimeError(f'Invalid {name}={value!r}; expected true or false.')
    return normalized == 'true'


def launch_pipeline(context):
    camera_id = context.launch_configurations['camera_id']
    camera_config = context.launch_configurations['camera_config']
    camera_frame = context.launch_configurations['camera_frame']
    startup_user_set = context.launch_configurations['startup_user_set']
    mtu_size = context.launch_configurations['mtu_size']
    respawn = parse_bool(context.launch_configurations['respawn'], 'respawn')
    scanner_ip = context.launch_configurations['scanner_ip']
    scanner_port = context.launch_configurations['scanner_port']
    reconnect_interval_s = context.launch_configurations['reconnect_interval_s']
    enable_apriltag = parse_bool(
        context.launch_configurations['enable_apriltag'], 'enable_apriltag'
    )
    enable_qrcode = parse_bool(
        context.launch_configurations['enable_qrcode'], 'enable_qrcode'
    )
    enable_keyence = parse_bool(
        context.launch_configurations['enable_keyence'], 'enable_keyence'
    )
    prefer_wechat_qr = parse_bool(
        context.launch_configurations['prefer_wechat_qr'], 'prefer_wechat_qr'
    )
    use_compressed = parse_bool(
        context.launch_configurations['use_compressed'], 'use_compressed'
    )
    handeye_calibration_file = context.launch_configurations.get(
        'handeye_calibration_file', ''
    )
    world_frame = context.launch_configurations.get('world_frame', '')
    base_frame = context.launch_configurations.get('base_frame', '')
    min_detect_interval_s = float(
        context.launch_configurations['min_detect_interval_s']
    )
    if not math.isfinite(min_detect_interval_s) or min_detect_interval_s < 0.0:
        raise RuntimeError('min_detect_interval_s must be finite and non-negative.')
    validate_pipeline_settings(
        camera_id,
        camera_frame,
        mtu_size,
        str(respawn).lower(),
        str(prefer_wechat_qr).lower(),
    )
    expected_components = []
    if enable_apriltag:
        expected_components.append('AprilTag Status')
    if enable_qrcode:
        expected_components.append('QR Detector Status')
    if enable_keyence:
        expected_components.append('Scanner Connection')
    scanner_port, reconnect_interval_s = parse_scanner_settings(
        scanner_port,
        reconnect_interval_s,
    )

    camera_info_topic = f'/{camera_id}/pylon_ros2_camera_node/camera_info'
    image_topic = f'/{camera_id}/pylon_ros2_camera_node/image_raw'

    # Namespaced output topics
    apriltag_pose_topic = f'/{camera_id}/apriltag/pose'
    apriltag_transform_topic = f'/{camera_id}/apriltag/transform'
    detections_topic = f'/{camera_id}/detections'
    qr_decoded_topic = f'/{camera_id}/qr/decoded_info'
    scanner_barcode_topic = f'/{camera_id}/scanner/barcode'
    scanner_trigger_topic = f'/{camera_id}/scanner/trigger'
    diagnostics_topic = f'/{camera_id}/diagnostics'
    vision_status_topic = f'/{camera_id}/vision/status'

    detector_config = os.path.join(
        get_package_share_directory('apriltag_pose_reader'),
        'config',
        'apriltag_36h11.yaml',
    )
    tag_ids = list(range(12))
    tag_frame_prefix = f'{camera_id}/'
    tag_frames = build_tag_frames(camera_id, len(tag_ids))

    nodes = []

    # ------------------------------------------------------------------
    # High-performance zero-copy component container:
    # Hosts Pylon Camera driver, AprilTag detector, and WeChatQR detector
    # in a single multi-threaded process with intra-process communication.
    # ------------------------------------------------------------------
    composable_nodes = [
        ComposableNode(
            package='pylon_ros2_camera_component',
            plugin='pylon_ros2_camera::PylonROS2CameraNode',
            name='pylon_ros2_camera_node',
            namespace=camera_id,
            parameters=[
                camera_config,
                {
                    'startup_user_set': startup_user_set,
                    'camera_frame': camera_frame,
                    'mtu_size': int(mtu_size),
                    'binning_x': 2,
                    'binning_y': 2,
                    'enable_status_publisher': True,
                    'enable_current_params_publisher': True,
                },
            ],
            extra_arguments=[{'use_intra_process_comms': True}],
            remappings=[('/diagnostics', diagnostics_topic)],
        ),
    ]

    if enable_apriltag:
        composable_nodes.append(ComposableNode(
            package='apriltag_ros',
            plugin='AprilTagNode',
            name='apriltag',
            namespace=camera_id,
            parameters=[detector_config, {
                'tag': {
                    'ids': tag_ids,
                    'frames': tag_frames,
                    'sizes': [0.05] * len(tag_ids),
                },
            }],
            remappings=[
                ('image_rect', image_topic),
                ('camera_info', camera_info_topic),
                ('/diagnostics', diagnostics_topic),
            ],
            extra_arguments=[{'use_intra_process_comms': True}],
        ))

    if enable_qrcode:
        composable_nodes.append(ComposableNode(
            package='qrcode_detector',
            plugin='qrcode_detector::QRCodeNode',
            name='wechat_qr_node',
            namespace=camera_id,
            parameters=[{
                'image_topic': image_topic,
                'camera_info_topic': camera_info_topic,
                'prefer_wechat_qr': prefer_wechat_qr,
                'use_camera_info': True,
                'deduplicate_window_s': 0.5,
                'min_detect_interval_s': min_detect_interval_s,
                'use_compressed': use_compressed,
                'queue_size': 1,
            }],
            remappings=[
                ('~/decoded_info', qr_decoded_topic),
                ('/diagnostics', diagnostics_topic),
            ],
            extra_arguments=[{'use_intra_process_comms': True}],
        ))

    container = ComposableNodeContainer(
        name=f'vision_container_{camera_id}',
        namespace='',
        package='rclcpp_components',
        executable='component_container_mt',
        composable_node_descriptions=composable_nodes,
        output='screen',
        respawn=respawn,
        respawn_delay=3.0,
    )
    nodes.append(container)

    # ------------------------------------------------------------------
    # AprilTag pose reader (conditional)
    # ------------------------------------------------------------------
    nodes.append(Node(
        package='apriltag_pose_reader',
        executable='apriltag_pose_reader',
        name='apriltag_pose_reader',
        namespace=camera_id,
        output='screen',
        respawn=respawn,
        respawn_delay=3.0,
        condition=IfCondition(str(enable_apriltag).lower()),
        parameters=[{
            'detections_topic': detections_topic,
            'tf_topic': '/tf',
            'lookup_parent_frame': camera_frame,
            'tag_frame_prefix': tag_frame_prefix,
            'lookup_rate_hz': 0.0,
            'publish_all_tags': True,
            'output_pose_topic': apriltag_pose_topic,
            'output_transform_topic': apriltag_transform_topic,
            'subscribe_detections': True,
            'publish_detection_logs': False,
        }],
        remappings=[('/diagnostics', diagnostics_topic)],
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
        respawn=respawn,
        respawn_delay=3.0,
        condition=IfCondition(str(enable_keyence).lower()),
        parameters=[{
            'scanner_ip': scanner_ip,
            'scanner_port': scanner_port,
            'reconnect_interval_s': reconnect_interval_s,
        }],
        remappings=[
            ('~/barcode', scanner_barcode_topic),
            ('~/trigger', scanner_trigger_topic),
            ('/diagnostics', diagnostics_topic),
        ],
    ))

    nodes.append(Node(
        package='industrial_vision_bringup',
        executable='vision_status_aggregator',
        name='vision_status_aggregator',
        namespace=camera_id,
        output='screen',
        parameters=[{
            'camera_id': camera_id,
            'diagnostics_topic': diagnostics_topic,
            'output_topic': vision_status_topic,
            'diagnostic_timeout_s': 5.0,
            'expected_components': expected_components,
        }],
    ))

    # ------------------------------------------------------------------
    # Optional Hand-Eye static TF broadcaster
    # ------------------------------------------------------------------
    if handeye_calibration_file:
        nodes.append(Node(
            package='apriltag_pose_reader',
            executable='handeye_static_tf_broadcaster',
            name='handeye_static_tf_broadcaster',
            namespace=camera_id,
            output='screen',
            parameters=[{
                'calibration_file': handeye_calibration_file,
                'child_frame': camera_frame,
            }],
        ))

    # Optional world -> base_link static anchor
    if world_frame and base_frame:
        nodes.append(Node(
            package='apriltag_pose_reader',
            executable='handeye_static_tf_broadcaster',
            name='world_base_static_tf_broadcaster',
            namespace=camera_id,
            output='screen',
            parameters=[{
                'parent_frame': world_frame,
                'child_frame': base_frame,
                'translation': [0.0, 0.0, 0.0],
                'rotation_rpy': [0.0, 0.0, 0.0],
            }],
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
        DeclareLaunchArgument('mtu_size', default_value='1500'),
        DeclareLaunchArgument('respawn', default_value='true'),
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
        DeclareLaunchArgument(
            'prefer_wechat_qr',
            default_value=os.environ.get('PREFER_WECHAT_QR', 'true'),
            description='Prefer the WeChatQR backend when its models are available',
        ),
        DeclareLaunchArgument(
            'min_detect_interval_s',
            default_value=os.environ.get('MIN_DETECT_INTERVAL_S', '0.2'),
        ),
        DeclareLaunchArgument(
            'use_compressed',
            default_value=os.environ.get('USE_COMPRESSED', 'false'),
        ),
        DeclareLaunchArgument(
            'handeye_calibration_file',
            default_value=os.environ.get('HANDEYE_CALIBRATION_FILE', ''),
            description='Path to hand-eye calibration YAML for static TF broadcasting',
        ),
        DeclareLaunchArgument(
            'world_frame',
            default_value=os.environ.get('WORLD_FRAME', ''),
            description='Global world frame ID for multi-camera anchor',
        ),
        DeclareLaunchArgument(
            'base_frame',
            default_value=os.environ.get('BASE_FRAME', ''),
            description='Robot base link frame ID',
        ),
        OpaqueFunction(function=launch_pipeline),
    ])
