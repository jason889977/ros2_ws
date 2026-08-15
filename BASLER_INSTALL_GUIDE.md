# Basler 相机驱动安装指南（Ubuntu 22.04 + ROS 2 Humble）

## 快速安装（推荐）

```bash
cd ~/ros2_ws
bash install_basler_driver.sh
```

脚本会自动完成所有安装步骤。如果自动下载失败，请按以下手动步骤操作。

---

## 手动安装步骤

### 1. 下载 pylon SDK

访问 Basler 官网下载页面：
- **网址**: https://www.baslerweb.com/en/downloads/software-downloads/
- **选择**: 
  - OS: Linux x86 (64位)
  - 版本: pylon 8.0.0
  - 格式: Debian 安装包 (`.tar.gz`)

或直接下载链接（可能变化）：
```bash
wget https://www.baslerweb.com/fp-1950067054/software/pylon-8.0.0-linux-x86_64_debs.tar.gz
```

### 2. 安装 pylon SDK

```bash
# 解压到独立目录，并定位实际 Debian 包目录
mkdir -p pylon-8.0.0-extracted
tar -xzf pylon-8.0.0-linux-x86_64_debs.tar.gz -C pylon-8.0.0-extracted
cd "$(dirname "$(find pylon-8.0.0-extracted -type f -name 'pylon_*.deb' -print -quit)")"

# 安装同目录内的全部 Basler Debian 包
sudo dpkg -i ./*.deb
sudo apt-get install -f -y  # 修复依赖

# 验证安装目录
test -d /opt/pylon
dpkg-query -W pylon codemeter
```

### 3. 配置 USB 权限（USB3 相机必需）

```bash
sudo /opt/pylon/share/pylon/setup-usb.sh
```

重新插拔 USB 相机以应用新规则。

### 4. 验证 pylon 安装

```bash
# 检查安装
ls /opt/pylon/bin/

# 启动 Pylon Viewer（图形界面）
/opt/pylon/bin/pylonviewer
```

### 5. 安装 pylon-ROS-camera

```bash
# 编译
cd ~/ros2_ws
source /opt/ros/humble/setup.bash
colcon build --symlink-install --cmake-args -DCMAKE_BUILD_TYPE=Release
```

### 6. 测试相机驱动

```bash
# 加载环境
source /opt/ros/humble/setup.bash
source ~/ros2_ws/install/setup.bash

# 启动相机节点
ros2 launch pylon_ros2_camera_wrapper pylon_ros2_camera.launch.py

# 在另一个终端查看话题
ros2 topic list | grep camera

# 查看图像
ros2 topic echo /my_camera/pylon_ros2_camera_node/image_raw --once
```

---

## 完整系统使用流程

### 终端 1: 启动 Basler 相机
```bash
source /opt/ros/humble/setup.bash
source ~/ros2_ws/install/setup.bash
ros2 launch pylon_ros2_camera_wrapper pylon_ros2_camera.launch.py
```

### 终端 2: 启动二维码识别
```bash
source /opt/ros/humble/setup.bash
source ~/ros2_ws/install/setup.bash
ros2 launch qrcode_detector qrcode_detector.launch.py
```

### 终端 3: 查看识别结果
```bash
ros2 topic echo /wechat_qr_node/decoded_info
```

---

## 常见问题

### Q1: 找不到相机设备
- 检查相机是否正确连接（网线或 USB）
- GigE 相机：确保 IP 地址在同一网段
- USB 相机：检查 USB 权限配置

### Q2: 图像话题无数据
```bash
# 检查话题列表
ros2 topic list

# 检查话题发布频率
ros2 topic hz /my_camera/pylon_ros2_camera_node/image_raw
```

### Q2.1: 出现错误 3774873620（buffer incompletely grabbed）

这是 GigE 链路/带宽路径承压时的典型现象。

快速处理顺序：
1. 保持 `mtu_size:=1500` 先验证稳定性。
2. 在相机 YAML 增加/调大 `inter_pkg_delay`（1000 起步）。
3. 下调 `frame_rate`（如 14 -> 12 -> 10）。
4. 检查网卡/交换机/网线质量。

更多处理步骤见 `handover_ros2_integration_2026-08-07/04-故障排查与回滚SOP.md`。

### Q3: pylon-ROS-camera 编译失败
确保已安装冻结版本的 pylon SDK。项目 launch 会为节点设置 `PYLON_ROOT=/opt/pylon`，不需要在父终端执行 pylon 环境脚本：
```bash
test -f /opt/pylon/bin/pylon-setup-env.sh
dpkg-query -W pylon
```

### Q4: 二维码识别节点无法启动
默认 `prefer_wechat_qr=false`，不依赖 WeChatQR 模型。若显式启用 WeChatQR，再检查模型文件：
```bash
ls ~/ros2_ws/install/qrcode_detector/share/qrcode_detector/models/
# 应该包含 4 个文件：detect.prototxt, detect.caffemodel, sr.prototxt, sr.caffemodel
```

---

## 相机启动参数

launch 支持 `camera_id`、`config_file`、`mtu_size`、`startup_user_set` 等参数；曝光、帧率等相机参数应写入 YAML：
```bash
ros2 launch pylon_ros2_camera_wrapper pylon_ros2_camera.launch.py \
  camera_id:=my_camera \
  config_file:=/home/ubuntu/ros2_ws/src/pylon_ros2_camera_wrapper/config/aca2500_106611_18.tuned_v3.yaml \
  mtu_size:=1500
```

---

## 技术支持

- **Basler 官方文档**: https://docs.baslerweb.com/
- **pylon-ROS-camera GitHub**: https://github.com/basler/pylon-ros-camera
- **ROS 2 文档**: https://docs.ros.org/en/humble/
