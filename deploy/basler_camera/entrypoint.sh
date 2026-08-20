#!/usr/bin/env bash
set -eo pipefail

source /opt/ros/humble/setup.bash
source /opt/ros2_ws/install/setup.bash

# ---------------------------------------------------------------------------
# Legacy single-camera launch (pylon_ros2_camera.launch.py)
# ---------------------------------------------------------------------------
if [[ "${*}" == *"pylon_ros2_camera.launch.py"* ]]; then
  exec "$@" \
    camera_id:="${CAMERA_ID:-my_camera}" \
    config_file:="${CAMERA_CONFIG_FILE:-/opt/ros2_ws/deploy/basler_camera/config/aca2500_106611_18.yaml}" \
    mtu_size:="${CAMERA_MTU_SIZE:-1500}" \
    startup_user_set:="${CAMERA_STARTUP_USER_SET:-Default}" \
    respawn:="${CAMERA_RESPAWN:-true}"
fi

# ---------------------------------------------------------------------------
# Unified vision pipeline — supports dual-camera via CAMERA_ID_2
# ---------------------------------------------------------------------------
if [[ "${*}" == *"vision_pipeline.launch.py"* ]]; then
  CAM1_ID="${CAMERA_ID:-my_camera}"
  CAM1_CONFIG="${CAMERA_CONFIG_FILE:-/opt/ros2_ws/deploy/basler_camera/config/aca2500_106611_18.yaml}"

  CAM1_ARGS=(
    camera_id:="$CAM1_ID"
    camera_config:="$CAM1_CONFIG"
    startup_user_set:="${CAMERA_STARTUP_USER_SET:-Default}"
    scanner_ip:="${SCANNER_IP:-172.31.0.91}"
    scanner_port:="${SCANNER_PORT:-9004}"
    reconnect_interval_s:="${RECONNECT_INTERVAL_S:-5.0}"
    enable_apriltag:="${ENABLE_APRILTAG:-true}"
    enable_qrcode:="${ENABLE_QRCODE:-true}"
    enable_keyence:="${ENABLE_KEYENCE:-true}"
  )

  if [[ -n "${CAMERA_ID_2:-}" ]]; then
    CAM2_CONFIG="${CAMERA_CONFIG_2:-$CAM1_CONFIG}"
    CAM2_ARGS=(
      camera_id:="$CAMERA_ID_2"
      camera_config:="$CAM2_CONFIG"
      startup_user_set:="${CAMERA_STARTUP_USER_SET_2:-Default}"
      scanner_ip:="${SCANNER_IP_2:-${SCANNER_IP:-172.31.0.91}}"
      scanner_port:="${SCANNER_PORT_2:-${SCANNER_PORT:-9004}}"
      reconnect_interval_s:="${RECONNECT_INTERVAL_S:-5.0}"
      enable_apriltag:="${ENABLE_APRILTAG_2:-true}"
      enable_qrcode:="${ENABLE_QRCODE_2:-true}"
      enable_keyence:="${ENABLE_KEYENCE_2:-true}"
    )

    echo "[entrypoint] Launching dual-camera pipeline:"
    echo "  cam1: $CAM1_ID  (apriltag=${ENABLE_APRILTAG:-true}, qr=${ENABLE_QRCODE:-true}, keyence=${ENABLE_KEYENCE:-true})"
    echo "  cam2: $CAMERA_ID_2  (apriltag=${ENABLE_APRILTAG_2:-true}, qr=${ENABLE_QRCODE_2:-true}, keyence=${ENABLE_KEYENCE_2:-true})"

    ros2 launch industrial_vision_bringup vision_pipeline.launch.py "${CAM1_ARGS[@]}" &
    PID1=$!

    ros2 launch industrial_vision_bringup vision_pipeline.launch.py "${CAM2_ARGS[@]}" &
    PID2=$!

    trap 'kill $PID1 $PID2 2>/dev/null || true' EXIT INT TERM
    wait $PID1 $PID2
  else
    echo "[entrypoint] Launching single-camera pipeline: $CAM1_ID"
    exec ros2 launch industrial_vision_bringup vision_pipeline.launch.py "${CAM1_ARGS[@]}"
  fi
  exit 0
fi

exec "$@"
