#!/usr/bin/env bash
set -euo pipefail

WS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RVIZ_CONFIG="$WS_DIR/deploy/basler_camera/config/rviz/my_camera_image_raw.rviz"

cd "$WS_DIR"
# ROS setup 脚本在部分环境会访问未定义变量，临时关闭 nounset 以避免中断。
set +u
source /opt/ros/humble/setup.bash
source install/setup.bash
set -u

if [[ ! -f "$RVIZ_CONFIG" ]]; then
  echo "[ERROR] RViz config not found: $RVIZ_CONFIG"
  exit 1
fi

exec rviz2 -d "$RVIZ_CONFIG"
