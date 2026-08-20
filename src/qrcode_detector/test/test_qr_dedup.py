"""Unit tests for QR node deduplication logic."""

import time
import unittest
from unittest.mock import patch

import numpy as np

from qrcode_detector.qrcode_node import WeChatQRNode


class _DedupTestNode:
    """Minimal object exposing only _should_publish for testing."""

    def __init__(self, window_s):
        self._deduplicate_window_s = window_s
        self._last_published_at = {}

    _should_publish = WeChatQRNode._should_publish


class TestQRDeduplication(unittest.TestCase):

    def test_first_call_always_publishes(self):
        node = _DedupTestNode(0.5)
        self.assertTrue(node._should_publish('ABC123'))

    def test_duplicate_within_window_suppressed(self):
        node = _DedupTestNode(1.0)
        node._should_publish('ABC123')
        self.assertFalse(node._should_publish('ABC123'))

    def test_different_content_not_suppressed(self):
        node = _DedupTestNode(1.0)
        node._should_publish('ABC')
        self.assertTrue(node._should_publish('XYZ'))

    def test_zero_window_always_publishes(self):
        node = _DedupTestNode(0.0)
        node._should_publish('ABC123')
        self.assertTrue(node._should_publish('ABC123'))

    def test_after_window_expires_publishes_again(self):
        node = _DedupTestNode(0.1)
        node._should_publish('ABC123')
        time.sleep(0.15)
        self.assertTrue(node._should_publish('ABC123'))

    def test_suppressed_duplicates_do_not_extend_window(self):
        node = _DedupTestNode(0.5)
        with patch(
            'qrcode_detector.qrcode_node.time.monotonic',
            side_effect=[0.0, 0.2, 0.4, 0.6],
        ):
            self.assertTrue(node._should_publish('ABC123'))
            self.assertFalse(node._should_publish('ABC123'))
            self.assertFalse(node._should_publish('ABC123'))
            self.assertTrue(node._should_publish('ABC123'))


class TestQRCorners(unittest.TestCase):

    def test_normalizes_single_code_corner_dimension(self):
        points = np.zeros((1, 4, 2), dtype=np.float32)
        corners = WeChatQRNode._normalize_corners(points)
        self.assertEqual(corners.shape, (4, 2))
        self.assertEqual(corners.dtype, np.float64)

    def test_rejects_invalid_or_non_finite_corners(self):
        self.assertIsNone(WeChatQRNode._normalize_corners(np.zeros((3, 2))))
        self.assertIsNone(
            WeChatQRNode._normalize_corners(
                np.array([[0.0, 0.0], [np.nan, 0.0], [0.0, 0.0], [0.0, 0.0]])
            )
        )


if __name__ == '__main__':
    unittest.main()
