"""ROS 2 Action server for remote AprilGrid camera calibration."""

from __future__ import annotations

import threading
import time
from pathlib import Path

import cv2
import numpy as np
from rclpy.action import ActionServer, CancelResponse, GoalResponse
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.node import Node

from apriltag_pose_reader_interfaces.action import CalibrateCamera
from vision_core import run_node

from .calibrator import AprilGridCalibrator, _CalibrationCancelledError, build_yaml, validate_spec
from .capture import collect_images
from .spec import AprilGridSpec


class AprilGridCalibrationServer(Node):
    """Run camera calibration as a cancellable ROS 2 action."""

    def __init__(self) -> None:
        super().__init__('aprilgrid_calibration_server')
        self._cancelled_goals: set[str] = set()
        self._lock = threading.Lock()
        self._action_server = ActionServer(
            self, CalibrateCamera, 'calibrate_camera',
            execute_callback=self._execute,
            goal_callback=self._on_goal,
            cancel_callback=self._on_cancel,
            callback_group=ReentrantCallbackGroup(),
        )
        self.get_logger().info('AprilGrid calibration action server ready.')

    def _on_goal(self, goal_request) -> GoalResponse:
        if not goal_request.input_dir or not goal_request.output_dir:
            self.get_logger().warning('Rejected goal: input_dir and output_dir are required')
            return GoalResponse.REJECT
        return GoalResponse.ACCEPT

    def _on_cancel(self, goal_handle) -> CancelResponse:
        with self._lock:
            self._cancelled_goals.add(str(goal_handle.goal_id))
        return CancelResponse.ACCEPT

    def _is_cancelled(self, goal_handle) -> bool:
        with self._lock:
            return str(goal_handle.goal_id) in self._cancelled_goals

    def _execute(self, goal_handle):
        with self._lock:
            self._cancelled_goals.discard(str(goal_handle.goal_id))
        request = goal_handle.request
        result = CalibrateCamera.Result()
        feedback = CalibrateCamera.Feedback()
        spec = AprilGridSpec(
            rows=request.rows or 4, cols=request.cols or 3,
            tag_size_m=request.tag_size_m or 0.05,
            tag_spacing_m=request.tag_spacing_m or 0.01,
            tag_family=request.tag_family or 'tag36h11',
        )
        validate_spec(spec)
        max_error = request.max_reprojection_error or 0.0
        output_name = request.output_name or 'camera_calibration.yaml'
        timeout_s = request.timeout_s or 0.0

        try:
            start_time = time.monotonic()
            feedback.phase = 'collecting'
            goal_handle.publish_feedback(feedback)
            collected = collect_images(request.input_dir, request.output_dir, prefix='calib_')
            if not collected:
                return self._abort(goal_handle, result, f'No calibration images found in {request.input_dir}')
            first_image = cv2.imread(collected[0], cv2.IMREAD_COLOR)
            if first_image is None:
                return self._abort(goal_handle, result, f'Cannot read first image: {collected[0]}')
            height, width = first_image.shape[:2]

            feedback.phase = 'detecting'
            goal_handle.publish_feedback(feedback)
            calibrator = AprilGridCalibrator(spec)

            def _progress(images_processed: int, detection_count: int) -> None:
                feedback.images_processed = images_processed
                feedback.last_detection_count = detection_count
                goal_handle.publish_feedback(feedback)

            def _is_cancelled_or_timed_out() -> bool:
                if self._is_cancelled(goal_handle):
                    return True
                if timeout_s > 0.0 and time.monotonic() - start_time > timeout_s:
                    return True
                return False

            try:
                camera_matrix, distortion, ret, images_used = calibrator.calibrate_from_images(
                    collected,
                    image_size=(height, width),
                    progress_callback=_progress,
                    cancel_callback=_is_cancelled_or_timed_out,
                )
            except _CalibrationCancelledError:
                if timeout_s > 0.0 and time.monotonic() - start_time > timeout_s:
                    return self._abort(goal_handle, result, f'Calibration timed out after {timeout_s:.0f}s')
                return self._abort(goal_handle, result, 'Cancelled by client')

            if max_error > 0.0 and ret > max_error:
                return self._abort(goal_handle, result, f'Reprojection error {ret:.4f} px exceeds threshold {max_error:.4f} px')

            output_path = Path(request.output_dir) / output_name
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(build_yaml(camera_matrix, distortion, (width, height)), encoding='utf-8')
            result.success = True
            result.message = f'Calibration complete. Reprojection error: {ret:.4f} px'
            result.camera_matrix = [float(value) for value in camera_matrix.reshape(-1)]
            result.distortion_coefficients = [float(value) for value in distortion.reshape(-1)[:5]]
            result.image_width, result.image_height = width, height
            result.images_used, result.reprojection_error = images_used, float(ret)
            result.output_yaml = str(output_path)
            feedback.phase = 'done'
            goal_handle.publish_feedback(feedback)
            goal_handle.succeed()
            return result
        except (FileNotFoundError, OSError, ValueError, cv2.error, np.linalg.LinAlgError) as exc:
            return self._abort(goal_handle, result, f'Calibration failed: {exc}')

    @staticmethod
    def _abort(goal_handle, result, message: str):
        result.success = False
        result.message = message
        goal_handle.abort()
        return result


def main(args=None):
    run_node(AprilGridCalibrationServer, args=args)


if __name__ == '__main__':
    main()