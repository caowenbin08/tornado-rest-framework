# -*- coding: utf-8 -*-
from setuptools import setup, find_packages

setup(
    name='tornado-rest-framework',
    version="0.1.1",
    keywords=("tornado", "asyncio", "rest api", "python3"),
    description='Tornado Rest Framework',
    long_description="Tornado Rest Framework",
    author='caowenbin',
    author_email='cwb201314@qq.com',
    url='https://github.com/caowenbin/tornado-rest-framework',
    download_url='https://github.com/caowenbin/tornado-rest-framework',
    license='BSD',
    packages=find_packages(exclude=('admin', 'admin.*', 'rest_framework.test', 'rest_framework.test.*')),
    include_package_data=True,
    zip_safe=False,
    classifiers=[
       'Programming Language :: Python :: 3.6',
    ],
    scripts=['rest_framework/bin/tornado-admin.py'],
    entry_points={'console_scripts': [
        'tornado-admin = rest_framework.core.script:execute_from_command_line',
    ]},
    install_requires=[
        "tornado>=4.5.2",
        "pytz",
        "blinker>=1.4",
        "Babel>=2.5.1",
        "ujson"
    ]
)
