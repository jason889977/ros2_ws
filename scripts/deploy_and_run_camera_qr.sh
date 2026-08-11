#!/usr/bin/env bash
set -euo pipefail

# One-shot deploy and run helper for Basler camera + QR detector pipeline.

WORKSPACE_DIR="/home/ubuntu/ros2_ws"
ROS_SETUP="/opt/ros/humble/setup.bash"
WS_SETUP="$WORKSPACE_DIR/install/setup.bash"
CAMERA_ID="basler_106611_18"
CAMERA_CONFIG="$WORKSPACE_DIR/install/pylon_ros2_camera_wrapper/share/pylon_ros2_camera_wrapper/config/aca2500_106611_18.yaml"
IMAGE_TOPIC="/$CAMERA_ID/pylon_ros2_camera_node/image_raw"
CAM_LAUNCH_PID=""
QR_LAUNCH_PID=""

cleanup() {
  if [[ -n "$QR_LAUNCH_PID" ]] && kill -0 "$QR_LAUNCH_PID" 2>/dev/null; then
    kill "$QR_LAUNCH_PID" || true
  fi
  if [[ -n "$CAM_LAUNCH_PID" ]] && kill -0 "$CAM_LAUNCH_PID" 2>/dev/null; then
    kill "$CAM_LAUNCH_PID" || true
  fi
}

trap cleanup EXIT INT TERM

if [[ ! -f "$ROS_SETUP" ]]; then
  echo "[ERROR] ROS setup not found: $ROS_SETUP"
  exit 1
fi

if [[ ! -d "$WORKSPACE_DIR" ]]; then
  echo "[ERROR] Workspace not found: $WORKSPACE_DIR"
  exit 1
fi

cd "$WORKSPACE_DIR"
source "$ROS_SETUP"

# Build required runtime packages to ensure config/scripts are installed.
colcon build --packages-select pylon_ros2_camera_wrapper qrcode_detector --symlink-install

if [[ ! -f "$WS_SETUP" ]]; then
  echo "[ERROR] Workspace setup not found after build: $WS_SETUP"
  exit 1
fi

source "$WS_SETUP"

if [[ ! -f "$CAMERA_CONFIG" ]]; then
  echo "[ERROR] Camera config not found: $CAMERA_CONFIG"
  exit 1
fi

echo "[INFO] Starting camera node..."
ros2 launch pylon_ros2_camera_wrapper pylon_ros2_camera.launch.py \
  camera_id:="$CAMERA_ID" \
  config_file:="$CAMERA_CONFIG" &
CAM_LAUNCH_PID=$!

sleep 4

echo "[INFO] Starting QR node..."
ros2 launch qrcode_detector qrcode_detector.launch.py \
  image_topic:="$IMAGE_TOPIC" &
QR_LAUNCH_PID=$!

cat <<EOF

[INFO] Pipeline started.
- Camera launch PID: $CAM_LAUNCH_PID
- QR launch PID: $QR_LAUNCH_PID

Validation commands:
  source $ROS_SETUP
  source $WS_SETUP
  ros2 topic list | grep -E "${CAMERA_ID}|decoded_info"
  ros2 topic echo /wechat_qr_node/decoded_info

To stop:
  kill $CAM_LAUNCH_PID $QR_LAUNCH_PID
EOF

wait
