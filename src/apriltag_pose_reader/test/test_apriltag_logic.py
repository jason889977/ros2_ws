"""Unit tests for AprilTag pose reader logic."""

import unittest
from unittest.mock import MagicMock, patch

import rclpy

from apriltag_pose_reader.apriltag_pose_reader_node import AprilTagPoseReader


class TestAprilTagNormalization(unittest.TestCase):

    def test_already_prefixed(self):
        self.assertEqual(
            AprilTagPoseReader._normalize_tag_family('tag36h11'), 'tag36h11',
        )

    def test_without_prefix(self):
        self.assertEqual(
            AprilTagPoseReader._normalize_tag_family('36h11'), 'tag36h11',
        )

    def test_empty_string(self):
        self.assertEqual(
            AprilTagPoseReader._normalize_tag_family(''), '',
        )

    def test_whitespace_stripped(self):
        self.assertEqual(
            AprilTagPoseReader._normalize_tag_family('  tag25h9  '), 'tag25h9',
        )


class TestAprilTagFrameFromDetection(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        rclpy.init()

    @classmethod
    def tearDownClass(cls):
        rclpy.shutdown()

    def _make_node(self):
        node = AprilTagPoseReader.__new__(AprilTagPoseReader)
        from rclpy.node import Node
        Node.__init__(node, '_test_apriltag')
        node._tag_frame_id = ''
        node._tag_family = ''
        node._tag_id = -1
        node._publish_all_tags = False
        node._tag_timeout_s = 1.0
        node._known_tag_frames = set()
        node._tag_last_seen = {}
        node._latest_frame_hint = None
        node._candidate_cache = None
        node._candidate_cache_dirty = True
        node._lookup_parent_frame = ''
        node._tag_frame_prefix = ''
        node._tf_buffer = MagicMock()
        return node

    def test_frame_from_valid_detection(self):
        node = self._make_node()
        detection = MagicMock()
        detection.family = 'tag36h11'
        detection.id = 5
        self.assertEqual(node._frame_from_detection(detection), 'tag36h11:5')
        node.destroy_node()

    def test_frame_from_detection_no_prefix(self):
        node = self._make_node()
        detection = MagicMock()
        detection.family = '36h11'
        detection.id = 0
        self.assertEqual(node._frame_from_detection(detection), 'tag36h11:0')
        node.destroy_node()

    def test_frame_from_detection_negative_id(self):
        node = self._make_node()
        detection = MagicMock()
        detection.family = 'tag36h11'
        detection.id = -1
        self.assertEqual(node._frame_from_detection(detection), '')
        node.destroy_node()

    def test_candidate_cache_expires_stale_tag(self):
        node = self._make_node()
        node._known_tag_frames = {'tag36h11:5'}
        node._tag_last_seen = {'tag36h11:5': 1.0}
        node._candidate_cache = {'tag36h11:5'}
        node._candidate_cache_dirty = False

        with patch(
            'apriltag_pose_reader.apriltag_pose_reader_node.time.monotonic',
            return_value=3.0,
        ):
            self.assertEqual(node._candidate_frames(), set())

        node.destroy_node()

    def test_tf_only_mode_discovers_tag_frame(self):
        node = self._make_node()
        transform = MagicMock()
        transform.child_frame_id = 'tag36h11:3'
        node._publish_transform = MagicMock()
        message = MagicMock()
        message.transforms = [transform]

        node._on_tf_message(message)

        self.assertEqual(node._known_tag_frames, {'tag36h11:3'})
        node._publish_transform.assert_called_once_with(transform)
        node.destroy_node()

    def test_tf_only_mode_ignores_non_tag_frame(self):
        node = self._make_node()
        transform = MagicMock()
        transform.child_frame_id = 'tool0'
        node._publish_transform = MagicMock()
        message = MagicMock()
        message.transforms = [transform]

        node._on_tf_message(message)

        self.assertEqual(node._known_tag_frames, set())
        node._publish_transform.assert_not_called()
        node.destroy_node()


if __name__ == '__main__':
    unittest.main()
