import importlib.util
from pathlib import Path


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


def test_two_camera_pipeline_actions_are_isolated():
    first = MODULE.launch_pipeline(Context('cam1'))
    second = MODULE.launch_pipeline(Context('cam2'))

    assert len(first) == 6
    assert len(second) == 6
    assert first[0]._Node__node_name == 'vision_container_cam1'
    assert second[0]._Node__node_name == 'vision_container_cam2'

    for actions, camera_id in ((first, 'cam1'), (second, 'cam2')):
        node_names = {action._Node__node_name for action in actions[1:]}
        assert node_names == {
            'apriltag',
            'apriltag_pose_reader',
            'wechat_qr_node',
            'keyence_sr_node',
            'vision_status_aggregator',
        }
        status_node = next(
            action for action in actions
            if action._Node__node_name == 'vision_status_aggregator'
        )
        assert status_node._Node__node_namespace == camera_id

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
    by_name = {
        action._Node__node_name: action
        for action in actions[1:]
    }

    assert by_name['apriltag']._Action__condition is not None
    assert by_name['wechat_qr_node']._Action__condition is not None
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
    by_name = {
        action._Node__node_name: action
        for action in actions[1:]
    }

    assert by_name['keyence_sr_node']._Node__node_namespace == 'scanner_cam'
    assert by_name['vision_status_aggregator']._Node__node_namespace == 'scanner_cam'


def test_qr_backend_preference_is_configurable():
    context = Context('cam1')
    context.launch_configurations['prefer_wechat_qr'] = 'false'

    actions = MODULE.launch_pipeline(context)
    qr_node = next(
        action for action in actions if action._Node__node_name == 'wechat_qr_node'
    )

    assert any(
        value is False
        for parameter_group in qr_node._Node__parameters
        for value in parameter_group.values()
    )


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
    qr_node = next(
        action for action in actions if action._Node__node_name == 'wechat_qr_node'
    )
    values = [
        value
        for group in qr_node._Node__parameters
        for value in group.values()
    ]
    assert 0.5 in values
    assert True in values
