"""ROS 2 node for web dashboard data collection.

Subscribes to vision status, diagnostics, camera images, and scan
results.  Provides thread-safe accessors used by the FastAPI routes
defined in ``dashboard_routes.py``.  This module has **no** dependency
on FastAPI or any web framework.
"""

from __future__ import annotations

import asyncio
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import cv2
from cv_bridge import CvBridge, CvBridgeError
from vision_core import (
    DiagnosticsSubscriber,
    diagnostic_level_name,
    dict_from_diagnostic_status,
    transform_message_to_matrix,
)
from vision_core.websocket import WebSocketManager
from diagnostic_msgs.msg import DiagnosticStatus
from diagnostic_updater import DiagnosticStatusWrapper, Updater
from pylon_ros2_camera_interfaces.msg import VisionStatus
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import Image
from std_msgs.msg import String
from std_srvs.srv import Trigger

try:
    from apriltag_pose_reader_interfaces.action import CalibrateCamera
    from apriltag_pose_reader_interfaces.srv import ReloadCalibration
    from rclpy.action import ActionClient
    _CALIBRATION_ACTION_AVAILABLE = True
except (ImportError, OSError):
    _CALIBRATION_ACTION_AVAILABLE = False
    ReloadCalibration = None

try:
    from geometry_msgs.msg import TransformStamped
except (ImportError, OSError):
    TransformStamped = None

try:
    from pylon_ros2_camera_interfaces.srv import (
        SetBinning,
        SetBrightness,
        SetExposure,
        SetGain,
        SetGamma,
    )
    _PYLON_SRV_AVAILABLE = True
except (ImportError, OSError):
    _PYLON_SRV_AVAILABLE = False


class WebDashboard(Node):
    """ROS 2 node that collects dashboard data from the vision pipeline."""

    def __init__(self, parameter_overrides=None) -> None:
        super().__init__(
            'web_dashboard', parameter_overrides=parameter_overrides or [],
        )

        self._diag_subscriber = DiagnosticsSubscriber()

        self.declare_parameter('camera_id', 'my_camera')
        self.declare_parameter('web_port', 8080)
        self.declare_parameter('archive_dir', '')
        self.declare_parameter('event_log_dir', '/var/log/vision')
        self.declare_parameter('calibration_dir', '/tmp/vision_calibration')
        self.declare_parameter('camera_config', '')
        self.declare_parameter('handeye_calibration_dir', '')
        self.declare_parameter('handeye_calibration_file', '')

        self._camera_id = str(self.get_parameter('camera_id').value)
        self._web_port = int(self.get_parameter('web_port').value)
        self._archive_dir = str(self.get_parameter('archive_dir').value)
        self._event_log_dir = str(self.get_parameter('event_log_dir').value)
        self._calibration_dir = str(self.get_parameter('calibration_dir').value)
        self._camera_config = str(self.get_parameter('camera_config').value)
        handeye_dir_param = str(self.get_parameter('handeye_calibration_dir').value)
        self._handeye_calibration_dir = (
            handeye_dir_param
            if handeye_dir_param
            else str(Path(self._calibration_dir) / 'handeye')
        )
        self._handeye_calibration_file = str(
            self.get_parameter('handeye_calibration_file').value
        )

        self._lock = threading.Lock()
        self._bridge = CvBridge()
        self._executor = ThreadPoolExecutor(max_workers=1)
        self._encoding_in_flight = False
        self._image_request_mono = 0.0

        self._status: dict[str, Any] = {}
        self._latest_jpeg: bytes | None = None
        self._latest_calibration_jpeg: bytes | None = None
        self._scan_history: deque[dict[str, Any]] = deque(maxlen=200)
        self._websocket_manager = WebSocketManager()
        self._image_failures_total = 0
        self._image_consecutive_failures = 0
        self._latest_tag: dict[str, Any] | None = None
        self._diag_updater = Updater(self)
        self._diag_updater.setHardwareID('web_dashboard')
        self._diag_updater.add('Image Conversion', self._image_conversion_diagnostic)

        image_qos = QoSProfile(depth=1)
        image_qos.reliability = ReliabilityPolicy.BEST_EFFORT

        ns = f'/{self._camera_id}'

        self.create_subscription(
            VisionStatus, f'{ns}/vision/status', self._on_status, 10)
        self._diag_subscriber.setup_diagnostics_subscription(self, f'{ns}/diagnostics')
        self.create_subscription(
            Image, f'{ns}/pylon_ros2_camera_node/image_raw',
            self._on_image, image_qos)
        self.create_subscription(
            String, f'{ns}/scanner/barcode', self._on_barcode_scan, 10)
        if TransformStamped is not None:
            self.create_subscription(
                TransformStamped, f'{ns}/apriltag/transform',
                self._on_tag_transform, 10)

        self.trigger_client = self.create_client(
            Trigger, f'{ns}/scanner/trigger')
        self.calibration_action_client = None
        self.handeye_reload_client = None
        if _CALIBRATION_ACTION_AVAILABLE:
            self.calibration_action_client = ActionClient(
                self, CalibrateCamera, '/calibrate_camera')
            if ReloadCalibration is not None:
                self.handeye_reload_client = self.create_client(
                    ReloadCalibration,
                    f'{ns}/handeye_static_tf_broadcaster/reload_calibration',
                )

        self.exposure_client = None
        self.gain_client = None
        self.gamma_client = None
        self.brightness_client = None
        self.binning_client = None
        if _PYLON_SRV_AVAILABLE:
            self.exposure_client = self.create_client(
                SetExposure, f'{ns}/pylon_ros2_camera_node/set_exposure')
            self.gain_client = self.create_client(
                SetGain, f'{ns}/pylon_ros2_camera_node/set_gain')
            self.gamma_client = self.create_client(
                SetGamma, f'{ns}/pylon_ros2_camera_node/set_gamma')
            self.brightness_client = self.create_client(
                SetBrightness, f'{ns}/pylon_ros2_camera_node/set_brightness')
            self.binning_client = self.create_client(
                SetBinning, f'{ns}/pylon_ros2_camera_node/set_binning')

        self.get_logger().info(
            f'Web dashboard starting on port {self._web_port} '
            f'(camera_id={self._camera_id})')

    # -- state accessors (thread-safe) ----------------------------------

    @property
    def camera_id(self) -> str:
        return self._camera_id

    @property
    def event_log_dir(self) -> str:
        return self._event_log_dir

    @property
    def archive_dir(self) -> str:
        return self._archive_dir

    @property
    def web_port(self) -> int:
        return self._web_port

    @property
    def calibration_dir(self) -> str:
        return self._calibration_dir

    @property
    def camera_config(self) -> str:
        return self._camera_config

    @property
    def handeye_calibration_dir(self) -> str:
        return self._handeye_calibration_dir

    @property
    def handeye_calibration_file(self) -> str:
        return self._handeye_calibration_file

    def get_latest_tag_transform(self) -> dict[str, Any] | None:
        """Return the latest AprilTag transform as a serializable dict.

        Returns None if no transform has been received yet, or if the last
        transform is older than 2 seconds (considered stale).
        """
        with self._lock:
            if self._latest_tag is None:
                return None
            age = time.monotonic() - self._latest_tag['received_mono']
            if age > 2.0:
                return None
            return dict(self._latest_tag)

    @staticmethod
    def _status_to_dict(msg: VisionStatus) -> dict[str, Any]:
        return {
            'camera_id': msg.camera_id,
            'overall_level': msg.overall_level,
            'overall_level_name': diagnostic_level_name(msg.overall_level),
            'summary': msg.summary,
            'active_components': msg.active_components,
            'warning_components': msg.warning_components,
            'error_components': msg.error_components,
            'components': list(zip(msg.component_names, msg.component_messages)),
            'metrics': dict(zip(msg.metric_names, msg.metric_values)),
            'scan_count_total': msg.scan_count_total,
            'keyence_scan_count': msg.keyence_scan_count,
            'scan_rate_per_minute': msg.scan_rate_per_minute,
            'miss_scan_duration_s': msg.miss_scan_duration_s,
            'timestamp': time.time(),
        }

    def get_status(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._status)

    def get_aggregate(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            cameras: dict[str, dict[str, Any]] = {}
            if self._status:
                cameras[self._camera_id] = dict(self._status)
            return cameras

    def get_diagnostics(self) -> dict[str, Any]:
        fresh = self._diag_subscriber.get_fresh_diagnostics()
        statuses = [dict_from_diagnostic_status(msg) for msg, _ in fresh.values()]
        newest = max((t for _, t in fresh.values()), default=None)
        # Age relative to the monotonic clock keeps this JSON-friendly and
        # lets the UI show how stale the diagnostics are.
        header_age_s = time.monotonic() - newest if newest is not None else None
        return {'header_age_s': header_age_s, 'statuses': statuses}

    def get_scans(self, limit: int) -> list[dict[str, Any]]:
        limit = max(1, int(limit))
        with self._lock:
            return list(self._scan_history)[-limit:]

    def get_latest_image(self) -> bytes | None:
        with self._lock:
            return self._latest_jpeg

    def get_latest_calibration_image(self) -> bytes | None:
        """Return the latest full-resolution image for intrinsic calibration."""
        with self._lock:
            return self._latest_calibration_jpeg

    def mark_image_request(self) -> None:
        """Record that a web consumer wants fresh frames.

        While no consumer has requested an image recently, incoming camera
        frames skip JPEG encoding to save CPU on the host.
        """
        self._image_request_mono = time.monotonic()

    # -- websocket helpers ------------------------------------------------

    def register_websocket(self, ws, loop: asyncio.AbstractEventLoop) -> None:
        self._websocket_manager.register(ws, loop)

    def unregister_websocket(self, ws) -> None:
        self._websocket_manager.unregister(ws)

    def _broadcast_ws(self, message: dict) -> None:
        self._websocket_manager.broadcast(message)

    # -- subscription callbacks -------------------------------------------

    def _on_status(self, msg: VisionStatus) -> None:
        data = self._status_to_dict(msg)
        with self._lock:
            self._status = data
        self._broadcast_ws({'v': 1, 'type': 'status', 'data': data})

    def _on_image(self, msg: Image) -> None:
        if self._encoding_in_flight:
            return
        # Skip encoding while nobody is consuming the stream/snapshot API.
        if time.monotonic() - self._image_request_mono > 10.0:
            return
        self._encoding_in_flight = True
        self._executor.submit(self._encode_image, msg)

    def _encode_image(self, msg: Image) -> None:
        try:
            cv_img = self._bridge.imgmsg_to_cv2(msg, 'bgr8')
            h, w = cv_img.shape[:2]
            scale = 320.0 / max(w, h)
            small = cv2.resize(cv_img, (int(w * scale), int(h * scale)))
            _, jpeg = cv2.imencode('.jpg', small, [cv2.IMWRITE_JPEG_QUALITY, 60])
            _, calibration_jpeg = cv2.imencode(
                '.jpg', cv_img, [cv2.IMWRITE_JPEG_QUALITY, 90])
            with self._lock:
                self._latest_jpeg = jpeg.tobytes()
                self._latest_calibration_jpeg = calibration_jpeg.tobytes()
                self._image_consecutive_failures = 0
        except (CvBridgeError, ValueError, TypeError, cv2.error) as error:
            with self._lock:
                self._image_failures_total += 1
                self._image_consecutive_failures = min(
                    self._image_consecutive_failures + 1, 9999)
            self.get_logger().debug(f'Image conversion failed: {error}')
        finally:
            self._encoding_in_flight = False

    def _image_conversion_diagnostic(
        self, status: DiagnosticStatusWrapper,
    ) -> DiagnosticStatusWrapper:
        with self._lock:
            consecutive = self._image_consecutive_failures
            total = self._image_failures_total
        if consecutive >= 5:
            status.summary(
                DiagnosticStatus.WARN,
                f'Image conversion failing ({consecutive} consecutive)',
            )
        elif consecutive > 0:
            status.summary(
                DiagnosticStatus.OK,
                f'Recovering ({consecutive} consecutive, {total} total)',
            )
        elif total > 0:
            status.summary(
                DiagnosticStatus.OK,
                f'Healthy ({total} past failures)',
            )
        else:
            status.summary(DiagnosticStatus.OK, 'Image conversion healthy')
        status.add('total_failures', str(total))
        status.add('consecutive_failures', str(consecutive))
        return status

    def _on_tag_transform(self, message) -> None:
        """Store the latest AprilTag TransformStamped for hand-eye capture.

        Convert to 4x4 homogeneous matrix and child_frame_id so the API
        layer can operate on plain numpy arrays without ROS dependencies.
        """
        try:
            matrix = transform_message_to_matrix(message)
        except ValueError as exc:
            self.get_logger().warning(f'Ignoring invalid tag transform: {exc}')
            return
        tag_info = {
            'received_mono': time.monotonic(),
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'child_frame_id': message.child_frame_id,
            'header_frame_id': message.header.frame_id,
            'matrix_4x4': [[float(v) for v in row] for row in matrix.tolist()],
            'rotation_3x3': [[float(v) for v in row] for row in matrix[:3, :3].tolist()],
            'translation_xyz_m': [
                float(matrix[0, 3]), float(matrix[1, 3]), float(matrix[2, 3]),
            ],
        }
        with self._lock:
            self._latest_tag = tag_info

    def _on_barcode_scan(self, msg: String) -> None:
        self._append_scan('keyence', msg.data)

    def _append_scan(self, source: str, data: str) -> None:
        entry = {
            'source': source,
            'data': data,
            'timestamp': datetime.now(timezone.utc).isoformat(),
        }
        with self._lock:
            self._scan_history.append(entry)
        self._broadcast_ws({'v': 1, 'type': 'scan', 'data': entry})

    def destroy_node(self) -> None:
        """Clean up resources before node shutdown."""
        self._executor.shutdown(wait=False)
        self._diag_subscriber.teardown()
        super().destroy_node()