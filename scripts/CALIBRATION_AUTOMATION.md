# 相机标定自动化

## 自动棋盘格标定

启动 Basler 相机后执行：

```bash
source /opt/ros/humble/setup.bash
source install/setup.bash
python3 scripts/camera_calibration_tool.py collect \
  --board-cols 8 --board-rows 6 --square-size-m 0.025 \
  --samples 25 \
  --output src/pylon_ros2_camera_wrapper/config/aca2500_106611_18.calib.yaml
```

程序只保存检测到棋盘格且相邻样本位移足够大的图像，生成标准 `CameraInfoManager` YAML。当前 Basler profile 已经指向这个文件；生成后重启相机节点即可自动加载新的内参。

## 在线质量监控

```bash
python3 scripts/camera_calibration_tool.py monitor \
  --calibration /tmp/basler_camera.yaml \
  --max-error-px 1.0
```

监控程序用当前棋盘格的平均重投影误差判断标定质量。持续超过阈值会输出漂移告警；它不能替代重新采集标定样本。

## 手眼标定

CSV 每行代表一个机器人姿态和一个同步拍摄的棋盘格位姿，列格式如下：

```text
gripper2base_r,gripper2base_t,target2cam_r,target2cam_t
1 0 0 0 1 0 0 0 1,0.1 0.2 0.3,1 0 0 0 1 0 0 0 1,0.02 0.01 0.5
```

建议采集 10-20 个覆盖不同位置和姿态的样本：

```bash
python3 scripts/handeye_calibrate.py \
  --input poses.csv --output handeye.yaml --mode eye_in_hand
```

`eye_in_hand` 输出 `camera_to_gripper`；`eye_to_hand` 输出文件中的结果命名为 `camera_to_base`。手眼结果必须结合机器人控制器的坐标变换约定做一次实机验证，不能只凭数值通过判断。
