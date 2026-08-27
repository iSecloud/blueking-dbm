---
name: dbm-redis-proxy-diagnose
description: Redis Proxy 异常排查 skill。当 Proxy 出现异常时触发，覆盖连接数、延迟、错误率等排查流程。
metadata: {"version":"1.0.3","space_id":"1d3d86fa67bef8c3","bk_skill_code":"dbm-redis-proxy-diagnose","openclaw":{"category":"tencent","emoji":"🦈","requires":{"env":[]}}}
---

## 0x00 工时记录（必须执行）

> 必须**成对**调用 `started` 与 `completed`，缺一会导致本次工时被推断为会话结束时刻（最长可达数小时）。

**开始时执行：**

```bash
node "/projects/.hermes/home/.bkai/openclaw-runtime/append-skill-event.js" "redis-proxy-diagnose" "started"
```

**完成后执行（必须）：**

```bash
node "/projects/.hermes/home/.bkai/openclaw-runtime/append-skill-event.js" "redis-proxy-diagnose" "completed"
```

> ## ⚠️ Hermes 环境适配说明（2026-05-12 移植）
>
> 本 skill 从龙虾平台移植而来，下文出现的 `/root/.openclaw/...` 路径**仅供历史对照**。
> 在 Hermes 环境下：
>
> | 旧（龙虾） | 新（Hermes） |
> |---|---|
> | `/root/.openclaw/workspace/skills/redis-daily-patrol/<file>.py` | `/projects/.hermes/skills/imate-template/redis-daily-patrol/<file>.py` |
> | `/root/.openclaw/workspace/skills/redis-daily-patrol/<watchlist>.json` | 同 skill 目录下，`patrol_compat.py:SKILL_DIR` 动态拼接 |
> | `bash logger.sh '意图' '操作' '结果'` | 已替换为 `audit.py:audit_call(...)` 库 API（见 `dbm-redis-mcp-auth` skill） |
> | `bash mcp_log call <tool> --args '<json>'` | 4 个 patrol .py 内置 `mcp_call(tool, args)`（自动审计） |
> | `mcporter call bkdbm-redis-X.tool` | `python3 dbm-redis-mcp-auth/scripts/mcp_client.py --user $USER --server bkdbm-mcp-prod-redis-X --action call --tool ... --args ...` |
>
> **Skill 内 .py 已修复**：路径动态化 + audit() / mcp_call() 已通过 `patrol_compat.py` 适配新环境。
> ---

---
name: redis-proxy-diagnose
description: Redis 个别 proxy 异常排查 skill。当出现以下情况时触发：集群访问耗时告警但 master 指标正常、慢查询分布不均（某1-2个 proxy 远超其他）、部分客户端超时而其他正常、proxy 节点 CPU/连接数异常。适用于 DBM 蓝鲸平台 TwemproxyRedis 集群。
metadata: {"version":"1.0.0","space_id":"1d3d86fa67bef8c3","bk_skill_code":"dbm-redis-proxy-diagnose","openclaw":{"category":"tencent","emoji":"🦈","requires":{"env":[]}}}
---

# Redis Proxy 异常排查

## 典型现象
- 集群平均访问耗时告警，但 master 侧 QPS/CPU 均正常
- 慢查询统计中，某 1-2 个 proxy 数量/耗时**远超**其余 proxy
- 客户端部分连接超时，非全量超时
- 告警 target 指向 proxy 节点（`instance_role: proxy`）

## 与热点 Key 的区别

| 特征 | 热点 Key | Proxy 异常 |
|------|---------|-----------|
| 慢查询分布 | 各 proxy 均匀，同一 key | 某 1-2 proxy 集中 |
| master CPU | 100% | 正常 |
| 慢查询 key | 集中 | 分散或无规律 |
| 告警 role | redis_master | proxy |

---

## 时间格式规范

⚠️ **所有时间参数统一使用 CST 带时区格式，不要手动转 UTC**

```
正确：2026-03-27T09:18:00+08:00
错误：2026-03-27T01:18:00Z   ← 禁止手动 -8h
```

告警时间前后各扩 ±30 分钟作为查询范围。

---

## MCP 工具调用规范

⚠️ **每次调用 MCP 工具前，必须先记录日志**

```bash
# 调用模板（封装版）
export MCP_USER_INPUT="<用户意图描述>"
bash /root/.openclaw/workspace/skills/operation-logger/scripts/mcp_log call <tool_name> --args '<json>'
```

---

## 排查流程

### Step 1：获取 Proxy 节点列表

```bash
python3 /projects/.hermes/skills/imate-template/dbm-redis-mcp-auth/scripts/mcp_client.py \
  --user "$SESSION_USER" \
  --server bkdbm-mcp-prod-redis-query-meta \
  --action call \
  --tool redis_query_meta_list_cluster_proxies \
  --args '{"body_param": {"cluster_domain": "<domain>"}}'
# 返回各 proxy 的 ip、port、status
```

---

### Step 2：慢查询统计 → 定位异常 Proxy

> ⚠️ **工具名勘误（2026-05-20 实测）**：skill 历史版本写的 `redis_query_log_get_cluster_slowlog_statics` 不存在。
> 正确工具名是 **`redis_query_log_query_slowlogs`**（属于 `bkdbm-mcp-prod-redis-query-log` server）。

```bash
python3 /projects/.hermes/skills/imate-template/dbm-redis-mcp-auth/scripts/mcp_client.py \
  --user "$SESSION_USER" \
  --server bkdbm-mcp-prod-redis-query-log \
  --action call \
  --tool redis_query_log_query_slowlogs \
  --args '{"body_param": {"cluster_domain": "<domain>", "start_time": "<CST+08:00>", "end_time": "<CST+08:00>"}}'
# 可选：传 "ip" 参数只查单台机器，不传则返回全集群统计
```

**响应结构（2026-05-20 实测确认）**：

```json
{
  "data": {
    "by_instance": {
      "<ip:port>": {
        "total_count": 52,
        "duration_stats": { "avg_ms": 154.2, "max_ms": 211.96, "median_ms": 137.93, "min_ms": 111.69 },
        "slowest_query":  { "cmd": "xrange", "key": "AS:30:MatchEvent:...", "duration_ms": 211.96, "create_time": "..." },
        "top_commands":   { "xrange": 30, "XADD": 1, ... }
      }
    },
    "summary": {
      "total_count": 1000,
      "instance_count": 70,
      "duration_stats": { "avg_ms": 142.9, "max_ms": 314.35, ... },
      "top_commands": { "XRANGE": 516, "MGET": 151, ... }
    }
  }
}
```

解析时注意：
- 顶层返回是 MCP content 包裹的 JSON 字符串，需二次 `json.loads`
- 全集群 summary 在 `data.summary`，各实例在 `data.by_instance`
- `top_commands` key 可能大小写混用（`xrange` 和 `XRANGE` 同时出现），合并统计时需 `.upper()`

对比 `by_instance` 各实例的 `total_count` 和 `duration_stats.avg_ms`：

```
正常实例：total_count 相近，avg_ms < 100ms
异常实例：total_count >> 其他，avg_ms > 200ms  ← 重点关注
```

记录异常实例的 `ip:port`。

---

### Step 3：查全量 Proxy CPU / QPS 时序

```bash
# 全量 proxy CPU（按 ip 分组，定位异常节点）
python3 /projects/.hermes/skills/imate-template/dbm-redis-mcp-auth/scripts/mcp_client.py \
  --user "$SESSION_USER" \
  --server bkdbm-mcp-prod-redis-metrics \
  --action call \
  --tool redis_metrics_query_cluster_proxy_series \
  --args '{"body_param": {"cluster_domains": ["<domain>"], "metric_type": "cpu_usage", "group_by": ["ip"], "start_time": "<CST+08:00>", "end_time": "<CST+08:00>", "max_len_datapoints": 12}}'

# 全量 proxy QPS（排查流量分配是否不均）
python3 /projects/.hermes/skills/imate-template/dbm-redis-mcp-auth/scripts/mcp_client.py \
  --user "$SESSION_USER" \
  --server bkdbm-mcp-prod-redis-metrics \
  --action call \
  --tool redis_metrics_query_cluster_proxy_series \
  --args '{"body_param": {"cluster_domains": ["<domain>"], "metric_type": "qps", "group_by": ["ip"], "start_time": "<CST+08:00>", "end_time": "<CST+08:00>", "max_len_datapoints": 12}}'
```

CPU > 50% 或 QPS 远超其他节点 → 确认为异常 proxy。

---

### Step 4：查异常 Proxy 慢命令明细

```bash
python3 /projects/.hermes/skills/imate-template/dbm-redis-mcp-auth/scripts/mcp_client.py \
  --user "$SESSION_USER" \
  --server bkdbm-mcp-prod-redis-query-log \
  --action call \
  --tool redis_query_log_query_slowlogs \
  --args '{"body_param": {"host": "<proxy_ip>", "port": <proxy_port>, "cluster_domain": "<domain>", "start_time": "<CST+08:00>", "end_time": "<CST+08:00>"}}'
```

> ⚠️ 此工具字段为 `host`（非 `ip`），必填 `cluster_domain`。

关注：
- 是否有 `MGET`/`KEYS`/`SCAN` 等批量命令（单条命令涉及大量 key）
- 慢查询时间点是否与业务流量突增/发版吻合
- 是否有异常 key 模式（模板变量未渲染如 `${item_clubid}`）

---

### Step 5：查告警验证

```bash
python3 /projects/.hermes/skills/imate-template/dbm-redis-mcp-auth/scripts/mcp_client.py \
  --user "$SESSION_USER" \
  --server bkdbm-mcp-prod-redis-query-alarm \
  --action call \
  --tool redis_query_alarm_fetch_app_alarms \
  --args '{"body_param": {"bk_biz_id": <id>, "start_time": "<CST+08:00>", "end_time": "<CST+08:00>"}}'
```

筛选 `instance_role: proxy` 的告警，确认是否指向同一台 proxy 机器。

---

### Step 5.5（新增）：Proxy host_latency 高 → Proxy→Backend 连通异常

**`host_latency`（Proxy 到后端 Master 的网络延迟）正常应在 1ms 以内。**

若 `host_latency` max 达到秒级（1000ms+）乃至数千毫秒，说明不是 proxy 自身问题，而是：
- Proxy 与后端 TendisPlus/TendisSSD master 之间**连接断续/网络抖动**
- 后端 master 节点**短暂不可达**（重启、网络故障、主从切换）

```bash
# 拉 proxy host_latency stats（按 ip 分组）
python3 mcp_client.py --user "$SESSION_USER" \
  --server bkdbm-mcp-prod-redis-metrics --action call \
  --tool redis_metrics_query_cluster_proxy_stats \
  --args '{"body_param": {"cluster_domains": ["<domain>"], "metric_type": "host_latency",
           "group_by": ["ip"], "start_time": "<CST+08:00>", "end_time": "<CST+08:00>",
           "max_len_datapoints": 15}}'
```

| host_latency avg | 诊断 |
|-----------------|------|
| < 5ms | 正常 |
| 5ms~100ms | 轻微抖动，关注 |
| 100ms~1000ms | 严重抖动，需定位后端节点 |
| **1000ms~10000ms** | **后端节点连接大规模断续，告警级别** |

**配套：查 Server Log 的 reopen connection 信号：**

```bash
python3 mcp_client.py --user "$SESSION_USER" \
  --server bkdbm-mcp-prod-redis-query-log --action call \
  --tool redis_server_log_query_server_logs \
  --args '{"body_param": {"cluster_domain": "<domain>",
           "start_time": "<CST+08:00>", "end_time": "<CST+08:00>"}}'
```

日志中出现如下内容说明 Predixy 在主动尝试重建连接：
```
check server reopen connection <backend_ip>:<port> <count>
```
- `<count>` 数值越大、短时间内重复越多 → 断连越严重
- `<backend_ip>` 即有问题的后端节点 IP，可通过 `redis_query_meta_list_clusters_by_hosts` 反查归属集群

### Step 6：根因判断与处置

根据 Step 3/Step 5.5 结果判断：

| 指标表现 | 根因 | 处置 |
|---------|------|------|
| proxy host_latency 秒级高 + reopen connection 日志 | 后端 master 节点不可达 / 网络抖动 | 查后端节点状态；确认是否有主从切换 |
| proxy CPU 高 | 处理线程瓶颈 | 重启 proxy；评估是否需扩容 proxy 数量 |
| proxy 连接数满 | 连接池耗尽 | 检查业务连接池配置；调大 proxy maxconn |
| proxy QPS 突增 | 流量集中打某 proxy | 检查客户端负载均衡配置，确保均匀分发 |
| proxy 指标正常但慢查询多 | 网络抖动 | 检查该机器网络，对比同机其他服务 |
| 批量命令（MGET/KEYS） | 业务大批量操作 | 拆分批量请求；禁止 KEYS 命令 |

---

### Step 7：输出根因链路

根因链路输出格式：
```
异常 proxy: <proxy_ip>:<proxy_port>
  → <根因>（CPU xx% / QPS xx / 批量命令 MGET N keys）
  → 该 proxy 请求处理堆积，avg_ms xxms（其他 proxy 正常）
  → 客户端部分连接超时 → 集群整体耗时指标被拉高
  → master 侧无异常（QPS/CPU 正常）
```

---

## 参数注意事项

| 工具 | 字段注意 |
| 工具 | 字段注意 |
|------|---------|
| `redis_query_log_query_slowlogs` | 单实例查询时字段是 `host`（非 `ip`）+ 必填 `cluster_domain`；不传 ip 则返回全集群统计 |
| `redis_metrics_query_cluster_proxy_series` | 必填 `cluster_domains`（**数组**）+ `group_by`（数组）；❌ 不是 `cluster_domain`（单数） |
| `redis_metrics_query_cluster_proxy_stats` | 同上，`cluster_domains`（数组）+ `metric_type`；❌ 不是 `metric_name` |
| `redis_query_meta_cluster_basic_overview` | 必须用 `cluster_domain`；❌ `immute_domain` 会报"cluster_id or cluster_domain is required" |
| metrics stats 响应统计字段 | **`p95`**（不是 `p99`）；字段集合：`avg, cv, latest, max, median, min, p95, trend, trend_unit` |
| 时间格式 | CST 带时区：`2026-05-20T16:41:37+08:00`，禁止手动转 UTC |

### ⚠️ 慢查询响应 top_commands 大小写陷阱

`redis_query_log_query_slowlogs` 返回的 `top_commands` key 可能同时出现大写和小写版本（如 `xrange` 和 `XRANGE`）。统计总量时必须做大小写合并：

```python
merged = {}
for k, v in top_commands.items():
    merged[k.upper()] = merged.get(k.upper(), 0) + v
```

## 参考
- 常见告警字段：`references/proxy_alarm_patterns.md`
- 慢查询工具响应结构 + 真实案例：`references/slowlog_response_structure.md`

## Pitfalls

1. **慢查询 top_commands 大小写**
   `redis_query_log_get_cluster_slowlog_statics` 返回的 top_commands key 是大写命令名（如 `MGET`），代码比对时注意统一大写。

2. **host_latency 正常 ≠ Proxy 无问题**
   host_latency 反映 Proxy→Backend 网络延迟，Proxy 自身 CPU 打满导致的排队延迟不会体现在 host_latency 里，需结合 CPU + command_latency 综合判断。

3. **慢日志只能按实例拉**
   无集群级逐条接口，必须用 `redis_query_log_fetch_host_slowlog`，参数是 `ip`（不是 `host`），必传 `cluster_domain`。

4. **proxy_series group_by 只支持 ["ip"] 或 ["cluster_domain"]**
   传 ["instance"] 返回空数据不报错，定位单节点问题时必须用 group_by ["ip"] 再按 IP 筛选。

5. **单 Proxy 异常 vs 全局异常判断顺序**
   必须先拉所有 Proxy CPU/QPS 时序对比，再定位单节点，不能只看告警 IP 就直接跳到单节点分析，否则容易漏掉全局性问题。
