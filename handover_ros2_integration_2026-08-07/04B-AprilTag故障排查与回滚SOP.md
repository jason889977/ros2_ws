# AprilTag 故障排查与回滚 SOP

## 1. 适用范围

本 SOP 仅用于“相机 + AprilTag 检测与位姿读取”链路。
不包含二维码 decoded_info 相关问题。

## 2. 排查总原则

按顺序排查:
1. 先看 ROS 图谱
2. 再看 detections 与位姿话题
3. 再看 TF2 变换
4. 最后看日志与参数

## 3. 场景A: AprilTag 节点在，但 /detections 无输出

现象:
- /apriltag 与 /apriltag_pose_reader 节点存在
- /detections 长时间无输出

排查步骤:

```bash
cd /home/ubuntu/ros2_ws
source /opt/ros/humble/setup.bash
source install/setup.bash
ros2 node list
ros2 topic info -v /my_camera/pylon_ros2_camera_node/image_raw
ros2 topic echo /detections --once
```

判定:
- 若 image_raw Publisher count = 0，先恢复相机启动
- 若 detections 无输出，检查标签是否入镜、tag family 与参数文件是否匹配

恢复命令:

```bash
pkill -f "apriltag_pose_reader|apriltag_node|apriltag_pose_reader.launch.py" || true
cd /home/ubuntu/ros2_ws
source /opt/ros/humble/setup.bash
source install/setup.bash
ros2 launch apriltag_pose_reader apriltag_pose_reader.launch.py
```

## 4. 场景B: /detections 有输出，但 /apriltag/pose 或 /apriltag/transform 无输出

现象:
- /detections 可见
- /apriltag/pose 或 /apriltag/transform 无持续输出

排查步骤:

```bash
cd /home/ubuntu/ros2_ws
source /opt/ros/humble/setup.bash
source install/setup.bash
ros2 topic echo /apriltag/pose --once
ros2 topic echo /apriltag/transform --once
```

判定:
- 若 transform 无输出，检查 tf 链路与 apriltag_pose_reader 是否正常运行
- 若仅 pose 缺失，重启 apriltag_pose_reader 节点

## 5. 场景C: TF2 报 frame 不存在或不连通

排查步骤:
1. 先执行:

```bash
ros2 topic echo /apriltag/transform --once
```

2. 记录输出中的 header.frame_id 与 child_frame_id，再执行:

```bash
ros2 run tf2_ros tf2_echo <header.frame_id> <child_frame_id>
```

判定:
- 若 frame 不存在，优先确认 /apriltag/transform 是否有持续更新
- 若 frame 名变化，更新 RViz2 Fixed Frame 或验证命令中的 frame 参数

## 6. 场景D: 出现 3774873620 或抓取不完整错误

快速扫描:

```bash
latest=$(ls -1t /home/ubuntu/.ros/log/pylon_ros2_camera_wrapper_*.log | head -n 1)
grep -E "3774873620|incompletely grabbed|Grab was not successful" -i "$latest" || true
```

处理顺序:
1. 检查网线/交换机/NIC
2. 保持 v3 配置，不做激进调参
3. 若反复出现，执行回滚

## 7. 回滚 SOP

回滚条件:
- v3 下出现持续稳定性回归
- 连续守门测试不通过

回滚命令:

```bash
pkill -f "apriltag_pose_reader|apriltag_node|apriltag_pose_reader.launch.py" || true
pkill -f "pylon_ros2_camera_node|pylon_ros2_camera.launch.py" || true
cd /home/ubuntu/ros2_ws
source /opt/ros/humble/setup.bash
source install/setup.bash
ros2 launch pylon_ros2_camera_wrapper pylon_ros2_camera.launch.py \
  config_file:=/home/ubuntu/ros2_ws/src/pylon_ros2_camera_wrapper/config/aca2500_106611_18.tuned_v3.yaml
```

回滚后必须执行:
- ./03B-AprilTag测试方法与验收标准.md 中的关键测试项

## 8. 升级调优触发条件

仅在下列情况触发新一轮调优:
- 检测结果持续丢失
- 位姿或 TF2 变换持续中断
- 启动链路回归为节点不注册或话题不连通
