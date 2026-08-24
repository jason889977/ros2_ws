# 相机与手眼标定自动化

当前项目统一使用 AprilTag AprilGrid，不再使用棋盘格标定。相机固定在机械臂末端时属于 `eye_in_hand`，AprilGrid 固定在工作台或机器人基座参考系。

内参标定完成后，手眼标定有两种可选方式：

| 方式 | 姿态来源 | 适用场景 |
| --- | --- | --- |
| A. 离线 CSV | 用户提供的机器人控制器或历史数据 | 不绑定具体机器人 |
| B. xArm 7 自动采集 | xArm7 `xarm_ros2` 的 `/xarm/robot_states` | 自动读取 xArm7 末端姿态 |

两种方式最终都调用 `scripts/handeye_calibrate.py`，输出固定的 `gripper -> camera` 安装变换。

## 1. 共用准备

AprilGrid 规格：4 行 × 3 列，共 12 个 `tag36h11`；Tag 边长 50 mm；相邻 Tag 间距 10 mm；中心间距 60 mm。标定板应打印清晰、保持平整，并在手眼采集期间固定不动。

```bash
cd /home/ubuntu/ros2_ws
source /opt/ros/humble/setup.bash
source install/setup.bash
ros2 run apriltag_pose_reader apriltag_calibration --help
ros2 run apriltag_pose_reader apriltag_pipeline --help
python3 scripts/handeye_calibrate.py --help
```

### 1.1 AprilGrid 内参标定

先准备 15～30 张 AprilGrid 图像，覆盖不同位置、距离、俯仰、偏航和滚转：

```bash
ros2 run apriltag_pose_reader apriltag_pipeline \
  /path/to/aprilgrid_images \
  --output-dir calibration_output
```

输出：`calibration_output/camera_calibration.yaml`。确认 CameraInfo 使用新文件，并重启视觉链路：

```bash
ros2 topic echo /my_camera/pylon_ros2_camera_node/camera_info --once
ros2 topic echo /apriltag/transform --once
```

## 2. 方式 A：离线 CSV 手眼标定

### 2.1 采集要求

1. 将 AprilGrid 刚性固定在工作台或基座参考系。
2. 相机刚性安装在机器人末端法兰。
3. 采集 10～20 个同步样本，推荐 15～20 个。
4. 样本应覆盖位置、距离、俯仰、偏航和滚转变化。
5. 每个样本必须同时记录机器人末端姿态和 AprilGrid 在相机中的姿态。

### 2.2 CSV 格式

首行必须为：

```text
gripper2base_r,gripper2base_t,target2cam_r,target2cam_t
```

- `gripper2base_r/t`：末端坐标系在机器人基座坐标系中的姿态。
- `target2cam_r/t`：AprilGrid 坐标系在相机坐标系中的姿态。
- 旋转矩阵按行展开为 9 个数，平移为 3 个数，平移单位为米。
- 控制器若输出 `base2gripper`，必须先求逆，不能只修改字段名。

### 2.3 求解

```bash
python3 scripts/handeye_calibrate.py \
  --input poses.csv \
  --output calibration_output/handeye.yaml \
  --algorithm park \
  --base-frame base_link \
  --gripper-frame tool0 \
  --camera-frame camera_optical_frame \
  --target-frame apriltag_board
```

可选算法：`tsai`、`park`、`horaud`、`daniilidis`。程序会校验 CSV、旋转矩阵、样本数量和姿态变化，并输出旋转、平移、4x4 矩阵、样本数和闭环误差。

## 3. 方式 B：xArm 7 自动采集

### 3.1 启动 xArm7

安装并 source 官方 `xarm_ros2` Humble 工作区，将 IP 替换为实际控制器地址：

```bash
source /opt/ros/humble/setup.bash
source ~/xarm_ros2/install/setup.bash
ros2 launch xarm_api xarm7_driver.launch.py robot_ip:=192.168.1.XXX
```

检查状态接口：

```bash
ros2 topic list -t | grep robot_states
ros2 topic echo /xarm/robot_states --once
```

`RobotMsg.pose` 为 `[x, y, z, roll, pitch, yaw]`，位置单位为毫米，姿态单位为弧度；采集节点会自动转换为米和旋转矩阵。如果实际命名空间不是 `/xarm`，以 `ros2 topic list -t` 结果为准。

### 3.2 启动视觉链路

```bash
ros2 topic hz /my_camera/pylon_ros2_camera_node/image_raw
ros2 topic echo /my_camera/pylon_ros2_camera_node/camera_info --once
ros2 topic echo /apriltag/transform --once
```

固定使用同一个标签，例如 `tag36h11:3`。

### 3.3 自动采集

```bash
cd /home/ubuntu/ros2_ws
source /opt/ros/humble/setup.bash
source install/setup.bash
ros2 run apriltag_pose_reader xarm_handeye_capture \
  --robot-states-topic /xarm/robot_states \
  --tag-transform-topic /apriltag/transform \
  --target-frame tag36h11:3 \
  --output-dir handeye_dataset \
  --samples 15 \
  --sync-tolerance-s 0.10 \
  --min-translation-m 0.01 \
  --min-rotation-deg 5.0
```

操作员手动将 xArm7 移动到每个新姿态并停稳。程序自动完成：

1. 读取 `/xarm/robot_states`。
2. 读取 `/apriltag/transform`。
3. 按时间戳配对。
4. 过滤时间不同步、重复和运动不足样本。
5. 写出 `handeye_dataset/poses.csv`。

节点只采集，不调用 `set_position` 或 `set_servo_angle`，不会自动移动机器人。达到目标数量后自动结束；按 `Ctrl-C` 也会保存已有数据。

### 3.4 使用相同求解器

```bash
python3 scripts/handeye_calibrate.py \
  --input handeye_dataset/poses.csv \
  --output handeye_dataset/handeye.yaml \
  --algorithm park \
  --base-frame base_link \
  --gripper-frame tool0 \
  --camera-frame camera_optical_frame \
  --target-frame apriltag_board
```

## 4. 结果与验证

核心结果是固定安装变换：

$$
{}^{gripper}T_{camera}
$$

运行时组合为：

$$
{}^{base}T_{camera} = {}^{base}T_{gripper} \\cdot {}^{gripper}T_{camera}
$$

不要把手眼输出直接当作静态 `base_link -> camera`。使用未参与标定的新姿态低速验证，并至少重复 3 次。发现轴方向错误、单位错误或米级误差时立即停止机器人。

## 5. 方式选择与故障排查

- 有现成机器人姿态 CSV 或使用其他机器人：选择方式 A。
- 使用 xArm7 且驱动正常：选择方式 B。
- xArm 驱动未安装或暂时不可用：仍可选择方式 A。
- 两种方式生成的 CSV 格式相同，但不要混合不同坐标方向或不同单位的数据。
- 没有 `/xarm/robot_states`：检查 xArm 驱动、命名空间和 `xarm_msgs` 环境。
- 没有 `/apriltag/transform`：检查相机、CameraInfo、AprilTag family 和目标 ID。
- 样本不增加：检查 ROS 时间戳、同步容差以及机器人姿态变化。

## 6. 旧脚本说明

旧棋盘格脚本已删除，不再作为项目入口。当前正式入口只有 AprilGrid 内参标定、离线 CSV 手眼标定和 xArm7 自动采集。
