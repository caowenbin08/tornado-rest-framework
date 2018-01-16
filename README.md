## 项目结构
```
   - rest_framework/
     - bin/

```
安装依赖包
pip install -r requirements.txt

tornado-fire 查看支持的命令集

表单方面
1、获得表单字段（比如user_name）默认值，如果值为None, 并form类中存在类似get_<field_name>的函数，即get_user_name()函数，则执行生成对应的字段默认值
2、表单字段检查
如果存在类似validate_<field_name>的函数，则执行检查，参数为字段的输入值
