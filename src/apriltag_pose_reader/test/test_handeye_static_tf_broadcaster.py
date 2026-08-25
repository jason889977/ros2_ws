"""Unit tests for handeye static TF broadcaster."""

import math
from pathlib import Path
import unittest

import cv2
import numpy as np
import pytest
import rclpy
from rclpy.parameter import Parameter

from apriltag_pose_reader.handeye_static_tf_broadcaster import (
    HandEyeStaticTFBroadcaster,
    load_transform_from_yaml,
    rotation_matrix_to_quaternion,
)


class TestHandEyeStaticTF(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        if not rclpy.ok():
            rclpy.init()

    @classmethod
    def tearDownClass(cls):
        if rclpy.ok():
            rclpy.shutdown()

    def test_rotation_matrix_to_quaternion_identity(self):
        R = np.eye(3, dtype=np.float64)
        qx, qy, qz, qw = rotation_matrix_to_quaternion(R)
        self.assertAlmostEqual(qw, 1.0, places=6)
        self.assertAlmostEqual(qx, 0.0, places=6)
        self.assertAlmostEqual(qy, 0.0, places=6)
        self.assertAlmostEqual(qz, 0.0, places=6)

    def test_rotation_matrix_to_quaternion_90deg_z(self):
        R = np.array([
            [0.0, -1.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 0.0, 1.0],
        ], dtype=np.float64)
        qx, qy, qz, qw = rotation_matrix_to_quaternion(R)
        self.assertAlmostEqual(qw, math.cos(math.pi / 4.0), places=5)
        self.assertAlmostEqual(qz, math.sin(math.pi / 4.0), places=5)
        self.assertAlmostEqual(qx, 0.0, places=5)
        self.assertAlmostEqual(qy, 0.0, places=5)

    def test_load_transform_from_yaml(self, tmp_path_factory=None):
        import tempfile
        with tempfile.NamedTemporaryFile(suffix='.yaml', mode='w', delete=False) as f:
            yaml_path = f.name

        try:
            fs = cv2.FileStorage(yaml_path, cv2.FILE_STORAGE_WRITE)
            fs.write('mode', 'eye_in_hand')
            fs.write('gripper_frame', 'tool0')
            fs.write('camera_frame', 'camera_optical_frame')
            g2c = np.eye(4, dtype=np.float64)
            g2c[0, 3] = 0.05
            g2c[1, 3] = -0.02
            g2c[2, 3] = 0.15
            fs.write('gripper_to_camera_matrix', g2c)
            fs.release()

            parent, child, trans, quat = load_transform_from_yaml(yaml_path)
            self.assertEqual(parent, 'tool0')
            self.assertEqual(child, 'camera_optical_frame')
            np.testing.assert_allclose(trans, [0.05, -0.02, 0.15], atol=1e-6)
            self.assertAlmostEqual(quat[3], 1.0, places=5)
        finally:
            Path(yaml_path).unlink(missing_ok=True)

    def test_node_instantiation_with_parameters(self):
        node = HandEyeStaticTFBroadcaster(parameter_overrides=[
            Parameter('parent_frame', Parameter.Type.STRING, 'world'),
            Parameter('child_frame', Parameter.Type.STRING, 'base_link'),
            Parameter('translation', Parameter.Type.DOUBLE_ARRAY, [0.1, 0.2, 0.3]),
            Parameter('rotation_rpy', Parameter.Type.DOUBLE_ARRAY, [0.0, 0.0, 1.5707963]),
        ])
        self.assertIsNotNone(node)
        node.destroy_node()


if __name__ == '__main__':
    unittest.main()
