# -*- coding: utf-8 -*-
from os.path import dirname, join
from setuptools import setup, find_packages
__author__ = 'caowenbin'

with open(join(dirname(__file__), 'VERSION'), 'rb') as f:
    version = f.read().decode('ascii').strip()


setup(
    name='tornado-rest-framework',
    version=version,
    url='',
    description='Tornado Rest Framework',
    author='caowenbin',
    author_email='binhua18@126.com',
    license='BSD',
    packages=find_packages(exclude=('admin', 'admin.*', 'rest_framework.test', 'rest_framework.test.*')),
    include_package_data=True,
    zip_safe=False,
    classifiers=[],
    entry_points={'console_scripts': [
        'tornado-fire = rest_framework.management:execute_from_command_line',
    ]},
    install_requires=[
        'tornado>=4.5.2',
        'peewee>=2.10.1',
        'nose',
        'PyMySQL>=0.7.11',
    ],
)
