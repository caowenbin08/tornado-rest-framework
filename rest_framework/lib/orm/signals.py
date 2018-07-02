# -*- coding: utf-8 -*-
from rest_framework.core.singnals import signal

pre_save = signal("pre_save")
post_save = signal("post_save")
pre_delete = signal("pre_delete")
post_delete = signal("post_delete")
pre_init = signal("pre_init")
