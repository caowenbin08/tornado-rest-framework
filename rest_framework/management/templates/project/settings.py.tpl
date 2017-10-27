# -*- coding: utf-8 -*-
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DEBUG = True

# 数据库配置
DATABASES = {
    'default': {
        'ENGINE': 'rest_framework.db.backend.sqlite3',
        'NAME': os.path.join(BASE_DIR, 'db.sqlite3'),
    }
}

# url根文件位置
ROOT_URLCONF = 'urls'

#表迁移model文件列表
INSTALLED_APPS = []
