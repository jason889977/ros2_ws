#!/bin/bash
# ============================================================================
# Basler pylon SDK + pylon-ROS-camera 完整安装脚本
# 适用于: Ubuntu 22.04 (Jammy) + ROS 2 Humble
# 
# 使用方法:
#   chmod +x install_basler_driver.sh
#   ./install_basler_driver.sh
# ============================================================================

set -euo pipefail

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

REQUIRED_OS_VERSION="22.04"
REQUIRED_ROS_DISTRO="humble"

echo -e "${BLUE}=========================================="
echo " Basler 相机驱动安装脚本"
echo " pylon SDK + pylon-ROS-camera"
echo -e "==========================================${NC}"

# 检查 sudo 权限
if [ "$EUID" -ne 0 ]; then
    echo -e "${YELLOW}需要管理员权限，请输入密码:${NC}"
    sudo -v || { echo -e "${RED}错误: 无法获取管理员权限${NC}"; exit 1; }
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_DIR="$SCRIPT_DIR"
PYLON_VERSION="8.0.0"
DOWNLOAD_DIR="/tmp/basler_download"

if [ ! -f /etc/os-release ]; then
    echo -e "${RED}错误: 无法识别操作系统${NC}"
    exit 1
fi

source /etc/os-release
if [ "$ID" != "ubuntu" ] || [ "$VERSION_ID" != "$REQUIRED_OS_VERSION" ]; then
    echo -e "${RED}错误: 当前系统为 ${PRETTY_NAME}，此脚本要求 Ubuntu ${REQUIRED_OS_VERSION}${NC}"
    exit 1
fi

if [ -z "${ROS_DISTRO:-}" ] && [ -f "/opt/ros/$REQUIRED_ROS_DISTRO/setup.bash" ]; then
    source "/opt/ros/$REQUIRED_ROS_DISTRO/setup.bash"
fi

if [ -z "${ROS_DISTRO:-}" ]; then
    echo -e "${RED}错误: ROS 2 环境未加载，请先执行 source /opt/ros/$REQUIRED_ROS_DISTRO/setup.bash${NC}"
    exit 1
fi

if [ "$ROS_DISTRO" != "$REQUIRED_ROS_DISTRO" ]; then
    echo -e "${RED}错误: 当前 ROS_DISTRO=$ROS_DISTRO，要求为 $REQUIRED_ROS_DISTRO${NC}"
    exit 1
fi

mkdir -p "$DOWNLOAD_DIR"
cd "$DOWNLOAD_DIR"

# ============================================================================
# 步骤 1: 下载 pylon SDK
# ============================================================================
echo -e "\n${GREEN}[1/5] 下载 pylon SDK ${PYLON_VERSION}...${NC}"

PYLON_URL="https://www.baslerweb.com/fp-1950067054/software/pylon-${PYLON_VERSION}-linux-x86_64_debs.tar.gz"
PYLON_FILE="pylon-${PYLON_VERSION}-linux-x86_64_debs.tar.gz"

if [ ! -f "$PYLON_FILE" ]; then
    echo -e "${BLUE}正在从 Basler 官网下载...${NC}"
    echo "URL: $PYLON_URL"
    
    # 尝试使用 wget 下载
    if ! wget --timeout=60 --tries=3 "$PYLON_URL" -O "$PYLON_FILE" 2>/dev/null; then
        echo -e "${YELLOW}自动下载失败，请手动下载:${NC}"
        echo ""
        echo -e "${BLUE}方法 1: 使用浏览器下载${NC}"
        echo "访问: https://www.baslerweb.com/en/downloads/software-downloads/"
        echo "选择: Linux x86 (64位) -> pylon ${PYLON_VERSION} -> Debian 安装包"
        echo ""
        echo -e "${BLUE}方法 2: 使用其他下载工具${NC}"
        echo "wget $PYLON_URL"
        echo ""
        echo -e "${BLUE}下载完成后，将文件放置到: ${DOWNLOAD_DIR}/${NC}"
        echo -e "${YELLOW}按回车键继续...${NC}"
        read -r
    fi
fi

if [ ! -f "$PYLON_FILE" ]; then
    echo -e "${RED}错误: 未找到 pylon SDK 安装包${NC}"
    exit 1
fi

echo -e "${GREEN}✓ pylon SDK 下载完成${NC}"

# ============================================================================
# 步骤 2: 解压并安装 pylon SDK
# ============================================================================
echo -e "\n${GREEN}[2/5] 安装 pylon SDK...${NC}"

echo "解压安装包..."
PYLON_TOP_DIR="$(tar -tzf "$PYLON_FILE" | head -1 | cut -d'/' -f1)"
if [ -z "$PYLON_TOP_DIR" ]; then
    echo -e "${RED}错误: 无法识别安装包目录结构${NC}"
    exit 1
fi
tar -xzf "$PYLON_FILE"

# 查找解压后的目录
PYLON_EXTRACT_DIR="./$PYLON_TOP_DIR"
if [ ! -d "$PYLON_EXTRACT_DIR" ]; then
    echo -e "${RED}错误: 解压目录不存在: $PYLON_EXTRACT_DIR${NC}"
    exit 1
fi

cd "$PYLON_EXTRACT_DIR"

echo "安装 Debian 包..."
sudo dpkg -i pylon_*.deb || {
    echo -e "${YELLOW}修复依赖...${NC}"
    sudo apt-get install -f -y
}

echo "验证 pylon SDK..."
if [ -d "/opt/pylon" ] && [ -f "/opt/pylon/bin/pylon-setup-env.sh" ]; then
    echo -e "${GREEN}✓ pylon SDK 安装完成${NC}"
else
    echo -e "${RED}错误: pylon SDK 安装失败${NC}"
    exit 1
fi

# ============================================================================
# 步骤 3: 设置 USB 权限（用于 USB3 相机）
# ============================================================================
echo -e "\n${GREEN}[3/5] 配置 USB 相机权限...${NC}"

if [ -f "/opt/pylon/share/pylon/setup-usb.sh" ]; then
    sudo /opt/pylon/share/pylon/setup-usb.sh
    echo -e "${GREEN}✓ USB 权限配置完成${NC}"
else
    echo -e "${YELLOW}警告: 未找到 USB 配置脚本，跳过${NC}"
fi

# ============================================================================
# 步骤 4: 编译当前工作区
# ============================================================================
echo -e "\n${GREEN}[4/5] 编译当前工作区...${NC}"

if [ ! -d "$WORKSPACE_DIR/src" ]; then
    echo -e "${RED}错误: 未找到 src 目录，请在 ros2 工作区根目录执行该脚本${NC}"
    exit 1
fi

cd "$WORKSPACE_DIR"
source "/opt/ros/$ROS_DISTRO/setup.bash"

echo "编译工作区..."
colcon build --symlink-install --cmake-args -DCMAKE_BUILD_TYPE=Release

echo -e "${GREEN}✓ 工作区编译完成${NC}"

# ============================================================================
# 步骤 5: 验证安装
# ============================================================================
echo -e "\n${GREEN}[5/5] 验证安装...${NC}"

source "$WORKSPACE_DIR/install/setup.bash"

echo ""
echo -e "${BLUE}=========================================="
echo -e "${GREEN}✅ 安装完成！${NC}"
echo -e "${BLUE}==========================================${NC}"
echo ""
echo -e "${YELLOW}后续步骤:${NC}"
echo ""
echo "1. 加载环境:"
echo -e "   ${GREEN}source $WORKSPACE_DIR/install/setup.bash${NC}"
echo ""
echo "2. 连接 Basler 相机（GigE 或 USB3）"
echo ""
echo "3. 测试相机驱动:"
echo -e "   ${GREEN}ros2 launch pylon_ros2_camera_wrapper pylon_ros2_camera.launch.py${NC}"
echo ""
echo "4. 在另一个终端启动二维码识别:"
echo -e "   ${GREEN}ros2 launch qrcode_detector qrcode_detector.launch.py${NC}"
echo ""
echo "5. 查看识别结果:"
echo -e "   ${GREEN}ros2 topic echo /wechat_qr_node/decoded_info${NC}"
echo ""
echo -e "${BLUE}==========================================${NC}"
echo -e "${YELLOW}常用命令:${NC}"
echo "  查看相机话题:  ros2 topic list | grep camera"
echo "  查看图像:      ros2 run rqt_image_view rqt_image_view"
echo "  检查相机状态:  ros2 topic echo /camera/image_raw --once"
echo -e "${BLUE}==========================================${NC}"
