# -*- coding: utf-8 -*-
from rest_framework import serializers
from rest_framework.helpers import status
from rest_framework.response import Response

__author__ = 'caowenbin'


class CreateModelMixin(object):
    """
    创建
    """
    def perform_create(self, form):
        """
        :param form:
        :return:
        """
        instance = form.save()
        return instance

    def create(self, *args, **kwargs):
        form = self.get_form(data=self.json_data)

        if form.is_valid(raise_exception=self.form_valid_raise_except):
            instance = self.perform_create(form)

            if self.need_obj_serializer:
                self.create_serializer(form)
                serializer = self.get_serializer(instance=instance)
                result = serializer.data
            else:
                pk = instance._meta.primary_key.name
                result = {"{}".format(pk): getattr(instance, pk, None)}

            return self.write_response(data=result, status_code=status.HTTP_201_CREATED)

        return self.write_response(data=form.errors, status_code=status.HTTP_400_BAD_REQUEST)

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
    def list(self, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.write_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)

        return Response(serializer.data)


class RetrieveModelMixin(object):
    """
    查看详情
    """
    def retrieve(self, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance=instance)
        return self.write_response(serializer.data)


class UpdateModelMixin(object):
    """
    修改实例对象
    """
    def update(self, *args, **kwargs):
        instance = self.get_object()
        form = self.get_form(instance=instance, data=self.json_data)

        if form.is_valid(raise_exception=self.form_valid_raise_except):
            instance = self.perform_update(form)
            if self.need_obj_serializer:
                self.create_serializer(form)
                serializer = self.get_serializer(instance=instance)
                result = serializer.data
            else:
                pk = instance._meta.primary_key.name
                result = {"{}".format(pk): getattr(instance, pk, None)}

            return self.write_response(data=result, status_code=status.HTTP_200_OK)

        return self.write_response(data=form.errors, status_code=status.HTTP_400_BAD_REQUEST)

    def perform_update(self, form):
        instance = form.save()
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
    def destroy(self, *args, **kwargs):
        instance = self.get_object()
        del_rows = self.perform_destroy(instance)
        return self.write_response(data=dict(rows=del_rows), status_code=status.HTTP_200_OK)

    def perform_destroy(self, instance):
        del_rows = instance.delete_instance()
        return del_rows
