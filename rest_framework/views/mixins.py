# -*- coding: utf-8 -*-
import asyncio
from rest_framework import serializers
from rest_framework.core.exceptions import SkipFilterError
from rest_framework.lib.orm.query import AsyncEmptyQuery
from rest_framework.core.translation import locale, make_lazy_gettext
from rest_framework.utils import status


__all__ = [
    'CreateModelMixin',
    'ListModelMixin',
    'RetrieveModelMixin',
    'UpdateModelMixin',
    'DestroyModelMixin'
]


class CreateModelMixin(object):
    """
    创建
    """
    async def perform_create(self, form):
        """
        :param form:
        :return:
        """
        instance = await form.save()
        return instance

    async def create(self, *args, **kwargs):
        form = self.get_form()

        if await form.is_valid():
            instance = await self.perform_create(form)

            if self.need_obj_serializer:
                self.create_serializer(form)
                serializer = self.get_serializer(instance=instance)
                result = await serializer.data
            else:
                pk = instance._meta.primary_key.name
                result = {"{}".format(pk): getattr(instance, pk, None)}

            return self.write_response(data=result, status_code=status.HTTP_201_CREATED)

        return self.write_response(data=await form.errors, status_code=status.HTTP_400_BAD_REQUEST)

    def create_serializer(self, form):
        """
        如果没有定义self.serializer_class，则自动创建
        :param form:
        :return:
        """
        if self.serializer_class is not None:
            return

        class Serializer(serializers.ModelSerializer):
            class Meta:
                model = form.Meta.model
                fields = '__all__'

        self.serializer_class = Serializer


class ListModelMixin(object):
    """
    分页查询列表
    """
    async def list(self, *args, **kwargs):
        try:
            queryset = await self.filter_queryset(self.get_queryset())
        except SkipFilterError:
            queryset = AsyncEmptyQuery()

        page = await self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return await self.write_paginated_response(await serializer.data)

        serializer = self.get_serializer(queryset, many=True)

        return self.write_response(await serializer.data)


class RetrieveModelMixin(object):
    """
    查看详情
    """
    async def retrieve(self, *args, **kwargs):
        instance = await self.get_object()
        serializer = self.get_serializer(instance=instance)
        return self.write_response(await serializer.data)


class UpdateModelMixin(object):
    """
    修改实例对象
    """
    async def update(self, *args, **kwargs):
        obj_instance = await self.get_object()
        form = self.get_form(empty_permitted=True, instance=obj_instance)
        if await form.is_valid():
            instance = await self.perform_update(form)
            if self.need_obj_serializer:
                self.create_serializer(form)
                serializer = self.get_serializer(instance=instance)
                result = await serializer.data
            else:
                pk = instance._meta.primary_key.name
                result = {"{}".format(pk): getattr(instance, pk, None)}

            return self.write_response(data=result, status_code=status.HTTP_200_OK)

        return self.write_response(data=await form.errors, status_code=status.HTTP_400_BAD_REQUEST)

    async def perform_update(self, form):
        instance = await form.save()
        return instance

    def create_serializer(self, form):
        """
        如果没有定义self.serializer_class，则自动创建
        :param form:
        :return:
        """
        if self.serializer_class is not None:
            return

        class Serializer(serializers.ModelSerializer):
            class Meta:
                model = form.Meta.model
                fields = '__all__'

        self.serializer_class = Serializer


class DestroyModelMixin(object):
    """
    删除对象
    """
    async def destroy(self, *args, **kwargs):
        instance = await self.get_object()
        del_rows = await self.perform_destroy(instance)
        return self.write_response(data=dict(rows=del_rows), status_code=status.HTTP_200_OK)

    async def perform_destroy(self, instance):
        del_rows = await instance.delete_instance()
        return del_rows


class BabelTranslatorMixin(object):
    """
    使用Babel国际化库包
    如果应用程序处理语言环境，则应实现`get_user_locale`方法
    """

    @property
    def _(self):
        """
        A helper to easily get lazy version ugettext
        """
        return make_lazy_gettext(lambda: self.locale.translate)

    def get_browser_locale(self, default="en_US"):
        """Determines the user's locale from Accept-Language header.

        """
        if "Accept-Language" in self.request.headers:
            languages = self.request.headers["Accept-Language"].split(",")
            locales = []
            for language in languages:
                parts = language.strip().split(";")
                if len(parts) > 1 and parts[1].startswith("q="):
                    try:
                        score = float(parts[1][2:])
                    except (ValueError, TypeError):
                        score = 0.0
                else:
                    score = 1.0
                locales.append((parts[0], score))
            if locales:
                locales.sort(key=lambda l, s: s, reverse=True)
                codes = [l[0] for l in locales]
                return locale.get(*codes)
        return locale.get(default)
