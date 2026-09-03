from launch import LaunchContext
from launch.utilities import perform_substitutions

from industrial_vision_bringup.bringup_utils import CameraPipelineConfig, PipelineTopics
from industrial_vision_bringup.composable_nodes import build_composable_nodes


TOPICS = PipelineTopics(
    camera_info='/cam1/pylon_ros2_camera_node/camera_info',
    image_raw='/cam1/pylon_ros2_camera_node/image_raw',
    image_rect='/cam1/pylon_ros2_camera_node/image_rect',
    apriltag_pose='/cam1/apriltag/pose',
    apriltag_transform='/cam1/apriltag/transform',
    detections='/cam1/detections',
    scanner_barcode='/cam1/scanner/barcode',
    scanner_trigger='/cam1/scanner/trigger',
    diagnostics='/cam1/diagnostics',
    vision_status='/cam1/vision/status',
)


def _name(component):
    value = getattr(component, '_ComposableNode__node_name')
    return perform_substitutions(LaunchContext(), value) if isinstance(value, list) else str(value)


def _components(**overrides):
    options = {
        'camera_id': 'cam1',
        'camera_config': '/tmp/camera.yaml',
        'camera_frame': 'cam1_frame',
        'startup_user_set': 'Default',
        'mtu_size': 1500,
        'binning_x': 0,
        'binning_y': 0,
        'enable_apriltag': True,
        'detector_config': '/tmp/apriltag.yaml',
        'tag_ids': [0, 1],
        'tag_frames': ['cam1/tag36h11:0', 'cam1/tag36h11:1'],
        'apriltag_size': 0.05,
        'topics': TOPICS,
    }
    options.update(overrides)
    return build_composable_nodes(CameraPipelineConfig(**options))


def test_composable_factory_omits_disabled_detectors():
    components = _components(enable_apriltag=False)

    assert [_name(component) for component in components] == ['pylon_ros2_camera_node']


def test_composable_factory_adds_only_nonzero_binning_overrides():
    camera = _components(binning_x=4)[0]
    parameters = camera._ComposableNode__parameters[1]
    resolved = {
        perform_substitutions(LaunchContext(), key): value
        for key, value in parameters.items()
    }

    assert resolved['binning_x'] == 4
    assert 'binning_y' not in resolved


def test_apriltag_uses_sensor_data_qos_for_camera_info_compatibility():
    apriltag = _components()[1]
    parameters = apriltag._ComposableNode__parameters[1]
    resolved = {}
    for key, value in parameters.items():
        name = perform_substitutions(LaunchContext(), key)
        if name in {'image_transport', 'qos_profile'}:
            resolved[name] = perform_substitutions(LaunchContext(), value).splitlines()[0]

    assert resolved['image_transport'] == 'raw'
    assert resolved['qos_profile'] == 'sensor_data'