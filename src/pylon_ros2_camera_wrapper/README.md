# pylon_ros2_camera_wrapper

Launch wrapper and camera configuration for `pylon_ros2_camera_component`.

## Contents

- Launch file that starts the camera component in a composable container
  with the production parameter set.
- `config/aca2500_106611_18.yaml` — camera-specific parameters for the
  deployed Basler aca2500 (the same file is mirrored in
  `deploy/basler_camera/config/`; CI verifies the two stay identical).
