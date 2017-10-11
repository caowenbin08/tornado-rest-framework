# -*- coding: utf-8 -*-

__author__ = 'caowenbin'

# 是否调试模式
DEBUG = False

# 是否开启XSRF防护, 默认不开启
XSRF_COOKIES = False

# 缓存配置
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
    }
}

# 分页记录量
PAGE_SIZE = 10
