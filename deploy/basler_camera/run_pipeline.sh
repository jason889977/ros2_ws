#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# run_pipeline.sh – bare-metal wrapper for the vision pipeline
#
# Automatically cleans up stale ROS 2 / dashboard / calibration processes
# before launch and on exit, preventing "port already in use" and
# "camera controlled by another application" errors.
#
# Usage:
#   ./run_pipeline.sh [launch arguments...]
#   ./run_pipeline.sh camera_id:=my_camera enable_apriltag:=true
#
# In Docker this script is not used (entrypoint.sh handles cleanup there).
# ---------------------------------------------------------------------------
set -eo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

WEB_PORT="${WEB_PORT:-8080}"
LAUNCH_PID=""

# Patterns for stale ROS 2 / vision processes
STALE_PATTERNS=(
  'component_container_mt'
  'component_container_py'
  'web_dashboard'
  'aprilgrid_calibration_server'
  'apriltag_pose_reader'
  'vision_status_aggregator'
  'event_logger'
  'keyence_sr_node'
)

cleanup_stale() {
  local killed=0
  for pat in "${STALE_PATTERNS[@]}"; do
    local pids
    pids="$(pgrep -f "$pat" 2>/dev/null || true)"
    if [[ -n "$pids" ]]; then
      echo "[run_pipeline] Killing stale ${pat}: ${pids}"
      # shellcheck disable=SC2086
      kill -9 $pids 2>/dev/null || true
      killed=1
    fi
  done
  # Free the web port
  if command -v fuser >/dev/null 2>&1; then
    fuser -k "${WEB_PORT}"/tcp 2>/dev/null || true
  fi
  if [[ "$killed" == "1" ]]; then
    sleep 2
  fi
}

shutdown_handler() {
  echo ""
  echo "[run_pipeline] Shutting down..."
  if [[ -n "${LAUNCH_PID:-}" ]] && kill -0 "$LAUNCH_PID" 2>/dev/null; then
    kill -INT "$LAUNCH_PID" 2>/dev/null || true
    # Wait up to 10s for graceful shutdown
    local waited=0
    while kill -0 "$LAUNCH_PID" 2>/dev/null && [[ $waited -lt 50 ]]; do
      sleep 0.2
      waited=$((waited + 1))
    done
    # Force kill if still alive
    kill -9 "$LAUNCH_PID" 2>/dev/null || true
    wait "$LAUNCH_PID" 2>/dev/null || true
  fi
  cleanup_stale
  echo "[run_pipeline] Done."
}

trap shutdown_handler EXIT INT TERM

# ---- pre-launch cleanup --------------------------------------------------
echo "[run_pipeline] Cleaning up stale processes..."
cleanup_stale

# ---- source ROS 2 --------------------------------------------------------
source /opt/ros/humble/setup.bash
if [[ -f "$WORKSPACE_ROOT/install/setup.bash" ]]; then
  source "$WORKSPACE_ROOT/install/setup.bash"
fi

# Pylon SDK library path (if present)
PYLON_LIB="${HOME}/.local/pylon-sdk-root/opt/pylon/lib"
if [[ -d "$PYLON_LIB" ]]; then
  export LD_LIBRARY_PATH="${PYLON_LIB}:${LD_LIBRARY_PATH:-}"
fi

# ---- default camera config -----------------------------------------------
CAMERA_CONFIG="${CAMERA_CONFIG_FILE:-$SCRIPT_DIR/config/aca2500_106611_18.yaml}"

# ---- launch --------------------------------------------------------------
echo "[run_pipeline] Launching vision pipeline (port ${WEB_PORT})..."
cd "$WORKSPACE_ROOT"

ros2 launch industrial_vision_bringup vision_pipeline.launch.py \
  camera_id:="${CAMERA_ID:-my_camera}" \
  camera_config:="$CAMERA_CONFIG" \
  enable_apriltag:="${ENABLE_APRILTAG:-true}" \
  enable_keyence:="${ENABLE_KEYENCE:-false}" \
  apriltag_ids:="${APRILTAG_IDS:-0}" \
  apriltag_size:="${APRILTAG_SIZE:-0.05}" \
  "$@" &
LAUNCH_PID=$!

wait "$LAUNCH_PID"
