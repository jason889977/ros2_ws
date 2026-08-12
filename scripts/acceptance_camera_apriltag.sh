#!/usr/bin/env bash
set -euo pipefail

# One-shot acceptance for Basler camera + AprilTag full path (A-F):
# A camera stream, B detections, C 6D pose topics, D TF2 transform,
# E RViz startup, F key error gate.

WORKSPACE_DIR="/home/ubuntu/ros2_ws"
ROS_SETUP="/opt/ros/humble/setup.bash"
WS_SETUP="$WORKSPACE_DIR/install/setup.bash"
CAMERA_ID="${CAMERA_ID:-basler_106611_18}"
CAMERA_CONFIG="${CAMERA_CONFIG:-$WORKSPACE_DIR/install/pylon_ros2_camera_wrapper/share/pylon_ros2_camera_wrapper/config/aca2500_106611_18.yaml}"
ACCEPTANCE_WINDOW="${ACCEPTANCE_WINDOW:-30}"
TOPIC_TIMEOUT="${TOPIC_TIMEOUT:-8}"
NO_TIME_LIMIT="${NO_TIME_LIMIT:-false}"
ENABLE_RVIZ="${ENABLE_RVIZ:-true}"
KEEP_ALIVE="${KEEP_ALIVE:-false}"
REPORT_DIR="${REPORT_DIR:-$WORKSPACE_DIR/log/acceptance}"

IMAGE_TOPIC=""
CAM_INFO_TOPIC=""
CAMERA_PID=""
APRILTAG_PID=""
RVIZ_PID=""

RESULT_TSV=""
REPORT_MD=""
REPORT_JSON=""

usage() {
  cat <<EOF
Usage: $0 [options]

Options:
  --camera-id <id>            Camera namespace (default: basler_106611_18)
  --camera-config <path>      Camera config YAML path
  --window <seconds>          Acceptance window in seconds (default: 30)
  --topic-timeout <seconds>   Per-topic wait timeout for --once checks (default: 8)
  --no-time-limit <true|false>  Disable time limits for node/topic waits (default: false)
  --enable-rviz <true|false>  Validate RViz startup (default: true)
  --keep-alive <true|false>   Keep launched processes after acceptance (default: false)
  --report-dir <path>         Report output directory (default: /home/ubuntu/ros2_ws/log/acceptance)
  -h, --help                  Show this help message

Exit codes:
  0  All checks passed
  1  Preflight failed
  2  Runtime acceptance failed
  3  Internal/unexpected error
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --camera-id)
      CAMERA_ID="${2:-}"
      shift 2
      ;;
    --camera-config)
      CAMERA_CONFIG="${2:-}"
      shift 2
      ;;
    --window)
      ACCEPTANCE_WINDOW="${2:-}"
      shift 2
      ;;
    --topic-timeout)
      TOPIC_TIMEOUT="${2:-}"
      shift 2
      ;;
    --no-time-limit)
      NO_TIME_LIMIT="${2:-}"
      shift 2
      ;;
    --enable-rviz)
      ENABLE_RVIZ="${2:-}"
      shift 2
      ;;
    --keep-alive)
      KEEP_ALIVE="${2:-}"
      shift 2
      ;;
    --report-dir)
      REPORT_DIR="${2:-}"
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

if ! [[ "$ACCEPTANCE_WINDOW" =~ ^[0-9]+$ ]]; then
  echo "[ERROR] --window must be an integer >= 0"
  exit 1
fi

if ! [[ "$TOPIC_TIMEOUT" =~ ^[0-9]+$ ]]; then
  echo "[ERROR] --topic-timeout must be an integer >= 0"
  exit 1
fi

if [[ "$NO_TIME_LIMIT" != "true" && "$NO_TIME_LIMIT" != "false" ]]; then
  echo "[ERROR] --no-time-limit must be true or false"
  exit 1
fi

if [[ "$NO_TIME_LIMIT" == "true" ]]; then
  ACCEPTANCE_WINDOW=0
  TOPIC_TIMEOUT=0
fi

if [[ "$ACCEPTANCE_WINDOW" -gt 0 && "$TOPIC_TIMEOUT" -gt "$ACCEPTANCE_WINDOW" ]]; then
  TOPIC_TIMEOUT="$ACCEPTANCE_WINDOW"
fi

if [[ "$ENABLE_RVIZ" != "true" && "$ENABLE_RVIZ" != "false" ]]; then
  echo "[ERROR] --enable-rviz must be true or false"
  exit 1
fi

if [[ "$KEEP_ALIVE" != "true" && "$KEEP_ALIVE" != "false" ]]; then
  echo "[ERROR] --keep-alive must be true or false"
  exit 1
fi

mkdir -p "$REPORT_DIR"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
RESULT_TSV="$REPORT_DIR/apriltag_acceptance_${TIMESTAMP}.tsv"
REPORT_MD="$REPORT_DIR/apriltag_acceptance_${TIMESTAMP}.md"
REPORT_JSON="$REPORT_DIR/apriltag_acceptance_${TIMESTAMP}.json"
: > "$RESULT_TSV"

cleanup() {
  local exit_code=$?

  if [[ "$KEEP_ALIVE" == "false" || "$exit_code" -ne 0 ]]; then
    if [[ -n "$RVIZ_PID" ]] && kill -0 "$RVIZ_PID" 2>/dev/null; then
      kill "$RVIZ_PID" 2>/dev/null || true
    fi
    if [[ -n "$APRILTAG_PID" ]] && kill -0 "$APRILTAG_PID" 2>/dev/null; then
      kill "$APRILTAG_PID" 2>/dev/null || true
    fi
    if [[ -n "$CAMERA_PID" ]] && kill -0 "$CAMERA_PID" 2>/dev/null; then
      kill "$CAMERA_PID" 2>/dev/null || true
    fi
  fi
}

trap cleanup EXIT INT TERM

record_result() {
  local item="$1"
  local status="$2"
  local evidence="$3"
  local advice="$4"
  printf '%s\t%s\t%s\t%s\n' "$item" "$status" "$evidence" "$advice" >> "$RESULT_TSV"
}

wait_for_node() {
  local node="$1"
  local timeout_s="$2"

  if [[ "$timeout_s" -eq 0 ]]; then
    while true; do
      if ros2 node list 2>/dev/null | grep -qx "$node"; then
        return 0
      fi
      sleep 1
    done
  fi

  local start
  start=$(date +%s)

  while true; do
    if ros2 node list 2>/dev/null | grep -qx "$node"; then
      return 0
    fi
    if (( $(date +%s) - start >= timeout_s )); then
      return 1
    fi
    sleep 1
  done
}

wait_for_topic_once() {
  local topic="$1"
  local timeout_s="$2"
  local out_file="$3"

  if [[ "$timeout_s" -eq 0 ]]; then
    ros2 topic echo "$topic" --once > "$out_file" 2>&1
    return $?
  fi

  timeout "${timeout_s}s" ros2 topic echo "$topic" --once > "$out_file" 2>&1
}

start_topic_probe() {
  local topic="$1"
  local timeout_s="$2"
  local out_file="$3"
  wait_for_topic_once "$topic" "$timeout_s" "$out_file" &
  echo $!
}

get_latest_camera_log() {
  ls -1t /home/ubuntu/.ros/log/pylon_ros2_camera_wrapper_*.log 2>/dev/null | head -n 1 || true
}

echo "[INFO] Preflight checks..."
for cmd in ros2 colcon timeout python3; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "[ERROR] Missing command: $cmd"
    exit 1
  fi
done

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

if ! ros2 pkg executables apriltag_ros | grep -q 'apriltag_node'; then
  echo "[ERROR] apriltag_ros executable not found. Please install ros-humble-apriltag-ros."
  exit 1
fi

echo "[INFO] Building required runtime packages..."
colcon build --packages-select pylon_ros2_camera_wrapper apriltag_pose_reader --symlink-install >/dev/null

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

if [[ "$ENABLE_RVIZ" == "true" && ! -f "$WORKSPACE_DIR/scripts/open_camera_rviz.sh" ]]; then
  echo "[ERROR] RViz helper script missing: $WORKSPACE_DIR/scripts/open_camera_rviz.sh"
  exit 1
fi

echo "[INFO] Restarting camera and AprilTag processes..."
pkill -f "apriltag_pose_reader|apriltag_node|apriltag_pose_reader.launch.py" || true
pkill -f "pylon_ros2_camera_node|pylon_ros2_camera.launch.py|pylon_ros2_camera_wrapper" || true
sleep 2

ros2 launch pylon_ros2_camera_wrapper pylon_ros2_camera.launch.py \
  camera_id:="$CAMERA_ID" \
  config_file:="$CAMERA_CONFIG" \
  > "$REPORT_DIR/camera_launch_${TIMESTAMP}.log" 2>&1 &
CAMERA_PID=$!

IMAGE_TOPIC="/$CAMERA_ID/pylon_ros2_camera_node/image_raw"
CAM_INFO_TOPIC="/$CAMERA_ID/pylon_ros2_camera_node/camera_info"

if ! wait_for_node "/$CAMERA_ID/pylon_ros2_camera_node" "$ACCEPTANCE_WINDOW"; then
  record_result "A. camera_node" "FAIL" "Node /$CAMERA_ID/pylon_ros2_camera_node not found in ${ACCEPTANCE_WINDOW}s" "Check camera cable, device_user_id, and config_file"
  echo "[ERROR] Camera node did not become ready"
  exit 2
fi

ros2 launch apriltag_pose_reader apriltag_pose_reader.launch.py \
  image_topic:="$IMAGE_TOPIC" \
  camera_info_topic:="$CAM_INFO_TOPIC" \
  tag_id:=-1 \
  > "$REPORT_DIR/apriltag_launch_${TIMESTAMP}.log" 2>&1 &
APRILTAG_PID=$!

wait_for_node "/apriltag" "$ACCEPTANCE_WINDOW" || true
wait_for_node "/apriltag_pose_reader" "$ACCEPTANCE_WINDOW" || true

if [[ "$ENABLE_RVIZ" == "true" ]]; then
  "$WORKSPACE_DIR/scripts/open_camera_rviz.sh" > "$REPORT_DIR/rviz_${TIMESTAMP}.log" 2>&1 &
  RVIZ_PID=$!
  sleep 3
fi

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"; cleanup' EXIT INT TERM

image_raw_file="$TMP_DIR/image_raw.txt"
cam_info_file="$TMP_DIR/camera_info.txt"
detections_file="$TMP_DIR/detections.txt"
pose_file="$TMP_DIR/pose.txt"
transform_file="$TMP_DIR/transform.txt"

# Probe all key topics concurrently to avoid serial timeout skew.
image_pid="$(start_topic_probe "$IMAGE_TOPIC" "$TOPIC_TIMEOUT" "$image_raw_file")"
cam_info_pid="$(start_topic_probe "$CAM_INFO_TOPIC" "$TOPIC_TIMEOUT" "$cam_info_file")"
detections_pid="$(start_topic_probe "/detections" "$TOPIC_TIMEOUT" "$detections_file")"
pose_pid="$(start_topic_probe "/apriltag/pose" "$TOPIC_TIMEOUT" "$pose_file")"
transform_pid="$(start_topic_probe "/apriltag/transform" "$TOPIC_TIMEOUT" "$transform_file")"

# A: image_raw and camera_info availability
if wait "$image_pid" && wait "$cam_info_pid"; then
  record_result "A. camera_stream" "PASS" "Received $IMAGE_TOPIC and $CAM_INFO_TOPIC" "None"
else
  record_result "A. camera_stream" "FAIL" "No message on $IMAGE_TOPIC or $CAM_INFO_TOPIC in ${ACCEPTANCE_WINDOW}s" "Verify camera node, transport, and calibration config"
fi

# B: detections availability
if wait "$detections_pid"; then
  family="$(awk '/^[[:space:]]*family:[[:space:]]*/ {print $2; exit}' "$detections_file" 2>/dev/null || true)"
  det_id="$(awk '/^[[:space:]]*id:[[:space:]]*-?[0-9]+/ {print $2; exit}' "$detections_file" 2>/dev/null || true)"
  hamming="$(awk '/^[[:space:]]*hamming:[[:space:]]*/ {print $2; exit}' "$detections_file" 2>/dev/null || true)"
  margin="$(awk '/^[[:space:]]*decision_margin:[[:space:]]*/ {print $2; exit}' "$detections_file" 2>/dev/null || true)"
  record_result "B. detections" "PASS" "family=${family:-n/a}, id=${det_id:-n/a}, hamming=${hamming:-n/a}, decision_margin=${margin:-n/a}" "None"
else
  record_result "B. detections" "FAIL" "No /detections message in ${ACCEPTANCE_WINDOW}s" "Ensure AprilTag is visible and detector parameters match the tag"
fi

# C: 6D pose topics availability
c_pass=true
if ! wait "$pose_pid"; then
  c_pass=false
fi
if ! wait "$transform_pid"; then
  c_pass=false
fi
if [[ "$c_pass" == "true" ]]; then
  record_result "C. pose_transform" "PASS" "Received /apriltag/pose and /apriltag/transform" "None"
else
  record_result "C. pose_transform" "FAIL" "Missing /apriltag/pose or /apriltag/transform in ${ACCEPTANCE_WINDOW}s" "Check apriltag_pose_reader and /tf stream"
fi

# D: TF2 transform check
parent_frame=""
child_frame=""
if [[ -f "$transform_file" ]]; then
  parent_frame="$(awk '/^[[:space:]]*frame_id:[[:space:]]*/ {print $2; exit}' "$transform_file" 2>/dev/null | tr -d '"' || true)"
  child_frame="$(awk '/^[[:space:]]*child_frame_id:[[:space:]]*/ {print $2; exit}' "$transform_file" 2>/dev/null | tr -d '"' || true)"
fi
parent_frame="${parent_frame#\'}"
parent_frame="${parent_frame%\'}"
child_frame="${child_frame#\'}"
child_frame="${child_frame%\'}"

tf_file="$TMP_DIR/tf2.txt"
if [[ -n "$parent_frame" && -n "$child_frame" ]]; then
  set +e
  timeout 6s ros2 run tf2_ros tf2_echo "$parent_frame" "$child_frame" > "$tf_file" 2>&1
  tf_status=$?
  set -e

  if [[ ( "$tf_status" -eq 0 || "$tf_status" -eq 124 ) && -s "$tf_file" ]] && \
     ! grep -E "Invalid frame ID|Lookup would require extrapolation|does not exist" -i "$tf_file" >/dev/null; then
    record_result "D. tf2" "PASS" "tf2_echo $parent_frame -> $child_frame produced transform output" "None"
  else
    record_result "D. tf2" "FAIL" "Failed tf2_echo for parent=${parent_frame:-n/a}, child=${child_frame:-n/a}" "Confirm /apriltag/transform frame ids and TF tree continuity"
  fi
else
  record_result "D. tf2" "FAIL" "Failed tf2_echo for parent=${parent_frame:-n/a}, child=${child_frame:-n/a}" "Confirm /apriltag/transform frame ids and TF tree continuity"
fi

# E: RViz startup
if [[ "$ENABLE_RVIZ" == "true" ]]; then
  if [[ -n "$RVIZ_PID" ]] && kill -0 "$RVIZ_PID" 2>/dev/null; then
    record_result "E. rviz" "PASS" "rviz2 process is alive (pid=$RVIZ_PID)" "None"
  else
    record_result "E. rviz" "FAIL" "rviz2 failed to start or exited early" "Check display environment and RViz config"
  fi
else
  record_result "E. rviz" "SKIP" "RViz check disabled by --enable-rviz=false" "None"
fi

# F: key camera error gate
latest_log="$(get_latest_camera_log)"
if [[ -n "$latest_log" ]]; then
  error_lines="$(grep -E "3774873620|incompletely grabbed|Grab was not successful" -i "$latest_log" || true)"
  if [[ -z "$error_lines" ]]; then
    record_result "F. key_error_gate" "PASS" "No repeated critical grab errors in $latest_log" "None"
  else
    short_err="$(echo "$error_lines" | head -n 3 | tr '\n' '; ')"
    record_result "F. key_error_gate" "FAIL" "$short_err" "Check NIC/cable/MTU/inter-packet delay and consider rollback"
  fi
else
  record_result "F. key_error_gate" "FAIL" "No pylon camera log file found under ~/.ros/log" "Check camera launch and logging path"
fi

# Build markdown report
{
  echo "# AprilTag 自动验收报告"
  echo
  echo "- 时间: $(date '+%F %T')"
  echo "- 工作区: $WORKSPACE_DIR"
  echo "- 相机命名空间: /$CAMERA_ID"
  echo "- 相机配置: $CAMERA_CONFIG"
  if [[ "$ACCEPTANCE_WINDOW" -eq 0 ]]; then
    echo "- 验收窗口: 无时间限制"
  else
    echo "- 验收窗口: ${ACCEPTANCE_WINDOW}s"
  fi
  if [[ "$TOPIC_TIMEOUT" -eq 0 ]]; then
    echo "- Topic 等待: 无时间限制"
  else
    echo "- Topic 等待: ${TOPIC_TIMEOUT}s"
  fi
  echo "- RViz 检查: $ENABLE_RVIZ"
  echo
  echo "| 检查项 | 结果 | 证据 | 建议 |"
  echo "|---|---|---|---|"
  while IFS=$'\t' read -r item status evidence advice; do
    safe_evidence="${evidence//|/\\|}"
    safe_advice="${advice//|/\\|}"
    echo "| $item | $status | $safe_evidence | $safe_advice |"
  done < "$RESULT_TSV"
} > "$REPORT_MD"

# Build JSON report
python3 - "$RESULT_TSV" "$REPORT_JSON" <<'PY'
import json
import sys
from pathlib import Path

in_path = Path(sys.argv[1])
out_path = Path(sys.argv[2])
items = []
for line in in_path.read_text().splitlines():
    if not line.strip():
        continue
    item, status, evidence, advice = line.split('\t', 3)
    items.append({
        "item": item,
        "status": status,
        "evidence": evidence,
        "advice": advice,
    })

summary = {
    "passed": sum(1 for i in items if i["status"] == "PASS"),
    "failed": sum(1 for i in items if i["status"] == "FAIL"),
    "skipped": sum(1 for i in items if i["status"] == "SKIP"),
    "total": len(items),
    "items": items,
}
out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2))
PY

FAIL_COUNT="$(awk -F '\t' '$2 == "FAIL" {count++} END {print count+0}' "$RESULT_TSV")"

echo "[INFO] Acceptance report generated:"
echo "  - $REPORT_MD"
echo "  - $REPORT_JSON"

if [[ "$FAIL_COUNT" -gt 0 ]]; then
  echo "[ERROR] AprilTag acceptance failed with $FAIL_COUNT failing check(s)."
  exit 2
fi

echo "[INFO] AprilTag acceptance PASSED."
exit 0
