#!/usr/bin/env bash
set -eo pipefail

source /opt/ros/humble/setup.bash
source /opt/ros2_ws/install/setup.bash

if [[ "${*}" == *"pylon_ros2_camera.launch.py"* ]]; then
  exec "$@" \
    camera_id:="${CAMERA_ID:-my_camera}" \
    config_file:="${CAMERA_CONFIG_FILE:-/opt/ros2_ws/deploy/basler_camera/config/aca2500_106611_18.yaml}" \
    mtu_size:="${CAMERA_MTU_SIZE:-1500}" \
    startup_user_set:="${CAMERA_STARTUP_USER_SET:-Default}" \
    respawn:="${CAMERA_RESPAWN:-true}"
fi

exec "$@"
