"""Shared mathematical utilities for industrial vision packages.

Frequently used symbols are re-exported here for convenience.
For less common helpers, import directly from the submodule:

    from vision_core.transforms import homogeneous_matrix
    from vision_core.handeye_utils import solve_hand_eye
    from vision_core.websocket import WebSocketManager
"""

from .transforms import (  # noqa: F401
    generate_aruco_marker,
    homogeneous_matrix,
    rotation_angle,
    rotation_from_quaternion,
    rotation_from_rotvec,
    rotation_from_rpy,
    rotation_matrix_to_quaternion,
    stamp_to_seconds,
    transform_message_to_matrix,
    xarm_pose_to_transform,
)
from .launch_helpers import (
    declare_and_get,
    parse_bool,
    parse_nonnegative_float,
    parse_positive_float,
)
from .handeye_utils import (  # noqa: F401
    HAND_EYE_ALGORITHMS,
    closed_loop_errors,
    fallback_calibrate_hand_eye,
    read_rows,
    rotation_diversity,
    rotation_span,
    should_collect_sample,
    solve_hand_eye,
    write_handeye_yaml,
)
from .tag_frame_tracker import TagFrameTracker
from .websocket import WebSocketManager  # noqa: F401
from .run_node import run_node
from .process import terminate_process
from .diagnostics import (  # noqa: F401
    DIAGNOSTIC_LEVEL_NAMES,
    DiagnosticsSubscriber,
    diagnostic_level_name,
    dict_from_diagnostic_status,
    safe_diagnostic_level,
)

# Core symbols commonly needed by consumers.
# Import less-used helpers directly from their submodules.
__all__ = [
    # Node lifecycle
    'run_node',
    'terminate_process',
    # Launch parameter parsing
    'parse_bool',
    'parse_nonnegative_float',
    'parse_positive_float',
    'declare_and_get',
    # Diagnostics
    'DIAGNOSTIC_LEVEL_NAMES',
    'diagnostic_level_name',
    'dict_from_diagnostic_status',
    'safe_diagnostic_level',
    # Tag tracking
    'TagFrameTracker',
    # Transforms (frequently used)
    'homogeneous_matrix',
    'rotation_from_rpy',
    'rotation_matrix_to_quaternion',
    'generate_aruco_marker',
]
