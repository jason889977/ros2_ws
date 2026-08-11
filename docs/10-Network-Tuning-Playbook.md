# 10 - Network Tuning Playbook (GigE)

## 1. Scope

This playbook targets GigE runtime instability, especially repeated error `3774873620` (buffer incompletely grabbed).

Applies to current field setup:
- Camera IP: `172.31.0.253`
- Camera serial: `22297681`
- DeviceUserID: `106611-18`
- Camera profile file: `src/pylon_ros2_camera_wrapper/config/aca2500_106611_18.yaml`

## 2. Why This Error Happens

`3774873620` usually indicates the host/network path cannot receive image packets in time.
Typical causes:
- NIC/switch/cable quality issues
- MTU mismatch
- Packet burst too aggressive for host path
- Frame payload too large for current bandwidth headroom

## 3. Baseline Checks (2 minutes)

```bash
# 1) Check host NIC and IP
ip -br a

# 2) Confirm camera reachability
ping -c 5 172.31.0.253

# 3) Ensure ROS graph has camera image topic
source /opt/ros/humble/setup.bash
source /home/ubuntu/ros2_ws/install/setup.bash
ros2 topic list | grep image_raw
```

Acceptance baseline:
- Packet loss in ping should be 0%.
- image_raw topic should exist continuously.

## 4. Recommended Tuning Ladder

Tune in order, one variable group at a time.

### Step A - Keep MTU conservative first

Start with:
- `mtu_size: 1500`

Reason:
- Fastest path to isolate whether instability comes from jumbo-frame mismatch.

### Step B - Raise inter-packet delay

In camera YAML, set:
- `inter_pkg_delay: 1000`

If still unstable, increase gradually:
- `2000` -> `4000` -> `8000`

Trade-off:
- Stability improves first.
- Peak frame rate can drop.

### Step C - Reduce effective throughput

In camera YAML, lower load in this order:
1. `frame_rate` (for example `14.0` -> `10.0` -> `8.0`)
2. ROI / output resolution if available in your profile

### Step D - Try jumbo MTU only after stable baseline

Only if NIC + switch + camera all support jumbo frames:
- test host NIC MTU (for example `ip link set dev <nic> mtu 3000`)
- set launch arg `mtu_size:=3000` (or higher supported value)

If instability increases, revert to `1500`.

## 5. Suggested Starting Profile for This Camera

For `aca2500_106611_18.yaml`:
- `frame_rate: 12.0`
- `mtu_size: 1500`
- `inter_pkg_delay: 1000`
- `grab_timeout: 1000`

If still seeing bursts:
- keep `frame_rate: 10.0`
- increase `inter_pkg_delay: 2000`

## 6. How To Apply (Direct Commands)

```bash
cd /home/ubuntu/ros2_ws
cp src/pylon_ros2_camera_wrapper/config/aca2500_106611_18.yaml \
   src/pylon_ros2_camera_wrapper/config/aca2500_106611_18.tuned.yaml

# edit tuned profile
sed -i 's/frame_rate: .*/frame_rate: 12.0/' src/pylon_ros2_camera_wrapper/config/aca2500_106611_18.tuned.yaml
sed -i 's/mtu_size: .*/mtu_size: 1500/' src/pylon_ros2_camera_wrapper/config/aca2500_106611_18.tuned.yaml
printf '\n    inter_pkg_delay: 1000\n' >> src/pylon_ros2_camera_wrapper/config/aca2500_106611_18.tuned.yaml
```

Note:
- If `inter_pkg_delay` already exists, edit existing key instead of appending.

Launch with tuned file:

```bash
source /opt/ros/humble/setup.bash
source /home/ubuntu/ros2_ws/install/setup.bash
ros2 launch pylon_ros2_camera_wrapper pylon_ros2_camera.launch.py \
  camera_id:=basler_106611_18 \
  config_file:=/home/ubuntu/ros2_ws/src/pylon_ros2_camera_wrapper/config/aca2500_106611_18.tuned.yaml
```

## 7. 15-Minute Validation SOP

Run in parallel terminals:

```bash
# A) camera hz
ros2 topic hz /basler_106611_18/pylon_ros2_camera_node/image_raw

# B) camera bandwidth
ros2 topic bw /basler_106611_18/pylon_ros2_camera_node/image_raw

# C) QR decode output
ros2 topic echo /wechat_qr_node/decoded_info
```

Pass criteria:
- No repeated bursts of `3774873620`.
- image topic remains continuous for 15 minutes.
- QR decode remains functional.

Block criteria:
- Repeated `3774873620` persists after Step B/C adjustments.

## 8. Rollback

If tuning worsens stability:
- Revert to original profile file
- Relaunch with original `aca2500_106611_18.yaml`

## 9. Evidence References

- GigE tuning comments in default profile: [src/pylon_ros2_camera_wrapper/config/default.yaml](../src/pylon_ros2_camera_wrapper/config/default.yaml#L112)
- Current camera profile values: [src/pylon_ros2_camera_wrapper/config/aca2500_106611_18.yaml](../src/pylon_ros2_camera_wrapper/config/aca2500_106611_18.yaml#L1)
- Launch argument support for `mtu_size` and `config_file`: [src/pylon_ros2_camera_wrapper/launch/pylon_ros2_camera.launch.py](../src/pylon_ros2_camera_wrapper/launch/pylon_ros2_camera.launch.py#L26)
