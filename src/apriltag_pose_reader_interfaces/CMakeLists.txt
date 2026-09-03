cmake_minimum_required(VERSION 3.22)
project(apriltag_pose_reader_interfaces)

if(NOT CMAKE_CXX_STANDARD)
  set(CMAKE_CXX_STANDARD 17)
endif()
if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

find_package(ament_cmake REQUIRED)
find_package(builtin_interfaces REQUIRED)
find_package(std_msgs REQUIRED)
find_package(sensor_msgs REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(rosidl_default_generators REQUIRED)

set(ACTION_FILES
  "action/CalibrateCamera.action"
)

set(SRV_FILES
  "srv/ReloadCalibration.srv"
)

rosidl_generate_interfaces(${PROJECT_NAME}
  ${ACTION_FILES}
  ${SRV_FILES}
  DEPENDENCIES builtin_interfaces std_msgs sensor_msgs geometry_msgs
)

ament_export_dependencies(rosidl_default_runtime)
ament_package()
