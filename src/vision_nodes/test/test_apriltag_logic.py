"""Unit tests for AprilTag pose reader logic."""

import time
import unittest
from unittest.mock import MagicMock, patch

import rclpy
from diagnostic_msgs.msg import DiagnosticStatus
from rclpy.parameter import Parameter

from vision_nodes.apriltag_pose_reader import AprilTagPoseReader, TagFrameTracker


class TestAprilTagNormalization(unittest.TestCase):

    def test_already_prefixed(self):
        self.assertEqual(TagFrameTracker.normalize_family('tag36h11'), 'tag36h11')

    def test_without_prefix(self):
        self.assertEqual(TagFrameTracker.normalize_family('36h11'), 'tag36h11')

    def test_empty_string(self):
        self.assertEqual(TagFrameTracker.normalize_family(''), '')

    def test_whitespace_stripped(self):
        self.assertEqual(TagFrameTracker.normalize_family('  tag25h9  '), 'tag25h9')


class TestAprilTagFrameFromDetection(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        rclpy.init()

    @classmethod
    def tearDownClass(cls):
        rclpy.shutdown()

    def _make_node(self):
        node = AprilTagPoseReader(parameter_overrides=[
            Parameter('tf_topic', value='/test/tf'),
            Parameter('lookup_rate_hz', value=0.0),
            Parameter('health_log_interval_s', value=0.0),
            Parameter('publish_detection_logs', value=False),
            Parameter('subscribe_detections', value=False),
        ])
        node._tf_buffer = MagicMock()
        return node

    def test_frame_from_valid_detection(self):
        node = self._make_node()
        detection = MagicMock()
        detection.family = 'tag36h11'
        detection.id = 5
        self.assertEqual(node._tracker.frame_from_detection(detection), 'tag36h11:5')
        node.destroy_node()

    def test_frame_from_detection_no_prefix(self):
        node = self._make_node()
        detection = MagicMock()
        detection.family = '36h11'
        detection.id = 0
        self.assertEqual(node._tracker.frame_from_detection(detection), 'tag36h11:0')
        node.destroy_node()

    def test_frame_from_detection_negative_id(self):
        node = self._make_node()
        detection = MagicMock()
        detection.family = 'tag36h11'
        detection.id = -1
        self.assertEqual(node._tracker.frame_from_detection(detection), '')
        node.destroy_node()

    def test_candidate_frame_includes_prefix_for_configured_tag(self):
        node = self._make_node()
        node._tracker.tag_frame_prefix = 'cam1'
        node._tracker.tag_family = 'tag36h11'
        node._tracker.tag_id = 5

        self.assertEqual(node._tracker.candidate_frames(), {'cam1/tag36h11:5'})

        node.destroy_node()

    def test_explicit_tag_frame_takes_precedence_over_prefix(self):
        node = self._make_node()
        node._tracker.tag_frame_prefix = 'cam1'
        node._tracker.tag_family = 'tag36h11'
        node._tracker.tag_id = 5
        node._tracker.tag_frame_id = 'manual_tag_frame'

        self.assertEqual(node._tracker.candidate_frames(), {'manual_tag_frame'})

        node.destroy_node()

    def test_candidate_cache_expires_stale_tag(self):
        node = self._make_node()
        node._tracker.known_frames = {'tag36h11:5'}
        node._tracker._last_seen = {'tag36h11:5': 1.0}
        node._tracker._cache = {'tag36h11:5'}
        node._tracker._cache_dirty = False

        with patch(
            'vision_nodes.apriltag_pose_reader.time.monotonic',
            return_value=3.0,
        ):
            node._tracker.expire_stale()
            self.assertEqual(node._tracker.candidate_frames(), set())

        node.destroy_node()

    def test_tf_only_mode_discovers_tag_frame(self):
        node = self._make_node()
        transform = MagicMock()
        transform.child_frame_id = 'tag36h11:3'
        node._publish_transform = MagicMock()
        message = MagicMock()
        message.transforms = [transform]

        node._on_tf_message(message)

        self.assertEqual(node._tracker.known_frames, {'tag36h11:3'})
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

        self.assertEqual(node._tracker.known_frames, set())
        node._publish_transform.assert_not_called()
        node.destroy_node()


class TestIsAutoTagFrame(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        rclpy.init()

    @classmethod
    def tearDownClass(cls):
        rclpy.shutdown()

    def _make_node(self):
        node = AprilTagPoseReader(parameter_overrides=[
            Parameter('tf_topic', value='/test/tf'),
            Parameter('lookup_rate_hz', value=0.0),
            Parameter('health_log_interval_s', value=0.0),
            Parameter('publish_detection_logs', value=False),
            Parameter('subscribe_detections', value=False),
        ])
        node._tf_buffer = MagicMock()
        return node

    def test_valid_tag_frame(self):
        node = self._make_node()
        self.assertTrue(node._tracker.is_auto_tag_frame('tag36h11:0'))
        node.destroy_node()

    def test_valid_tag_frame_with_prefix(self):
        node = self._make_node()
        node._tracker.tag_frame_prefix = 'cam1'
        self.assertTrue(node._tracker.is_auto_tag_frame('cam1/tag36h11:5'))
        node.destroy_node()

    def test_wrong_prefix_rejected(self):
        node = self._make_node()
        node._tracker.tag_frame_prefix = 'cam1'
        self.assertFalse(node._tracker.is_auto_tag_frame('cam2/tag36h11:5'))
        node.destroy_node()

    def test_non_tag_frame_rejected(self):
        node = self._make_node()
        self.assertFalse(node._tracker.is_auto_tag_frame('tool0'))
        node.destroy_node()

    def test_family_filter(self):
        node = self._make_node()
        node._tracker.tag_family = 'tag25h9'
        self.assertFalse(node._tracker.is_auto_tag_frame('tag36h11:0'))
        self.assertTrue(node._tracker.is_auto_tag_frame('tag25h9:0'))
        node.destroy_node()

    def test_id_filter(self):
        node = self._make_node()
        node._tracker.tag_id = 3
        self.assertTrue(node._tracker.is_auto_tag_frame('tag36h11:3'))
        self.assertFalse(node._tracker.is_auto_tag_frame('tag36h11:5'))
        node.destroy_node()

    def test_leading_slash_stripped(self):
        node = self._make_node()
        self.assertTrue(node._tracker.is_auto_tag_frame('/tag36h11:0'))
        node.destroy_node()


class TestCandidateFramesPriority(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        rclpy.init()

    @classmethod
    def tearDownClass(cls):
        rclpy.shutdown()

    def _make_node(self):
        node = AprilTagPoseReader(parameter_overrides=[
            Parameter('tf_topic', value='/test/tf'),
            Parameter('lookup_rate_hz', value=0.0),
            Parameter('health_log_interval_s', value=0.0),
            Parameter('publish_detection_logs', value=False),
            Parameter('subscribe_detections', value=False),
        ])
        node._tf_buffer = MagicMock()
        return node

    def test_publish_all_returns_all_known(self):
        node = self._make_node()
        node._tracker.publish_all_tags = True
        node._tracker.known_frames = {'tag36h11:0', 'tag36h11:1'}
        result = node._tracker.candidate_frames()
        self.assertEqual(result, {'tag36h11:0', 'tag36h11:1'})
        node.destroy_node()

    def test_latest_frame_hint_when_not_publish_all(self):
        node = self._make_node()
        node._tracker.known_frames = {'tag36h11:0', 'tag36h11:1'}
        node._tracker.latest_hint = 'tag36h11:1'
        result = node._tracker.candidate_frames()
        self.assertEqual(result, {'tag36h11:1'})
        node.destroy_node()

    def test_empty_when_no_hints(self):
        node = self._make_node()
        node._tracker.known_frames = set()
        node._tracker.latest_hint = None
        result = node._tracker.candidate_frames()
        self.assertEqual(result, set())
        node.destroy_node()

    def test_diag_reports_ok_in_tf_only_mode_with_recent_transforms(self):
        """TF-only mode (no detections subscription) must not warn forever."""
        node = self._make_node()
        node._transforms_published = 5
        node._last_transform_mono = time.monotonic()
        stat = MagicMock()
        node._diag_status(stat)
        stat.summary.assert_called_once_with(
            DiagnosticStatus.OK, 'Tracking tags')
        node.destroy_node()

    def test_diag_warns_when_transforms_stale(self):
        node = self._make_node()
        node._transforms_published = 5
        node._last_transform_mono = time.monotonic() - 3600.0
        stat = MagicMock()
        node._diag_status(stat)
        stat.summary.assert_called_once_with(
            DiagnosticStatus.WARN, 'No recent tag transforms')
        node.destroy_node()

    def test_diag_warns_when_never_published(self):
        node = self._make_node()
        stat = MagicMock()
        node._diag_status(stat)
        stat.summary.assert_called_once_with(
            DiagnosticStatus.WARN, 'No detections yet')
        node.destroy_node()

    def test_lookup_warnings_are_throttled(self):
        node = self._make_node()
        node._tracker.known_frames = set()
        with patch.object(node, 'get_logger') as logger:
            node.lookup_and_publish_latest()
            node.lookup_and_publish_latest()
            node.lookup_and_publish_latest()
            self.assertEqual(logger.return_value.warning.call_count, 1)
        node.destroy_node()

    def test_family_plus_id_composes_frame(self):
        node = self._make_node()
        node._tracker.tag_family = 'tag36h11'
        node._tracker.tag_id = 7
        result = node._tracker.candidate_frames()
        self.assertEqual(result, {'tag36h11:7'})
        node.destroy_node()


if __name__ == '__main__':
    unittest.main()
