# 二维码故障排查与回滚 SOP

## 1. 适用范围

本 SOP 仅用于“相机 + 二维码识别”链路。
不包含 AprilTag 检测、TF2 与 6D 位姿相关问题。

## 2. 排查总原则

按顺序排查:
1. 先看 ROS 图谱
2. 再看 topic 发布与订阅
3. 最后看日志与参数

## 3. 场景A: 二维码节点进程在，但无 decoded_info

现象:
- qrcode_node 进程存在
- /wechat_qr_node/decoded_info 无输出

排查步骤:

```bash
cd /home/ubuntu/ros2_ws
source /opt/ros/humble/setup.bash
source install/setup.bash
ros2 node list
ros2 topic info -v /my_camera/pylon_ros2_camera_node/image_raw
```

判定:
- 若 image_raw Publisher count = 0，先恢复相机启动
- 若 Subscription count = 0，重启二维码节点

恢复命令:

```bash
pkill -f "qrcode_node|qrcode_detector.launch.py" || true
cd /home/ubuntu/ros2_ws
source /opt/ros/humble/setup.bash
source install/setup.bash
ros2 launch qrcode_detector qrcode_detector.launch.py
```

## 4. 场景B: 只看到 wechat_qr_node，看不到相机节点

现象:
- ros2 node list 仅有 /wechat_qr_node

处理:

```bash
cd /home/ubuntu/ros2_ws
source /opt/ros/humble/setup.bash
source install/setup.bash
ros2 launch pylon_ros2_camera_wrapper pylon_ros2_camera.launch.py \
  config_file:=/home/ubuntu/ros2_ws/src/pylon_ros2_camera_wrapper/config/aca2500_106611_18.yaml \
  startup_user_set:=Default
```

## 5. 场景C: 出现 3774873620 或抓取不完整错误

快速扫描:

```bash
latest=$(ls -1t /home/ubuntu/.ros/log/pylon_ros2_camera_wrapper_*.log | head -n 1)
grep -E "3774873620|incompletely grabbed|Grab was not successful" -i "$latest" || true
```

处理顺序:
1. 检查网线/交换机/NIC
2. 先保持默认全分辨率配置，确认错误是否持续出现
3. 若反复出现，执行降载回退

## 6. 降载/故障回退 SOP

回退条件:
- 默认全分辨率配置下出现持续抓取或链路稳定性问题
- 连续守门测试不通过

`tuned_v3` 使用 8 FPS、2x2 binning 和更大的包间隔，仅作为带宽降载配置。

回退命令:

```bash
pkill -f "qrcode_node|qrcode_detector.launch.py" || true
pkill -f "pylon_ros2_camera_node|pylon_ros2_camera.launch.py" || true
cd /home/ubuntu/ros2_ws
source /opt/ros/humble/setup.bash
source install/setup.bash
ros2 launch pylon_ros2_camera_wrapper pylon_ros2_camera.launch.py \
  config_file:=/home/ubuntu/ros2_ws/src/pylon_ros2_camera_wrapper/config/aca2500_106611_18.tuned_v3.yaml \
  startup_user_set:=Default
```

回退后必须执行:
- ./03A-二维码测试方法与验收标准.md 中的关键测试项

## 7. 升级调优触发条件

仅在下列情况触发新一轮调优:
- 关键错误重复出现
- 相同场景下识别连续性明显下降
- 启动链路回归为节点不注册或话题不连通
