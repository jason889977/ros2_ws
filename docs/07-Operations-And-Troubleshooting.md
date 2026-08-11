# 07 - Operations and Troubleshooting

## 1. 5-Minute Health Check

```bash
source /opt/ros/humble/setup.bash
source /home/ubuntu/ros2_ws/install/setup.bash
ros2 node list
ros2 topic list | grep -E "image_raw|decoded_info"
ros2 topic echo /basler_106611_18/pylon_ros2_camera_node/image_raw --once
```

## 2. Common Problems

### 2.1 No camera detected

Symptoms:
- launch logs report no available camera device

Checks:
- Verify physical link and power
- Verify subnet match and ping camera IP
- Verify DeviceUserID binding by serial

### 2.2 Topic exists but low/unstable hz

Symptoms:
- image_raw rate lower than configured frame_rate

Checks:
- Use topic bw to confirm payload flow
- Check exposure and resolution impact
- Tune MTU and network path
- Reduce ROI/frame size for throughput margin

### 2.3 QR node starts but no decode output

Checks:
- Confirm image_topic mapping exactly matches camera namespace
- Validate model files exist in installed package share/models
- Confirm scene contains readable QR and adequate focus/exposure

### 2.4 Distorted image warning only

Meaning:
- camera_info_url missing, no rectification available

Action:
- Provide valid calibration file and camera_info_url

## 3. Escalation Data to Collect

- launch logs from camera and QR terminals
- ros2 node info outputs
- ros2 topic list and selected topic echo samples
- test-result summaries

## 4. Known Runtime Issue: 3774873620

Observed symptom:
- repeated GigE error: `The buffer was incompletely grabbed` (`3774873620`)

Operational impact:
- image stream instability and possible downstream decode jitter

Mitigation runbook:
1. Verify link quality (NIC/switch/cable) and camera subnet reachability.
2. Keep `mtu_size` conservative (`1500`) for baseline.
3. Increase `inter_pkg_delay` progressively (`1000` -> `2000` -> `4000`).
4. Reduce load via `frame_rate` and ROI/resolution.
5. Validate 15-minute continuous run with no repeated bursts.

Reference playbook:
- [10-Network-Tuning-Playbook](10-Network-Tuning-Playbook.md)

## 5. Evidence References

- GigE MTU/inter-packet guidance from wrapper default profile:
	[src/pylon_ros2_camera_wrapper/config/default.yaml](../src/pylon_ros2_camera_wrapper/config/default.yaml#L112)
- Camera launch supports overriding `mtu_size` and `config_file`:
	[src/pylon_ros2_camera_wrapper/launch/pylon_ros2_camera.launch.py](../src/pylon_ros2_camera_wrapper/launch/pylon_ros2_camera.launch.py#L26)
- Field profile currently used in this workspace:
	[src/pylon_ros2_camera_wrapper/config/aca2500_106611_18.yaml](../src/pylon_ros2_camera_wrapper/config/aca2500_106611_18.yaml#L1)
