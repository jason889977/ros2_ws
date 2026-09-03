import importlib.util
import os
import tempfile
from pathlib import Path

import pytest
from launch import LaunchContext
from launch.utilities import perform_substitutions


MODULE_PATH = Path(__file__).parents[1] / 'launch' / 'vision_pipeline.launch.py'
SPEC = importlib.util.spec_from_file_location('vision_pipeline_launch', MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class Context:
    def __init__(self, camera_id):
        self.launch_configurations = {
            'camera_id': camera_id,
            'camera_config': '/tmp/camera.yaml',
            'camera_frame': f'{camera_id}_frame',
            'startup_user_set': 'Default',
            'mtu_size': '1500',
            'respawn': 'true',
            'scanner_ip': '127.0.0.1',
            'scanner_port': '9004',
            'reconnect_interval_s': '5.0',
            'binning_x': '0',
            'binning_y': '0',
            'apriltag_ids': '',
            'apriltag_size': '0.0',
            'enable_apriltag': 'true',
            'enable_keyence': 'true',
        }


def _eval_comp_name(lc, comp):
    name_obj = getattr(comp, '_ComposableNode__node_name', None)
    if isinstance(name_obj, list):
        return perform_substitutions(lc, name_obj)
    return str(name_obj)


def _eval_comp_namespace(lc, comp):
    ns_obj = getattr(comp, '_ComposableNode__node_namespace', None)
    if isinstance(ns_obj, list):
        return perform_substitutions(lc, ns_obj)
    return str(ns_obj)


def _eval_node_name(lc, action):
    name_obj = getattr(action, '_Node__node_name', None)
    if isinstance(name_obj, list):
        return perform_substitutions(lc, name_obj)
    return str(name_obj)


def _eval_node_namespace(lc, action):
    ns_obj = getattr(action, '_Node__node_namespace', None)
    if isinstance(ns_obj, list):
        return perform_substitutions(lc, ns_obj)
    return str(ns_obj)


def test_two_camera_pipeline_actions_are_isolated():
    first = MODULE.launch_pipeline(Context('cam1'))
    second = MODULE.launch_pipeline(Context('cam2'))
    lc = LaunchContext()

    assert len(first) == 6
    assert len(second) == 6
    assert _eval_node_name(lc, first[0]) == 'vision_container_cam1'
    assert _eval_node_name(lc, second[0]) == 'vision_container_cam2'

    # Check composable nodes inside container
    for container_action, camera_id in ((first[0], 'cam1'), (second[0], 'cam2')):
        comp_descriptions = getattr(
            container_action,
            '_ComposableNodeContainer__composable_node_descriptions',
            [],
        )
        comp_names = {_eval_comp_name(lc, comp) for comp in comp_descriptions}
        assert comp_names == {
            'pylon_ros2_camera_node',
            'apriltag',
        }
        for comp in comp_descriptions:
            assert _eval_comp_namespace(lc, comp) == camera_id

    # Check standalone nodes
    for actions, camera_id in ((first, 'cam1'), (second, 'cam2')):
        node_names = {_eval_node_name(lc, action) for action in actions[1:]}
        assert node_names == {
            'apriltag_pose_reader',
            'keyence_sr_node',
            'vision_status_aggregator',
            'event_logger',
            'web_dashboard',
        }
        status_node = next(
            action for action in actions
            if _eval_node_name(lc, action) == 'vision_status_aggregator'
        )
        assert _eval_node_namespace(lc, status_node) == camera_id

    first_frames = MODULE.build_tag_frames('cam1')
    second_frames = MODULE.build_tag_frames('cam2')
    assert first_frames[0] == 'cam1/tag36h11:0'
    assert second_frames[0] == 'cam2/tag36h11:0'
    assert set(first_frames).isdisjoint(second_frames)


def test_disabled_modules_remain_declared_but_are_conditioned_off():
    context = Context('cam1')
    context.launch_configurations.update({
        'enable_apriltag': 'false',
        'enable_keyence': 'true',
    })

    actions = MODULE.launch_pipeline(context)
    container = actions[0]
    lc = LaunchContext()
    comp_descriptions = getattr(
        container,
        '_ComposableNodeContainer__composable_node_descriptions',
        [],
    )
    comp_names = {_eval_comp_name(lc, comp) for comp in comp_descriptions}
    assert comp_names == {'pylon_ros2_camera_node'}

    by_name = {
        _eval_node_name(lc, action): action
        for action in actions[1:]
    }

    assert by_name['apriltag_pose_reader']._Action__condition is not None
    assert by_name['keyence_sr_node']._Action__condition is not None
    assert by_name['vision_status_aggregator']._Action__condition is None


def test_invalid_scanner_settings_are_rejected_before_startup():
    try:
        MODULE.parse_scanner_settings('0', '5.0')
    except RuntimeError as error:
        assert 'scanner_port' in str(error)
    else:
        raise AssertionError('invalid scanner port was accepted')

    try:
        MODULE.parse_scanner_settings('9004', 'nan')
    except RuntimeError as error:
        assert 'reconnect_interval_s' in str(error)
    else:
        raise AssertionError('invalid reconnect interval was accepted')


def test_keyence_only_pipeline_keeps_camera_namespace():
    context = Context('scanner_cam')
    context.launch_configurations.update({
        'enable_apriltag': 'false',
        'enable_keyence': 'true',
    })

    actions = MODULE.launch_pipeline(context)
    lc = LaunchContext()
    by_name = {
        _eval_node_name(lc, action): action
        for action in actions[1:]
    }

    assert _eval_node_namespace(lc, by_name['keyence_sr_node']) == 'scanner_cam'
    assert _eval_node_namespace(lc, by_name['vision_status_aggregator']) == 'scanner_cam'


def test_invalid_pipeline_settings_are_rejected():
    invalid_values = [
        ('bad-id', 'camera_frame', '1500'),
        ('cam1', '', '1500'),
        ('cam1', 'camera_frame', '12000'),
    ]

    for values in invalid_values:
        try:
            MODULE.validate_pipeline_settings(*values)
        except RuntimeError:
            continue
        raise AssertionError(f'invalid settings were accepted: {values!r}')


def test_invalid_module_switch_is_rejected():
    try:
        MODULE.launch_pipeline(Context('cam1'))
        context = Context('cam1')
        context.launch_configurations['enable_apriltag'] = 'enabled'
        MODULE.launch_pipeline(context)
    except RuntimeError as error:
        assert 'enable_apriltag' in str(error)
    else:
        raise AssertionError('invalid module switch was accepted')


def _get_camera_params(actions, lc):
    """Extract Pylon camera composable node parameters."""
    container = actions[0]
    comp_descriptions = getattr(
        container,
        '_ComposableNodeContainer__composable_node_descriptions',
        [],
    )
    camera_comp = next(
        comp for comp in comp_descriptions
        if _eval_comp_name(lc, comp) == 'pylon_ros2_camera_node'
    )
    return camera_comp._ComposableNode__parameters


def _get_apriltag_params(actions, lc):
    """Extract AprilTag composable node parameters."""
    container = actions[0]
    comp_descriptions = getattr(
        container,
        '_ComposableNodeContainer__composable_node_descriptions',
        [],
    )
    tag_comp = next(
        comp for comp in comp_descriptions
        if _eval_comp_name(lc, comp) == 'apriltag'
    )
    return tag_comp._ComposableNode__parameters


def _flatten_params(params, lc):
    """Flatten parameter list into a single dict of resolved key-value pairs."""
    result = {}
    for param in params:
        if isinstance(param, dict):
            for k, v in param.items():
                if isinstance(k, (list, tuple)):
                    k_str = perform_substitutions(lc, k)
                else:
                    k_str = str(k)
                if isinstance(v, (list, tuple)) and v and hasattr(v[0], 'perform'):
                    result[k_str] = perform_substitutions(lc, v)
                elif isinstance(v, tuple) and v and isinstance(v[0], (list, tuple)):
                    result[k_str] = [perform_substitutions(lc, item) for item in v]
                else:
                    result[k_str] = v
    return result


def test_binning_default_omits_override():
    """binning_x/y=0 should NOT inject binning into camera params (YAML is source)."""
    context = Context('cam1')
    context.launch_configurations['binning_x'] = '0'
    context.launch_configurations['binning_y'] = '0'

    actions = MODULE.launch_pipeline(context)
    lc = LaunchContext()
    flat = _flatten_params(_get_camera_params(actions, lc), lc)

    assert 'binning_x' not in flat
    assert 'binning_y' not in flat


def test_binning_override_injected_when_nonzero():
    """binning_x/y > 0 should override camera YAML values."""
    context = Context('cam1')
    context.launch_configurations['binning_x'] = '4'
    context.launch_configurations['binning_y'] = '4'

    actions = MODULE.launch_pipeline(context)
    lc = LaunchContext()
    flat = _flatten_params(_get_camera_params(actions, lc), lc)

    assert flat.get('binning_x') == 4
    assert flat.get('binning_y') == 4


def test_binning_partial_override_independent():
    """binning_x and binning_y should be independently overridable."""
    context = Context('cam1')
    context.launch_configurations['binning_x'] = '4'
    context.launch_configurations['binning_y'] = '0'

    actions = MODULE.launch_pipeline(context)
    lc = LaunchContext()
    flat = _flatten_params(_get_camera_params(actions, lc), lc)

    assert flat.get('binning_x') == 4
    assert 'binning_y' not in flat


def test_invalid_apriltag_ids_rejected():
    """Non-integer apriltag_ids should raise RuntimeError."""
    context = Context('cam1')
    context.launch_configurations['apriltag_ids'] = '0,abc,7'

    try:
        MODULE.launch_pipeline(context)
    except RuntimeError as error:
        assert 'apriltag_ids' in str(error)
    else:
        raise AssertionError('invalid apriltag_ids was accepted')


def test_apriltag_default_ids():
    """Empty apriltag_ids should default to 0-11."""
    context = Context('cam1')
    context.launch_configurations['apriltag_ids'] = ''

    actions = MODULE.launch_pipeline(context)
    lc = LaunchContext()
    flat = _flatten_params(_get_apriltag_params(actions, lc), lc)

    assert list(flat['tag.ids']) == list(range(12))
    assert len(flat['tag.frames']) == 12
    assert list(flat['tag.sizes']) == [0.05] * 12


def test_apriltag_custom_ids():
    """Comma-separated apriltag_ids should be parsed and forwarded."""
    context = Context('cam1')
    context.launch_configurations['apriltag_ids'] = '0,3,7'
    context.launch_configurations['apriltag_size'] = '0.08'

    actions = MODULE.launch_pipeline(context)
    lc = LaunchContext()
    flat = _flatten_params(_get_apriltag_params(actions, lc), lc)

    assert list(flat['tag.ids']) == [0, 3, 7]
    assert len(flat['tag.frames']) == 3
    assert list(flat['tag.sizes']) == [0.08] * 3


def test_dual_camera_binning_and_apriltag_independent():
    """Dual camera pipelines should support independent binning and AprilTag config."""
    cam1 = Context('cam1')
    cam1.launch_configurations['binning_x'] = '2'
    cam1.launch_configurations['binning_y'] = '2'
    cam1.launch_configurations['apriltag_ids'] = '0,1,2'
    cam1.launch_configurations['apriltag_size'] = '0.05'

    cam2 = Context('cam2')
    cam2.launch_configurations['binning_x'] = '4'
    cam2.launch_configurations['binning_y'] = '4'
    cam2.launch_configurations['apriltag_ids'] = '5,6'
    cam2.launch_configurations['apriltag_size'] = '0.10'

    actions1 = MODULE.launch_pipeline(cam1)
    actions2 = MODULE.launch_pipeline(cam2)
    lc = LaunchContext()

    flat1 = _flatten_params(_get_camera_params(actions1, lc), lc)
    flat2 = _flatten_params(_get_camera_params(actions2, lc), lc)

    assert flat1.get('binning_x') == 2
    assert flat2.get('binning_x') == 4

    tag1 = _flatten_params(_get_apriltag_params(actions1, lc), lc)
    tag2 = _flatten_params(_get_apriltag_params(actions2, lc), lc)

    assert list(tag1['tag.ids']) == [0, 1, 2]
    assert list(tag2['tag.ids']) == [5, 6]
    assert list(tag1['tag.sizes']) == [0.05] * 3
    assert list(tag2['tag.sizes']) == [0.10] * 2


def test_optional_static_transform_nodes_are_added_when_configured():
    context = Context('cam1')
    context.launch_configurations.update({
        'handeye_calibration_file': '/tmp/handeye.yaml',
        'world_frame': 'world',
        'base_frame': 'base_link',
    })

    actions = MODULE.launch_pipeline(context)
    lc = LaunchContext()
    nodes_by_name = {
        _eval_node_name(lc, action): action
        for action in actions
    }

    assert 'handeye_static_tf_broadcaster' in nodes_by_name
    assert 'world_base_static_tf_broadcaster' in nodes_by_name
    assert _eval_node_namespace(
        lc, nodes_by_name['handeye_static_tf_broadcaster'],
    ) == 'cam1'
    assert _eval_node_namespace(
        lc, nodes_by_name['world_base_static_tf_broadcaster'],
    ) == 'cam1'


def test_params_with_optional_file_inline_only():
    from industrial_vision_bringup.pipeline_nodes import _params_with_optional_file

    result = _params_with_optional_file({'key': 'val'}, '')
    assert result == [{'key': 'val'}]


def test_params_with_optional_file_nonexistent_path():
    from industrial_vision_bringup.pipeline_nodes import _params_with_optional_file

    with pytest.raises(FileNotFoundError, match='params_file not found'):
        _params_with_optional_file({'key': 'val'}, '/nonexistent/params.yaml')


def test_params_with_optional_file_existing_yaml():
    from industrial_vision_bringup.pipeline_nodes import _params_with_optional_file

    with tempfile.NamedTemporaryFile(suffix='.yaml', delete=False) as f:
        f.write(b'test: true\n')
        yaml_path = f.name
    try:
        result = _params_with_optional_file({'key': 'val'}, yaml_path)
        assert len(result) == 2
        assert result[0] == {'key': 'val'}
        assert result[1] == yaml_path
    finally:
        os.unlink(yaml_path)


def test_params_file_launch_argument_is_declared():
    desc = MODULE.generate_launch_description()
    arg_names = [
        a.name for a in desc.entities
        if hasattr(a, 'name')
    ]
    assert 'params_file' in arg_names
