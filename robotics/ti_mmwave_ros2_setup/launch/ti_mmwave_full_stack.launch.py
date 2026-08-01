"""
Full robotics stack launch: TI IWR6843 + PointPillars + Nav2 + SLAM

Components:
1. IWR6843 driver → Point cloud publishing
2. Point cloud → 2D laser scan (for legacy SLAM)
3. PointPillars detector → Object detection (3D bboxes)
4. OctoMap SLAM → 3D environment mapping
5. Nav2 → Navigation with radar costmap
6. Obstacle detector → Collision avoidance
"""

from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription, DeclareLaunchArgument, SetEnvironmentVariable
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare
import os


def generate_launch_description():
    """Launch the complete TI mmWave robotics stack."""

    # Arguments
    uart_port = LaunchConfiguration('uart_port')
    baud_rate = LaunchConfiguration('baud_rate')
    enable_slam = LaunchConfiguration('enable_slam')
    enable_nav2 = LaunchConfiguration('enable_nav2')
    enable_detector = LaunchConfiguration('enable_detector')

    declare_uart_port = DeclareLaunchArgument(
        'uart_port',
        default_value='/dev/ttyUSB0',
        description='UART port for IWR6843'
    )

    declare_baud_rate = DeclareLaunchArgument(
        'baud_rate',
        default_value='115200',
        description='UART baud rate'
    )

    declare_enable_slam = DeclareLaunchArgument(
        'enable_slam',
        default_value='true',
        description='Enable OctoMap SLAM'
    )

    declare_enable_nav2 = DeclareLaunchArgument(
        'enable_nav2',
        default_value='true',
        description='Enable Nav2 navigation'
    )

    declare_enable_detector = DeclareLaunchArgument(
        'enable_detector',
        default_value='true',
        description='Enable PointPillars object detection'
    )

    # Get package path
    pkg_share = FindPackageShare('ti_mmwave_robotics').find('ti_mmwave_robotics')
    config_dir = PathJoinSubstitution([pkg_share, 'config'])

    # ====== 1. IWR6843 Driver Node ======
    ti_mmwave_node = Node(
        package='ti_mmwave_robotics',
        executable='ti_mmwave_ros_node',
        name='ti_mmwave_driver',
        output='screen',
        parameters=[
            {
                'uart_port': uart_port,
                'baud_rate': baud_rate,
                'frame_id': 'radar',
                'publish_rate_hz': 10.0,
                'max_range_m': 50.0,
                'min_range_m': 0.5,
                'azimuth_fov_deg': 120.0,
                'elevation_fov_deg': 60.0,
                'enable_clustering': True,
                'cluster_threshold_m': 0.5,
            }
        ],
        remappings=[
            ('/radar/pointcloud', '/radar/raw_pointcloud'),
            ('/radar/raw_data', '/radar/raw_measurements'),
        ]
    )

    # ====== 2. Point Cloud to 2D Laser Scan (for SLAM compatibility) ======
    pointcloud_to_scan_node = Node(
        package='pointcloud_to_laserscan',
        executable='pointcloud_to_laserscan_node',
        name='pointcloud_to_scan',
        output='screen',
        parameters=[
            config_dir + '/pointcloud_to_scan.yaml'
        ],
        remappings=[
            ('cloud_in', '/radar/raw_pointcloud'),
            ('scan', '/radar/scan_2d'),
        ]
    )

    # ====== 3. PointPillars 3D Object Detector ======
    pointpillars_node = Node(
        package='ti_mmwave_robotics',
        executable='pointpillars_detector_node',
        name='pointpillars_detector',
        output='screen',
        parameters=[
            {
                'model_path': PathJoinSubstitution([pkg_share, 'models', 'pointpillars_radar.onnx']),
                'score_threshold': 0.5,
                'nms_threshold': 0.5,
                'max_objects': 20,
                'input_cloud_topic': '/radar/raw_pointcloud',
                'output_detections_topic': '/radar/objects_3d',
                'frame_id': 'radar',
            }
        ],
        condition=IncludeLaunchDescription(
            'enable_detector'
        )
    )

    # ====== 4. OctoMap SLAM Node ======
    octomap_node = Node(
        package='ti_mmwave_robotics',
        executable='radar_octomap_node',
        name='radar_octomap_mapping',
        output='screen',
        parameters=[
            {
                'input_topic': '/radar/raw_pointcloud',
                'frame_id': 'radar',
                'octomap_publish_rate': 2.0,
                'octree_resolution': 0.05,  # 5cm voxels
                'occupancy_threshold': 0.5,
                'max_range': 50.0,
                'min_range': 0.5,
            }
        ],
        condition=IncludeLaunchDescription(
            'enable_slam'
        )
    )

    # ====== 5. Nav2 Navigation Stack (optional) ======
    # This would normally include full nav2 bringup with costmap, planner, controller
    # Simplified here - full config in separate launch file
    nav2_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource([
            PathJoinSubstitution([
                FindPackageShare('nav2_bringup'),
                'launch',
                'bringup_launch.py'
            ])
        ]),
        launch_arguments={
            'use_sim_time': 'false',
            'params_file': PathJoinSubstitution([config_dir, 'nav2_params.yaml']),
        },
        condition=IncludeLaunchDescription(
            'enable_nav2'
        )
    )

    # ====== 6. Radar Obstacle Detector (Collision Avoidance) ======
    obstacle_detector_node = Node(
        package='ti_mmwave_robotics',
        executable='radar_obstacle_detector_node',
        name='radar_obstacle_detector',
        output='screen',
        parameters=[
            {
                'input_topic': '/radar/raw_pointcloud',
                'detection_output_topic': '/radar/obstacles',
                'frame_id': 'radar',
                'danger_zone_radius_m': 2.0,
                'warning_zone_radius_m': 5.0,
                'min_object_height_m': 0.1,
                'min_cluster_size': 5,
                'ground_removal_enabled': True,
                'ground_plane_height_m': -0.5,
                'ground_thickness_m': 0.3,
            }
        ]
    )

    # ====== 7. TF Publisher (radar → base_link) ======
    tf_node = Node(
        package='tf2_ros',
        executable='static_transform_publisher',
        name='radar_tf_broadcaster',
        output='screen',
        arguments=[
            '0', '0', '0.5',      # x, y, z translation (50cm height)
            '0', '0', '0',        # roll, pitch, yaw rotation
            'base_link', 'radar'  # parent_frame, child_frame
        ]
    )

    # ====== Build launch description ======
    ld = LaunchDescription([
        # Declare launch arguments
        declare_uart_port,
        declare_baud_rate,
        declare_enable_slam,
        declare_enable_nav2,
        declare_enable_detector,

        # Set environment
        SetEnvironmentVariable('ROS_LOG_DIR', '/tmp/ros_logs'),

        # Core nodes (always run)
        ti_mmwave_node,
        pointcloud_to_scan_node,
        tf_node,
        obstacle_detector_node,

        # Optional components
        pointpillars_node,
        octomap_node,
        nav2_launch,
    ])

    return ld
