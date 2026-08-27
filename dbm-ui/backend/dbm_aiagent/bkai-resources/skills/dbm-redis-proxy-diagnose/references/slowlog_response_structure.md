# redis_query_log_query_slowlogs 响应结构（2026-05-20 实测）

## 工具信息

- Server: `bkdbm-mcp-prod-redis-query-log`
- Tool: `redis_query_log_query_slowlogs`
- 调用方式: `mcp_client.py --user $SESSION_USER --server ... --action call --tool ...`

## inputSchema

```json
{
  "body_param": {
    "cluster_domain": "string (required)",
    "start_time":     "datetime (required, CST+08:00)",
    "end_time":       "datetime (required, CST+08:00)",
    "ip":             "string (optional) — 不传则查全集群统计",
    "port":           "integer (optional) — 配合 ip 使用"
  }
}
```

## 响应结构

MCP 外层是 content 包裹，需二次 json.loads：

```python
outer = json.loads(mcp_stdout)
inner = json.loads(outer['content'][0]['text'])
data  = inner['response_body']['data']

by_instance = data['by_instance']   # dict, key = "ip:port"
summary     = data['summary']
```

### by_instance 单条结构

```json
{
  "11.153.75.121:50000": {
    "total_count": 10,
    "duration_stats": {
      "avg_ms":    165.45,
      "max_ms":    314.35,
      "median_ms": 145.24,
      "min_ms":    108.84
    },
    "slowest_query": {
      "cmd":         "MGET",
      "key":         "AS:30:OnlineStat:11055884716676775902",
      "duration_ms": 314.35,
      "create_time": "2026-05-20T16:46:01.746560569+08:00"
    },
    "top_commands": {
      "GET":  1,
      "MGET": 9
    }
  }
}
```

### summary 结构

```json
{
  "total_count":    1000,
  "instance_count": 70,
  "duration_stats": {
    "avg_ms": 142.9, "max_ms": 314.35, "median_ms": 134.0, "min_ms": 100.0
  },
  "top_commands": {
    "EXISTS": 22, "GET": 81, "MGET": 151, "SET": 39,
    "XADD": 58, "ZADD": 2, "ZCARD": 2,
    "expire": 4, "xadd": 122, "xrange": 516
  }
}
```

## 已知陷阱

1. **total_count 上限 = 1000**：返回上限是 1000 条。高负载集群 10 分钟内可能 >1000，此时数据截断，结论仅供参考趋势，不代表精确计数。

2. **top_commands 大小写混用**：同一命令可能同时出现 `xrange` 和 `XRANGE`。统计必须做大小写合并：
   ```python
   merged = {}
   for k, v in top_commands.items():
       merged[k.upper()] = merged.get(k.upper(), 0) + v
   ```

3. **字段名陷阱**：
   - 全集群查询（不传 ip）时字段名是 `host`（非 `ip`）用于单实例细查
   - `by_instance` 的 key 是 `"ip:port"` 字符串，不是嵌套对象

## 真实案例（cache.online1.nba2kx.db，2026-05-20）

| 指标 | 值 |
|------|----|
| 实例数 | 70 |
| 总慢查询（10分钟） | 1000（触顶） |
| avg_ms | 142.9 |
| max_ms | 314.35（11.153.75.121） |
| 主要命令 | XRANGE 51.6%，XADD 18%，MGET 15% |
| 主要 key 前缀 | AS:30:OnlineStat (36实例)、AS:30:MatchEvent (18实例) |

结论：整体分布均匀，无单点异常集中，属正常负载下慢查询散布。XRANGE 比例高，业务大量使用 Stream 读取。
