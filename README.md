# 发票报销系统

## 多用户系统

支持普通员工、财务和管理员。普通员工提交报销信息，财务负责审核和录入付款信息。管理员负责全局的管理。

## 自动提取发票信息

自动提取pdf电子发票的金额、开票时间、发票号码。自动排重电子发票。


## 发票类型汇总

指定发票类型，按照类型进行汇总

## 生成报销单

自动排版，将上传的发票生成汇总单据

# 使用方法

## 创建环境

``` bash
git clone https://github.com/wangsirgan-jpg/fapiaobaoxiao.git
cd fapiaobaoxiao
python -m venv .venv
.venv/bin/pip install -r requirements  # linux
.venv/Script/pip install -r requirements  # windows
```

## 初始化系统
修改 `config.py`文件的 `COMPANY_NAME_KEYWORD`变量，表示只识别含有这个关键词的发票。

## 启动系统

.venv/Script/python app.py  # windows
.venv/bin/python app.py  # linux

## 访问系统

http://127.0.0.1:5000/

# 联系方式

微信 niuxya

# 注意事项

## 人生很短，不要重复造轮子

## 互尊互爱，以暴制暴

## 扯蛋也是工作，但扯多了会丧失繁衍能力

