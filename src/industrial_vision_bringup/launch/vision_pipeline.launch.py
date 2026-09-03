"""Launch the single-camera vision pipeline with per-module enable flags.

All output topics are namespaced under /{camera_id}/.  Each detection
module (AprilTag, Keyence) can be independently enabled/disabled.
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.actions import OpaqueFunction
from launch_ros.actions import ComposableNodeContainer
from industrial_vision_bringup.composable_nodes import build_composable_nodes
from industrial_vision_bringup.pipeline_nodes import (
    build_apriltag_pose_reader,
    build_handeye_static_transform,
    build_keyence_scanner,
    build_observability_nodes,
    build_world_base_static_transform,
)
from industrial_vision_bringup.bringup_utils import (
    CameraPipelineConfig,
    ObservabilityConfig,
    build_namespaced_topics,
    build_tag_frames,
    parse_scanner_settings,
    validate_pipeline_settings,
)
from vision_core import parse_bool


def _parse_launch_config(context):
    """Parse and validate all launch parameters into a config dict."""
    lc = context.launch_configurations

    camera_id = lc['camera_id']
    camera_frame = lc['camera_frame']
    mtu_size = lc['mtu_size']

    validate_pipeline_settings(camera_id, camera_frame, mtu_size)

    enable_apriltag = parse_bool(lc['enable_apriltag'], 'enable_apriltag')
    enable_keyence = parse_bool(lc['enable_keyence'], 'enable_keyence')

    expected_components = ['camera_availability']
    if enable_apriltag:
        expected_components.append('AprilTag Status')
    if enable_keyence:
        expected_components.append('Scanner Connection')

    scanner_port, reconnect_interval_s = parse_scanner_settings(
        lc['scanner_port'], lc['reconnect_interval_s'],
    )

    apriltag_ids_str = lc.get('apriltag_ids', '')
    if apriltag_ids_str:
        try:
            tag_ids = [int(x.strip()) for x in apriltag_ids_str.split(',') if x.strip()]
        except ValueError as error:
            raise RuntimeError(
                f'Invalid apriltag_ids={apriltag_ids_str!r}; expected comma-separated integers.'
            ) from error
        tag_frames = [f'{camera_id}/tag36h11:{tid}' for tid in tag_ids]
    else:
        tag_ids = list(range(12))
        tag_frames = build_tag_frames(camera_id, len(tag_ids))

    return {
        'camera_id': camera_id,
        'camera_config': lc['camera_config'],
        'camera_frame': camera_frame,
        'startup_user_set': lc['startup_user_set'],
        'mtu_size': int(mtu_size),
        'respawn': parse_bool(lc['respawn'], 'respawn'),
        'scanner_ip': lc['scanner_ip'],
        'scanner_port': scanner_port,
        'reconnect_interval_s': reconnect_interval_s,
        'enable_apriltag': enable_apriltag,
        'enable_keyence': enable_keyence,
        'handeye_calibration_file': lc.get('handeye_calibration_file', ''),
        'world_frame': lc.get('world_frame', ''),
        'base_frame': lc.get('base_frame', ''),
        'web_port': int(lc.get('web_port', '8080')),
        'enable_web_dashboard': parse_bool(
            lc.get('enable_web_dashboard', 'true'), 'enable_web_dashboard'),
        'archive_dir': lc.get('archive_dir', ''),
        'event_log_dir': lc.get('event_log_dir', '/var/log/vision'),
        'calibration_dir': lc.get('calibration_dir', '/tmp/vision_calibration'),
        'handeye_calibration_dir': lc.get(
            'handeye_calibration_dir',
            os.path.join(lc.get('calibration_dir', '/tmp/vision_calibration'), 'handeye'),
        ),
        'binning_x': int(lc.get('binning_x', '0')),
        'binning_y': int(lc.get('binning_y', '0')),
        'apriltag_size': float(lc.get('apriltag_size', '0.0')),
        'tag_ids': tag_ids,
        'tag_frames': tag_frames,
        'expected_components': expected_components,
        'params_file': lc.get('params_file', ''),
    }


def _build_pipeline_nodes(cfg):
    """Construct the list of launch nodes from a parsed config dict."""
    topics = build_namespaced_topics(cfg['camera_id'])
    tag_frame_prefix = f"{cfg['camera_id']}/"

    detector_config = os.path.join(
        get_package_share_directory('apriltag_pose_reader'),
        'config',
        'apriltag_36h11.yaml',
    )

    composable_nodes = build_composable_nodes(CameraPipelineConfig(
        camera_id=cfg['camera_id'],
        camera_config=cfg['camera_config'],
        camera_frame=cfg['camera_frame'],
        startup_user_set=cfg['startup_user_set'],
        mtu_size=cfg['mtu_size'],
        binning_x=cfg['binning_x'],
        binning_y=cfg['binning_y'],
        enable_apriltag=cfg['enable_apriltag'],
        detector_config=detector_config,
        tag_ids=cfg['tag_ids'],
        tag_frames=cfg['tag_frames'],
        apriltag_size=cfg['apriltag_size'],
        topics=topics,
    ))

    nodes = [
        ComposableNodeContainer(
            name=f"vision_container_{cfg['camera_id']}",
            namespace='',
            package='rclcpp_components',
            executable='component_container_mt',
            composable_node_descriptions=composable_nodes,
            output='screen',
            respawn=cfg['respawn'],
            respawn_delay=3.0,
        ),
        build_apriltag_pose_reader(
            camera_id=cfg['camera_id'],
            camera_frame=cfg['camera_frame'],
            tag_frame_prefix=tag_frame_prefix,
            respawn=cfg['respawn'],
            enabled=cfg['enable_apriltag'],
            topics=topics,
        ),
        build_keyence_scanner(
            camera_id=cfg['camera_id'],
            scanner_ip=cfg['scanner_ip'],
            scanner_port=cfg['scanner_port'],
            reconnect_interval_s=cfg['reconnect_interval_s'],
            respawn=cfg['respawn'],
            enabled=cfg['enable_keyence'],
            topics=topics,
        ),
    ]

    nodes.extend(build_observability_nodes(ObservabilityConfig(
        camera_id=cfg['camera_id'],
        expected_components=cfg['expected_components'],
        enable_keyence=cfg['enable_keyence'],
        enable_web_dashboard=cfg['enable_web_dashboard'],
        web_port=cfg['web_port'],
        archive_dir=cfg['archive_dir'],
        event_log_dir=cfg['event_log_dir'],
        calibration_dir=cfg['calibration_dir'],
        handeye_calibration_dir=cfg['handeye_calibration_dir'],
        handeye_calibration_file=cfg['handeye_calibration_file'],
        camera_config=cfg['camera_config'],
        topics=topics,
        params_file=cfg['params_file'],
    )))

    if cfg['handeye_calibration_file']:
        nodes.append(build_handeye_static_transform(
            camera_id=cfg['camera_id'],
            camera_frame=cfg['camera_frame'],
            calibration_file=cfg['handeye_calibration_file'],
        ))

    if cfg['world_frame'] and cfg['base_frame']:
        nodes.append(build_world_base_static_transform(
            camera_id=cfg['camera_id'],
            world_frame=cfg['world_frame'],
            base_frame=cfg['base_frame'],
        ))

    return nodes


def launch_pipeline(context):
    cfg = _parse_launch_config(context)
    return _build_pipeline_nodes(cfg)


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
        DeclareLaunchArgument(
            'binning_x',
            default_value=os.environ.get('BINNING_X', '0'),
            description='Camera binning_x override; 0 = use camera YAML value',
        ),
        DeclareLaunchArgument(
            'binning_y',
            default_value=os.environ.get('BINNING_Y', '0'),
            description='Camera binning_y override; 0 = use camera YAML value',
        ),
        DeclareLaunchArgument(
            'apriltag_ids',
            default_value=os.environ.get('APRILTAG_IDS', ''),
            description='Comma-separated AprilTag IDs; empty = default 0-11',
        ),
        DeclareLaunchArgument(
            'apriltag_size',
            default_value=os.environ.get('APRILTAG_SIZE', '0.0'),
            description='AprilTag edge size in meters; 0.0 = default 0.05',
        ),
        DeclareLaunchArgument('enable_apriltag', default_value='true',
                              description='Enable AprilTag detection chain'),
        DeclareLaunchArgument('enable_keyence', default_value='true',
                              description='Enable Keyence scanner node'),
        DeclareLaunchArgument(
            'handeye_calibration_file',
            default_value=os.environ.get('HANDEYE_CALIBRATION_FILE', ''),
            description='Path to hand-eye calibration YAML for static TF broadcasting',
        ),
        DeclareLaunchArgument(
            'world_frame',
            default_value=os.environ.get('WORLD_FRAME', ''),
            description='Global world frame ID for the static anchor',
        ),
        DeclareLaunchArgument(
            'base_frame',
            default_value=os.environ.get('BASE_FRAME', ''),
            description='Robot base link frame ID',
        ),
        DeclareLaunchArgument(
            'web_port',
            default_value=os.environ.get('WEB_PORT', '8080'),
            description='Web dashboard HTTP port',
        ),
        DeclareLaunchArgument(
            'enable_web_dashboard',
            default_value='true',
            description='Enable the Web dashboard for this camera pipeline',
        ),
        DeclareLaunchArgument(
            'archive_dir',
            default_value=os.environ.get('ARCHIVE_DIR', ''),
            description='Directory for archived dashboard snapshots',
        ),
        DeclareLaunchArgument(
            'event_log_dir',
            default_value=os.environ.get('EVENT_LOG_DIR', '/var/log/vision'),
            description='Directory for persistent event logs',
        ),
        DeclareLaunchArgument(
            'calibration_dir',
            default_value=os.environ.get('CALIBRATION_DIR', '/tmp/vision_calibration'),
            description='Directory for camera-calibration captures and results',
        ),
        DeclareLaunchArgument(
            'handeye_calibration_dir',
            default_value=os.environ.get('HANDEYE_CALIBRATION_DIR', ''),
            description='Directory for hand-eye captures and results (empty => $calibration_dir/handeye)',
        ),
        DeclareLaunchArgument(
            'params_file',
            default_value='',
            description='Path to a YAML parameter file for pipeline node overrides',
        ),
        OpaqueFunction(function=launch_pipeline),
    ])
