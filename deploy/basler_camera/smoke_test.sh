#!/usr/bin/env bash
set -euo pipefail

source /opt/ros/humble/setup.bash
source /opt/ros2_ws/install/setup.bash

namespace="/${CAMERA_ID:-my_camera}"
node="${namespace}/pylon_ros2_camera_node"
image_topic="${node}/image_raw"
info_topic="${node}/camera_info"

fail() { echo "SMOKE TEST FAILED: $*" >&2; exit 1; }

ros2 node list | grep -Fxq "$node" || fail "camera node is not running"
ros2 topic type "$image_topic" | grep -Fxq 'sensor_msgs/msg/Image' || fail "image topic type is wrong"
ros2 topic type "$info_topic" | grep -Fxq 'sensor_msgs/msg/CameraInfo' || fail "camera_info topic type is wrong"
timeout 10s ros2 topic echo "$info_topic" --once >/tmp/basler_camera_info.yaml || fail "no camera_info message"
timeout 10s ros2 topic echo "$image_topic" --once >/dev/null || fail "no image message"

echo "SMOKE TEST PASSED: $node is publishing camera_info and image_raw"
