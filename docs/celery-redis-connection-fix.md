# Celery Redis 连接错误修复说明

## 问题描述

错误信息：`redis.exceptions.ResponseError: server closed connection`

这是一个 Celery Worker 在运行时与 Redis 服务器断开连接的问题。

## 错误原因分析

### 1. 直接原因
- Redis 服务器主动关闭了与 Celery Worker 的连接
- Celery Worker 在执行 BRPOP 操作（阻塞式读取队列）时连接被断开

### 2. 可能的根本原因

#### Redis 服务器端配置问题
- **timeout 配置过短**：Redis 的 `timeout` 参数决定了空闲连接的存活时间
  - 默认值：0（永不超时）
  - 如果设置了较小值（如 60 秒），空闲连接会被自动关闭
- **maxclients 限制**：Redis 同时连接数达到上限
- **内存不足**：Redis 内存达到 `maxmemory` 限制，可能导致连接被强制关闭
- **Redis 服务重启**：Redis 服务异常重启或手动重启

#### 网络问题
- 网络不稳定导致 TCP 连接中断
- 防火墙或 NAT 设备的空闲连接超时设置
- 负载均衡器的健康检查或超时配置

#### 客户端配置问题（已修复）
- 缺少连接健康检查机制
- 没有配置 TCP Keepalive
- 缺少自动重连机制
- 连接池配置不当

## 解决方案

### 已实施的代码修复

我们已经对以下文件进行了修复：

#### 1. `backend/utils/redis.py` - 增强连接工厂
```python
class ConnectionFactory(Factory):
    """自定义ConnectionFactory以注入decode_responses参数和连接健康检查"""
    
    def make_connection_params(self, url):
        kwargs = super().make_connection_params(url)
        # 健康检查：每30秒检查连接状态
        kwargs["health_check_interval"] = 30
        # TCP Keepalive：维持长连接
        kwargs["socket_keepalive"] = True
        kwargs["socket_keepalive_options"] = {
            1: 60,  # 60秒后开始发送keepalive探测包
            2: 10,  # 每10秒发送一次
            3: 3,   # 最多发送3次
        }
        # 超时配置
        kwargs["socket_timeout"] = 5
        kwargs["socket_connect_timeout"] = 5
        kwargs["retry_on_timeout"] = True
        return kwargs
```

**关键改进：**
- `health_check_interval=30`：每30秒自动检查连接健康状态，及时发现已断开的连接
- `socket_keepalive=True`：启用 TCP Keepalive，在网络层面保持连接活跃
- `retry_on_timeout=True`：超时时自动重试

#### 2. `config/default.py` - Celery Broker 配置
```python
# Celery Broker 连接配置
app.conf.broker_connection_retry = True  # 自动重试
app.conf.broker_connection_retry_on_startup = True  # 启动时重试
app.conf.broker_connection_max_retries = 10  # 最大重试10次
app.conf.broker_pool_limit = 10  # 连接池大小
app.conf.broker_heartbeat = 30  # 30秒心跳
app.conf.broker_heartbeat_checkrate = 2  # 心跳检查频率

# Redis 特定配置
app.conf.redis_socket_keepalive = True
app.conf.redis_socket_timeout = 5
app.conf.redis_max_connections = 50
```

**关键改进：**
- `broker_connection_retry=True`：连接失败时自动重试
- `broker_heartbeat=30`：每30秒发送心跳，保持连接活跃
- `broker_pool_limit=10`：使用连接池，提高连接复用性

#### 3. `config/default.py` - Django Cache 配置
增强了 Django Redis Cache 的连接参数，与 Celery 保持一致。

### 需要检查的 Redis 服务器配置

请检查您的 Redis 服务器配置文件（通常是 `redis.conf`）：

```bash
# 查看 Redis 配置
redis-cli CONFIG GET timeout
redis-cli CONFIG GET maxclients
redis-cli CONFIG GET maxmemory
```

#### 推荐配置

1. **timeout 配置**
```conf
# redis.conf
timeout 0  # 0表示永不超时，推荐设置
# 或者设置一个较大的值，如 300（5分钟）
timeout 300
```

2. **maxclients 配置**
```conf
# redis.conf
maxclients 10000  # 根据实际需要调整，建议设置较大值
```

3. **TCP Keepalive 配置**
```conf
# redis.conf
tcp-keepalive 300  # 推荐设置为300秒
```

4. **内存配置**
```conf
# redis.conf
maxmemory 2gb  # 根据实际内存大小设置
maxmemory-policy allkeys-lru  # 内存满时的淘汰策略
```

### 运维建议

#### 1. 监控 Redis 连接状态
```bash
# 查看当前连接数
redis-cli INFO clients

# 实时监控
watch -n 1 'redis-cli INFO clients | grep connected_clients'
```

#### 2. 监控 Celery Worker 状态
```bash
# 查看 Celery worker 状态
celery -A config inspect active
celery -A config inspect stats

# 查看连接池状态
celery -A config inspect pool
```

#### 3. 日志监控
建议设置告警规则，监控以下关键词：
- `server closed connection`
- `Connection refused`
- `Connection reset by peer`
- `Timeout`

#### 4. 重启 Celery Worker
应用配置更改后，需要重启 Celery Worker：

```bash
# 优雅重启（等待当前任务完成）
celery -A config multi restart worker1 -A config

# 或者使用 supervisorctl/systemctl 重启
supervisorctl restart celery-worker
# 或
systemctl restart celery-worker
```

### 环境变量配置

确保以下环境变量正确配置：

```bash
# Redis 连接配置
REDIS_HOST=your-redis-host
REDIS_PORT=6379
REDIS_PASSWORD=your-redis-password

# 或使用完整的 BROKER_URL
BROKER_URL=redis://:password@host:port/db
```

## 预防措施

### 1. 设置合理的超时时间
- Redis timeout: 建议设置为 0（永不超时）或较大值（如 300 秒）
- Socket timeout: 5-10 秒
- Connection timeout: 5 秒

### 2. 使用连接池
- 设置合适的连接池大小
- 启用连接健康检查
- 配置连接重试机制

### 3. 启用 TCP Keepalive
- 客户端启用 socket_keepalive
- Redis 服务器启用 tcp-keepalive
- 配置合理的 keepalive 参数

### 4. 监控和告警
- 监控 Redis 连接数
- 监控 Celery Worker 健康状态
- 设置连接失败告警

### 5. 网络优化
- 确保网络稳定性
- 检查防火墙和 NAT 超时设置
- 如使用负载均衡器，配置合理的超时和健康检查

## 常见问题排查

### Q1: 修复后仍然出现连接关闭错误
**排查步骤：**
1. 检查 Redis 服务器是否正常运行：`redis-cli PING`
2. 检查网络连接：`telnet redis-host 6379`
3. 查看 Redis 日志：`tail -f /var/log/redis/redis-server.log`
4. 检查防火墙规则：`iptables -L -n`

### Q2: 连接数持续增长
**可能原因：**
- 连接没有正确关闭
- 连接池配置过大
- 存在连接泄漏

**解决方法：**
- 检查代码中是否正确关闭连接
- 调整连接池大小
- 使用连接池管理器

### Q3: 偶尔出现超时错误
**可能原因：**
- Redis 服务器负载过高
- 网络抖动
- 慢查询

**解决方法：**
- 优化 Redis 查询
- 增加 Redis 服务器资源
- 检查慢查询日志：`redis-cli SLOWLOG GET 10`

## 总结

此次修复主要解决了以下问题：
1. ✅ 添加了连接健康检查机制
2. ✅ 启用了 TCP Keepalive 保持长连接
3. ✅ 配置了自动重连机制
4. ✅ 优化了连接池配置
5. ✅ 增强了超时和重试策略

这些改进将显著提高 Celery 与 Redis 连接的稳定性和可靠性。

## 参考资料

- [Celery Broker Configuration](https://docs.celeryq.dev/en/stable/userguide/configuration.html#broker-settings)
- [Redis Configuration](https://redis.io/docs/management/config/)
- [Redis Python Client Documentation](https://redis-py.readthedocs.io/)
- [TCP Keepalive HOWTO](http://www.tldp.org/HOWTO/TCP-Keepalive-HOWTO/)
