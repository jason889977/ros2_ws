# 09 - Release Gate Checklist

## 1. Purpose

Define auditable release gates for this workspace, including minimal publish criteria and full quality criteria.

## 2. Gate Modes

### 2.1 Minimal Publish Gate (Field-Ready)

Required:
- Build passes for runtime packages.
- Camera launch succeeds with bound DeviceUserID.
- image_raw and decoded_info topics are active.
- qrcode_detector flake8/pep257 passes.
- wrapper flake8/pep257 passes.

Allowed with risk note:
- Heavy style gates skipped by minimal lint mode in wrapper.

Evidence pointers:
- wrapper minimal lint option: [src/pylon_ros2_camera_wrapper/CMakeLists.txt](../src/pylon_ros2_camera_wrapper/CMakeLists.txt#L78)
- skip switches: [src/pylon_ros2_camera_wrapper/CMakeLists.txt](../src/pylon_ros2_camera_wrapper/CMakeLists.txt#L158)
- test pass log sample: [log/latest_test/events.log](../log/latest_test/events.log#L103)

### 2.2 Full Quality Gate (Release-to-Mainline)

Required:
- Minimal Publish Gate all pass.
- cpplint/uncrustify/lint_cmake/xmllint/copyright pass according to package policy.
- Integration tests (auto/2d/3d where applicable) pass in controlled environment.
- Regression report signed by R&D + QA.

## 3. Runtime Health Gates (Hardware-In-Loop)

- Network reachability and subnet alignment verified.
- No sustained fatal errors in launch logs.
- If error 3774873620 appears, release is blocked until mitigation validation.

### 3.1 Error 3774873620 Block Rule

Block condition:
- Repeated "buffer was incompletely grabbed" bursts during nominal run.

Mitigation checklist:
1. Validate NIC/switch/cable quality.
2. Tune MTU and inter-packet delay.
3. Reduce ROI/frame size or frame rate.
4. Increase grab buffers where applicable.
5. Re-run runtime smoke for 15 minutes without repeated bursts.

## 4. Acceptance Checklist Template

- [ ] Build gate pass
- [ ] Minimal lint gate pass
- [ ] Runtime launch gate pass
- [ ] Topic topology gate pass
- [ ] QR decode gate pass
- [ ] No blocked runtime errors
- [ ] Test report archived

## 5. Sign-off

- R&D owner:
- QA owner:
- Date:
- Gate mode used: Minimal Publish / Full Quality
- Risk acceptance note (if any):
