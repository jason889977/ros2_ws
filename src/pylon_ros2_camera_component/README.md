# pylon_ros2_camera_component

Composable camera driver for Basler GigE cameras (Pylon SDK). Vendor driver
code with project-specific diagnostics and parameter validation on top.

## Node: `pylon_ros2_camera_node` (component `pylon_ros2_camera::PylonROS2CameraNode`)

- **Topics**: `~/image_raw`, `~/image_rect`, `~/camera_info` (RELIABLE QoS,
  matching `image_transport` defaults).
- **Diagnostics**: `pylon_ros2_camera_node: camera_availability` plus
  `image_publish_rate` (with `fps` field) — consumed by
  `vision_status_aggregator` and the web dashboard.
- **Key parameters**: `device_user_id`, `frame_rate`, `exposure` (ms),
  `gain` (0–1), `brightness`, `mtu_size`, binning, image encoding.
  Out-of-range values are clamped/reset by `validateParameterSet`.
- **Runtime services**: exposure/gain control (used by
  `vision_dashboard/pylon_routes.py`).

## Build

Requires the Pylon SDK (`/opt/pylon` or `PYLON_SDK_SEARCH_PATHS`). Without
it, CI skips this package; see `.github/workflows/build-test.yml`.

## Testing

`test/test_pylon_parameters.cpp` — gtest for the hardware-independent
parameter validation (frame rate reset, exposure/gain/brightness range
checks, shutter mode strings).
