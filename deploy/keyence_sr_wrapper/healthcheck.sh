#!/usr/bin/env bash
set -eo pipefail

source /opt/ros/humble/setup.bash
source /opt/ros2_ws/install/setup.bash

node="/keyence_sr_node"
barcode_topic="/scanner/barcode"
trigger_service="/scanner/trigger"

ros2 node list | grep -Fxq "$node" || exit 1
ros2 topic list | grep -Fxq "$barcode_topic" || exit 1
ros2 service list | grep -Fxq "$trigger_service" || exit 1
ros2 topic type "$barcode_topic" | grep -Fxq 'std_msgs/msg/String' || exit 1

exit 0
