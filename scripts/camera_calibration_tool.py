#!/usr/bin/env python3
"""Automatic chessboard calibration and online reprojection monitoring."""

import argparse
import os
import time

import cv2
import numpy as np
import yaml
import rclpy
from cv_bridge import CvBridge
from rclpy.node import Node
from sensor_msgs.msg import CameraInfo, Image


class CalibrationNode(Node):
    def __init__(self, args):
        super().__init__('camera_calibration_tool')
        self.args = args
        self.bridge = CvBridge()
        self.latest_image = None
        self.latest_camera_info = None
        self.image_count = 0
        self.create_subscription(Image, args.image_topic, self._on_image, args.queue_size)
        self.create_subscription(CameraInfo, args.camera_info_topic, self._on_camera_info, 10)

    def _on_image(self, msg):
        try:
            self.latest_image = self.bridge.imgmsg_to_cv2(msg, 'mono8')
            self.image_count += 1
        except Exception as exc:
            self.get_logger().error(f'Image conversion failed: {exc}')

    def _on_camera_info(self, msg):
        self.latest_camera_info = msg


def board_points(cols, rows, square_size):
    points = np.zeros((cols * rows, 3), np.float32)
    points[:, :2] = np.mgrid[0:cols, 0:rows].T.reshape(-1, 2)
    return points * square_size


def find_corners(image, pattern_size):
    flags = cv2.CALIB_CB_ADAPTIVE_THRESH + cv2.CALIB_CB_NORMALIZE_IMAGE
    found, corners = cv2.findChessboardCorners(image, pattern_size, flags)
    if not found:
        return None
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)
    return cv2.cornerSubPix(image, corners, (11, 11), (-1, -1), criteria)


def wait_for_image(node, previous_count):
    deadline = time.monotonic() + node.args.timeout_s
    while rclpy.ok() and node.image_count == previous_count:
        rclpy.spin_once(node, timeout_sec=0.1)
        if time.monotonic() >= deadline:
            return None
    return node.latest_image


def write_camera_yaml(path, camera_name, image_size, matrix, distortion, rms):
    width, height = image_size
    identity = np.eye(3)
    projection = np.zeros((3, 4))
    projection[:, :3] = matrix

    def values(array):
        return ', '.join(f'{float(value):.12g}' for value in array.ravel())

    content = f'''%YAML:1.0
image_width: {width}
image_height: {height}
camera_name: {camera_name}
camera_matrix:
  rows: 3
  cols: 3
  data: [{values(matrix)}]
distortion_model: plumb_bob
distortion_coefficients:
  rows: 1
  cols: {distortion.size}
  data: [{values(distortion)}]
rectification_matrix:
  rows: 3
  cols: 3
  data: [{values(identity)}]
projection_matrix:
  rows: 3
  cols: 4
  data: [{values(projection)}]
# calibration_rms: {rms:.8f}
'''
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as stream:
        stream.write(content)


def collect(node):
    pattern = (node.args.board_cols, node.args.board_rows)
    object_template = board_points(*pattern, node.args.square_size_m)
    object_points = []
    image_points = []
    last_center = None
    last_capture = 0.0
    image_size = None
    while len(image_points) < node.args.samples and rclpy.ok():
        previous_count = node.image_count
        image = wait_for_image(node, previous_count)
        if image is None:
            node.get_logger().warning('Timed out waiting for camera image')
            continue
        image_size = (image.shape[1], image.shape[0])
        corners = find_corners(image, pattern)
        if corners is None:
            continue
        center = corners.reshape(-1, 2).mean(axis=0)
        moved = last_center is None or np.linalg.norm(center - last_center) >= node.args.min_motion_px
        cooled = time.monotonic() - last_capture >= node.args.min_interval_s
        if not moved or not cooled:
            continue
        object_points.append(object_template.copy())
        image_points.append(corners)
        last_center = center
        last_capture = time.monotonic()
        node.get_logger().info(f'Collected {len(image_points)}/{node.args.samples} samples')

    if len(image_points) < node.args.min_samples:
        raise RuntimeError(f'Only {len(image_points)} valid samples collected')
    rms, matrix, distortion, _, _ = cv2.calibrateCamera(
        object_points, image_points, image_size, None, None
    )
    write_camera_yaml(node.args.output, node.args.camera_name, image_size, matrix, distortion, rms)
    node.get_logger().info(f'Calibration saved to {node.args.output}; RMS={rms:.6f}')


def load_calibration(path):
    with open(path, encoding='utf-8') as stream:
        content = stream.read()
    if content.startswith('%YAML:1.0'):
        content = content.split('\n', 1)[1]
    data = yaml.safe_load(content)
    camera_matrix = data.get('camera_matrix', {})
    distortion_data = data.get('distortion_coefficients', {})
    matrix = np.asarray(camera_matrix.get('data', []), dtype=np.float64).reshape(
        int(camera_matrix.get('rows', 0)), int(camera_matrix.get('cols', 0))
    )
    distortion = np.asarray(distortion_data.get('data', []), dtype=np.float64)
    if matrix.shape != (3, 3) or distortion.size == 0:
        raise RuntimeError('Calibration file lacks camera_matrix or distortion_coefficients')
    return matrix, distortion


def monitor(node):
    matrix, distortion = load_calibration(node.args.calibration)
    pattern = (node.args.board_cols, node.args.board_rows)
    object_template = board_points(*pattern, node.args.square_size_m)
    errors = []
    while rclpy.ok():
        previous_count = node.image_count
        image = wait_for_image(node, previous_count)
        if image is None:
            node.get_logger().warning('No image received during monitoring')
            continue
        corners = find_corners(image, pattern)
        if corners is None:
            continue
        ok, rvec, tvec = cv2.solvePnP(object_template, corners, matrix, distortion)
        if not ok:
            continue
        projected, _ = cv2.projectPoints(object_template, rvec, tvec, matrix, distortion)
        error = float(np.mean(np.linalg.norm(projected.reshape(-1, 2) - corners.reshape(-1, 2), axis=1)))
        errors.append(error)
        errors = errors[-node.args.window:]
        mean_error = float(np.mean(errors))
        if mean_error > node.args.max_error_px:
            node.get_logger().error(f'Calibration drift warning: {mean_error:.3f}px > {node.args.max_error_px:.3f}px')
        else:
            node.get_logger().info(f'Calibration quality: {mean_error:.3f}px')


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=('collect', 'monitor'))
    parser.add_argument('--image-topic', default='/my_camera/pylon_ros2_camera_node/image_raw')
    parser.add_argument('--camera-info-topic', default='/my_camera/pylon_ros2_camera_node/camera_info')
    parser.add_argument('--board-cols', type=int, default=8)
    parser.add_argument('--board-rows', type=int, default=6)
    parser.add_argument('--square-size-m', type=float, default=0.025)
    parser.add_argument('--queue-size', type=int, default=2)
    parser.add_argument('--timeout-s', type=float, default=5.0)
    parser.add_argument('--samples', type=int, default=25)
    parser.add_argument('--min-samples', type=int, default=12)
    parser.add_argument('--min-motion-px', type=float, default=30.0)
    parser.add_argument('--min-interval-s', type=float, default=0.5)
    parser.add_argument('--camera-name', default='basler_camera')
    parser.add_argument('--output', default='camera_calibration.yaml')
    parser.add_argument('--calibration', default='camera_calibration.yaml')
    parser.add_argument('--window', type=int, default=10)
    parser.add_argument('--max-error-px', type=float, default=1.0)
    return parser.parse_args()


def main():
    args = parse_args()
    rclpy.init()
    node = CalibrationNode(args)
    try:
        collect(node) if args.mode == 'collect' else monitor(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
