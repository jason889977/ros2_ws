#!/bin/bash
# ============================================================================
# ROS2 工作区迁移脚本: Ubuntu 22.04 + ROS 2 Humble
# 作用:
#   1) 校验系统与 ROS 发行版
#   2) 清理旧构建产物
#   3) 通过 rosdep 安装依赖
#   4) 全量重建并做关键校验
# 用法:
#   chmod +x scripts/migrate_to_humble.sh
#   ./scripts/migrate_to_humble.sh
# ============================================================================

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

REQUIRED_OS_VERSION="22.04"
REQUIRED_ROS_DISTRO="humble"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "=========================================="
echo " ROS 2 Humble 迁移脚本"
echo "=========================================="
echo "工作区: $WORKSPACE_DIR"

if [ ! -f /etc/os-release ]; then
  echo -e "${RED}错误: 无法识别操作系统${NC}"
  exit 1
fi

source /etc/os-release
if [ "$ID" != "ubuntu" ] || [ "$VERSION_ID" != "$REQUIRED_OS_VERSION" ]; then
  echo -e "${RED}错误: 当前系统为 ${PRETTY_NAME}，要求 Ubuntu ${REQUIRED_OS_VERSION}${NC}"
  exit 1
fi

echo -e "${GREEN}[1/6] 校验 ROS 2 环境...${NC}"
if [ -z "${ROS_DISTRO:-}" ] && [ -f "/opt/ros/$REQUIRED_ROS_DISTRO/setup.bash" ]; then
  source "/opt/ros/$REQUIRED_ROS_DISTRO/setup.bash"
fi

if [ -z "${ROS_DISTRO:-}" ]; then
  echo -e "${RED}错误: ROS_DISTRO 未设置，请先安装并加载 ROS 2 Humble${NC}"
  echo "执行: source /opt/ros/$REQUIRED_ROS_DISTRO/setup.bash"
  exit 1
fi

if [ "$ROS_DISTRO" != "$REQUIRED_ROS_DISTRO" ]; then
  echo -e "${RED}错误: 当前 ROS_DISTRO=$ROS_DISTRO，要求 $REQUIRED_ROS_DISTRO${NC}"
  exit 1
fi

echo -e "${GREEN}[2/6] 清理旧构建产物...${NC}"
cd "$WORKSPACE_DIR"
rm -rf build install log

echo -e "${GREEN}[3/6] 安装基础工具...${NC}"
sudo apt-get update
sudo apt-get install -y \
  python3-colcon-common-extensions \
  python3-rosdep \
  python3-opencv \
  python3-pip \
  build-essential \
  cmake

echo -e "${GREEN}[4/6] 安装 ROS 依赖...${NC}"
if [ ! -f /etc/ros/rosdep/sources.list.d/20-default.list ]; then
  sudo rosdep init || true
fi
rosdep update
rosdep install --from-paths src --ignore-src -r -y --rosdistro "$ROS_DISTRO"

echo -e "${GREEN}[5/6] 重新构建工作区...${NC}"
source "/opt/ros/$ROS_DISTRO/setup.bash"
colcon build --symlink-install --cmake-args -DCMAKE_BUILD_TYPE=Release

echo -e "${GREEN}[6/6] 构建后关键校验...${NC}"
if grep -R --line-number "/opt/ros/" install/setup.bash install/local_setup.bash 2>/dev/null | grep -v "/opt/ros/$ROS_DISTRO" >/dev/null; then
  echo -e "${RED}错误: install 空间仍引用非当前 ROS 发行版，请检查环境污染${NC}"
  exit 1
fi

CURRENT_PY_MM="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
if grep -R --line-number "python3\\.[0-9]\+" install/ 2>/dev/null | grep -v "python${CURRENT_PY_MM}" >/dev/null; then
  echo -e "${YELLOW}警告: install 空间发现与当前 Python 版本不一致的路径，请核对运行时${NC}"
else
  echo -e "${GREEN}✓ Python 路径与当前运行时一致${NC}"
fi

echo ""
echo "=========================================="
echo -e "${GREEN}✅ 迁移完成: Ubuntu 22.04 + ROS 2 Humble${NC}"
echo "=========================================="
echo ""
echo "后续请执行:"
echo "source /opt/ros/$ROS_DISTRO/setup.bash"
echo "source $WORKSPACE_DIR/install/setup.bash"
