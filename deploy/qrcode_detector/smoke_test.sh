#!/usr/bin/env bash
set -eo pipefail

source /opt/ros/humble/setup.bash
source /opt/ros2_ws/install/setup.bash

node="/wechat_qr_node"
topic="/wechat_qr_node/decoded_info"

fail() { echo "SMOKE TEST FAILED: $*" >&2; exit 1; }

ros2 node list | grep -Fxq "$node" || fail "QR node is not running"
ros2 topic list | grep -Fxq "$topic" || fail "decoded_info topic is not available"
ros2 topic type "$topic" | grep -Fxq 'std_msgs/msg/String' || fail "decoded_info topic type is wrong"

timeout 10s ros2 topic echo "$topic" --once >/tmp/qrcode_decoded.txt 2>/dev/null || fail "no decoded output"

echo "SMOKE TEST PASSED: $node is publishing decoded QR strings"
