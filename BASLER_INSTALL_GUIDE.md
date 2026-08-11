# Basler 相机驱动安装指南（Ubuntu 22.04 + ROS 2 Humble）

## 快速安装（推荐）

```bash
cd ~/ros2_ws
./install_basler_driver.sh
```

脚本会自动完成所有安装步骤。如果自动下载失败，请按以下手动步骤操作。

---

## 手动安装步骤

### 1. 下载 pylon SDK

访问 Basler 官网下载页面：
- **网址**: https://www.baslerweb.com/en/downloads/software-downloads/
- **选择**: 
  - OS: Linux x86 (64位)
  - 版本: pylon 8.0.0 或更高
  - 格式: Debian 安装包 (`.tar.gz`)

或直接下载链接（可能变化）：
```bash
wget https://www.baslerweb.com/fp-1950067054/software/pylon-8.0.0-linux-x86_64_debs.tar.gz
```

### 2. 安装 pylon SDK

```bash
# 解压
tar -xzf pylon-8.0.0-linux-x86_64_debs.tar.gz
cd pylon-8.0.0-linux-x86_64_debs

# 安装
sudo dpkg -i pylon_*.deb
sudo apt-get install -f -y  # 修复依赖

# 验证安装目录
test -d /opt/pylon
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
source ~/ros2_ws/install/setup.bash

# 启动相机节点
ros2 launch pylon_ros2_camera_wrapper pylon_ros2_camera.launch.py

# 在另一个终端查看话题
ros2 topic list | grep camera

# 查看图像
ros2 topic echo /camera/image_raw --once
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
ros2 topic hz /camera/image_raw
```

### Q2.1: 出现错误 3774873620（buffer incompletely grabbed）

这是 GigE 链路/带宽路径承压时的典型现象。

快速处理顺序：
1. 保持 `mtu_size:=1500` 先验证稳定性。
2. 在相机 YAML 增加/调大 `inter_pkg_delay`（1000 起步）。
3. 下调 `frame_rate`（如 14 -> 12 -> 10）。
4. 检查网卡/交换机/网线质量。

可直接参考并执行：
- [docs/10-Network-Tuning-Playbook.md](docs/10-Network-Tuning-Playbook.md)

### Q3: pylon-ROS-camera 编译失败
确保已安装 pylon SDK 并正确配置环境变量：
```bash
echo $PYLON_ROOT  # 应该显示 /opt/pylon
```

### Q4: 二维码识别节点无法启动
检查模型文件是否存在：
```bash
ls ~/ros2_ws/install/qrcode_detector/share/qrcode_detector/models/
# 应该包含 4 个文件：detect.prototxt, detect.caffemodel, sr.prototxt, sr.caffemodel
```

---

## 相机参数配置

编辑 launch 文件自定义相机参数：
```bash
ros2 launch pylon_ros2_camera_wrapper pylon_ros2_camera.launch.py \
    image_topic:=/my_camera/image_raw \
    frame_rate:=30.0 \
    exposure:=5000
```

---

## 技术支持

- **Basler 官方文档**: https://docs.baslerweb.com/
- **pylon-ROS-camera GitHub**: https://github.com/basler/pylon-ros-camera
- **ROS 2 文档**: https://docs.ros.org/en/humble/

---

## 附：本仓库调优文档入口

- 网络稳定性与 3774873620 专项调优：
  [docs/10-Network-Tuning-Playbook.md](docs/10-Network-Tuning-Playbook.md)
