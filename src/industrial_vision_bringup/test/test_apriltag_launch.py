import importlib.util
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).parents[1] / 'launch' / 'apriltag_pose_reader.launch.py'
SPEC = importlib.util.spec_from_file_location('industrial_vision_bringup.apriltag_pose_reader_launch', MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_parse_bool_accepts_case_insensitive_values():
    assert MODULE.parse_bool('TRUE', 'start_detector') is True
    assert MODULE.parse_bool(' false ', 'publish_all_tags') is False


@pytest.mark.parametrize('value', ['yes', '', '1', 'on'])
def test_parse_bool_rejects_ambiguous_values(value):
    with pytest.raises(RuntimeError, match='start_detector'):
        MODULE.parse_bool(value, 'start_detector')


def test_parse_int_accepts_valid_integers():
    assert MODULE.parse_int('5', 'tag_id') == 5
    assert MODULE.parse_int('-1', 'tag_id') == -1


@pytest.mark.parametrize('value', ['abc', '1.5', ''])
def test_parse_int_rejects_invalid_values(value):
    with pytest.raises(RuntimeError, match='tag_id'):
        MODULE.parse_int(value, 'tag_id')


@pytest.mark.parametrize('value', ['nan', '-1', 'bad'])
def test_parse_nonnegative_float_rejects_invalid_values(value):
    with pytest.raises(RuntimeError, match='lookup_rate_hz'):
        MODULE.parse_nonnegative_float(value, 'lookup_rate_hz')


def test_parse_nonnegative_float_accepts_valid_values():
    assert MODULE.parse_nonnegative_float('0.0', 'lookup_rate_hz') == 0.0
    assert MODULE.parse_nonnegative_float('10.5', 'health_log_interval_s') == 10.5
