# 04 - Deployment SOP

## 1. Purpose

Provide a deterministic deployment path from clean host to camera+QR runtime.

## 2. Preconditions

- Ubuntu 22.04
- ROS 2 Humble installed at /opt/ros/humble
- Sudo access
- Basler camera physically connected and reachable

## 3. Standard Deployment Path

### Step 1: Enter workspace

```bash
cd ~/ros2_ws
```

### Step 2: Load ROS environment

```bash
source /opt/ros/humble/setup.bash
```

### Step 2.5: Clean old build artifacts (mandatory during migration)

```bash
./scripts/migrate_to_humble.sh
```

If you already executed this migration script once, skip to Step 3.

### Step 3: Install base dependencies

```bash
./install_dependencies.sh
```

### Step 4: Install Basler stack and build

```bash
./install_basler_driver.sh
```

### Step 5: Source workspace

```bash
source install/setup.bash
```

## 4. Camera Binding SOP (Recommended)

Use serial number to bind deterministic device_user_id.

```bash
/home/ubuntu/ros2_ws/install/pylon_ros2_camera_component/lib/pylon_ros2_camera_component/set_device_user_id -sn 22297681 106611-18
```

Expected output includes:
- Successfully wrote 106611-18 to the camera acA2500-14gc

## 5. Runtime Launch SOP

### Terminal A: Camera

```bash
source /opt/ros/humble/setup.bash
source /home/ubuntu/ros2_ws/install/setup.bash
ros2 launch pylon_ros2_camera_wrapper pylon_ros2_camera.launch.py \
  camera_id:=basler_106611_18 \
  config_file:=/home/ubuntu/ros2_ws/install/pylon_ros2_camera_wrapper/share/pylon_ros2_camera_wrapper/config/aca2500_106611_18.yaml
```

### Terminal B: QR detector

```bash
source /opt/ros/humble/setup.bash
source /home/ubuntu/ros2_ws/install/setup.bash
ros2 launch qrcode_detector qrcode_detector.launch.py \
  image_topic:=/basler_106611_18/pylon_ros2_camera_node/image_raw
```

### Terminal C: Validate output

```bash
ros2 topic echo /wechat_qr_node/decoded_info
```

## 6. Acceptance Checklist

- [ ] Camera node starts and reports found device model
- [ ] image_raw topic exists in expected namespace
- [ ] image_raw --once returns valid sensor_msgs/Image
- [ ] qrcode_detector starts and subscribes expected topic
- [ ] decoded_info topic exists and emits when QR present

## 7. Rollback and Recovery

- If deployment script fails, rerun from Step 2 after fixing root cause.
- If camera unavailable, verify IP/subnet and DeviceUserID.
- If topic mismatch, override qrcode launch argument image_topic.

## 8. One-Command Deployment Option

Use the automation helper script:

```bash
cd /home/ubuntu/ros2_ws
./scripts/deploy_and_run_camera_qr.sh
```

Notes:
- The script will build `pylon_ros2_camera_wrapper` and `qrcode_detector` before launch.
- It launches both nodes in background and prints validation commands.
- Stop both launches with the `kill` command printed by the script.

## 9. Known Runtime Risk During Deployment

GigE runtime may hit error `3774873620` (buffer incompletely grabbed) under network stress.

Immediate actions:
- check NIC/switch/cable quality
- tune MTU/inter-packet parameters
- lower effective load by ROI/frame rate optimization

This condition is a release blocker in full quality gate.

## 10. Evidence References

- deployment launch commands: [BASLER_INSTALL_GUIDE.md](../BASLER_INSTALL_GUIDE.md#L79), [BASLER_INSTALL_GUIDE.md](../BASLER_INSTALL_GUIDE.md#L101), [BASLER_INSTALL_GUIDE.md](../BASLER_INSTALL_GUIDE.md#L106)
- serial based DeviceUserID binding support: [src/pylon_ros2_camera_component/src/tools/set_device_user_id.cpp](../src/pylon_ros2_camera_component/src/tools/set_device_user_id.cpp#L93), [src/pylon_ros2_camera_component/src/tools/set_device_user_id.cpp](../src/pylon_ros2_camera_component/src/tools/set_device_user_id.cpp#L109)
