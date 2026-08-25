import importlib.util
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).parents[1] / 'launch' / 'qrcode_detector.launch.py'
SPEC = importlib.util.spec_from_file_location('qrcode_detector_launch', MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_parse_bool_accepts_case_insensitive_values():
    assert MODULE.parse_bool('TRUE', 'enabled') is True
    assert MODULE.parse_bool(' false ', 'enabled') is False


@pytest.mark.parametrize('value', ['yes', '', '1'])
def test_parse_bool_rejects_ambiguous_values(value):
    with pytest.raises(RuntimeError, match='enabled'):
        MODULE.parse_bool(value, 'enabled')


@pytest.mark.parametrize('value', ['nan', '-1', 'bad'])
def test_parse_nonnegative_float_rejects_invalid_values(value):
    with pytest.raises(RuntimeError, match='interval'):
        MODULE.parse_nonnegative_float(value, 'interval')


@pytest.mark.parametrize('value', ['0', 'nan', '-1', 'bad'])
def test_parse_positive_float_rejects_invalid_values(value):
    with pytest.raises(RuntimeError, match='qr_size_m'):
        MODULE.parse_positive_float(value, 'qr_size_m')


def test_parse_positive_float_accepts_positive_value():
    assert MODULE.parse_positive_float('0.025', 'qr_size_m') == 0.025
