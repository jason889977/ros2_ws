#!/usr/bin/env bash
set -eo pipefail

source /opt/ros/humble/setup.bash
source /opt/ros2_ws/install/setup.bash

resolve_startup_timeout_s() {
  local raw_timeout="${CAMERA_STARTUP_TIMEOUT_S:-120}"
  if ! [[ "$raw_timeout" =~ ^[0-9]+$ ]] || (( raw_timeout <= 0 )); then
    echo "[entrypoint] CAMERA_STARTUP_TIMEOUT_S must be a positive integer (seconds), got: ${raw_timeout}" >&2
    exit 64
  fi
  echo "$raw_timeout"
}

wait_for_camera_ready() {
  local camera_id="$1"
  local launch_pid="$2"
  local timeout_s="$3"
  local topic="/${camera_id}/pylon_ros2_camera_node/camera_info"
  local deadline=$((SECONDS + timeout_s))

  while (( SECONDS < deadline )); do
    if ! kill -0 "$launch_pid" 2>/dev/null; then
      wait "$launch_pid" 2>/dev/null || true
      echo "[entrypoint] Pipeline process exited before ${topic} became available." >&2
      return 2
    fi

    if timeout 3 ros2 topic echo "$topic" --once >/dev/null 2>&1; then
      echo "[entrypoint] Camera ready on topic: ${topic}"
      return 0
    fi

    sleep 1
  done

  echo "[entrypoint] Camera startup timeout (${timeout_s}s): ${topic} has no data. Possible causes: camera unavailable or occupied by another application." >&2
  return 1
}

# Build the launch argument array for the single camera pipeline.
# Results are stored in the global array BUILD_CAMERA_ARGS_RESULT.
build_camera_args() {
  local config_path="$1"
  BUILD_CAMERA_ARGS_RESULT=(
    camera_id:="${CAMERA_ID:-my_camera}"
    camera_config:="$config_path"
    camera_frame:="${CAMERA_FRAME:-basler_aca2500_106611_18}"
    mtu_size:="${CAMERA_MTU_SIZE:-1500}"
    respawn:="${CAMERA_RESPAWN:-true}"
    startup_user_set:="${CAMERA_STARTUP_USER_SET:-Default}"
    scanner_ip:="${SCANNER_IP:-172.31.0.91}"
    scanner_port:="${SCANNER_PORT:-9004}"
    reconnect_interval_s:="${RECONNECT_INTERVAL_S:-5.0}"
    binning_x:="${BINNING_X:-0}"
    binning_y:="${BINNING_Y:-0}"
    apriltag_size:="${APRILTAG_SIZE:-0.0}"
    enable_apriltag:="${ENABLE_APRILTAG:-true}"
    enable_keyence:="${ENABLE_KEYENCE:-true}"
    web_port:="${WEB_PORT:-8080}"
    enable_web_dashboard:="${ENABLE_WEB_DASHBOARD:-true}"
    archive_dir:="${ARCHIVE_DIR:-}"
    event_log_dir:="${EVENT_LOG_DIR:-/var/log/vision}"
    calibration_dir:="${CALIBRATION_DIR:-/var/lib/vision/calibration}"
  )
  if [[ -n "${APRILTAG_IDS:-}" ]]; then
    BUILD_CAMERA_ARGS_RESULT+=(apriltag_ids:="$APRILTAG_IDS")
  fi
}

_cleanup_procs() {
  local pids=("$@")
  kill -- "${pids[@]}" 2>/dev/null || kill "${pids[@]}" 2>/dev/null || true
  for i in $(seq 1 10); do
    local alive=false
    for pid in "${pids[@]}"; do
      kill -0 "$pid" 2>/dev/null && alive=true
    done
    $alive || break
    sleep 1
  done
  kill -9 -- "${pids[@]}" 2>/dev/null || kill -9 "${pids[@]}" 2>/dev/null || true
  wait "${pids[@]}" 2>/dev/null || true
}

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
# Unified vision pipeline (single Basler camera)
# ---------------------------------------------------------------------------
if [[ "${*}" == *"vision_pipeline.launch.py"* ]]; then
  STARTUP_TIMEOUT_S="$(resolve_startup_timeout_s)"
  CAM_ID="${CAMERA_ID:-my_camera}"
  CAM_CONFIG="${CAMERA_CONFIG_FILE:-/opt/ros2_ws/deploy/basler_camera/config/aca2500_106611_18.yaml}"

  if [[ ! -f "$CAM_CONFIG" ]]; then
    echo "[entrypoint] Camera config not found: $CAM_CONFIG" >&2
    exit 64
  fi

  WEB_PORT_VAL="${WEB_PORT:-8080}"

  # Clean up stale processes that might hold the web port or camera device.
  # In Docker this is a no-op (fresh container); on bare metal it prevents
  # "address already in use" / "device controlled by another application" errors.
  _cleanup_stale() {
    local port="$1"
    local stale_pids=()

    # Kill any process listening on the web port
    if command -v fuser >/dev/null 2>&1; then
      local port_pids
      port_pids="$(fuser -k "${port}"/tcp 2>/dev/null || true)"
      if [[ -n "$port_pids" ]]; then
        echo "[entrypoint] Killed stale processes on port ${port}: ${port_pids}"
      fi
    fi

    # Kill leftover ROS 2 / dashboard / calibration processes
    local patterns=('component_container_mt' 'web_dashboard' 'aprilgrid_calibration_server' 'apriltag_pose_reader' 'vision_status_aggregator')
    for pat in "${patterns[@]}"; do
      local pids
      pids="$(pgrep -f "$pat" 2>/dev/null || true)"
      if [[ -n "$pids" ]]; then
        echo "[entrypoint] Killing stale ${pat} processes: ${pids}"
        # shellcheck disable=SC2086
        kill -9 $pids 2>/dev/null || true
      fi
    done

    sleep 1
  }

  _cleanup_stale "$WEB_PORT_VAL"

  build_camera_args "$CAM_CONFIG"
  CAM_ARGS=("${BUILD_CAMERA_ARGS_RESULT[@]}")

  echo "[entrypoint] Launching vision pipeline: $CAM_ID (apriltag=${ENABLE_APRILTAG:-true}, keyence=${ENABLE_KEYENCE:-true})"
  ros2 launch industrial_vision_bringup vision_pipeline.launch.py "${CAM_ARGS[@]}" &
  PID=$!
  trap "_cleanup_procs $PID" EXIT INT TERM

  if ! wait_for_camera_ready "$CAM_ID" "$PID" "$STARTUP_TIMEOUT_S"; then exit 70; fi
  wait "$PID"
  exit $?
fi

exec "$@"
