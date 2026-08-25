cmake_minimum_required(VERSION 3.8)
project(qrcode_detector)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(rclcpp_components REQUIRED)
find_package(sensor_msgs REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(std_msgs REQUIRED)
find_package(diagnostic_msgs REQUIRED)
find_package(diagnostic_updater REQUIRED)
find_package(cv_bridge REQUIRED)
find_package(ament_index_cpp REQUIRED)
find_package(OpenCV REQUIRED)

include_directories(include)

# Component library
add_library(qrcode_detector_component SHARED
  src/qrcode_node.cpp
)

target_include_directories(qrcode_detector_component PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>
  ${OpenCV_INCLUDE_DIRS}
)

target_compile_definitions(qrcode_detector_component PRIVATE
  QRCODE_DETECTOR_BUILDING_LIBRARY
)

ament_target_dependencies(qrcode_detector_component
  rclcpp
  rclcpp_components
  sensor_msgs
  geometry_msgs
  std_msgs
  diagnostic_msgs
  diagnostic_updater
  cv_bridge
  ament_index_cpp
)

target_link_libraries(qrcode_detector_component
  ${OpenCV_LIBRARIES}
)

rclcpp_components_register_node(qrcode_detector_component
  PLUGIN "qrcode_detector::QRCodeNode"
  EXECUTABLE qrcode_node
)

# Standalone executable
add_executable(qrcode_node_bin
  src/qrcode_node_main.cpp
)
set_target_properties(qrcode_node_bin PROPERTIES OUTPUT_NAME qrcode_node)

target_include_directories(qrcode_node_bin PRIVATE
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  ${OpenCV_INCLUDE_DIRS}
)

target_link_libraries(qrcode_node_bin
  qrcode_detector_component
)

ament_target_dependencies(qrcode_node_bin
  rclcpp
)

# Install rules
install(TARGETS
  qrcode_detector_component
  ARCHIVE DESTINATION lib
  LIBRARY DESTINATION lib
  RUNTIME DESTINATION bin
)

install(TARGETS
  qrcode_node_bin
  DESTINATION lib/${PROJECT_NAME}
)

install(DIRECTORY include/
  DESTINATION include
)

install(DIRECTORY models config launch
  DESTINATION share/${PROJECT_NAME}
)

if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  list(APPEND AMENT_LINT_AUTO_EXCLUDE
    ament_cmake_copyright
    ament_cmake_cpplint
    ament_cmake_uncrustify
    ament_cmake_lint_cmake
    ament_cmake_flake8
    ament_cmake_pep257
  )
  ament_lint_auto_find_test_dependencies()

  find_package(ament_cmake_gtest REQUIRED)
  ament_add_gtest(test_qr_node
    test/test_qr_node.cpp
  )
  target_include_directories(test_qr_node PRIVATE
    include
    ${OpenCV_INCLUDE_DIRS}
  )
  target_link_libraries(test_qr_node
    qrcode_detector_component
    ${OpenCV_LIBRARIES}
  )
  ament_target_dependencies(test_qr_node
    rclcpp
  )

  find_package(ament_cmake_pytest REQUIRED)
  ament_add_pytest_test(test_qr_launch
    test/test_qr_launch.py
  )
endif()

ament_package()
