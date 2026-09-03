import json
from unittest.mock import patch

import pytest
import rclpy
from rclpy.parameter import Parameter

from vision_nodes.event_logger import EventLogger


@pytest.fixture(scope='module', autouse=True)
def ros_context():
    initialized_here = not rclpy.ok()
    if initialized_here:
        rclpy.init()
    yield
    if initialized_here and rclpy.ok():
        rclpy.shutdown()


@pytest.fixture
def logger(tmp_path):
    node = EventLogger(parameter_overrides=[
        Parameter('camera_id', value='test_cam'),
        Parameter('log_dir', value=str(tmp_path)),
        Parameter('max_file_size_mb', value=1),
        Parameter('max_file_count', value=3),
    ])
    yield node
    node.destroy_node()


def test_event_logger_persists_json_line(logger, tmp_path):
    logger._write_event('test', {'data': 'payload'})
    logger._file_handle.flush()

    records = [
        json.loads(line)
        for line in (tmp_path / 'test_cam_events.jsonl').read_text().splitlines()
    ]
    assert records[0]['event'] == 'test'
    assert records[0]['camera_id'] == 'test_cam'
    assert records[0]['data'] == 'payload'


def test_event_logger_rotates_large_files(logger, tmp_path):
    for _ in range(6000):
        logger._write_event('test', {'data': 'x' * 200})

    rotated = tmp_path / 'test_cam_events.jsonl.1'
    assert rotated.exists()
    assert rotated.stat().st_size > 0


def test_event_logger_recovers_when_rotation_rename_fails(logger, tmp_path):
    logger._max_file_size = 1
    logger._write_event('before_failure', {'data': 'payload'})
    logger._file_handle.flush()

    with patch('vision_nodes.event_logger.os.replace', side_effect=OSError('rename failed')):
        logger._maybe_rotate()

    logger._max_file_size = 1024 * 1024
    logger._write_event('after_failure', {'data': 'payload'})
    logger._file_handle.flush()

    records = [
        json.loads(line)
        for line in (tmp_path / 'test_cam_events.jsonl').read_text().splitlines()
    ]
    assert [record['event'] for record in records] == [
        'before_failure', 'after_failure',
    ]