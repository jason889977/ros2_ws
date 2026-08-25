import importlib.util
from pathlib import Path

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
            'enable_apriltag': 'true',
            'enable_qrcode': 'true',
            'enable_keyence': 'true',
            'prefer_wechat_qr': 'true',
            'min_detect_interval_s': '0.2',
            'use_compressed': 'false',
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

    assert len(first) == 4
    assert len(second) == 4
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
            'wechat_qr_node',
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
        'enable_qrcode': 'false',
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
        'enable_qrcode': 'false',
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


def test_qr_backend_preference_is_configurable():
    context = Context('cam1')
    context.launch_configurations['prefer_wechat_qr'] = 'false'

    actions = MODULE.launch_pipeline(context)
    container = actions[0]
    lc = LaunchContext()
    comp_descriptions = getattr(
        container,
        '_ComposableNodeContainer__composable_node_descriptions',
        [],
    )
    qr_comp = next(
        comp for comp in comp_descriptions
        if _eval_comp_name(lc, comp) == 'wechat_qr_node'
    )

    params = qr_comp._ComposableNode__parameters
    found_false = False
    for param in params:
        if isinstance(param, dict):
            for k, v in param.items():
                k_str = perform_substitutions(lc, k) if isinstance(k, (list, tuple)) else str(k)
                if 'prefer_wechat_qr' in k_str:
                    v_val = perform_substitutions(lc, v) if isinstance(v, (list, tuple)) else v
                    if v_val is False or str(v_val).lower() == 'false':
                        found_false = True
    assert found_false


def test_invalid_pipeline_settings_are_rejected():
    invalid_values = [
        ('bad-id', 'camera_frame', '1500', 'true', 'true'),
        ('cam1', '', '1500', 'true', 'true'),
        ('cam1', 'camera_frame', '12000', 'true', 'true'),
        ('cam1', 'camera_frame', '1500', 'maybe', 'true'),
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
        context.launch_configurations['enable_qrcode'] = 'enabled'
        MODULE.launch_pipeline(context)
    except RuntimeError as error:
        assert 'enable_qrcode' in str(error)
    else:
        raise AssertionError('invalid module switch was accepted')


def test_qr_timing_and_compression_settings_are_forwarded():
    context = Context('cam1')
    context.launch_configurations.update({
        'min_detect_interval_s': '0.5',
        'use_compressed': 'true',
    })
    actions = MODULE.launch_pipeline(context)
    container = actions[0]
    lc = LaunchContext()
    comp_descriptions = getattr(
        container,
        '_ComposableNodeContainer__composable_node_descriptions',
        [],
    )
    qr_node = next(
        comp for comp in comp_descriptions
        if _eval_comp_name(lc, comp) == 'wechat_qr_node'
    )
    params = qr_node._ComposableNode__parameters
    all_values = []
    for param in params:
        if isinstance(param, dict):
            for k, v in param.items():
                v_val = perform_substitutions(lc, v) if isinstance(v, (list, tuple)) else v
                all_values.append(v_val)
    assert 0.5 in all_values or '0.5' in all_values
    assert True in all_values or 'true' in [str(x).lower() for x in all_values]
