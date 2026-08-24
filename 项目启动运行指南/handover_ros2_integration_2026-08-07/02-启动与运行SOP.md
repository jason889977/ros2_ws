# 启动与运行 SOP（公共相机部分）

## 1. 目的

本文件仅保留相机公共流程与跨业务共用步骤。
二维码与 AprilTag 已拆分为独立 SOP，避免混用与交叉测试。

- 二维码专用: ./02A-二维码启动与运行SOP.md
- AprilTag 专用: ./02B-AprilTag启动与运行SOP.md

## 2. 统一前置

在每个终端先执行:

```bash
cd /home/ubuntu/ros2_ws
source /opt/ros/humble/setup.bash
source install/setup.bash
```

## 3. 公共相机启动

```bash
cd /home/ubuntu/ros2_ws
sudo -n docker restart basler_camera
sudo -n docker inspect --format '{{.State.Status}} {{.State.Health.Status}}' basler_camera
```

日常不要在宿主机再次启动 Basler launch，也不要运行会抢占相机的旧一键脚本。容器 profile 必须启用 `binning_x: 2`、`binning_y: 2`，输出应为 Mono8、`1294x970`。

容器内确认原始流:

```bash
sudo -n docker exec basler_camera bash -lc \
  'source /opt/ros/humble/setup.bash && source /opt/ros2_ws/install/setup.bash && \
   timeout 8 ros2 topic hz /my_camera/pylon_ros2_camera_node/image_raw'
```

统一容器启动后直接检查:

```bash
source /opt/ros/humble/setup.bash
source /home/ubuntu/ros2_ws/install/setup.bash
sudo -n docker exec basler_camera bash -lc \
  'source /opt/ros/humble/setup.bash && source /opt/ros2_ws/install/setup.bash && \
   ros2 node list'
```

统一容器主流程的判据是容器内 `/my_camera/detections`、`/my_camera/apriltag/pose` 和 `/my_camera/qr/decoded_info` 可用；如果 `.env` 中禁用了对应模块，则不检查该模块的话题。

## 4. 公共可视化入口

```bash
/home/ubuntu/ros2_ws/scripts/open_camera_rviz.sh
```

## 5. 相机更换与重新绑定 SOP

当更换相机后，优先按下面顺序恢复到可运行状态。

### 5.1 重新绑定设备号

先用序列号把新相机绑定成固定的 `device_user_id`，这样后续 launch 不用改。

```bash
/home/ubuntu/ros2_ws/install/pylon_ros2_camera_component/lib/pylon_ros2_camera_component/set_device_user_id -sn <新相机序列号> 106611-18
```

如果你希望这台新相机使用新的名字，也可以把 `106611-18` 换成新的 `device_user_id`，但要同步修改 YAML 里的 `device_user_id`。

### 5.2 必要时重新配置相机 IP

如果是 GigE 相机，而且新相机不在当前网段或不可达，先配置 IP 再启动主程序。

```bash
cd /home/ubuntu/ros2_ws
source /opt/ros/humble/setup.bash
source install/setup.bash
/opt/pylon/bin/pylon_ip_auto_config
```

根据厂商工具提示：

- 选择要配置的相机编号
- 输入目标 IP
- 输入子网掩码

配置完成后，按需验证：

```bash
ping -c 5 <相机IP>
```

### 5.3 更新运行参数

如果你沿用旧的相机命名，通常只需要更新这两个地方：

- `config_file`：对应新的相机 YAML
- `device_user_id`：对应新相机的绑定名

参考位置：

- [pylon_ros2_camera.launch.py](../src/pylon_ros2_camera_wrapper/launch/pylon_ros2_camera.launch.py)
- [device_user_id 配置示例](../src/pylon_ros2_camera_wrapper/config/aca2500_106611_18.yaml)

## 6. 公共快速判定规则

- 相机正常: /my_camera/pylon_ros2_camera_node 存在
- 图像链路正常: 容器内 `/my_camera/pylon_ros2_camera_node/image_raw` 能实际收到消息

二维码与 AprilTag 的业务判定标准，请分别参考:

- ./02A-二维码启动与运行SOP.md
- ./02B-AprilTag启动与运行SOP.md

## 7. 公共日常巡检命令

```bash
ros2 node list
sudo -n docker exec basler_camera bash -lc \
  'source /opt/ros/humble/setup.bash && source /opt/ros2_ws/install/setup.bash && \
   ros2 topic hz /my_camera/pylon_ros2_camera_node/image_raw'
```

`ros2 topic hz` 显示容器内算法订阅端实际收到的速率；驱动发布计数以容器日志中的 `Image publish FPS` 为准。

## 8. 公共停止流程

```bash
sudo -n docker stop basler_camera
```

业务节点停止请分别参考:

- 二维码: ./02A-二维码启动与运行SOP.md
- AprilTag: ./02B-AprilTag启动与运行SOP.md
