cmake_minimum_required(VERSION 3.16)
project(ti_mmwave_robotics VERSION 1.0.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

# ROS2 dependencies
find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(rclcpp_components REQUIRED)
find_package(sensor_msgs REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(nav_msgs REQUIRED)
find_package(tf2 REQUIRED)
find_package(tf2_ros REQUIRED)
find_package(PCL REQUIRED)
find_package(pcl_ros REQUIRED)
find_package(pcl_conversions REQUIRED)

# Point cloud processing
find_package(OpenCV REQUIRED)
find_package(Eigen3 REQUIRED)

# Include directories
include_directories(
  include
  ${PCL_INCLUDE_DIRS}
  ${OpenCV_INCLUDE_DIRS}
)

# Add library for IWR6843 driver wrapper
add_library(ti_mmwave_driver
  src/ti_mmwave_driver.cpp
  src/uart_interface.cpp
  src/pointcloud_converter.cpp
)

target_link_libraries(ti_mmwave_driver
  ${PCL_LIBRARIES}
  ${OpenCV_LIBRARIES}
)

# IWR6843 ROS2 Node
add_executable(ti_mmwave_ros_node
  src/ti_mmwave_ros_node.cpp
)

target_link_libraries(ti_mmwave_ros_node
  ti_mmwave_driver
  ${PCL_LIBRARIES}
  ${OpenCV_LIBRARIES}
)

ament_target_dependencies(ti_mmwave_ros_node
  rclcpp
  rclcpp_components
  sensor_msgs
  geometry_msgs
  pcl_ros
  pcl_conversions
  tf2
  tf2_ros
)

# Pointcloud to laserscan converter
add_executable(pointcloud_to_laserscan_node
  src/pointcloud_to_laserscan_node.cpp
)

ament_target_dependencies(pointcloud_to_laserscan_node
  rclcpp
  sensor_msgs
  geometry_msgs
  pcl_ros
)

# PointPillars object detector
add_executable(pointpillars_detector_node
  src/pointpillars_detector_node.cpp
)

ament_target_dependencies(pointpillars_detector_node
  rclcpp
  sensor_msgs
  geometry_msgs
  tf2
  tf2_ros
)

# SLAM node (OctoMap integration)
add_executable(radar_octomap_node
  src/radar_octomap_node.cpp
)

target_link_libraries(radar_octomap_node
  ${PCL_LIBRARIES}
)

ament_target_dependencies(radar_octomap_node
  rclcpp
  sensor_msgs
  geometry_msgs
  pcl_ros
  pcl_conversions
)

# Obstacle detector for collision avoidance
add_executable(radar_obstacle_detector_node
  src/radar_obstacle_detector_node.cpp
)

ament_target_dependencies(radar_obstacle_detector_node
  rclcpp
  sensor_msgs
  geometry_msgs
  tf2_ros
)

# Install targets
install(TARGETS
  ti_mmwave_ros_node
  pointcloud_to_laserscan_node
  pointpillars_detector_node
  radar_octomap_node
  radar_obstacle_detector_node
  DESTINATION lib/${PROJECT_NAME}
)

# Install launch files
install(DIRECTORY
  launch/
  DESTINATION share/${PROJECT_NAME}/launch
)

# Install config files
install(DIRECTORY
  config/
  DESTINATION share/${PROJECT_NAME}/config
)

# Install headers for downstream packages
install(DIRECTORY
  include/
  DESTINATION include
)

# Export library
ament_export_libraries(ti_mmwave_driver)
ament_export_targets(ti_mmwave_driver HAS_LIBRARY_TARGET)
ament_export_dependencies(
  rclcpp
  sensor_msgs
  geometry_msgs
  pcl_ros
  pcl_conversions
)

ament_package()
