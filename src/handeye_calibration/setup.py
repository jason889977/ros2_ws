from setuptools import find_packages, setup

package_name = 'handeye_calibration'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='jason889977',
    maintainer_email='jason889977@users.noreply.github.com',
    description='ROS 2 hand-eye calibration offline solver and static TF tools.',
    license='BSD-3-Clause',
    extras_require={'test': ['pytest']},
    entry_points={
        'console_scripts': [
            'handeye_static_tf_broadcaster = handeye_calibration.handeye_static_tf_broadcaster:main',
            'handeye_calibrate = handeye_calibration.solve:main',
        ],
    },
)
