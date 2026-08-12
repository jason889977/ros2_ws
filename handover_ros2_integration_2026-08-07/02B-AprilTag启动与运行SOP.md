# AprilTag 启动与运行 SOP

## 1. 适用范围

本 SOP 仅用于“相机 + AprilTag 检测与位姿读取”链路。
不包含二维码识别节点启动与 decoded_info 验证步骤。

## 2. 统一前置

在每个终端先执行:

```bash
cd /home/ubuntu/ros2_ws
source /opt/ros/humble/setup.bash
source install/setup.bash
```

## 3. 标准启动

### 终端1: 启动相机

```bash
cd /home/ubuntu/ros2_ws
source /opt/ros/humble/setup.bash
source install/setup.bash
ros2 launch pylon_ros2_camera_wrapper pylon_ros2_camera.launch.py \
  config_file:=/home/ubuntu/ros2_ws/src/pylon_ros2_camera_wrapper/config/aca2500_106611_18.tuned_v3.yaml
```

### 终端2: 启动 AprilTag 检测与位姿读取

```bash
cd /home/ubuntu/ros2_ws
source /opt/ros/humble/setup.bash
source install/setup.bash
ros2 launch apriltag_pose_reader apriltag_pose_reader.launch.py
```

常用参数（可选）:

- `lookup_parent_frame:=<frame>`: 指定 TF 查询父坐标系；不指定时自动使用最近一次 TF 消息中的父坐标系
- `lookup_rate_hz:=<hz>`: 大于 0 时启用 TF buffer 周期性回查发布
- `health_log_interval_s:=<sec>`: 健康日志周期，设为 `0` 或负值可关闭

示例:

```bash
ros2 launch apriltag_pose_reader apriltag_pose_reader.launch.py \
  lookup_parent_frame:=map \
  lookup_rate_hz:=2.0 \
  health_log_interval_s:=10.0
```

### 终端3: 验证链路

```bash
cd /home/ubuntu/ros2_ws
source /opt/ros/humble/setup.bash
source install/setup.bash
ros2 node list
ros2 topic echo /detections --once
ros2 topic echo /apriltag/pose --once
ros2 topic echo /apriltag/transform --once
```

## 4. 6D 位姿与 TF2 变换验证

AprilTag 检测到的 6D 位姿会同时出现在两个话题:

- /apriltag/pose: geometry_msgs/PoseStamped
- /apriltag/transform: geometry_msgs/TransformStamped

先读取一次 transform，确认父子坐标系名称:

```bash
ros2 topic echo /apriltag/transform --once
```

输出中重点关注:

- header.frame_id: 父坐标系
- child_frame_id: 标签坐标系，例如 tag36h11:3

然后用 TF2 持续观测变换:

```bash
ros2 run tf2_ros tf2_echo <header.frame_id> <child_frame_id>
```

## 5. 一键脚本

```bash
# 默认复用已有相机节点，避免设备占用冲突
/home/ubuntu/ros2_ws/scripts/deploy_and_run_camera_apriltag.sh

# 若需要先自动停掉旧相机再重启
CAMERA_MODE=restart /home/ubuntu/ros2_ws/scripts/deploy_and_run_camera_apriltag.sh
```

## 6. 手动验收（推荐）

当需要在真实相机上做一次性完整验收（A-F）时，请按以下顺序执行:

1. 执行 [03B-AprilTag测试方法与验收标准.md](03B-AprilTag测试方法与验收标准.md) 的测试项 A-D。
2. 启动 RViz2，确认标签姿态与 TF2 连通。
3. 检查最新相机日志中是否出现关键错误码（3774873620 / incompletely grabbed / Grab was not successful）。

关键日志检查命令:

```bash
latest=$(ls -1t /home/ubuntu/.ros/log/pylon_ros2_camera_wrapper_*.log | head -n 1)
grep -E "3774873620|incompletely grabbed|Grab was not successful" -i "$latest" || true
```

## 7. 可选: RViz2 查看标签三维位置

```bash
cd /home/ubuntu/ros2_ws
source /opt/ros/humble/setup.bash
source install/setup.bash
rviz2
```

RViz2 建议配置:

- Global Options -> Fixed Frame 设为 map，或设为 /apriltag/transform 中的父坐标系
- Add -> TF
- Add -> Pose，Topic 选择 /apriltag/pose
- 如需叠加图像，Add -> Image，Topic 选择 /my_camera/pylon_ros2_camera_node/image_raw

## 8. 相机标定（仅当链路提示未标定时）

```bash
# 先确保相机节点已启动，然后执行标定脚本
/home/ubuntu/ros2_ws/scripts/calibrate_basler_camera_and_apply.sh

# 标定完成后重建并重启 AprilTag 链路
cd /home/ubuntu/ros2_ws
source /opt/ros/humble/setup.bash
colcon build --packages-select pylon_ros2_camera_wrapper --symlink-install
source install/setup.bash
/home/ubuntu/ros2_ws/scripts/deploy_and_run_camera_apriltag.sh
```

## 9. 快速判定规则

- 相机正常: /my_camera/pylon_ros2_camera_node 存在
- 检测正常: /detections 有持续输出
- AprilTag 位姿正常: /apriltag/pose 或 /apriltag/transform 有持续输出
- TF2 正常: tf2_echo 能持续输出变换
- RViz2 正常: TF 与 Pose 能看到标签三维位置变化

## 10. 停止流程

```bash
pkill -f "apriltag_pose_reader|apriltag_node|apriltag_pose_reader.launch.py" || true
pkill -f "pylon_ros2_camera_node|pylon_ros2_camera.launch.py" || true
```

按先停 AprilTag、再停相机执行。
