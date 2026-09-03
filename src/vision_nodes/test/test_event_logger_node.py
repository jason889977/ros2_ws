import json
from concurrent.futures import ThreadPoolExecutor

import rclpy
from rclpy.parameter import Parameter

from vision_nodes.event_logger import EventLogger


def test_event_logger_writes_json_lines(tmp_path):
    initialized_here = not rclpy.ok()
    if initialized_here:
        rclpy.init()
    node = EventLogger(parameter_overrides=[
        Parameter('camera_id', value='test_cam'),
        Parameter('log_dir', value=str(tmp_path)),
    ])
    try:
        node._write_event('test', {'data': 'payload'})
        node._file_handle.flush()
        record = json.loads((tmp_path / 'test_cam_events.jsonl').read_text().splitlines()[0])
        assert record['event'] == 'test'
        assert record['camera_id'] == 'test_cam'
        assert record['data'] == 'payload'
    finally:
        node.destroy_node()
        if initialized_here and rclpy.ok():
            rclpy.shutdown()


def test_event_logger_serializes_concurrent_writes(tmp_path):
    initialized_here = not rclpy.ok()
    if initialized_here:
        rclpy.init()
    node = EventLogger(parameter_overrides=[
        Parameter('camera_id', value='concurrent_cam'),
        Parameter('log_dir', value=str(tmp_path)),
    ])
    try:
        with ThreadPoolExecutor(max_workers=4) as executor:
            list(executor.map(
                lambda index: node._write_event('test', {'index': index}),
                range(40),
            ))
        node._file_handle.flush()
        records = [
            json.loads(line)
            for line in (tmp_path / 'concurrent_cam_events.jsonl').read_text().splitlines()
        ]
        assert len(records) == 40
        assert {record['index'] for record in records} == set(range(40))
    finally:
        node.destroy_node()
        if initialized_here and rclpy.ok():
            rclpy.shutdown()
