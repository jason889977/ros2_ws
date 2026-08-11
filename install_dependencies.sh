#!/bin/bash
# ============================================================================
# Basler 相机 + ROS 2 二维码识别 完整依赖安装脚本
# 适用于: Ubuntu 22.04 (Jammy) + ROS 2 Humble
# 用法: chmod +x install_dependencies.sh && ./install_dependencies.sh
# ============================================================================

set -euo pipefail

echo "=========================================="
echo " Basler 相机 ROS 2 依赖安装脚本"
echo "=========================================="

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

REQUIRED_OS_VERSION="22.04"
REQUIRED_ROS_DISTRO="humble"

require_sudo() {
    if [ "$EUID" -ne 0 ]; then
        sudo -v || { echo -e "${RED}错误: 无法获取管理员权限${NC}"; exit 1; }
    fi
}

# 检查是否在 Ubuntu 系统
if [ ! -f /etc/os-release ]; then
    echo -e "${RED}错误: 无法识别操作系统${NC}"
    exit 1
fi

source /etc/os-release
if [ "$ID" != "ubuntu" ] || [ "$VERSION_ID" != "$REQUIRED_OS_VERSION" ]; then
    echo -e "${RED}错误: 当前系统为 ${PRETTY_NAME}，此脚本要求 Ubuntu ${REQUIRED_OS_VERSION}${NC}"
    exit 1
fi

require_sudo

echo -e "${GREEN}[1/6] 安装系统基础依赖...${NC}"
sudo apt-get update
sudo apt-get install -y \
    build-essential \
    cmake \
    git \
    wget \
    curl \
    libusb-1.0-0-dev \
    python3-opencv \
    python3-pip \
    python3-colcon-common-extensions \
    python3-rosdep

echo -e "${GREEN}[2/6] 检查 ROS 2 环境...${NC}"
if [ -z "${ROS_DISTRO:-}" ] && [ -f "/opt/ros/$REQUIRED_ROS_DISTRO/setup.bash" ]; then
    source "/opt/ros/$REQUIRED_ROS_DISTRO/setup.bash"
fi

if [ -z "${ROS_DISTRO:-}" ]; then
    echo -e "${RED}错误: ROS 2 环境变量未设置，请先安装并执行:${NC}"
    echo "source /opt/ros/$REQUIRED_ROS_DISTRO/setup.bash"
    exit 1
fi

if [ "$ROS_DISTRO" != "$REQUIRED_ROS_DISTRO" ]; then
    echo -e "${RED}错误: 当前 ROS_DISTRO=$ROS_DISTRO，要求为 $REQUIRED_ROS_DISTRO${NC}"
    echo "请执行: source /opt/ros/$REQUIRED_ROS_DISTRO/setup.bash"
    exit 1
fi
echo "检测到 ROS 2 版本: $ROS_DISTRO"

echo -e "${GREEN}[3/6] 安装 ROS 2 相关依赖...${NC}"
sudo apt-get install -y \
    ros-$ROS_DISTRO-image-transport \
    ros-$ROS_DISTRO-camera-info-manager \
    ros-$ROS_DISTRO-cv-bridge \
    ros-$ROS_DISTRO-launch \
    ros-$ROS_DISTRO-launch-ros

echo -e "${GREEN}[4/6] 使用 rosdep 补齐工作区依赖...${NC}"
if [ ! -f /etc/ros/rosdep/sources.list.d/20-default.list ]; then
    sudo rosdep init || true
fi
rosdep update

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_DIR="$SCRIPT_DIR"
if [ ! -d "$WORKSPACE_DIR/src" ]; then
    echo -e "${RED}错误: 未找到 src 目录，请在 ros2 工作区根目录执行该脚本${NC}"
    exit 1
fi

cd "$WORKSPACE_DIR"
rosdep install --from-paths src --ignore-src -r -y --rosdistro "$ROS_DISTRO"

echo -e "${GREEN}[5/6] 安装 pylon SDK (Basler 相机驱动)...${NC}"
echo -e "${YELLOW}请手动下载 pylon SDK:${NC}"
echo "1. 访问: https://www.baslerweb.com/zh-cn/downloads/software/"
echo "2. 选择: Linux x86 (64位) -> pylon 8.x Debian 安装包"
echo "3. 下载后放置到任意目录，然后执行以下命令:"
echo ""
echo "   cd <下载目录>"
echo "   tar -xzf pylon-*.tar.gz"
echo "   cd pylon-*"
echo "   sudo dpkg -i pylon_*.deb"
echo "   sudo apt-get install -f -y"
echo "   test -d /opt/pylon"
echo ""
read -r -p "按回车键继续（如果已安装 pylon）或取消脚本手动安装..."

# 检查 pylon 是否已安装
if [ ! -d "/opt/pylon" ] && [ ! -d "/opt/pylon6" ] && [ ! -d "/opt/pylon5" ]; then
    echo -e "${RED}错误: pylon SDK 未安装，请先安装 pylon SDK${NC}"
    exit 1
fi
echo -e "${GREEN}✓ pylon SDK 已安装${NC}"

echo -e "${GREEN}[6/6] 编译当前工作区...${NC}"

echo "使用当前工作区: $WORKSPACE_DIR"
source "/opt/ros/$ROS_DISTRO/setup.bash"

echo "编译当前工作区..."
colcon build --symlink-install --cmake-args -DCMAKE_BUILD_TYPE=Release

echo ""
echo "=========================================="
echo -e "${GREEN}✅ 所有依赖安装完成！${NC}"
echo "=========================================="
echo ""
echo "后续步骤:"
echo "1. source 工作空间:"
echo "   source $WORKSPACE_DIR/install/setup.bash"
echo ""
echo "2. 连接 Basler 相机并测试:"
echo "   ros2 launch pylon_ros2_camera_wrapper pylon_ros2_camera.launch.py"
echo ""
echo "3. 启动二维码识别节点:"
echo "   ros2 launch qrcode_detector qrcode_detector.launch.py"
echo ""
