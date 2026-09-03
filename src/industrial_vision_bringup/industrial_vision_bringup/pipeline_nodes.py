"""Factories for standalone nodes in the vision pipeline."""

from __future__ import annotations

import os

from industrial_vision_bringup.bringup_utils import ObservabilityConfig, PipelineTopics
from launch.conditions import IfCondition
from launch_ros.actions import Node


def _params_with_optional_file(inline: dict, params_file: str) -> list:
    """Return a parameter list: inline dict plus optional YAML file."""
    result: list = [inline]
    if params_file:
        if not os.path.isfile(params_file):
            raise FileNotFoundError(f'params_file not found: {params_file}')
        result.append(params_file)
    return result


def build_apriltag_pose_reader(
    *,
    camera_id: str,
    camera_frame: str,
    tag_frame_prefix: str,
    respawn: bool,
    enabled: bool,
    topics: PipelineTopics,
) -> Node:
    """Create the conditional AprilTag pose reader node."""
    return Node(
        package='vision_nodes',
        executable='apriltag_pose_reader',
        name='apriltag_pose_reader',
        namespace=camera_id,
        output='screen',
        respawn=respawn,
        respawn_delay=3.0,
        condition=IfCondition(str(enabled).lower()),
        parameters=[{
            'detections_topic': topics.detections,
            'tf_topic': '/tf',
            'lookup_parent_frame': camera_frame,
            'tag_frame_prefix': tag_frame_prefix,
            'publish_all_tags': True,
            'output_pose_topic': topics.apriltag_pose,
            'output_transform_topic': topics.apriltag_transform,
            'publish_detection_logs': False,
        }],
        remappings=[('/diagnostics', topics.diagnostics)],
    )


def build_keyence_scanner(
    *,
    camera_id: str,
    scanner_ip: str,
    scanner_port: int,
    reconnect_interval_s: float,
    respawn: bool,
    enabled: bool,
    topics: PipelineTopics,
) -> Node:
    """Create the conditional Keyence scanner node."""
    return Node(
        package='keyence_sr_wrapper',
        executable='keyence_sr_node',
        name='keyence_sr_node',
        namespace=camera_id,
        output='screen',
        respawn=respawn,
        respawn_delay=3.0,
        condition=IfCondition(str(enabled).lower()),
        parameters=[{
            'scanner_ip': scanner_ip,
            'scanner_port': scanner_port,
            'reconnect_interval_s': reconnect_interval_s,
        }],
        remappings=[
            ('~/barcode', topics.scanner_barcode),
            ('~/trigger', topics.scanner_trigger),
            ('/diagnostics', topics.diagnostics),
        ],
    )


def build_observability_nodes(cfg: ObservabilityConfig) -> list[Node]:
    """Create the status, event logging, and optional dashboard nodes."""
    nodes = [
        Node(
            package='vision_nodes',
            executable='vision_status_aggregator',
            name='vision_status_aggregator',
            namespace=cfg.camera_id,
            output='screen',
            parameters=_params_with_optional_file({
                'camera_id': cfg.camera_id,
                'diagnostics_topic': cfg.topics.diagnostics,
                'output_topic': cfg.topics.vision_status,
                'diagnostic_timeout_s': 5.0,
                'expected_components': cfg.expected_components,
                'scanner_barcode_topic': (
                    cfg.topics.scanner_barcode if cfg.enable_keyence else ''
                ),
            }, cfg.params_file),
        ),
        Node(
            package='vision_nodes',
            executable='event_logger',
            name='event_logger',
            namespace=cfg.camera_id,
            output='screen',
            parameters=_params_with_optional_file({
                'camera_id': cfg.camera_id,
                'diagnostics_topic': cfg.topics.diagnostics,
                'vision_status_topic': cfg.topics.vision_status,
                'scanner_barcode_topic': (
                    cfg.topics.scanner_barcode if cfg.enable_keyence else ''
                ),
                'log_dir': cfg.event_log_dir,
            }, cfg.params_file),
        ),
    ]
    if cfg.enable_web_dashboard:
        nodes.append(Node(
            package='vision_dashboard',
            executable='web_dashboard_bootstrap',
            name='web_dashboard',
            namespace=cfg.camera_id,
            output='screen',
            parameters=_params_with_optional_file({
                'camera_id': cfg.camera_id,
                'web_port': cfg.web_port,
                'archive_dir': cfg.archive_dir,
                'event_log_dir': cfg.event_log_dir,
                'calibration_dir': cfg.calibration_dir,
                'handeye_calibration_dir': cfg.handeye_calibration_dir,
                'handeye_calibration_file': cfg.handeye_calibration_file,
                'camera_config': cfg.camera_config,
            }, cfg.params_file),
        ))
    return nodes


def build_handeye_static_transform(
    *, camera_id: str, camera_frame: str, calibration_file: str,
) -> Node:
    """Create the camera hand-eye static transform broadcaster."""
    return Node(
        package='handeye_calibration',
        executable='handeye_static_tf_broadcaster',
        name='handeye_static_tf_broadcaster',
        namespace=camera_id,
        output='screen',
        parameters=[{
            'calibration_file': calibration_file,
            'child_frame': camera_frame,
        }],
    )


def build_world_base_static_transform(
    *, camera_id: str, world_frame: str, base_frame: str,
) -> Node:
    """Create the world-to-base static transform broadcaster."""
    return Node(
        package='handeye_calibration',
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
    )