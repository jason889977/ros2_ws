# 06 - Testing and Acceptance

## 1. Test Strategy

Use layered testing:
1. Lint/static quality gates
2. Build verification
3. Integration launch tests
4. Hardware-in-loop runtime checks

## 2. Commands

### 2.1 Build

```bash
source /opt/ros/humble/setup.bash
cd /home/ubuntu/ros2_ws
colcon build --symlink-install --cmake-args -DCMAKE_BUILD_TYPE=Release
```

### 2.2 Targeted test for two main packages

```bash
source /opt/ros/humble/setup.bash
cd /home/ubuntu/ros2_ws
colcon test --packages-select qrcode_detector pylon_ros2_camera_wrapper --event-handlers console_direct+
colcon test-result --verbose --test-result-base build/qrcode_detector
colcon test-result --verbose --test-result-base build/pylon_ros2_camera_wrapper
```

### 2.3 Minimal release lint mode note

wrapper CMake currently supports minimal release lint mode by skipping selected heavy gates while preserving key Python lint checks.

## 3. Hardware Acceptance Procedure

1. Confirm network reachability to camera IP.
2. Launch camera node with bound DeviceUserID.
3. Validate image_raw stream exists and is readable.
4. Launch QR node with explicit image_topic mapping.
5. Present known QR samples and verify decoded_info output.

## 4. Acceptance Criteria

- Build success for all required runtime packages.
- qrcode_detector flake8/pep257 passes.
- wrapper flake8/pep257 passes (and selected release gate policy documented).
- End-to-end camera->QR topic path active.
- Runtime logs contain no fatal error.

## 5. Test Report Template

## Test Metadata
- Date:
- Operator:
- Host:
- Camera Model/SN:
- Workspace Commit/State:

## Executed Commands
- build:
- test:
- runtime checks:

## Results
- Build: PASS/FAIL
- Lint/Test: PASS/FAIL
- Runtime stream: PASS/FAIL
- QR decode: PASS/FAIL

## Issues and Actions
- Issue:
- Root cause:
- Fix:
- Retest result:

## 6. Release Gate Mapping

- Minimal publish gate: see [09-Release-Gate-Checklist](09-Release-Gate-Checklist.md)
- Full quality gate: see [09-Release-Gate-Checklist](09-Release-Gate-Checklist.md)

## 7. Evidence References

- qrcode test session start trace: [log/latest_test/events.log](../log/latest_test/events.log#L47)
- wrapper 100% passed trace (targeted gate): [log/latest_test/events.log](../log/latest_test/events.log#L103)
- wrapper minimal release lint controls: [src/pylon_ros2_camera_wrapper/CMakeLists.txt](../src/pylon_ros2_camera_wrapper/CMakeLists.txt#L158)
