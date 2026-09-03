"""Tests for diagnostic helpers (canonical: vision_core.diagnostics)."""

from diagnostic_msgs.msg import DiagnosticStatus, KeyValue

from vision_core import (
    DIAGNOSTIC_LEVEL_NAMES,
    diagnostic_level_name,
    dict_from_diagnostic_status,
    safe_diagnostic_level,
)


class TestDiagnosticLevelName:
    def test_known_levels(self):
        assert diagnostic_level_name(0) == 'OK'
        assert diagnostic_level_name(1) == 'WARN'
        assert diagnostic_level_name(2) == 'ERROR'
        assert diagnostic_level_name(3) == 'STALE'

    def test_out_of_range_clamps_to_stale(self):
        assert diagnostic_level_name(4) == 'STALE'
        assert diagnostic_level_name(99) == 'STALE'

    def test_bytes_input(self):
        assert diagnostic_level_name(b'\x01') == 'WARN'
        assert diagnostic_level_name(b'\x00') == 'OK'

    def test_negative_clamps_to_ok(self):
        assert diagnostic_level_name(-1) == 'OK'


class TestSafeDiagnosticLevel:
    def test_int_passthrough(self):
        assert safe_diagnostic_level(0) == 0
        assert safe_diagnostic_level(2) == 2

    def test_bytes_conversion(self):
        assert safe_diagnostic_level(b'\x02') == 2


class TestDictFromDiagnosticStatus:
    def test_converts_all_fields(self):
        msg = DiagnosticStatus()
        msg.name = 'TestComponent'
        msg.level = DiagnosticStatus.WARN
        msg.message = 'something wrong'
        msg.hardware_id = 'hw42'
        msg.values = [KeyValue(key='k1', value='v1'), KeyValue(key='k2', value='v2')]

        result = dict_from_diagnostic_status(msg)
        assert result['name'] == 'TestComponent'
        assert result['level'] == 1
        assert result['level_name'] == 'WARN'
        assert result['message'] == 'something wrong'
        assert result['hardware_id'] == 'hw42'
        assert result['values'] == {'k1': 'v1', 'k2': 'v2'}

    def test_empty_values(self):
        msg = DiagnosticStatus()
        msg.name = 'Empty'
        msg.level = DiagnosticStatus.OK
        result = dict_from_diagnostic_status(msg)
        assert result['values'] == {}
        assert result['level_name'] == 'OK'
