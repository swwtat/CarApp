from setuptools import setup, find_packages
import os
from glob import glob

package_name = 'icar_face'

setup(
    name=package_name,
    version='1.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name, 'launch'),
            glob('launch/*.launch.py')),
        (os.path.join('share', package_name, 'models'),
            glob('models/*')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='iCar Team',
    maintainer_email='admin@icar.local',
    description='iCar face recognition for delivery robot',
    license='MIT',
    entry_points={
        'console_scripts': [
            'face_detector = icar_face.face_detector:main',
            'face_recognizer = icar_face.face_recognizer:main',
            'face_bridge = icar_face.face_bridge:main',
            'face_server = icar_face.face_server:main',
        ],
    },
)
