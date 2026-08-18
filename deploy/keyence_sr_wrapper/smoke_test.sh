#!/usr/bin/env bash
set -eo pipefail

source /opt/ros/humble/setup.bash
source /opt/ros2_ws/install/setup.bash

node="/keyence_sr_node"
barcode_topic="/scanner/barcode"
trigger_service="/scanner/trigger"

fail() { echo "SMOKE TEST FAILED: $*" >&2; exit 1; }

ros2 node list | grep -Fxq "$node" || fail "Keyence node is not running"
ros2 topic list | grep -Fxq "$barcode_topic" || fail "barcode topic is not available"
ros2 service list | grep -Fxq "$trigger_service" || fail "trigger service is not available"
ros2 topic type "$barcode_topic" | grep -Fxq 'std_msgs/msg/String' || fail "barcode topic type is wrong"

echo "SMOKE TEST PASSED: Keyence scanner wrapper is active"
