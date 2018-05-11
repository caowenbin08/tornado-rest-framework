# -*- coding: utf-8 -*-
from os.path import dirname, join, abspath
from setuptools import setup, find_packages

HERE = abspath(dirname(__file__))

with open(join(HERE, 'VERSION'), 'rb') as f:
    version = f.read().decode('ascii').strip()

with open(join(HERE, "requirements.txt"), encoding='utf-8') as f:
    REQUIRES = f.readlines()


setup(
    name='tornado-rest-framework',
    version=version,
    description='Tornado Rest Framework',
    author='caowenbin',
    author_email='cwb201314@qq.com',
    keywords="tornado asyncio api",
    url='https://github.com/caowenbin/tornado-rest-framework',
    download_url='https://github.com/caowenbin/tornado-rest-framework',
    license='BSD',
    packages=find_packages(exclude=('admin', 'admin.*', 'rest_framework.test', 'rest_framework.test.*')),
    include_package_data=True,
    zip_safe=False,
    classifiers=[
       'Programming Language :: Python :: 3.6.1',
    ],
    scripts=['rest_framework/bin/tornado-admin.py'],
    entry_points={'console_scripts': [
        'tornado-admin = rest_framework.core.script:execute_from_command_line',
    ]},
    install_requires=REQUIRES
)
