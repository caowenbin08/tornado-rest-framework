# -*- coding: utf-8 -*-
from rest_framework import forms
from rest_framework.exceptions import ValidationError

__author__ = 'caowenbin'


class TestFormFields(object):

    # def setup(self):
    #     print('setup 方法执行于本类中每条用例之前')
    #
    # @classmethod
    # def setup_class(cls):
    #     print('setup_class 类方法执行于本类中任何用例开始之前,且仅执行一次')

    def test_boolean_field(self):
        try:
            forms.BooleanField(null=True)
        except AssertionError:
            assert True
        else:
            assert False

        try:
            forms.BooleanField(default=False)
        except AssertionError:
            assert True
        else:
            assert False

        try:
            forms.BooleanField().run_validation()
        except ValidationError as e:
            assert e.detail[0].code == "required"
        else:
            assert False

        field = forms.BooleanField(required=False)
        field.bind(field_name="status", parent=self)
        assert field.run_validation() == 0
        field = forms.BooleanField(required=False, default=False)
        req_data = dict(status=1)
        field.bind(field_name="status", parent=self)
        primitive_value = field.get_value(req_data)
        assert primitive_value == 1
        validated_value = field.run_validation(primitive_value)
        assert validated_value
        primitive_value = field.get_value(dict(status="OFF"))
        assert primitive_value == "OFF"
        validated_value = field.run_validation(primitive_value)
        assert validated_value is False
        assert field.run_validation() is False
        assert field.to_internal_value("F") is False
        try:
            field.to_internal_value(88)
        except ValidationError as e:
            assert e.detail[0].code == "invalid"
        else:
            assert False

        assert field.to_internal_value("true")

    @staticmethod
    def gen_status():
        return 0

    def test_null_boolean_field(self):
        try:
            forms.NullBooleanField(null=True)
        except AssertionError:
            assert True
        else:
            assert False

        assert forms.NullBooleanField().run_validation() is None
        assert forms.NullBooleanField().to_representation("null") is None
        assert forms.NullBooleanField().to_representation("None") is True
        assert forms.NullBooleanField().to_representation(False) is False
        try:
            forms.NullBooleanField().to_internal_value("None")
        except ValidationError as e:
            assert e.detail[0].code == "invalid"
        else:
            assert False

    def test_char_field(self):
        try:
            forms.CharField(null=True, min_length=2)
        except AssertionError:
            assert True
        else:
            assert False

        field = forms.CharField(null=True, trim_whitespace=False, max_length=5, min_length=0)
        assert field.run_validation() is None
        try:
            field.run_validation("   1234  ")
        except ValidationError as e:
            assert e.detail[0].code == "max_length"
        else:
            assert False

        field = forms.CharField(trim_whitespace=True, max_length=5, min_length=2)
        assert field.run_validation("   1234  ") == "1234"
        try:
            field.run_validation(" 1 ")
        except ValidationError as e:
            assert e.detail[0].code == "min_length"
        else:
            assert False

        try:
            field.run_validation(True)
        except ValidationError as e:
            assert e.detail[0].code == "invalid"
        else:
            assert False

    def test_email_field(self):
        try:
            forms.EmailField(null=True, min_length=2)
        except AssertionError:
            assert True
        else:
            assert False

        field = forms.EmailField(null=True, trim_whitespace=False, max_length=5, min_length=0)
        assert field.run_validation() is None
        try:
            field.run_validation("   1234  ")
        except ValidationError as e:
            code_list = e.get_codes()
            for code in ("max_length", "invalid"):
                assert code in code_list
        else:
            assert False

        try:
            forms.EmailField(trim_whitespace=True, min_length=20).run_validation(" cwb@@qq.com ")
        except ValidationError as e:
            code_list = e.get_codes()
            for code in ("min_length", "invalid"):
                assert code in code_list
        else:
            assert False

        assert forms.EmailField(trim_whitespace=True).run_validation("   cwb@qq.com  ") == "cwb@qq.com"
        assert forms.EmailField().run_validation("  cw9_b@q.com ") == "cw9_b@q.com"
        try:
            forms.EmailField().run_validation("cwb@@.com")
        except ValidationError as e:
            assert e.detail[0].code == "invalid"
        else:
            assert False

    def test_regex_field(self):
        try:
            forms.RegexField(regex=r"^[\u4e00-\u9fa5]{0,}$", null=True, min_length=2)
        except AssertionError:
            assert True
        else:
            assert False

        assert forms.RegexField(regex=r"^[\u4e00-\u9fa5]{0,}$").run_validation("曹文彬") == "曹文彬"
        assert forms.RegexField(regex=r"^[\u4e00-\u9fa5]{0,}$").run_validation(" 曹文彬 ") == "曹文彬"
        try:
            forms.RegexField(regex=r"^[\u4e00-\u9fa5]{0,}$").run_validation(" 曹文彬1")
        except ValidationError as e:
            assert e.detail[0].code == "invalid"
        else:
            assert False

    def test_url_field(self):
        try:
            forms.URLField(null=True, min_length=2)
        except AssertionError:
            assert True
        else:
            assert False

        assert forms.URLField().run_validation("http://www.qq.com") == "http://www.qq.com"
        assert forms.URLField().run_validation(" ftp://qq.com ") == "ftp://qq.com"
        assert forms.URLField().run_validation("https://localhost/order?pk=1 ") == "https://localhost/order?pk=1"
        assert forms.URLField(null=True).run_validation() is None
        try:
            forms.URLField(min_length=10).run_validation("  444  5555")
        except ValidationError as e:
            code_list = e.get_codes()
            for code in ("min_length", "invalid"):
                assert code in code_list
        else:
            assert False

        try:
            forms.URLField().run_validation(" qq.com")
        except ValidationError as e:
            assert e.detail[0].code == "invalid"
        else:
            assert False

    def test_uuid_field(self):
        import uuid
        import time
        try:
            forms.UUIDField(format="uuid")
        except ValueError:
            assert True
        else:
            assert False

        assert forms.UUIDField(null=True).run_validation() is None
        try:
            forms.UUIDField().run_validation()
        except ValidationError as e:
            assert e.detail[0].code == "required"
        else:
            assert False

        value = uuid.uuid1()
        assert forms.UUIDField().run_validation(value) == value
        assert forms.UUIDField().run_validation(2) == uuid.UUID(int=2)
        forms.UUIDField(null=True).run_validation(True) == uuid.UUID(int=1)
        try:
            forms.UUIDField(null=True).run_validation(time.time())
        except ValidationError as e:
            assert e.detail[0].code == "invalid"
        else:
            assert False

        assert forms.UUIDField().to_representation(None) is None
        assert forms.UUIDField(format="int").to_representation(None) is None

    def test_ipaddress_field(self):
        try:
            forms.IPAddressField(null=True, min_length=2)
        except AssertionError:
            assert True
        else:
            assert False

        assert forms.IPAddressField(null=True).run_validation() is None
        try:
            forms.IPAddressField().run_validation()
        except ValidationError as e:
            assert e.detail[0].code == "required"

        assert forms.IPAddressField().run_validation(" 127.0.0  ") == "127.0.0"
        assert forms.IPAddressField().run_validation(" 2000:0:0:0:0:0:0:1  ") == "2000:0:0:0:0:0:0:1"
        try:
            forms.IPAddressField().run_validation("localhost  ")
        except ValidationError as e:
            assert e.detail[0].code == "invalid"
        else:
            assert False

        assert forms.IPAddressField(protocol="ipv6").run_validation("2000:0:0:0:0:0:0:1") == "2000:0:0:0:0:0:0:1"
        assert forms.IPAddressField(protocol="ipv4").run_validation("192.78.9.0") == "192.78.9.0"
        try:
            forms.IPAddressField(protocol="ipv4").run_validation("192.78.9")
        except ValidationError as e:
            assert e.detail[0].code == "invalid"
        else:
            assert False

    def test_integer_field(self):
        try:
            forms.IntegerField(null=True)
        except AssertionError:
            assert True
        else:
            assert False
        field = forms.IntegerField(null=False, max_value=10, min_value=5)
        try:
            field.run_validation(11)
        except ValidationError as e:
            assert e.detail[0].code == "max_value"
        else:
            assert False
        try:
            field.run_validation(3)
        except ValidationError as e:
            assert e.detail[0].code == "min_value"
        else:
            assert False
        assert field.run_validation(10) == 10
        assert field.run_validation(5) == 5
        assert field.run_validation(8.0) == 8
        assert forms.IntegerField().run_validation(True) == 1
        assert forms.IntegerField().run_validation(False) == 0
        assert forms.IntegerField().run_validation("12") == 12
        assert forms.IntegerField().run_validation("128.0") == 128
        try:
            forms.IntegerField().run_validation(0.10)
        except ValidationError as e:
            assert e.detail[0].code == "invalid"
        else:
            assert False

    def test_float_field(self):
        try:
            forms.FloatField(null=True)
        except AssertionError:
            assert True
        else:
            assert False

        field = forms.FloatField(null=False, max_value=10, min_value=5)
        try:
            field.run_validation(11)
        except ValidationError as e:
            assert e.detail[0].code == "max_value"
        else:
            assert False
        try:
            field.run_validation(3)
        except ValidationError as e:
            assert e.detail[0].code == "min_value"
        else:
            assert False
        assert field.run_validation(10) == 10.0
        assert field.run_validation(5) == 5.0
        assert field.run_validation(8.09) == 8.09
        assert field.run_validation("8.0") == 8.0
        try:
            field.run_validation("e3")
        except ValidationError as e:
            assert e.detail[0].code == "invalid"

    def test_datetime_field(self):
        import datetime
        datetime_parser = datetime.datetime.strptime
        assert forms.DateTimeField(null=True).run_validation() is None
        value = forms.DateTimeField(required=False, default=datetime.datetime.now).run_validation()
        assert value != datetime.datetime.now() and value is not None
        now_time = datetime.datetime.now()
        assert forms.DateTimeField(required=False, default=now_time).run_validation() == now_time
        assert forms.DateTimeField(input_formats="%Y-%m-%d %H:%M:%S").run_validation(now_time) == now_time
        today_date = datetime.date.today()
        assert forms.DateTimeField().run_validation(today_date) == datetime.datetime(
            today_date.year, today_date.month, today_date.day)
        assert forms.DateTimeField(input_formats="%Y-%m-%d").run_validation("2017-09-09") == datetime_parser(
            "2017-09-09", "%Y-%m-%d")
        assert forms.DateTimeField(input_formats="%H:%M:%S").run_validation("09:09:09") == datetime_parser(
            "09:09:09", "%H:%M:%S")

        field = forms.DateTimeField(output_format="%Y-%m-%d %H:%M:%S")
        assert field.to_representation(None) is None
        assert field.to_representation("2017-09-09") == "2017-09-09"
        assert field.to_representation(now_time) == now_time.strftime("%Y-%m-%d %H:%M:%S")
        assert forms.DateTimeField(output_format="%Y-%m-%d").to_representation(now_time) == now_time.strftime("%Y-%m-%d")
        try:
            forms.DateTimeField(input_formats="%Y-%m-%d").run_validation("20170909")
        except ValidationError as e:
            assert e.detail[0].code == "invalid"
        else:
            assert False

    def test_date_field(self):
        import datetime
        datetime_parser = datetime.datetime.strptime
        assert forms.DateField(null=True).run_validation() is None
        value = forms.DateField(required=False, default=datetime.date.today).run_validation()
        today_date = datetime.date.today()
        assert value == today_date
        now_time = datetime.datetime.now()
        assert forms.DateField(input_formats="%Y-%m-%d %H:%M:%S").run_validation(now_time) == today_date
        assert forms.DateField().run_validation(today_date) == today_date
        assert forms.DateField(input_formats="%Y-%m-%d").run_validation("2017-09-09") == datetime_parser(
            "2017-09-09", "%Y-%m-%d").date()
        assert forms.DateField(input_formats="%H:%M:%S").run_validation("09:09:09") == datetime_parser(
            "09:09:09", "%H:%M:%S").date()

        field = forms.DateField(output_format="%Y-%m-%d %H:%M:%S")
        assert field.to_representation(None) is None
        assert field.to_representation("2017-09-09") == "2017-09-09"
        assert field.to_representation(now_time) == now_time.strftime("%Y-%m-%d %H:%M:%S")
        assert forms.DateField(output_format="%Y-%m-%d").to_representation(now_time) == now_time.strftime("%Y-%m-%d")
        try:
            forms.DateTimeField(input_formats="%Y-%m-%d").run_validation("20170909")
        except ValidationError as e:
            assert e.detail[0].code == "invalid"
        else:
            assert False

    def test_time_field(self):
        import datetime
        datetime_parser = datetime.datetime.strptime
        assert forms.TimeField(null=True).run_validation() is None
        now_time = datetime.datetime.now()
        assert forms.TimeField(input_formats="%Y-%m-%d %H:%M:%S").run_validation(now_time) == now_time.time()
        assert forms.TimeField(input_formats="%Y-%m-%d %H:%M:%S").run_validation("2017-09-09 09:09:09") == datetime_parser(
            "2017-09-09 09:09:09", "%Y-%m-%d %H:%M:%S").time()
        assert forms.TimeField(input_formats="%H:%M:%S").run_validation("09:09:09") == datetime_parser(
            "09:09:09", "%H:%M:%S").time()
        try:
            forms.TimeField(input_formats="%Y-%m-%d").run_validation("2017-09-09 09:09:09") == datetime_parser(
                "2017-09-09 09:09:09", "%Y-%m-%d").time()
        except ValidationError as e:
            assert e.detail[0].code == "invalid"
        else:
            assert False

        field = forms.TimeField(output_format="%H:%M:%S")
        assert field.to_representation(None) is None
        assert field.to_representation("09:09:09") == "09:09:09"
        assert field.to_representation(now_time) == now_time.strftime("%H:%M:%S")
        assert forms.TimeField(output_format="%H").to_representation(datetime_parser(
            "2017-09-09 09:09:09", "%Y-%m-%d %H:%M:%S").time()) == "09"
        try:
            forms.TimeField(input_formats="%Y-%m-%d").run_validation(datetime.date.today())
        except ValidationError as e:
            assert e.detail[0].code == "invalid"
        else:
            assert False
