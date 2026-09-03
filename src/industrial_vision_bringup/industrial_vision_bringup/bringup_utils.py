"""Validation and parsing helpers shared by vision launch files."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from vision_core.launch_helpers import parse_nonnegative_float, validate_ros_identifier


def parse_scanner_settings(scanner_port_value, reconnect_interval_value):
    """Parse and validate scanner connection settings from launch arguments."""
    try:
        scanner_port = int(scanner_port_value)
    except (TypeError, ValueError) as error:
        raise RuntimeError(
            f'Invalid scanner_port={scanner_port_value!r}; expected an integer from 1 to 65535.'
        ) from error
    if not 1 <= scanner_port <= 65535:
        raise RuntimeError(
            f'Invalid scanner_port={scanner_port_value!r}; expected an integer from 1 to 65535.'
        )

    try:
        reconnect_interval_s = parse_nonnegative_float(
            reconnect_interval_value, 'reconnect_interval_s'
        )
    except RuntimeError:
        raise RuntimeError(
            f'Invalid reconnect_interval_s={reconnect_interval_value!r}; expected a finite value >= 0.'
        )
    return scanner_port, reconnect_interval_s


def validate_pipeline_settings(camera_id, camera_frame, mtu_size):
    """Validate launch values before creating any ROS actions."""
    try:
        validate_ros_identifier(camera_id, 'camera_id')
    except ValueError as exc:
        raise RuntimeError(str(exc)) from exc
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


def build_tag_frames(camera_id, tag_count=12):
    """Return unique AprilTag child frames for one camera pipeline."""
    return [f'{camera_id}/tag36h11:{tag_id}' for tag_id in range(tag_count)]


@dataclass(frozen=True)
class PipelineTopics:
    """Topic names for a single camera pipeline."""
    camera_info: str
    image_raw: str
    image_rect: str
    apriltag_pose: str
    apriltag_transform: str
    detections: str
    scanner_barcode: str
    scanner_trigger: str
    diagnostics: str
    vision_status: str


def build_namespaced_topics(camera_id) -> PipelineTopics:
    """Build the topic names shared by one camera pipeline."""
    prefix = f'/{camera_id}'
    return PipelineTopics(
        camera_info=f'{prefix}/pylon_ros2_camera_node/camera_info',
        image_raw=f'{prefix}/pylon_ros2_camera_node/image_raw',
        image_rect=f'{prefix}/pylon_ros2_camera_node/image_rect',
        apriltag_pose=f'{prefix}/apriltag/pose',
        apriltag_transform=f'{prefix}/apriltag/transform',
        detections=f'{prefix}/detections',
        scanner_barcode=f'{prefix}/scanner/barcode',
        scanner_trigger=f'{prefix}/scanner/trigger',
        diagnostics=f'{prefix}/diagnostics',
        vision_status=f'{prefix}/vision/status',
    )


@dataclass(frozen=True)
class CameraPipelineConfig:
    """All settings needed to build composable camera + detector nodes."""

    camera_id: str
    camera_config: str
    camera_frame: str
    startup_user_set: str
    mtu_size: int
    binning_x: int
    binning_y: int
    enable_apriltag: bool
    detector_config: str
    tag_ids: list[int]
    tag_frames: list[str]
    apriltag_size: float
    topics: PipelineTopics


@dataclass(frozen=True)
class ObservabilityConfig:
    """Settings for the status aggregator, event logger, and dashboard nodes."""

    camera_id: str
    expected_components: list[str]
    enable_keyence: bool
    enable_web_dashboard: bool
    web_port: int
    archive_dir: str
    event_log_dir: str
    calibration_dir: str
    handeye_calibration_dir: str
    handeye_calibration_file: str
    camera_config: str
    topics: PipelineTopics
    params_file: str = ''
