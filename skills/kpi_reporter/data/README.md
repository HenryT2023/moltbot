# 数据样例说明

本目录包含用于测试的示例数据文件。

## 文件列表

- `sample_crm.csv` - CRM 数据（线索、客户）
- `sample_ads.csv` - 广告数据（支出、点击、展示）
- `sample_web.csv` - 网站数据（页面浏览、会话）
- `sample_orders.csv` - 订单数据（订单数、收入）

## 数据格式

所有文件统一使用以下列：

| 列名 | 类型 | 说明 |
| ---- | ---- | ---- |
| date | string | 日期，格式 YYYY-MM-DD |
| metric_name | string | 指标名称 |
| metric_value | number | 指标值 |
| campaign | string | 广告系列（仅 ads） |
| channel | string | 渠道（仅 ads） |
| page | string | 页面路径（仅 web） |
| product | string | 产品名称（仅 orders） |
| region | string | 地区（仅 orders） |

## 使用方式

1. 将实际数据导出为 CSV 格式
2. 按照上述列名规范整理
3. 放入本目录
4. 运行 KPI Reporter
