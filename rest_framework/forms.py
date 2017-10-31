# -*- coding: utf-8 -*-
import copy
import traceback
from collections import OrderedDict, Mapping

from rest_framework.conf import settings
from rest_framework.db import models
from rest_framework.exceptions import ErrorDetail, ValidationError, ImproperlyConfigured
from rest_framework.fields import *
from rest_framework.helpers import functional, model_meta
from rest_framework.helpers.cached_property import cached_property
from rest_framework.helpers.field_mapping import ClassLookupDict
from rest_framework.helpers.field_mapping import get_field_kwargs
from rest_framework.fields import __all__ as fields_all
from rest_framework.validators import UniqueTogetherValidator

__author__ = 'caowenbin'

__all__ = ['Form', 'ModelForm'] + fields_all
ALL_FIELDS = '__all__'


class BaseForm(Field):

    def __init__(self, instance=None, data=empty, **kwargs):
        """
        :param instance: 待变更数据model对象 （从数据库查询）
        :param data:  变更数据参数（字典结构）
        :param kwargs:
        """
        self.instance = instance
        if data is not empty:
            self.initial_data = data

        # self.partial = kwargs.pop('partial', False)
        # self._context = kwargs.pop('context', {})
        self._data = None
        # self._validated_data = None
        self._errors = None
        kwargs["null"] = True
        kwargs["required"] = False
        super(BaseForm, self).__init__(**kwargs)

    def to_internal_value(self, data):
        raise NotImplementedError('`to_internal_value()` must be implemented.')

    def to_representation(self, instance):
        pass

    def update(self, instance, validated_data):
        raise NotImplementedError('`update()` must be implemented.')

    def create(self, validated_data):
        raise NotImplementedError('`create()` must be implemented.')

    def save(self, **kwargs):
        assert hasattr(self, '_errors'), "没有显式调用执行`.is_valid()`"
        assert not self.errors, "存在无效的参数"

        validated_data = dict(
            list(self.data.items()) +
            list(kwargs.items())
        )

        if self.instance is not None:
            self.instance = self.update(self.instance, validated_data)
            assert self.instance is not None, (
                '`update()` did not return an object instance.'
            )
        else:
            self.instance = self.create(validated_data)
            assert self.instance is not None, (
                '`create()` did not return an object instance.'
            )

        return self.instance

    def is_valid(self, raise_exception=False):
        assert hasattr(self, 'initial_data'), (
            'Cannot call `.is_valid()` as no `data=` keyword argument was '
            'passed when instantiating the serializer instance.'
        )

        if self._data is None:
            try:
                self._data = self.resolve_validation_data(self.initial_data)
            except ValidationError as exc:
                self._data = {}
                self._errors = exc.detail
            else:
                self._errors = {}

        if self._errors and raise_exception:
            raise ValidationError(self.errors)

        return not bool(self._errors)

    @property
    def errors(self):
        if self._errors is None:
            raise AssertionError("必须显式调用`.is_valid()`方可获取`errors`")
        return self._errors

    @property
    def data(self):
        if self._data is None:
            raise AssertionError("必须显式调用`.is_valid()`方可获取`data`")
        return self._data


class FormMetaclass(type):

    @staticmethod
    def _get_declared_fields(bases, attributes):
        fields = [(field_name, attributes.pop(field_name))
                  for field_name, obj in list(attributes.items())
                  if isinstance(obj, Field)]

        fields.sort(key=lambda x: getattr(x[1], "_creation_counter"))

        for base in reversed(bases):
            if hasattr(base, '_declared_fields'):
                fields = [
                    (field_name, obj) for field_name, obj
                    in getattr(base, "_declared_fields").items()
                    if field_name not in attributes
                ] + fields

        return OrderedDict(fields)

    def __new__(mcs, name, bases, attributes):
        attributes['_declared_fields'] = mcs._get_declared_fields(bases, attributes)
        return super(FormMetaclass, mcs).__new__(mcs, name, bases, attributes)


def as_form_error(exc):
    """
    把字典或列表错误列表转成对应的字典结构
    :param exc:
    :return:
    """
    assert isinstance(exc, ValidationError)
    detail = exc.detail

    if isinstance(detail, Mapping):
        return {
            key: value if isinstance(value, (list, Mapping)) else [value]
            for key, value in detail.items()
        }
    elif isinstance(detail, list):
        return {
            settings.FIELD_ERRORS_KEY: detail[0] if len(detail) == 1 else detail
        }

    return {
        settings.FIELD_ERRORS_KEY: detail
    }


@functional.add_metaclass(FormMetaclass)
class Form(BaseForm):
    default_error_messages = {
        'invalid': '无效数据。 期望字典，但其数据类型为{data_type}'
    }

    def update(self, instance, validated_data):
        raise NotImplementedError('`update()` must be implemented.')

    def create(self, validated_data):
        raise NotImplementedError('`create()` must be implemented.')

    @property
    def fields(self):
        """
        返回字典结构
        类似：{field_name: field_instance}
        :return:
        """
        if not hasattr(self, '_fields'):
            setattr(self, "_fields", functional.BindingDict(self))
            for key, value in self.get_fields().items():
                self._fields[key] = value
        return self._fields

    @cached_property
    def _writable_fields(self):
        """
        返回可修改的字段列表
        过滤掉只读及默认值为空的字段
        :return:
        """
        return [field for field in self.fields.values() if (not field.read_only) or (field.default is not None)]

    def get_fields(self):
        """
        获得所有字段数据，类似{field_name: field_instance}
        每一个新的序列化器创建克隆领域的实例,允许用户动态地修改字段序列化器, 不影响其他实例序列化器类
        """
        return copy.deepcopy(self._declared_fields)

    def get_validators(self):
        """
        从Meta中获取定义的校验函数列表
        :return:
        """
        meta = getattr(self, 'Meta', None)
        validators = getattr(meta, 'validators', None)
        assert isinstance(validators, (type(None), tuple, list)), "`Meta.validators`的结构必须为tuple或list"
        return validators[:] if validators is not None else []

    def get_value(self, dictionary):
        """
        根据参数名从参数组（字典结构）获取参数的值
        :param dictionary: 参数组（字典结构）
        :return:
        """
        return dictionary.get(self.field_name, empty)

    def resolve_validation_data(self, data=empty):
        """
        解析字段的值以及校验值的合格性，如果不合格则抛出对应的校验异常，反之对应的字段值，其可能是默认值
        :param data:
        :return:
        """
        is_empty_value, data = self.validate_empty_values(data)
        # 如果值为空或默认值，则直接返回，不再执行值的约束条件判断方法
        if is_empty_value:
            return data

        value = self.to_internal_value(data)
        try:
            self.run_validators(value)
            value = self.validate(value)
            assert value is not None, '.validate()必须要返回校验之后的值'
        except ValidationError as exc:
            raise ValidationError(detail=as_form_error(exc))

        return value

    def validate(self, params):
        """
        所有字段校验之后，进行业务或字段组合检查
        :param params:
        :return:
        """
        return params

    def to_internal_value(self, data):
        """
        表单数据转成模型对应的数据结构
        :param data: 表单数据
        :return:
        """
        ret = OrderedDict()
        errors = OrderedDict()

        for field in self._writable_fields:
            # 是否有自定义的检查方法
            validate_method = getattr(self, 'validate_' + field.field_name, None)
            # 表单原始值
            primitive_value = field.get_value(data)
            try:
                # 解析字段的值以及校验值的合格性，如果不合格则抛出对应的校验异常，反之对应的字段值，其可能是默认值
                validated_value = field.resolve_validation_data(primitive_value)

                if validate_method is not None:
                    validated_value = validate_method(validated_value)

            except ValidationError as exc:
                detail = exc.detail
                errors[field.field_name] = exc.detail[0] if len(detail) == 1 else detail

            else:
                functional.set_value(ret, field.source_attrs, validated_value)

        if errors:
            raise ValidationError(errors)

        return ret

    def __iter__(self):
        for field in self.fields.values():
            yield self[field.field_name]

    @property
    def errors(self):
        ret = super(Form, self).errors
        if isinstance(ret, list) and len(ret) == 1 and getattr(ret[0], 'code', None) == 'null':
            # 边界情况。提供一个更具描述性的错误说明，比“这个字段可能不空”好。当没有数据传递。
            detail = ErrorDetail(string='没有提供数据', code='null')
            ret = {"non_field_errors": [detail]}
        return ret
        # return functional.ReturnDict(ret, serializer=self)


class ModelForm(Form):
    """
    基于数据模型的表单
    """
    # 模型的字段类型与表单字段类型的对应关系
    form_field_mapping = {
        models.CharField: CharField,
        models.FixedCharField: CharField,
        models.TextField: CharField,
        models.DateTimeField: DateTimeField,
        models.IntegerField: IntegerField,
        models.BooleanField: BooleanField,
        models.FloatField: FloatField,
        models.DoubleField: FloatField,
        models.BigIntegerField: IntegerField,
        models.SmallIntegerField: IntegerField,
        models.PrimaryKeyField: IntegerField,
        models.ForeignKeyField: IntegerField,
        models.DateField: DateField,
        models.TimeField: TimeField,
        models.TimestampField: IntegerField,
        models.UUIDField: UUIDField,
    }
    form_choice_field = ChoiceField

    def raise_errors_on_nested_writes(self, method_name, validated_data):
        """
        给出明确的错误当用户试图通过可写的嵌套数据
        :param method_name:
        :param validated_data:
        :return:
        """
        # 确保我们没有一个可写的嵌套字段. For example:
        #
        # class UserForm(ModelForm):
        #     ...
        #     profile = ProfileForm()

        assert not any(
            isinstance(field, BaseForm) and
            (field.source in validated_data) and
            isinstance(validated_data[field.source], (list, dict))
            for field in self._writable_fields
        ), (
            'The `.{method_name}()` method does not support writable nested '
            'fields by default.\nWrite an explicit `.{method_name}()` method for '
            'serializer `{module}.{class_name}`, or set `read_only=True` on '
            'nested serializer fields.'.format(
                method_name=method_name,
                module=self.__class__.__module__,
                class_name=self.__class__.__name__
            )
        )

        # 确保我们没有可写的dotted-source字段. For example:
        #
        # class UserForm(ModelForm):
        #     ...
        #     address = forms.CharField('profile.address')

        assert not any(
            '.' in field.source and
            (key in validated_data) and
            isinstance(validated_data[key], (list, dict))
            for key, field in self.fields.items()
        ), (
            'The `.{method_name}()` method does not support writable dotted-source '
            'fields by default.\nWrite an explicit `.{method_name}()` method for '
            'serializer `{module}.{class_name}`, or set `read_only=True` on '
            'dotted-source serializer fields.'.format(
                method_name=method_name,
                module=self.__class__.__module__,
                class_name=self.__class__.__name__
            )
        )

    def create(self, validated_data):
        """
        创建
        :param validated_data:
        :return:
        """
        self.raise_errors_on_nested_writes('create', validated_data)
        model_class = self.Meta.model
        try:
            instance = model_class.create(**validated_data)
        except TypeError:
            tb = traceback.format_exc()
            msg = (
                'Got a `TypeError` when calling `%s.objects.create()`. '
                'This may be because you have a writable field on the '
                'serializer class that is not a valid argument to '
                '`%s.objects.create()`. You may need to make the field '
                'read-only, or override the %s.create() method to handle '
                'this correctly.\nOriginal exception was:\n %s' %
                (
                    model_class.__name__,
                    model_class.__name__,
                    self.__class__.__name__,
                    tb
                )
            )
            raise TypeError(msg)

        return instance

    def update(self, instance, validated_data):
        """
        修改
        :param instance:
        :param validated_data:
        :return:
        """
        self.raise_errors_on_nested_writes('update', validated_data)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        return instance

    def get_validators(self):
        """
        确定校验时使用Meta的validators列表
        :return:
        """
        validators = getattr(getattr(self, 'Meta', None), 'validators', [])
        assert isinstance(validators, (tuple, list)), "`Meta.validators`的结构必须为tuple或list"
        unique_together_validators = self.get_unique_together_validators()
        unique_together_validators.extend(validators)
        return unique_together_validators

    def get_unique_together_validators(self):
        """
        获取Model的`Meta.indexes`中定义的唯一索引列表
        :return:
        """
        # 获得 `Meta.indexes`中定义的唯一索引
        indexes = getattr(getattr(self.Meta.model, "_meta", None), "indexes", [])
        model_unique_together_list = (index[0] for index in indexes if index[1] is True)
        field_names = {
            field.source for field in self._writable_fields
            if (field.source != '*') and ('.' not in field.source)
        }
        validators = []
        for unique_together in model_unique_together_list:
            if field_names.issuperset(unique_together):
                validator = UniqueTogetherValidator(
                    queryset=self.Meta.model.select(),
                    fields=unique_together
                )
                validators.append(validator)
        return validators

    def get_fields(self):
        """
        返回所有字段的数据
        结构为{field name: field instances}，即字段关键名称 ——> 字段实例对象
        当实例化表单，请调用`self.fields`
        """
        form_class = self.__class__.__name__
        assert hasattr(self, 'Meta'), "表单类{form_class}没有定义'Meta'属性".format(form_class=form_class)
        assert hasattr(self.Meta, 'model'), "表单类{form_class}没有定义'Meta.model'属性".format(form_class=form_class)
        # 自定义的字段，非从model的
        declared_fields = copy.deepcopy(self._declared_fields)
        model = getattr(self.Meta, 'model')
        depth = getattr(self.Meta, 'depth', 0)

        if depth is not None:
            assert depth >= 0, "'depth'不能为负数."
            assert depth <= 10, "'depth'最大不能超过10."

        # 检索元数据字段和关系模型类
        info = model_meta.get_field_info(model)
        field_names = self.get_field_names(declared_fields, info)
        extra_kwargs = self.get_extra_kwargs()

        fields = OrderedDict()

        for field_name in field_names:
            # 如果字段在类上显式声明，则直接使用
            if field_name in declared_fields:
                fields[field_name] = declared_fields[field_name]
                continue

            extra_field_kwargs = extra_kwargs.get(field_name, {})
            source = extra_field_kwargs.get('source') or field_name
            field_class, field_kwargs = self.build_field(source, info, model, depth)
            field_kwargs = self.include_extra_kwargs(field_kwargs, extra_field_kwargs)
            fields[field_name] = field_class(**field_kwargs)

        return fields

    @staticmethod
    def include_extra_kwargs(kwargs, extra_kwargs):
        """
        删除任何不兼容的现有关键字参数
        :param kwargs: 字段本身的关键参数
        :param extra_kwargs:  `Meta.extra_kwargs`定义的字段扩展关键参数
        :return:
        """
        if extra_kwargs.get('read_only', False):
            for attr in ['required', 'default', 'null', 'min_length',
                         'max_length', 'min_value', 'max_value', 'validators']:
                kwargs.pop(attr, None)

        if extra_kwargs.get('default') and kwargs.get('required') is False:
            kwargs.pop('required')

        if extra_kwargs.get('read_only', kwargs.get('read_only', False)):
            extra_kwargs.pop('required', None)

        kwargs.update(extra_kwargs)

        return kwargs

    def get_extra_kwargs(self):
        """
        获得表单的字段扩展参数以及解析只读字段标识
        返回字段与字段参数组成的字典结构
        """
        extra_kwargs = copy.deepcopy(getattr(self.Meta, 'extra_kwargs', {}))
        read_only_fields = getattr(self.Meta, 'read_only_fields', None)
        if read_only_fields is not None:
            if not isinstance(read_only_fields, (list, tuple)):
                raise TypeError(
                    'The `read_only_fields` option must be a list or tuple. '
                    'Got %s.' % type(read_only_fields).__name__
                )

            for field_name in read_only_fields:
                kwargs = extra_kwargs.get(field_name, {})
                kwargs['read_only'] = True
                extra_kwargs[field_name] = kwargs

        return extra_kwargs

    def get_field_names(self, declared_fields, info):
        """
        返回所有指定的字段名字列表
        返回的列表由自定义的字段（declared_fields）、Meta.exclude、Meta.fields三个拼成的
        :param declared_fields: 自定义的字段列表
        :param info:
        :return:
        """
        fields = getattr(self.Meta, 'fields', None)
        exclude = getattr(self.Meta, 'exclude', None)

        if fields and fields != ALL_FIELDS and not isinstance(fields, (list, tuple)):
            raise TypeError("Meta.fields的属性或值必须为list、tuple、__all__ 三者之一，"
                            "而不是{field_type}".format(field_type=type(fields).__name__))

        if exclude and not isinstance(exclude, (list, tuple)):
            raise TypeError("Meta.exclude的属性或值必须为list或tuple，"
                            "而不是{field_type}".format(field_type=type(exclude).__name__))

        assert not (fields and exclude), "表单类{form_class}的Meta不能同时存在'fields'和'exclude'".format(
            form_class=self.__class__.__name__)

        assert not (fields is None and exclude is None), "表单类{form_class}的Mete必须存在'fields'或'exclude'".format(
            form_class=self.__class__.__name__)

        if fields == ALL_FIELDS:
            fields = None

        if fields is not None:
            required_field_names = set(declared_fields)
            for cls in self.__class__.__bases__:
                required_field_names -= set(getattr(cls, '_declared_fields', []))

            for field_name in required_field_names:
                assert field_name in fields, "字段'{field_name}'定义在表单`{form_class}`中，但没有包括在'fields'中".format(
                    field_name=field_name, form_class=self.__class__.__name__
                )

            return fields

        # 如果`Meta.fields`为__all__，则获取默认的表单字段
        fields = self.get_default_field_names(declared_fields, info)

        if exclude is not None:
            for field_name in exclude:
                assert field_name in fields, "exclude的`{field_name}`属性不在表单类`{form_class}`中".format(
                    field_name=field_name, form_class=self.__class__.__name__
                )
                fields.remove(field_name)

        return fields

    @staticmethod
    def get_default_field_names(declared_fields, model_info):
        """
        Return the default list of field names that will be used if the
        `Meta.fields` option is not specified.
        """
        return (
            [model_info.pk.name] +
            list(declared_fields.keys()) +
            list(model_info.fields.keys()) +
            list(model_info.forward_relations.keys())
        )

    def build_field(self, field_name, info, model_class, nested_depth):
        """
        Return a two tuple of (cls, kwargs) to build a serializer field with.
        """
        if field_name in info.fields_and_pk:
            model_field = info.fields_and_pk[field_name]
            return self.build_standard_field(field_name, model_field)

        return self.build_unknown_field(field_name, model_class)

    def build_standard_field(self, field_name, model_field):
        """
         模型字段与表单字段绑定
        :param field_name: 字段名
        :param model_field: 模型字段类型
        :return:
        """
        field_mapping = ClassLookupDict(self.form_field_mapping)

        field_class = field_mapping[model_field]
        field_kwargs = get_field_kwargs(field_name, model_field)

        if 'choices' in field_kwargs:
            field_class = self.form_choice_field
            valid_kwargs = set((
                'required', 'default', 'source',
                'error_messages', 'validators', 'null',
                'choices'
            ))
            for key in list(field_kwargs.keys()):
                if key not in valid_kwargs:
                    field_kwargs.pop(key)

        return field_class, field_kwargs

    @staticmethod
    def build_unknown_field(field_name, model_class):
        """
        抛出没有定义的字段异常
        """
        raise ImproperlyConfigured(
            'Field name `%s` is not valid for model `%s`.' %
            (field_name, model_class.__name__)
        )
