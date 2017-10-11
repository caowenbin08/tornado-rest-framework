# -*- coding: utf-8 -*-
import datetime
from rest_framework import forms
__author__ = 'caowenbin'

#
# class CreateUserForm(forms.Form):
#     """
#     表单
#         'BooleanField', 'NullBooleanField', 'CharField', 'EmailField',
#     'RegexField', 'URLField', 'UUIDField', 'IPAddressField',
#     'IntegerField', 'FloatField', 'DateTimeField', 'DateField',
#     'TimeField',  'ChoiceField', 'MultipleChoiceField',  '_UnvalidatedField', 'ListField', 'JSONField'
#     """
#     MAN, WOMAN = 1, 2
#     SEX_CHOICES = (
#         (MAN, "男"),
#         (WOMAN, "女"),
#     )
#
#     is_admin = forms.BooleanField("是否管理员", required=False, default=False, null=True)
#     is_super = forms.NullBooleanField("是否超级管理员", default=False, null=False)
#     user_name = forms.CharField("用户名")
#     email = forms.EmailField("邮箱地址")
#     login_name = forms.RegexField(regex="^[A-Za-z0-9_]+$", verbose_name="登录名")
#     blog_url = forms.URLField("博客")
#     login_ip = forms.IPAddressField("登录IP")
#     age = forms.IntegerField("年龄", min_value=18, max_value=60)
#     money = forms.FloatField("金钱",)
#     login_time = forms.DateTimeField("登录时间", default=datetime.datetime.now)
#     birthday = forms.DateField("生日", input_formats="%Y/%m/%d", null=True)
#     alarm_clock = forms.TimeField("闹钟时间", null=True)
#     sex = forms.ChoiceField("性别", choices=SEX_CHOICES, default=MAN)


class TestForm(object):
    def test_boolean_field_error_1(self):
        try:
            class BooleanForm(forms.Form):
                is_admin = forms.BooleanField("是否管理员", required=False, default=False, null=True)
        except AssertionError:
            assert True
        else:
            assert False
