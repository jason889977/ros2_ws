"""Tests for industrial_vision_bringup.bringup_utils validation helpers."""

import pytest
from industrial_vision_bringup.bringup_utils import (
    build_namespaced_topics,
    build_tag_frames,
    parse_scanner_settings,
    validate_pipeline_settings,
)
from vision_core import parse_bool


class TestParseBool:
    def test_true_values(self):
        assert parse_bool('true', 'x') is True
        assert parse_bool('True', 'x') is True
        assert parse_bool('TRUE', 'x') is True

    def test_false_values(self):
        assert parse_bool('false', 'x') is False
        assert parse_bool('False', 'x') is False

    def test_invalid_raises(self):
        with pytest.raises(RuntimeError, match='Invalid x='):
            parse_bool('yes', 'x')
        with pytest.raises(RuntimeError, match='Invalid x='):
            parse_bool('', 'x')


class TestParseScannerSettings:
    def test_valid(self):
        port, interval = parse_scanner_settings('9004', '5.0')
        assert port == 9004
        assert interval == 5.0

    def test_invalid_port_type(self):
        with pytest.raises(RuntimeError, match='scanner_port'):
            parse_scanner_settings('abc', '5.0')

    def test_port_out_of_range(self):
        with pytest.raises(RuntimeError, match='scanner_port'):
            parse_scanner_settings('0', '5.0')
        with pytest.raises(RuntimeError, match='scanner_port'):
            parse_scanner_settings('70000', '5.0')

    def test_invalid_reconnect(self):
        with pytest.raises(RuntimeError, match='reconnect_interval_s'):
            parse_scanner_settings('9004', 'not_a_number')

    def test_negative_reconnect(self):
        with pytest.raises(RuntimeError, match='reconnect_interval_s'):
            parse_scanner_settings('9004', '-1.0')


class TestValidatePipelineSettings:
    def test_valid(self):
        validate_pipeline_settings('cam1', 'cam1_frame', '1500')

    def test_invalid_camera_id(self):
        with pytest.raises(RuntimeError, match='camera_id'):
            validate_pipeline_settings('123bad', 'frame', '1500')
        with pytest.raises(RuntimeError, match='camera_id'):
            validate_pipeline_settings('has-dash', 'frame', '1500')

    def test_empty_camera_frame(self):
        with pytest.raises(RuntimeError, match='camera_frame'):
            validate_pipeline_settings('cam1', '', '1500')

    def test_invalid_mtu(self):
        with pytest.raises(RuntimeError, match='mtu_size'):
            validate_pipeline_settings('cam1', 'frame', '100')
        with pytest.raises(RuntimeError, match='mtu_size'):
            validate_pipeline_settings('cam1', 'frame', '10000')


class TestBuildTagFrames:
    def test_default_count(self):
        frames = build_tag_frames('cam1')
        assert len(frames) == 12
        assert frames[0] == 'cam1/tag36h11:0'
        assert frames[-1] == 'cam1/tag36h11:11'

    def test_custom_count(self):
        frames = build_tag_frames('cam2', 3)
        assert len(frames) == 3
        assert frames[0] == 'cam2/tag36h11:0'


class TestBuildNamespacedTopics:
    def test_all_fields_present(self):
        topics = build_namespaced_topics('my_cam')
        expected_fields = {
            'camera_info', 'image_raw', 'image_rect',
            'apriltag_pose', 'apriltag_transform', 'detections',
            'scanner_barcode', 'scanner_trigger',
            'diagnostics', 'vision_status',
        }
        assert {f.name for f in __import__('dataclasses').fields(topics)} == expected_fields

    def test_namespace_prefix(self):
        topics = build_namespaced_topics('cam1')
        from dataclasses import fields
        for f in fields(topics):
            assert getattr(topics, f.name).startswith('/cam1/')
