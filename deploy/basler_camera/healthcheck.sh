#!/usr/bin/env bash
set -eo pipefail

source /opt/ros/humble/setup.bash
source /opt/ros2_ws/install/setup.bash

namespace="/${CAMERA_ID:-my_camera}"
node="${namespace}/pylon_ros2_camera_node"
topic="${node}/camera_info"

ros2 node list | grep -Fxq "$node" || exit 1
ros2 topic type "$topic" | grep -Fxq 'sensor_msgs/msg/CameraInfo' || exit 1
timeout 5s ros2 topic echo "$topic" --once >/dev/null
