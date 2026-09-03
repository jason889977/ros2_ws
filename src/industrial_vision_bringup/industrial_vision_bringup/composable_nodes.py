"""Factories for composable nodes in the vision pipeline."""

from __future__ import annotations

from typing import Any

from launch_ros.descriptions import ComposableNode

from industrial_vision_bringup.bringup_utils import CameraPipelineConfig


def build_composable_nodes(cfg: CameraPipelineConfig) -> list[ComposableNode]:
    """Build the camera and optional detector components for one pipeline."""
    camera_parameters: dict[str, Any] = {
        'startup_user_set': cfg.startup_user_set,
        'camera_frame': cfg.camera_frame,
        'mtu_size': cfg.mtu_size,
        'enable_status_publisher': True,
        'enable_current_params_publisher': False,
    }
    if cfg.binning_x > 0:
        camera_parameters['binning_x'] = cfg.binning_x
    if cfg.binning_y > 0:
        camera_parameters['binning_y'] = cfg.binning_y

    components = [ComposableNode(
        package='pylon_ros2_camera_component',
        plugin='pylon_ros2_camera::PylonROS2CameraNode',
        name='pylon_ros2_camera_node',
        namespace=cfg.camera_id,
        parameters=[cfg.camera_config, camera_parameters],
        extra_arguments=[{'use_intra_process_comms': True}],
        remappings=[('/diagnostics', cfg.topics.diagnostics)],
    )]

    if cfg.enable_apriltag:
        components.append(ComposableNode(
            package='apriltag_ros',
            plugin='AprilTagNode',
            name='apriltag',
            namespace=cfg.camera_id,
            parameters=[cfg.detector_config, {
                'image_transport': 'raw',
                'qos_profile': 'sensor_data',
                'tag': {
                    'ids': cfg.tag_ids,
                    'frames': cfg.tag_frames,
                    'sizes': [cfg.apriltag_size if cfg.apriltag_size > 0 else 0.05]
                    * len(cfg.tag_ids),
                },
            }],
            remappings=[
                ('image_rect', cfg.topics.image_rect),
                ('camera_info', cfg.topics.camera_info),
                ('/diagnostics', cfg.topics.diagnostics),
            ],
            extra_arguments=[{'use_intra_process_comms': True}],
        ))

    return components
