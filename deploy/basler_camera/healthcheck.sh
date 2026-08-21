#!/usr/bin/env bash
set -eo pipefail

source /opt/ros/humble/setup.bash
source /opt/ros2_ws/install/setup.bash

check_camera() {
  local camera_id="$1"
  local node="/${camera_id}/pylon_ros2_camera_node"
  local info_topic="${node}/camera_info"

  ros2 topic type "$info_topic" 2>/dev/null | grep -Fxq 'sensor_msgs/msg/CameraInfo' || return 1
  timeout 5s ros2 topic echo "$info_topic" --once >/dev/null 2>&1 || return 1
}

# 1. Every configured camera must be healthy.
check_camera "${CAMERA_ID:-my_camera}" || exit 1
if [[ -n "${CAMERA_ID_2:-}" ]]; then
  check_camera "$CAMERA_ID_2" || exit 1
fi

check_modules() {
  local camera_id="$1"
  local enable_apriltag="$2"
  local enable_qrcode="$3"
  local enable_keyence="$4"
  local module_namespace="/${camera_id}"
  local wait_timeout_s=8

  wait_for_node() {
    local target_node="$1"
    local elapsed=0
    while (( elapsed < wait_timeout_s )); do
      if ros2 node list 2>/dev/null | grep -Fxq "$target_node"; then
        return 0
      fi
      sleep 1
      elapsed=$((elapsed + 1))
    done
    return 1
  }

  # An enabled module is required for this pipeline to be healthy. Compose's
  # start period absorbs normal respawn/startup delay before health is checked.
  if [[ "$enable_apriltag" == "true" ]]; then
    if ! wait_for_node "${module_namespace}/apriltag_pose_reader"; then
      echo "${camera_id}: apriltag_pose_reader not running" >&2
      return 1
    fi
  fi

  if [[ "$enable_qrcode" == "true" ]]; then
    if ! wait_for_node "${module_namespace}/wechat_qr_node"; then
      echo "${camera_id}: wechat_qr_node not running" >&2
      return 1
    fi
  fi

  if [[ "$enable_keyence" == "true" ]]; then
    if ! wait_for_node "${module_namespace}/keyence_sr_node"; then
      echo "${camera_id}: keyence_sr_node not running" >&2
      return 1
    fi
  fi
}

check_modules "${CAMERA_ID:-my_camera}" "${ENABLE_APRILTAG:-true}" \
  "${ENABLE_QRCODE:-true}" "${ENABLE_KEYENCE:-true}" || exit 1
if [[ -n "${CAMERA_ID_2:-}" ]]; then
  check_modules "$CAMERA_ID_2" "${ENABLE_APRILTAG_2:-true}" \
    "${ENABLE_QRCODE_2:-true}" "${ENABLE_KEYENCE_2:-true}" || exit 1
fi

echo "OK"
