"""Unit tests for QR node deduplication logic."""

import time
import unittest

import rclpy
from rclpy.node import Node

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


if __name__ == '__main__':
    unittest.main()
