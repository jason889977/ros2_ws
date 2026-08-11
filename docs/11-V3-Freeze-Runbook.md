# 11 - V3 Freeze Runbook (Basler + QR)

## 1. Purpose

Provide an operations runbook after freezing camera config to v3 in VM environment.
Primary goal: stable publish path over aggressive performance tuning.

## 2. Baseline

- Camera config file:
  - `src/pylon_ros2_camera_wrapper/config/aca2500_106611_18.tuned_v3.yaml`
- Key v3 settings:
  - `frame_rate: 8.0`
  - `grab_timeout: 1500`
  - `mtu_size: 1500`
  - `inter_pkg_delay: 1000`
  - `binning_x: 2`
  - `binning_y: 2`
- Expected startup ROI after binning:
  - approximately `1294x970`

## 3. Start Procedure

Run in workspace root `ros2_ws`:

```bash
source /opt/ros/humble/setup.bash
source install/setup.bash
```

Start camera:

```bash
ros2 launch pylon_ros2_camera_wrapper pylon_ros2_camera.launch.py \
  config_file:=/home/ubuntu/ros2_ws/src/pylon_ros2_camera_wrapper/config/aca2500_106611_18.tuned_v3.yaml
```

Start QR detector (new terminal, same sourced env):

```bash
source /opt/ros/humble/setup.bash
source /home/ubuntu/ros2_ws/install/setup.bash
ros2 launch qrcode_detector qrcode_detector.launch.py
```

## 4. Fast Health Check (2-3 min)

```bash
ros2 node list
ros2 topic info -v /my_camera/pylon_ros2_camera_node/image_raw
ros2 topic echo /wechat_qr_node/decoded_info --once
```

Pass criteria:
- `/wechat_qr_node` exists.
- `/wechat_qr_node/decoded_info` returns expected payload (for validation card, usually `ABCDE`).
- `/wechat_qr_node` subscribes to `/my_camera/pylon_ros2_camera_node/image_raw`.

## 5. Guard Check (10-15 min)

Observe continuous recognition logs from QR node and scan camera log for blockers.

Find latest camera log:

```bash
ls -1t /home/ubuntu/.ros/log/pylon_ros2_camera_wrapper_*.log | head -n 1
```

Scan blocker signatures:

```bash
latest=$(ls -1t /home/ubuntu/.ros/log/pylon_ros2_camera_wrapper_*.log | head -n 1)
grep -E "3774873620|incompletely grabbed|Grab was not successful" -i "$latest" || true
```

Pass criteria:
- No repeated blocker signatures above.
- QR recognition remains continuous.

## 6. Release Decision in VM

Use this rule:
- If chain is stable and no repeated `3774873620`, keep v3 frozen.
- Do not continue deep tuning in VM unless failure recurs.

Performance note:
- VM path may show lower effective throughput; prioritize stability and reproducibility over fps chasing.

## 7. Rollback Plan

If severe instability returns:

1. Stop current launches.
2. Roll back to previous known config:

```bash
ros2 launch pylon_ros2_camera_wrapper pylon_ros2_camera.launch.py \
  config_file:=/home/ubuntu/ros2_ws/src/pylon_ros2_camera_wrapper/config/aca2500_106611_18.tuned.yaml
```

3. Re-run Fast Health Check and Guard Check.
4. Record timestamp, errors, and environment (VM load/network) before any new tuning.

## 8. Escalation Trigger

Start a new tuning round only when one of these is true:
- repeated `3774873620` bursts,
- decoding continuity breaks under same scene,
- launch-only path regresses (node present but no graph/topic activity).

## 9. Daily Ops Checklist

- [ ] Camera launch started with v3 file.
- [ ] QR launch started and node visible.
- [ ] `decoded_info` one-shot check passed.
- [ ] 10+ min guard check passed.
- [ ] No blocker signature in latest camera log.
- [ ] Any anomaly captured with command output and timestamp.
