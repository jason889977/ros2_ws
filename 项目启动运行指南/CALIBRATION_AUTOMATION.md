# 相机与手眼标定自动化

当前项目统一采用 AprilTag AprilGrid 进行高精度标定，取代传统棋盘格标定。当相机刚性固定在机械臂末端法兰时属于 `eye_in_hand`（眼在手上），AprilGrid 标定板固定在工作台或机器人基座参考系。

完成相机内参标定后，手眼标定支持以下两种自动化与离线解算方式：

| 标定方式 | 姿态数据来源 | 适用场景 |
| --- | --- | --- |
| **方式 A：离线 CSV 标定** | 机械臂控制器导出或第三方离线位姿数据 | 通用工业机器人（ABB、KUKA、FANUC、UR 等） |
| **方式 B：xArm 7 自动同步采集** | 订阅 `xarm_ros2` 的 `/xarm/robot_states` 话题 | xArm7 机械臂全自动高精度同步标定 |

两种方式最终均通过 [scripts/handeye_calibrate.py](scripts/handeye_calibrate.py) 进行统一数值解算，输出标准 OpenCV YAML 格式的手眼变换矩阵（${}^{tool0}T_{camera}$）。

---

## 1. 标定前准备与 AprilGrid 规格

- **标定板规格**：4 行 $\times$ 3 列，共 12 个 `tag36h11` 系列标签；标签边长 $50\text{ mm}$；相邻标签黑边间距 $10\text{ mm}$；中心间距 $60\text{ mm}$。
- **环境准备**：将标定板平整牢固粘贴于硬质平面上，确保标定期间标定板与工作台绝对无相对晃动。

```bash
cd /home/ubuntu/ros2_ws
source /opt/ros/humble/setup.bash
source install/setup.bash

# 查看标定工具命令行参数说明
ros2 run apriltag_pose_reader apriltag_calibration --help
ros2 run apriltag_pose_reader apriltag_pipeline --help
python3 scripts/handeye_calibrate.py --help
```

### 1.1 AprilGrid 相机内参标定

采集 $15 \sim 30$ 张覆盖不同距离、角度、倾斜（俯仰/偏航/滚转）的 AprilGrid 图像保存至目录，执行全自动标定流水线：

```bash
ros2 run apriltag_pose_reader apriltag_pipeline \
  /path/to/aprilgrid_images \
  --output-dir calibration_output
```

解算完成后，输出标准相机标定配置文件 `calibration_output/camera_calibration.yaml`。将该文件路径配置至相机 YAML 或生产环境后重启视觉节点：

```bash
ros2 topic echo /my_camera/pylon_ros2_camera_node/camera_info --once
ros2 topic echo /my_camera/apriltag/transform --once
```

---

## 2. 方式 A：通用离线 CSV 手眼标定

### 2.1 采集规范

1. 将 AprilGrid 标定板刚性固定于工作台。
2. 相机刚性固定于机械臂末端法兰。
3. 移动机械臂采集 $15 \sim 20$ 组不同位姿的样本数据，姿态旋转角度变化量应大于 $5^\circ$。
4. 记录每组对应的机械臂末端在基座下的位姿及标定板在相机坐标系下的位姿。

### 2.2 CSV 格式规范

CSV 文件第一行必须为表头：

```text
gripper2base_r,gripper2base_t,target2cam_r,target2cam_t
```

- `gripper2base_r/t`：末端法兰在机器人基座坐标系下的姿态（$3 \times 3$ 旋转矩阵按行展开为 9 个数值，平移向量为 3 个数值，单位为米）。
- `target2cam_r/t`：AprilGrid 标定板在相机光学坐标系下的姿态。

### 2.3 运行求解

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

支持的算法参数包括：`tsai`、`park`、`horaud`、`daniilidis`。解算器将自动校验旋转矩阵正交性、计算重投影与闭环平均平移与旋转误差。

---

## 3. 方式 B：xArm 7 全自动在线采集与解算

### 3.1 启动 xArm 7 驱动

```bash
source /opt/ros/humble/setup.bash
source ~/xarm_ros2/install/setup.bash
ros2 launch xarm_api xarm7_driver.launch.py robot_ip:=192.168.1.XXX
```

### 3.2 启动视觉链路

```bash
ros2 topic hz /my_camera/pylon_ros2_camera_node/image_raw
ros2 topic echo /my_camera/pylon_ros2_camera_node/camera_info --once
ros2 topic echo /my_camera/apriltag/transform --once
```

### 3.3 运行自动同步采集节点

```bash
cd /home/ubuntu/ros2_ws
source /opt/ros/humble/setup.bash && source install/setup.bash

ros2 run apriltag_pose_reader xarm_handeye_capture \
  --robot-states-topic /xarm/robot_states \
  --tag-transform-topic /my_camera/apriltag/transform \
  --target-frame tag36h11:3 \
  --output-dir handeye_dataset \
  --samples 15 \
  --sync-tolerance-s 0.10 \
  --min-translation-m 0.01 \
  --min-rotation-deg 5.0
```

操作人员手动将机械臂示教到不同的姿态并保持静止，节点将自动基于时间戳同步配对、过滤运动不足的样本，并在达到设定样本数后自动保存 `handeye_dataset/poses.csv`。

### 3.4 手眼矩阵解算

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

---

## 4. 生产应用与 TF 树闭环验证

### 4.1 数学关系与变换矩阵

解算结果保存于 YAML 文件中，核心矩阵关系为：

$$
{}^{gripper}T_{camera} = {}^{tool0}T_{camera}
$$

实时运行时，相机在机器人基座坐标系下的位姿通过 TF 树动态合成：

$$
{}^{base}T_{camera} = {}^{base}T_{gripper} \cdot {}^{gripper}T_{camera}
$$

### 4.2 接入生产流水线（自动广播静态 TF）

#### 方式一：集成至 vision_pipeline 流水线（推荐）

通过 Launch 参数直接加载手眼标定 YAML 文件：

```bash
ros2 launch industrial_vision_bringup vision_pipeline.launch.py \
  handeye_calibration_file:=/home/ubuntu/ros2_ws/handeye_dataset/handeye.yaml \
  world_frame:=world \
  base_frame:=base_link
```

在 [deploy/basler_camera/.env](deploy/basler_camera/.env) 中配置：

```dotenv
HANDEYE_CALIBRATION_FILE=/opt/ros2_ws/deploy/basler_camera/config/handeye.yaml
WORLD_FRAME=world
BASE_FRAME=base_link
```

#### 方式二：独立启动静态 TF 广播节点

```bash
ros2 run apriltag_pose_reader handeye_static_tf_broadcaster \
  --ros-args -p calibration_file:=handeye_dataset/handeye.yaml
```

### 4.3 TF 精度闭环验证

1. **查询相机在基座下的实时位姿**：
```bash
ros2 run tf2_ros tf2_echo base_link camera_optical_frame
```

2. **静止目标一致性验证**：
在视野内放置固定 AprilTag 标签，查询其在机械臂基座坐标系下的坐标：
```bash
ros2 run tf2_ros tf2_echo base_link tag36h11:3
```
手动慢速移动机械臂各轴关节，观察终端输出的 `base_link -> tag36h11:3` 位姿坐标。若坐标保持恒定不动（仅有毫米级微小抖动），则证明手眼标定结果与 TF 链路完全正确闭环。

