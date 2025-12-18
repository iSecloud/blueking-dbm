# Celery Redis 连接错误修复 - 使用说明

## 问题概述

您遇到的错误：
```
redis.exceptions.ResponseError: server closed connection
```

这是 Celery Worker 与 Redis 服务器连接被意外断开导致的问题。

## 已完成的修复

### 1. 代码修改

我们已对以下文件进行了修复：

#### ✅ `backend/utils/redis.py`
- 添加了连接健康检查（每30秒）
- 启用了 TCP Keepalive 机制
- 配置了超时和重试参数

#### ✅ `config/default.py`
- 增强了 Celery Broker 连接配置
- 添加了自动重连机制
- 优化了连接池配置
- 更新了 Django Cache 的 Redis 连接参数

### 2. 新增工具

#### ✅ `docs/celery-redis-connection-fix.md`
详细的问题分析和解决方案文档

#### ✅ `scripts/check_redis_config.py`
Redis 配置检查脚本，帮助快速诊断配置问题

## 使用步骤

### 第一步：检查 Redis 配置

运行配置检查脚本：

```bash
# 设置 Redis 连接信息（如果未在环境变量中配置）
export REDIS_HOST=your-redis-host
export REDIS_PORT=6379
export REDIS_PASSWORD=your-password

# 运行检查脚本
python scripts/check_redis_config.py
```

脚本会检查以下配置项：
- `timeout`：空闲连接超时时间
- `maxclients`：最大客户端连接数
- `tcp-keepalive`：TCP keepalive 设置
- `maxmemory`：最大内存限制
- `maxmemory-policy`：内存淘汰策略

### 第二步：修改 Redis 配置（如需要）

如果检查脚本提示需要修改配置，编辑 Redis 配置文件：

```bash
# 编辑 Redis 配置文件
sudo vim /etc/redis/redis.conf

# 或查找配置文件位置
redis-cli INFO | grep config_file
```

**推荐配置：**

```conf
# 空闲连接超时（0表示永不超时）
timeout 0

# 最大客户端连接数
maxclients 10000

# TCP keepalive（秒）
tcp-keepalive 300

# 最大内存（根据实际情况设置）
maxmemory 2gb

# 内存淘汰策略
maxmemory-policy allkeys-lru
```

修改配置后重启 Redis：

```bash
# 方法1：使用 systemctl
sudo systemctl restart redis

# 方法2：使用 redis-cli
redis-cli CONFIG REWRITE
redis-cli SHUTDOWN SAVE
# 然后启动 Redis 服务
```

### 第三步：重启 Celery Worker

代码修改后，需要重启 Celery Worker 才能生效：

```bash
# 如果使用 supervisord
supervisorctl restart celery-worker

# 如果使用 systemctl
sudo systemctl restart celery-worker

# 如果使用 Celery multi
celery -A config multi restart worker1

# 手动启动（用于测试）
celery -A config worker -l info
```

### 第四步：验证修复

启动 Worker 后，观察日志确认没有再出现连接错误：

```bash
# 查看 Celery Worker 日志
tail -f /path/to/celery/log

# 检查 Worker 状态
celery -A config inspect active
celery -A config inspect stats

# 测试发送任务
python -c "from backend.db_periodic_task.local_tasks import your_task; your_task.delay()"
```

## 监控建议

### 1. Redis 连接监控

```bash
# 实时监控 Redis 连接数
watch -n 1 'redis-cli INFO clients | grep connected_clients'

# 查看慢查询
redis-cli SLOWLOG GET 10
```

### 2. Celery Worker 监控

```bash
# 查看 Worker 状态
celery -A config inspect active

# 查看连接池状态
celery -A config inspect pool

# 查看统计信息
celery -A config inspect stats
```

### 3. 设置告警

建议在日志监控系统中设置以下关键词告警：
- `server closed connection`
- `Connection refused`
- `Connection reset by peer`
- `redis.exceptions`

## 常见问题

### Q1: 修复后仍然出现连接关闭错误？

**可能原因和解决方法：**

1. **Redis 服务未正常运行**
   ```bash
   redis-cli PING
   # 应该返回 PONG
   ```

2. **网络连接问题**
   ```bash
   telnet redis-host 6379
   # 应该能够连接
   ```

3. **防火墙阻止连接**
   ```bash
   # 检查防火墙规则
   sudo iptables -L -n | grep 6379
   ```

4. **Redis 日志中的错误**
   ```bash
   tail -f /var/log/redis/redis-server.log
   ```

### Q2: 连接数持续增长？

检查是否存在连接泄漏：

```bash
# 监控连接数变化
watch -n 1 'redis-cli INFO clients'

# 查看当前所有客户端连接
redis-cli CLIENT LIST
```

如果连接数异常增长，检查：
- 代码中是否正确关闭连接
- 连接池配置是否合理
- 是否有大量失败的连接尝试

### Q3: 偶尔出现超时错误？

可能是 Redis 负载过高或存在慢查询：

```bash
# 查看慢查询日志
redis-cli SLOWLOG GET 10

# 监控 Redis 性能
redis-cli --latency

# 查看 Redis 状态
redis-cli INFO stats
```

## 技术细节

### 修复原理

1. **健康检查机制**
   - 每30秒自动检查连接是否有效
   - 及时发现并关闭无效连接
   - 避免使用已断开的连接

2. **TCP Keepalive**
   - 在传输层保持连接活跃
   - 60秒无数据后发送探测包
   - 每10秒发送一次，最多3次
   - 网络设备不会关闭"活跃"的连接

3. **自动重连机制**
   - 连接失败时自动重试
   - 最多重试10次
   - 使用指数退避策略

4. **连接池优化**
   - 复用连接，减少建立连接的开销
   - 限制最大连接数，避免资源耗尽
   - 连接池健康检查

### 关键配置参数

| 参数 | 作用 | 推荐值 |
|------|------|--------|
| `health_check_interval` | 健康检查间隔 | 30秒 |
| `socket_keepalive` | 启用 TCP Keepalive | True |
| `socket_timeout` | Socket 超时 | 5秒 |
| `broker_heartbeat` | Broker 心跳间隔 | 30秒 |
| `broker_connection_retry` | 启用自动重连 | True |
| `redis_max_connections` | 最大连接数 | 50 |

## 进一步优化

如果问题依然存在，可以考虑：

1. **使用 Redis Sentinel 或 Cluster**
   - 提供高可用性
   - 自动故障转移

2. **优化任务设计**
   - 减少长时间运行的任务
   - 使用任务超时限制
   - 合理设置任务优先级

3. **监控和告警**
   - 部署 Prometheus + Grafana
   - 使用 Celery Flower 监控
   - 设置自动告警

4. **资源优化**
   - 增加 Redis 服务器内存
   - 使用 SSD 存储
   - 优化网络配置

## 相关文档

- [完整技术文档](docs/celery-redis-connection-fix.md)
- [Celery 官方文档](https://docs.celeryq.dev/)
- [Redis 官方文档](https://redis.io/docs/)

## 联系支持

如果问题仍未解决，请提供：
- 完整的错误日志
- Redis 配置文件
- Celery 配置信息
- `scripts/check_redis_config.py` 的输出结果

---

**修复日期：** 2025-12-18  
**修复版本：** v1.5.0  
**分支：** cursor/celery-redis-connection-error-4577
