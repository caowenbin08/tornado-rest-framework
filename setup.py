# -*- coding: utf-8 -*-
from os.path import dirname, join, abspath
from setuptools import setup, find_packages
__author__ = 'caowenbin'

HERE = abspath(dirname(__file__))

with open(join(HERE, 'VERSION'), 'rb') as f:
    version = f.read().decode('ascii').strip()

with open(join(HERE, "requirements.txt"), encoding='utf-8') as f:
    REQUIRES = f.readlines()


setup(
    name='rest_framework',
    version=version,
    url='',
    description='Tornado Rest Framework',
    author='binhua',
    author_email='binhua18@126.com',
    license='BSD',
    packages=find_packages(exclude=('admin', 'admin.*', 'rest_framework.test', 'rest_framework.test.*')),
    include_package_data=True,
    zip_safe=False,
    classifiers=[],
    scripts=['rest_framework/bin/tornado-admin.py'],
    entry_points={'console_scripts': [
        'tornado-admin = rest_framework.core.script:execute_from_command_line',
    ]},
    install_requires=REQUIRES
)
