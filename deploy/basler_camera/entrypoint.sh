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
    if [[ -z "${CAMERA_CONFIG_2:-}" ]]; then
      echo "[entrypoint] CAMERA_CONFIG_2 is required when CAMERA_ID_2 is set" >&2
      exit 64
    fi
    CAM2_CONFIG="$CAMERA_CONFIG_2"
    if [[ "$CAM2_CONFIG" == "$CAM1_CONFIG" ]]; then
      echo "[entrypoint] CAMERA_CONFIG_2 must differ from CAMERA_CONFIG_FILE" >&2
      exit 64
    fi
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

    _cleanup() {
      kill "$PID1" "$PID2" 2>/dev/null || true
      # 等待子进程退出，最多 10 秒
      for i in $(seq 1 10); do
        kill -0 "$PID1" 2>/dev/null || kill -0 "$PID2" 2>/dev/null || break
        sleep 1
      done
      # 仍未退出则强制杀死
      kill -9 "$PID1" "$PID2" 2>/dev/null || true
      wait "$PID1" "$PID2" 2>/dev/null || true
    }
    trap _cleanup EXIT INT TERM
    # 任一路流水线退出时立即结束另一条，避免故障被仍在运行的子进程遮蔽。
    set +e
    wait -n "$PID1" "$PID2"
    PIPELINE_EXIT=$?
    set -e
    kill "$PID1" "$PID2" 2>/dev/null || true
    wait "$PID1" 2>/dev/null || true
    wait "$PID2" 2>/dev/null || true
    if [[ $PIPELINE_EXIT -ne 0 ]]; then
      echo "[entrypoint] Pipeline exited with status $PIPELINE_EXIT" >&2
    fi
    exit "$PIPELINE_EXIT"
  else
    echo "[entrypoint] Launching single-camera pipeline: $CAM1_ID"
    exec ros2 launch industrial_vision_bringup vision_pipeline.launch.py "${CAM1_ARGS[@]}"
  fi
  exit 0
fi

exec "$@"
