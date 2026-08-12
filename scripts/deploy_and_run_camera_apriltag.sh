#!/usr/bin/env bash
set -euo pipefail

# One-shot deploy and run helper for Basler camera + official AprilTag ROS + pose reader.
# Camera mode:
#   reuse   - reuse an already running pylon camera node if found (default)
#   restart - stop old camera processes first, then launch a fresh camera node

WORKSPACE_DIR="/home/ubuntu/ros2_ws"
ROS_SETUP="/opt/ros/humble/setup.bash"
WS_SETUP="$WORKSPACE_DIR/install/setup.bash"
CAMERA_MODE="${CAMERA_MODE:-reuse}"
CAMERA_ID="${CAMERA_ID:-basler_106611_18}"
CAMERA_CONFIG="$WORKSPACE_DIR/install/pylon_ros2_camera_wrapper/share/pylon_ros2_camera_wrapper/config/aca2500_106611_18.yaml"
IMAGE_TOPIC=""
CAM_INFO_TOPIC=""
START_CAMERA=true
CAM_LAUNCH_PID=""
APRILTAG_LAUNCH_PID=""

usage() {
  cat <<EOF
Usage: $0 [--camera-mode reuse|restart] [--camera-id <id>]

Options:
  --camera-mode   reuse existing camera node or restart camera before launch.
                  Default: reuse
  --camera-id     camera namespace when launching a new camera.
                  Default: basler_106611_18
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --camera-mode)
      CAMERA_MODE="${2:-}"
      shift 2
      ;;
    --camera-id)
      CAMERA_ID="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "[ERROR] Unknown argument: $1"
      usage
      exit 1
      ;;
  esac
done

if [[ "$CAMERA_MODE" != "reuse" && "$CAMERA_MODE" != "restart" ]]; then
  echo "[ERROR] Invalid --camera-mode: $CAMERA_MODE (expected reuse or restart)"
  exit 1
fi

detect_running_camera_id() {
  local node
  node=$(ros2 node list 2>/dev/null | grep -E '^/[^/]+/pylon_ros2_camera_node$' | head -n1 || true)
  if [[ -z "$node" ]]; then
    return 1
  fi

  local ns
  ns="${node#/}"
  echo "${ns%%/*}"
}

stop_existing_camera() {
  echo "[INFO] Stopping existing camera processes before restart..."
  pkill -f "pylon_ros2_camera_node|pylon_ros2_camera.launch.py|pylon_ros2_camera_wrapper" || true
  sleep 2
}

cleanup() {
  if [[ -n "$APRILTAG_LAUNCH_PID" ]] && kill -0 "$APRILTAG_LAUNCH_PID" 2>/dev/null; then
    kill "$APRILTAG_LAUNCH_PID" || true
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
set +u
source "$ROS_SETUP"
set -u

# Build required runtime packages to ensure config/scripts are installed.
colcon build --packages-select pylon_ros2_camera_wrapper apriltag_pose_reader --symlink-install

if [[ ! -f "$WS_SETUP" ]]; then
  echo "[ERROR] Workspace setup not found after build: $WS_SETUP"
  exit 1
fi

set +u
source "$WS_SETUP"
set -u

if [[ ! -f "$CAMERA_CONFIG" ]]; then
  echo "[ERROR] Camera config not found: $CAMERA_CONFIG"
  exit 1
fi

if [[ "$CAMERA_MODE" == "restart" ]]; then
  stop_existing_camera
else
  RUNNING_CAMERA_ID="$(detect_running_camera_id || true)"
  if [[ -n "$RUNNING_CAMERA_ID" ]]; then
    START_CAMERA=false
    CAMERA_ID="$RUNNING_CAMERA_ID"
    echo "[INFO] Reusing existing camera node namespace: /$CAMERA_ID"
  fi
fi

if [[ "$START_CAMERA" == true ]]; then
  echo "[INFO] Starting camera node in namespace: /$CAMERA_ID"
  ros2 launch pylon_ros2_camera_wrapper pylon_ros2_camera.launch.py \
    camera_id:="$CAMERA_ID" \
    config_file:="$CAMERA_CONFIG" &
  CAM_LAUNCH_PID=$!
  sleep 4
fi

IMAGE_TOPIC="/$CAMERA_ID/pylon_ros2_camera_node/image_raw"
CAM_INFO_TOPIC="/$CAMERA_ID/pylon_ros2_camera_node/camera_info"

echo "[INFO] Starting AprilTag detection and pose reader..."
ros2 launch apriltag_pose_reader apriltag_pose_reader.launch.py \
  image_topic:="$IMAGE_TOPIC" \
  camera_info_topic:="$CAM_INFO_TOPIC" &
APRILTAG_LAUNCH_PID=$!

cat <<EOF

[INFO] Pipeline started.
- Camera mode: $CAMERA_MODE
- Camera namespace: /$CAMERA_ID
- Camera launch PID: ${CAM_LAUNCH_PID:-<reused-existing-node>}
- AprilTag launch PID: $APRILTAG_LAUNCH_PID

Validation commands:
  source $ROS_SETUP
  source $WS_SETUP
  ros2 topic list | grep -E "${CAMERA_ID}|detections|apriltag"
  ros2 topic echo /detections --once
  ros2 topic echo /apriltag/pose --once

To stop:
  kill $CAM_LAUNCH_PID $APRILTAG_LAUNCH_PID
EOF
