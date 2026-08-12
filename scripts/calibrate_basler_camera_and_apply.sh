#!/usr/bin/env bash
set -euo pipefail

# Interactive camera calibration helper for the Basler pipeline.
# Workflow:
# 1) Ensure camera node is already publishing image_raw + camera_info.
# 2) Launch cameracalibrator GUI and complete CALIBRATE -> SAVE.
# 3) Copy generated calibration YAML into package config path used by camera profiles.

WORKSPACE_DIR="/home/ubuntu/ros2_ws"
ROS_SETUP="/opt/ros/humble/setup.bash"
WS_SETUP="$WORKSPACE_DIR/install/setup.bash"

CAMERA_ID="${CAMERA_ID:-basler_106611_18}"
BOARD_SIZE="${BOARD_SIZE:-8x6}"
SQUARE_SIZE_M="${SQUARE_SIZE_M:-0.025}"
CAMERA_NAME="${CAMERA_NAME:-aca2500_106611_18}"
TARGET_CALIB_FILE="$WORKSPACE_DIR/src/pylon_ros2_camera_wrapper/config/aca2500_106611_18.calib.yaml"

setup_qt_font_env() {
  # OpenCV Qt backend may fail to render text if font path is not discoverable.
  if [[ -n "${QT_QPA_FONTDIR:-}" && -d "${QT_QPA_FONTDIR}" ]]; then
    echo "[INFO] Using existing QT_QPA_FONTDIR=${QT_QPA_FONTDIR}"
    return 0
  fi

  local candidate_dirs=(
    "/usr/share/fonts/truetype"
    "/usr/share/fonts"
    "/usr/local/share/fonts"
    "$HOME/.local/share/fonts"
  )

  local dir
  for dir in "${candidate_dirs[@]}"; do
    if [[ -d "$dir" ]]; then
      export QT_QPA_FONTDIR="$dir"
      echo "[INFO] Auto-set QT_QPA_FONTDIR=${QT_QPA_FONTDIR}"
      return 0
    fi
  done

  echo "[WARN] No valid font directory found for QT_QPA_FONTDIR; Qt font rendering may fail."
}

setup_qt_runtime_env() {
  # Force xcb by default to avoid noisy Wayland fallback warnings in Qt apps.
  export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-xcb}"
  echo "[INFO] QT_QPA_PLATFORM=${QT_QPA_PLATFORM}"

  setup_qt_font_env

  # Some OpenCV wheels expect cv2/qt/fonts to exist; create a symlink fallback.
  local cv2_qt_dir
  cv2_qt_dir="$(find "$HOME/.local/lib" -type d -path '*/site-packages/cv2/qt' 2>/dev/null | head -n1 || true)"
  if [[ -n "$cv2_qt_dir" && ! -d "$cv2_qt_dir/fonts" && -n "${QT_QPA_FONTDIR:-}" && -d "${QT_QPA_FONTDIR}" ]]; then
    ln -s "$QT_QPA_FONTDIR" "$cv2_qt_dir/fonts" 2>/dev/null || true
    if [[ -L "$cv2_qt_dir/fonts" || -d "$cv2_qt_dir/fonts" ]]; then
      echo "[INFO] Linked missing cv2 Qt fonts dir: $cv2_qt_dir/fonts -> $QT_QPA_FONTDIR"
    fi
  fi
}

usage() {
  cat <<EOF
Usage: $0 [--camera-id <id>] [--board-size <NxM>] [--square-size <meters>] [--camera-name <name>]

Examples:
  $0
  $0 --board-size 9x6 --square-size 0.020
  CAMERA_ID=basler_106611_18 BOARD_SIZE=8x6 SQUARE_SIZE_M=0.025 $0

Notes:
  - Start camera first (or run deploy script in restart/reuse mode).
  - In GUI, complete CALIBRATE then SAVE before closing.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --camera-id)
      CAMERA_ID="${2:-}"
      shift 2
      ;;
    --board-size)
      BOARD_SIZE="${2:-}"
      shift 2
      ;;
    --square-size)
      SQUARE_SIZE_M="${2:-}"
      shift 2
      ;;
    --camera-name)
      CAMERA_NAME="${2:-}"
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

if [[ ! -f "$ROS_SETUP" ]]; then
  echo "[ERROR] ROS setup not found: $ROS_SETUP"
  exit 1
fi

if [[ ! -f "$WS_SETUP" ]]; then
  echo "[ERROR] Workspace setup not found: $WS_SETUP"
  exit 1
fi

cd "$WORKSPACE_DIR"
set +u
source "$ROS_SETUP"
source "$WS_SETUP"
set -u

if ! ros2 node list | grep -qE "^/${CAMERA_ID}/pylon_ros2_camera_node$"; then
  echo "[ERROR] Camera node /${CAMERA_ID}/pylon_ros2_camera_node not found."
  echo "        Start camera first, then rerun this calibration script."
  exit 1
fi

IMAGE_TOPIC="/${CAMERA_ID}/pylon_ros2_camera_node/image_raw"
CAMERA_TOPIC="/${CAMERA_ID}/pylon_ros2_camera_node"

echo "[INFO] Starting interactive calibration GUI..."
echo "       board_size=${BOARD_SIZE}, square_size=${SQUARE_SIZE_M}m"
echo "       image topic: ${IMAGE_TOPIC}"
echo "       camera topic: ${CAMERA_TOPIC}"

setup_qt_runtime_env

ros2 run camera_calibration cameracalibrator \
  --size "${BOARD_SIZE}" \
  --square "${SQUARE_SIZE_M}" \
  --camera_name "${CAMERA_NAME}" \
  image:="${IMAGE_TOPIC}" \
  camera:="${CAMERA_TOPIC}"

mkdir -p "$(dirname "$TARGET_CALIB_FILE")"

CANDIDATE_FILE="$HOME/.ros/camera_info/${CAMERA_NAME}.yaml"
if [[ -f "$CANDIDATE_FILE" ]]; then
  cp "$CANDIDATE_FILE" "$TARGET_CALIB_FILE"
else
  LATEST_CALIB_FILE="$(ls -t "$HOME"/.ros/camera_info/*.yaml 2>/dev/null | head -1 || true)"
  if [[ -z "$LATEST_CALIB_FILE" ]]; then
    echo "[ERROR] No calibration YAML found under ~/.ros/camera_info/."
    echo "        Ensure you clicked SAVE in the calibration GUI."
    exit 1
  fi
  cp "$LATEST_CALIB_FILE" "$TARGET_CALIB_FILE"
fi

echo "[INFO] Calibration saved to: $TARGET_CALIB_FILE"
echo "[INFO] Next steps:"
echo "  1) Rebuild wrapper package:"
echo "     colcon build --packages-select pylon_ros2_camera_wrapper --symlink-install"
echo "  2) Restart camera + apriltag pipeline and verify /apriltag/pose."
