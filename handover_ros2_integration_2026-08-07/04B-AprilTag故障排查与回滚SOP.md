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
2. 先保持默认全分辨率配置，确认错误是否持续出现
3. 若反复出现，执行降载回退

## 7. 降载/故障回退 SOP

回退条件:
- 默认全分辨率配置下出现持续抓取或链路稳定性问题
- 连续守门测试不通过

`tuned_v3` 使用 8 FPS、2x2 binning 和更大的包间隔，仅作为带宽降载配置。

回退命令:

```bash
pkill -f "apriltag_pose_reader|apriltag_node|apriltag_pose_reader.launch.py" || true
pkill -f "pylon_ros2_camera_node|pylon_ros2_camera.launch.py" || true
cd /home/ubuntu/ros2_ws
source /opt/ros/humble/setup.bash
source install/setup.bash
ros2 launch pylon_ros2_camera_wrapper pylon_ros2_camera.launch.py \
  config_file:=/home/ubuntu/ros2_ws/src/pylon_ros2_camera_wrapper/config/aca2500_106611_18.tuned_v3.yaml \
  startup_user_set:=Default
```

回退后必须执行:
- ./03B-AprilTag测试方法与验收标准.md 中的关键测试项

## 8. 场景E: 相机报 0xE1018006 被其他应用控制

先检查当前主机是否仍有占用进程或 GigE Vision 控制连接:

```bash
ps -eo user,pid,ppid,stat,cmd | grep -Ei 'pylon|basler|camera' | grep -v grep
ss -uanp | grep -E '(:3956|172\.31\.0\.88)' || true
```

优先使用一键脚本的 `restart` 模式。脚本会分阶段停止本机相机进程、确认无残留，
并等待 GigE 控制锁释放:

```bash
CAMERA_MODE=restart /home/ubuntu/ros2_ws/scripts/deploy_and_run_camera_apriltag.sh
```

判定:
- 若仍能看到本机相机进程，先查明其所属用户或服务，不要并行启动第二个相机节点
- 若本机无相机进程、无 UDP 3956 连接，等待 10 秒后仍报 `0xE1018006`，控制权来自其他主机或 Pylon Viewer
- 此时应关闭同一相机网段其他主机上的 Pylon Viewer/采集程序；不要反复启动 ROS 节点
- 确认不存在合法控制端后，最后手段是给相机断电重启；该操作会中断所有相机连接

## 9. 升级调优触发条件

仅在下列情况触发新一轮调优:
- 检测结果持续丢失
- 位姿或 TF2 变换持续中断
- 启动链路回归为节点不注册或话题不连通
