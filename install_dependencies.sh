#!/bin/bash
# ============================================================================
# Basler 相机 + QR + AprilTag + Keyence ROS 2 完整依赖安装脚本
# 适用于: Ubuntu 22.04 (Jammy) + ROS 2 Humble
# 用法: bash install_dependencies.sh
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
NUMPY_VERSION="1.26.4"
OPENCV_VERSION="4.8.1.78"

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

echo -e "${GREEN}[1/7] 安装系统基础依赖...${NC}"
sudo apt-get update
sudo apt-get install -y \
    build-essential \
    cmake \
    pkg-config \
    git \
    wget \
    curl \
    libusb-1.0-0-dev \
    python3-opencv \
    python3-pip \
    python3-setuptools \
    python3-dev \
    python3-pytest \
    python3-colcon-common-extensions \
    python3-rosdep \
    iproute2 \
    ethtool \
    xterm \
    gdb \
    fonts-dejavu-core

echo -e "${GREEN}[2/7] 安装并检查 ROS 2 Humble...${NC}"
if ! apt-cache show "ros-$REQUIRED_ROS_DISTRO-desktop" >/dev/null 2>&1; then
    echo -e "${RED}错误: 未找到 ROS 2 Humble apt 软件源。${NC}"
    echo "请先按照 https://docs.ros.org/en/humble/Installation/Ubuntu-Install-Debs.html 配置 ROS 2 软件源。"
    exit 1
fi
sudo apt-get install -y "ros-$REQUIRED_ROS_DISTRO-desktop"

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

echo -e "${GREEN}[3/7] 安装 ROS 2 相关依赖...${NC}"
sudo apt-get install -y \
    ros-$ROS_DISTRO-ament-cmake \
    ros-$ROS_DISTRO-ament-lint-auto \
    ros-$ROS_DISTRO-ament-lint-common \
    ros-$ROS_DISTRO-rclpy \
    ros-$ROS_DISTRO-rclcpp \
    ros-$ROS_DISTRO-rclcpp-action \
    ros-$ROS_DISTRO-rclcpp-components \
    ros-$ROS_DISTRO-rcutils \
    ros-$ROS_DISTRO-action-msgs \
    ros-$ROS_DISTRO-builtin-interfaces \
    ros-$ROS_DISTRO-geometry-msgs \
    ros-$ROS_DISTRO-sensor-msgs \
    ros-$ROS_DISTRO-std-msgs \
    ros-$ROS_DISTRO-std-srvs \
    ros-$ROS_DISTRO-tf2-msgs \
    ros-$ROS_DISTRO-tf2-ros \
    ros-$ROS_DISTRO-rosidl-default-generators \
    ros-$ROS_DISTRO-rosidl-default-runtime \
    ros-$ROS_DISTRO-launch \
    ros-$ROS_DISTRO-launch-ros \
    ros-$ROS_DISTRO-ament-index-python \
    ros-$ROS_DISTRO-cv-bridge \
    ros-$ROS_DISTRO-image-transport \
    ros-$ROS_DISTRO-image-geometry \
    ros-$ROS_DISTRO-camera-info-manager \
    ros-$ROS_DISTRO-camera-calibration \
    ros-$ROS_DISTRO-diagnostic-updater \
    ros-$ROS_DISTRO-pcl-ros \
    ros-$ROS_DISTRO-apriltag-ros \
    ros-$ROS_DISTRO-apriltag-msgs \
    ros-$ROS_DISTRO-rviz2 \
    ros-$ROS_DISTRO-rqt-image-view

echo -e "${GREEN}[4/7] 安装已验证的 Python 图像依赖...${NC}"
python3 -m pip uninstall -y \
    opencv-python \
    opencv-python-headless \
    opencv-contrib-python \
    opencv-contrib-python-headless || true
python3 -m pip install --user --no-cache-dir \
    "numpy==$NUMPY_VERSION" \
    "opencv-contrib-python-headless==$OPENCV_VERSION"

python3 - <<PY
import cv2
import numpy

assert cv2.__version__ == "${OPENCV_VERSION%.*}", cv2.__version__
assert numpy.__version__ == "$NUMPY_VERSION", numpy.__version__
assert hasattr(cv2, "QRCodeDetector")
assert hasattr(cv2, "wechat_qrcode_WeChatQRCode")
print(f"OpenCV {cv2.__version__}, NumPy {numpy.__version__}: OK")
PY

echo -e "${GREEN}[5/7] 使用 rosdep 补齐工作区依赖...${NC}"
if [ ! -f /etc/ros/rosdep/sources.list.d/20-default.list ]; then
    sudo rosdep init || true
fi
if rosdep update; then
    ROSDEP_READY=true
else
    ROSDEP_READY=false
    echo -e "${YELLOW}警告: rosdep update 失败，将依靠上面显式安装的软件包继续。${NC}"
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_DIR="$SCRIPT_DIR"
if [ ! -d "$WORKSPACE_DIR/src" ]; then
    echo -e "${RED}错误: 未找到 src 目录，请在 ros2 工作区根目录执行该脚本${NC}"
    exit 1
fi

cd "$WORKSPACE_DIR"
if [ "$ROSDEP_READY" = true ]; then
    rosdep install --from-paths src --ignore-src -r -y --rosdistro "$ROS_DISTRO"
fi

echo -e "${GREEN}[6/7] 检查或安装 pylon SDK...${NC}"
if [ ! -d "/opt/pylon" ] || [ ! -f "/opt/pylon/bin/pylon-setup-env.sh" ]; then
    bash "$WORKSPACE_DIR/install_basler_driver.sh" --install-only
fi
echo -e "${GREEN}✓ pylon SDK 已安装${NC}"

echo -e "${GREEN}[7/7] 编译当前工作区...${NC}"

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
echo "4. 启动 AprilTag 检测和姿态读取:"
echo "   ros2 launch apriltag_pose_reader apriltag_pose_reader.launch.py"
echo ""
