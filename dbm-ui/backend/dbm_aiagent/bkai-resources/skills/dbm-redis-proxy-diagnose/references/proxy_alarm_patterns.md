# Proxy 异常告警模式

## fetch_app_alarms proxy 相关告警

```
instance_role: "proxy"  ← 关键过滤字段
```

常见告警规则：

| 规则名 | 含义 | description 示例 |
|--------|------|-----------------|
| Redis(TendisCache)集群平均访问耗时 | proxy 侧 P50 耗时超阈值 | 当前值 1427ms（阈值 32ms） |
| Redis Proxy连接数 | 单 proxy 连接数超阈值 | 当前值 5000（阈值 4000） |
| Redis Proxy CPU使用率 | proxy 所在机器 CPU 高 | 当前值 85% |

## 筛选代码

```python
for cluster, alert_dict in alarm_data.items():
    for alert_name, alarms in alert_dict.items():
        for a in alarms:
            if a.get('instance_role') == 'proxy':
                print(f"[PROXY] {alert_name} | {a['target_key']} | {a['description']}")
```

## 时间转换

```python
from datetime import datetime, timezone, timedelta
CST = timezone(timedelta(hours=8))
t = datetime.fromtimestamp(a['begin_time'], tz=CST).strftime('%H:%M')
```
