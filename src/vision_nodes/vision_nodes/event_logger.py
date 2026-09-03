"""Structured event logger for industrial vision pipeline.

Writes key events (scan success/failure, camera disconnect/reconnect,
status changes) as JSON Lines to a configurable log file with rotation.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from typing import Any

from diagnostic_msgs.msg import DiagnosticArray
from pylon_ros2_camera_interfaces.msg import VisionStatus
from rclpy.node import Node
from vision_core import run_node
from vision_core import DIAGNOSTIC_LEVEL_NAMES
from std_msgs.msg import String


class EventLogger(Node):

    def __init__(self, parameter_overrides=None) -> None:
        super().__init__(
            'event_logger', parameter_overrides=parameter_overrides or [],
        )

        self.declare_parameter('camera_id', 'my_camera')
        self.declare_parameter('log_dir', '/var/log/vision')
        self.declare_parameter('max_file_size_mb', 50)
        self.declare_parameter('max_file_count', 5)
        self.declare_parameter('diagnostics_topic', '/diagnostics')
        self.declare_parameter('vision_status_topic', '~/status')
        self.declare_parameter('scanner_barcode_topic', '')

        self._camera_id = str(self.get_parameter('camera_id').value)
        self._log_dir = str(self.get_parameter('log_dir').value)
        self._max_file_size = int(
            float(self.get_parameter('max_file_size_mb').value) * 1024 * 1024
        )
        self._max_file_count = int(self.get_parameter('max_file_count').value)

        os.makedirs(self._log_dir, exist_ok=True)
        self._current_path = os.path.join(
            self._log_dir, f'{self._camera_id}_events.jsonl'
        )
        self._file_lock = threading.RLock()
        self._prev_status_level: int | None = None
        self._prev_component_errors: dict[str, int] = {}
        self._events_since_flush = 0
        self._flush_interval = 10

        diag_topic = str(self.get_parameter('diagnostics_topic').value)
        self.create_subscription(
            DiagnosticArray, diag_topic, self._on_diagnostics, 10,
        )

        status_topic = str(self.get_parameter('vision_status_topic').value)
        self.create_subscription(
            VisionStatus, status_topic, self._on_vision_status, 10,
        )

        barcode_topic = str(self.get_parameter('scanner_barcode_topic').value)
        if barcode_topic:
            self.create_subscription(
                String, barcode_topic, self._on_barcode_scan, 10,
            )

        self._file_handle = None

        self.get_logger().info(
            f'Event logger started. camera_id={self._camera_id}, '
            f'log_dir={self._log_dir}'
        )

    def _ensure_file_handle(self) -> None:
        """Lazily open the log file on first write.  Caller must hold ``self._file_lock``."""
        if self._file_handle is None:
            self._file_handle = open(self._current_path, 'a', encoding='utf-8')

    def _write_event(self, event_type: str, data: dict[str, Any]) -> None:
        record = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'camera_id': self._camera_id,
            'event': event_type,
            **data,
        }
        line = json.dumps(record, ensure_ascii=False, default=str) + '\n'
        with self._file_lock:
            try:
                self._ensure_file_handle()
                self._file_handle.write(line)
                self._events_since_flush += 1
                if self._events_since_flush >= self._flush_interval:
                    self._file_handle.flush()
                    self._events_since_flush = 0
                    self._maybe_rotate()
            except OSError as e:
                self.get_logger().warning(f'Failed to write event log: {e}')

    def _maybe_rotate(self) -> None:
        """Check and rotate the log file if it exceeds the size limit.

        Caller must hold ``self._file_lock``.
        """
        try:
            size = os.path.getsize(self._current_path)
        except OSError:
            return
        if size < self._max_file_size:
            return

        try:
            self._file_handle.flush()
            os.fsync(self._file_handle.fileno())
            self._file_handle.close()
            self._file_handle = None

            oldest = f'{self._current_path}.{self._max_file_count}'
            try:
                os.remove(oldest)
            except FileNotFoundError:
                pass
            for index in range(self._max_file_count - 1, 0, -1):
                src = f'{self._current_path}.{index}'
                dst = f'{self._current_path}.{index + 1}'
                try:
                    os.replace(src, dst)
                except FileNotFoundError:
                    pass
            os.replace(self._current_path, f'{self._current_path}.1')
        except OSError as error:
            self.get_logger().warning(f'Failed to rotate event log: {error}')
        finally:
            self._ensure_file_handle()

    def destroy_node(self) -> None:
        with self._file_lock:
            if self._file_handle is not None:
                try:
                    self._file_handle.flush()
                    self._file_handle.close()
                except OSError:
                    pass
        super().destroy_node()

    def _on_diagnostics(self, msg: DiagnosticArray) -> None:
        for status in msg.status:
            prev = self._prev_component_errors.get(status.name)
            current = status.level
            if prev is not None and current != prev:
                self._write_event('component_level_change', {
                    'component': status.name,
                    'from': DIAGNOSTIC_LEVEL_NAMES.get(prev, str(prev)),
                    'to': DIAGNOSTIC_LEVEL_NAMES.get(current, str(current)),
                    'message': status.message,
                })
            self._prev_component_errors[status.name] = current

    def _on_vision_status(self, msg: VisionStatus) -> None:
        if self._prev_status_level is not None and msg.overall_level != self._prev_status_level:
            self._write_event('pipeline_status_change', {
                'from': DIAGNOSTIC_LEVEL_NAMES.get(
                    self._prev_status_level, str(self._prev_status_level)),
                'to': DIAGNOSTIC_LEVEL_NAMES.get(msg.overall_level, str(msg.overall_level)),
                'summary': msg.summary,
                'active_components': msg.active_components,
                'error_components': msg.error_components,
            })
        self._prev_status_level = msg.overall_level

    def _on_barcode_scan(self, msg: String) -> None:
        self._write_event('barcode_scan', {
            'source': 'keyence',
            'data': msg.data,
        })


def main(args=None) -> None:
    run_node(EventLogger, args=args)


if __name__ == '__main__':
    main()