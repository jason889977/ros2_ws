#!/usr/bin/env bash
set -eo pipefail

source /opt/ros/humble/setup.bash
source /opt/ros2_ws/install/setup.bash

node="/wechat_qr_node"
topic="/wechat_qr_node/decoded_info"

ros2 node list | grep -Fxq "$node" || exit 1
ros2 topic list | grep -Fxq "$topic" || exit 1
ros2 topic type "$topic" | grep -Fxq 'std_msgs/msg/String' || exit 1

timeout 5s ros2 topic hz "$topic" >/dev/null 2>&1 || true
exit 0
