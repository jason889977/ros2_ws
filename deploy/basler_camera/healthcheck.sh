#!/usr/bin/env bash
set -eo pipefail

source /opt/ros/humble/setup.bash
source /opt/ros2_ws/install/setup.bash

namespace="/${CAMERA_ID:-my_camera}"
node="${namespace}/pylon_ros2_camera_node"
info_topic="${node}/camera_info"

# 1. Camera must always be healthy
ros2 topic type "$info_topic" 2>/dev/null | grep -Fxq 'sensor_msgs/msg/CameraInfo' || exit 1
timeout 5s ros2 topic echo "$info_topic" --once >/dev/null 2>&1 || exit 1

# 2. Check enabled detection modules (non-fatal: log warning but don't fail)
#    Detection nodes have respawn=True, so transient failures self-heal.
#    We only verify the nodes are registered, not that they have active data.
WARNINGS=""

if [[ "${ENABLE_APRILTAG:-true}" == "true" ]]; then
  if ! ros2 node list 2>/dev/null | grep -Fxq "${namespace}/apriltag_pose_reader"; then
    WARNINGS="${WARNINGS}apriltag_pose_reader not running; "
  fi
fi

if [[ "${ENABLE_QRCODE:-true}" == "true" ]]; then
  if ! ros2 node list 2>/dev/null | grep -Fxq "${namespace}/wechat_qr_node"; then
    WARNINGS="${WARNINGS}wechat_qr_node not running; "
  fi
fi

if [[ "${ENABLE_KEYENCE:-true}" == "true" ]]; then
  if ! ros2 node list 2>/dev/null | grep -Fxq "${namespace}/keyence_sr_node"; then
    WARNINGS="${WARNINGS}keyence_sr_node not running; "
  fi
fi

if [[ -n "$WARNINGS" ]]; then
  echo "HEALTHY (camera OK) WARNINGS: ${WARNINGS}" >&2
fi

echo "OK"
