# -*- coding: utf-8 -*-
# from rest_framework.core.exceptions import ErrorList, ErrorDict
from rest_framework.conf import settings
from rest_framework.core.exceptions import ValidationError
from rest_framework.utils.cached_property import cached_property
from rest_framework.core.translation import lazy_translate as _

__all__ = ('BaseFormSet', 'formset_factory', 'all_valid')

# 默认表单集最小的数量
DEFAULT_MIN_NUM = 0
# 在formset中默认的最大表单数量，以防止内存耗尽
DEFAULT_MAX_NUM = 1000


class BaseFormSet(object):
    """
    A collection of instances of the same Form class.
    """
    def __init__(self, request=None, data=None, files=None, initial=None, form_kwargs=None):
        self.request = request
        self.is_bound = data is not None or files is not None
        self.data = [] if data is None else data
        self.files = [] if files is None else files
        self.initial = initial
        self.form_kwargs = form_kwargs or {}
        self._errors = None
        self.total_form_count = len(self.data)

    @cached_property
    def forms(self):
        forms = [self._construct_form(i, **self.get_form_kwargs(i))
                 for i in range(self.total_form_count)]
        return forms

    def get_form_kwargs(self, index):
        return self.form_kwargs.copy()

    def _construct_form(self, i, **kwargs):
        defaults = {
            'request': self.request
        }

        if self.is_bound:
            defaults['data'] = self.data[i]
            defaults['files'] = self.files

        if self.initial and 'initial' not in kwargs:
            try:
                defaults['initial'] = self.initial[i]
            except IndexError:
                pass

        if i >= self.min_num:
            defaults['empty_permitted'] = True

        defaults.update(kwargs)
        form = self.form(**defaults)
        return form

    @property
    async def cleaned_data(self):
        """
        Returns a list of form.cleaned_data dicts for every form in self.forms.
        """
        if not await self.is_valid():
            return []
        return [await form.cleaned_data for form in self.forms]

    @property
    async def errors(self):
        """
        Returns a list of form.errors for every form in self.forms.
        """
        if self._errors is None:
            await self.full_clean()
        return self._errors

    async def is_valid(self):
        """
        Returns True if every form in self.forms is valid.
        """
        if not self.is_bound:
            return False
        if not isinstance(self.data, list):
            raise ValidationError(
                detail=_("The form data format must be a list structure, not a %s structure."),
                code='FormDataFormatError',
                params=type(self.data).__name__
            )
        forms_valid = True

        for i in range(0, self.total_form_count):
            form = self.forms[i]
            forms_valid &= await form.is_valid()

        return forms_valid and not await self.errors

    async def full_clean(self):
        """
        Cleans all of self.data and populates self._errors and
        self._non_form_errors.
        """
        self._errors = {}

        if not self.is_bound:
            return

        if not isinstance(self.data, list):
            raise ValidationError(
                detail=_("The form data format must be a list structure, not a %s structure."),
                code='FormDataFormatError',
                params=type(self.data).__name__
            )
        for i in range(0, self.total_form_count):
            form = self.forms[i]
            form_error = await form.part_errors
            if form_error:
                for k, v in form_error.items():
                    self._errors["%s-%d" % (k, i+1)] = v

        try:
            if self.max_num is not None and self.total_form_count > self.max_num:
                raise ValidationError(
                    detail=_("Please submit %d or fewer forms"),
                    code='too_many_forms',
                    params=self.max_num
                )
            if self.min_num is not None and self.total_form_count < self.min_num:
                raise ValidationError(
                    detail=_("Please submit %d or more forms"),
                    code='too_few_forms',
                    params=self.min_num
                )

            self.clean()
        except ValidationError as e:
            self._errors[settings.NON_FIELD_ERRORS] = e.detail

    def clean(self):
        """
        Hook for doing any extra formset-wide cleaning after Form.clean() has
        been called on every form. Any ValidationError raised by this method
        will not be associated with a particular form; it will be accessible
        via formset.non_form_errors()
        """
        pass


def formset_factory(form, formset=BaseFormSet, min_num=1, max_num=None):
    """
     创建 Form 的集合
    """
    if min_num is None:
        min_num = DEFAULT_MIN_NUM

    if max_num is None:
        max_num = DEFAULT_MAX_NUM

    attrs = {
        'form': form,
        'min_num': min_num,
        'max_num': max_num
    }

    return type(form.__name__ + str('FormSet'), (formset,), attrs)


async def all_valid(formsets):
    """Returns true if every formset in formsets is valid."""
    valid = True
    for formset in formsets:
        if not await formset.is_valid():
            valid = False
    return valid
