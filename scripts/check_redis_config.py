#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Redis 连接配置检查脚本

用于检查 Redis 服务器配置是否符合 Celery 稳定运行的要求
"""
import os
import sys
import redis
from typing import Dict, List, Tuple


class RedisConfigChecker:
    """Redis 配置检查器"""
    
    def __init__(self, host: str = None, port: int = None, password: str = None, db: int = 0):
        """
        初始化 Redis 连接
        
        Args:
            host: Redis 主机地址
            port: Redis 端口
            password: Redis 密码
            db: Redis 数据库编号
        """
        self.host = host or os.getenv('REDIS_HOST', 'localhost')
        self.port = port or int(os.getenv('REDIS_PORT', 6379))
        self.password = password or os.getenv('REDIS_PASSWORD', '')
        self.db = db
        
        try:
            self.client = redis.StrictRedis(
                host=self.host,
                port=self.port,
                password=self.password if self.password else None,
                db=self.db,
                decode_responses=True,
                socket_connect_timeout=5,
            )
            # 测试连接
            self.client.ping()
            print(f"✅ 成功连接到 Redis: {self.host}:{self.port}")
        except redis.ConnectionError as e:
            print(f"❌ 无法连接到 Redis: {e}")
            sys.exit(1)
        except redis.AuthenticationError as e:
            print(f"❌ Redis 认证失败: {e}")
            sys.exit(1)
    
    def check_config(self, config_name: str, expected_value=None, 
                     comparison: str = None) -> Tuple[bool, str, str]:
        """
        检查 Redis 配置项
        
        Args:
            config_name: 配置项名称
            expected_value: 期望的值
            comparison: 比较方式 ('eq', 'ne', 'gt', 'lt', 'gte', 'lte', 'in')
        
        Returns:
            (是否通过, 当前值, 建议信息)
        """
        try:
            current_value = self.client.config_get(config_name).get(config_name, 'N/A')
            
            if expected_value is None:
                return True, current_value, ""
            
            # 转换类型
            if current_value != 'N/A' and isinstance(expected_value, int):
                current_value = int(current_value)
            
            # 比较值
            passed = True
            suggestion = ""
            
            if comparison == 'eq':
                passed = current_value == expected_value
                if not passed:
                    suggestion = f"建议设置为: {expected_value}"
            elif comparison == 'ne':
                passed = current_value != expected_value
            elif comparison == 'gt':
                passed = current_value > expected_value
                if not passed:
                    suggestion = f"建议设置为大于 {expected_value} 的值"
            elif comparison == 'lt':
                passed = current_value < expected_value
                if not passed:
                    suggestion = f"建议设置为小于 {expected_value} 的值"
            elif comparison == 'gte':
                passed = current_value >= expected_value
                if not passed:
                    suggestion = f"建议设置为至少 {expected_value}"
            elif comparison == 'lte':
                passed = current_value <= expected_value
            elif comparison == 'in':
                passed = current_value in expected_value
                if not passed:
                    suggestion = f"建议设置为: {expected_value} 之一"
            
            return passed, current_value, suggestion
            
        except Exception as e:
            return False, "检查失败", f"错误: {e}"
    
    def check_all(self) -> Dict[str, Dict]:
        """执行所有配置检查"""
        results = {}
        
        # 1. 检查 timeout 配置
        print("\n📋 检查 Redis 配置...")
        print("-" * 60)
        
        passed, value, suggestion = self.check_config('timeout')
        results['timeout'] = {
            'value': value,
            'passed': True,  # timeout 只是信息性检查
            'recommendation': '推荐设置为 0（永不超时）或较大值（如 300 秒）',
            'current_suggestion': suggestion
        }
        status = "✅" if value in ['0', 0] or int(value) >= 300 else "⚠️"
        print(f"{status} timeout: {value}")
        if value not in ['0', 0] and int(value) < 300:
            print(f"   {results['timeout']['recommendation']}")
        
        # 2. 检查 maxclients
        passed, value, suggestion = self.check_config('maxclients', 1000, 'gte')
        results['maxclients'] = {
            'value': value,
            'passed': passed,
            'recommendation': '推荐设置为至少 1000，建议 10000',
            'current_suggestion': suggestion
        }
        status = "✅" if passed else "⚠️"
        print(f"{status} maxclients: {value}")
        if not passed or int(value) < 10000:
            print(f"   {results['maxclients']['recommendation']}")
        
        # 3. 检查 tcp-keepalive
        passed, value, suggestion = self.check_config('tcp-keepalive', 0, 'gt')
        results['tcp-keepalive'] = {
            'value': value,
            'passed': passed,
            'recommendation': '推荐设置为 300 秒',
            'current_suggestion': suggestion
        }
        status = "✅" if passed else "⚠️"
        print(f"{status} tcp-keepalive: {value}")
        if not passed:
            print(f"   {results['tcp-keepalive']['recommendation']}")
        
        # 4. 检查 maxmemory
        passed, value, suggestion = self.check_config('maxmemory')
        results['maxmemory'] = {
            'value': value,
            'passed': True,
            'recommendation': '根据服务器实际内存大小设置',
            'current_suggestion': suggestion
        }
        maxmem_bytes = int(value) if value not in ['N/A', '0', 0] else 0
        maxmem_gb = maxmem_bytes / (1024**3) if maxmem_bytes > 0 else 0
        status = "✅" if maxmem_bytes > 0 else "⚠️"
        print(f"{status} maxmemory: {value} ({maxmem_gb:.2f} GB)" if maxmem_bytes > 0 else f"{status} maxmemory: 未设置（无限制）")
        if maxmem_bytes == 0:
            print(f"   {results['maxmemory']['recommendation']}")
        
        # 5. 检查 maxmemory-policy
        passed, value, suggestion = self.check_config('maxmemory-policy')
        results['maxmemory-policy'] = {
            'value': value,
            'passed': True,
            'recommendation': '推荐: allkeys-lru 或 volatile-lru',
            'current_suggestion': suggestion
        }
        recommended_policies = ['allkeys-lru', 'volatile-lru', 'allkeys-lfu', 'volatile-lfu']
        status = "✅" if value in recommended_policies else "⚠️"
        print(f"{status} maxmemory-policy: {value}")
        if value not in recommended_policies:
            print(f"   {results['maxmemory-policy']['recommendation']}")
        
        return results
    
    def check_info(self):
        """检查 Redis 运行信息"""
        print("\n📊 Redis 运行信息...")
        print("-" * 60)
        
        try:
            info = self.client.info()
            
            # 连接信息
            connected_clients = info.get('connected_clients', 0)
            print(f"当前连接数: {connected_clients}")
            
            # 内存使用
            used_memory = info.get('used_memory', 0)
            used_memory_human = info.get('used_memory_human', 'N/A')
            maxmemory = info.get('maxmemory', 0)
            print(f"已使用内存: {used_memory_human} ({used_memory} bytes)")
            if maxmemory > 0:
                usage_percent = (used_memory / maxmemory) * 100
                print(f"内存使用率: {usage_percent:.2f}%")
                if usage_percent > 80:
                    print("   ⚠️ 内存使用率超过 80%，建议增加 maxmemory 或优化数据")
            
            # Redis 版本
            redis_version = info.get('redis_version', 'N/A')
            print(f"Redis 版本: {redis_version}")
            
            # 运行时间
            uptime_in_seconds = info.get('uptime_in_seconds', 0)
            uptime_days = uptime_in_seconds / 86400
            print(f"运行时间: {uptime_days:.2f} 天")
            
            # 慢查询
            if 'Commandstats' in info or 'stats' in info:
                print("\n慢查询检查...")
                slowlog = self.client.slowlog_get(10)
                if slowlog:
                    print(f"⚠️ 发现 {len(slowlog)} 条慢查询记录")
                    for idx, log in enumerate(slowlog[:3], 1):
                        print(f"   {idx}. {log['command'][:50]}... (耗时: {log['duration']/1000:.2f}ms)")
                else:
                    print("✅ 未发现慢查询")
            
        except Exception as e:
            print(f"❌ 获取 Redis 信息失败: {e}")
    
    def test_connection_stability(self, iterations: int = 10):
        """测试连接稳定性"""
        print(f"\n🔄 测试连接稳定性 ({iterations} 次)...")
        print("-" * 60)
        
        success_count = 0
        total_time = 0
        
        for i in range(iterations):
            try:
                import time
                start = time.time()
                self.client.ping()
                elapsed = time.time() - start
                total_time += elapsed
                success_count += 1
                print(f"   测试 {i+1}/{iterations}: ✅ ({elapsed*1000:.2f}ms)")
            except Exception as e:
                print(f"   测试 {i+1}/{iterations}: ❌ {e}")
        
        print(f"\n成功率: {success_count}/{iterations} ({success_count/iterations*100:.1f}%)")
        if success_count > 0:
            avg_time = total_time / success_count
            print(f"平均响应时间: {avg_time*1000:.2f}ms")
        
        if success_count < iterations:
            print("⚠️ 连接不稳定，建议检查网络和 Redis 服务器状态")
    
    def print_recommendations(self, results: Dict):
        """打印配置建议"""
        print("\n💡 配置建议...")
        print("-" * 60)
        
        recommendations = []
        
        for config_name, result in results.items():
            if not result['passed'] or result['current_suggestion']:
                recommendations.append({
                    'config': config_name,
                    'current': result['value'],
                    'recommendation': result['recommendation']
                })
        
        if recommendations:
            print("建议修改以下配置项（在 redis.conf 中）：\n")
            for rec in recommendations:
                print(f"  {rec['config']}")
                print(f"    当前值: {rec['current']}")
                print(f"    建议: {rec['recommendation']}")
                print()
            
            print("修改配置后，需要重启 Redis 服务：")
            print("  sudo systemctl restart redis")
            print("  或")
            print("  redis-cli CONFIG REWRITE && redis-cli CONFIG RELOAD")
        else:
            print("✅ Redis 配置良好，无需修改")
    
    def close(self):
        """关闭连接"""
        if self.client:
            self.client.close()


def main():
    """主函数"""
    print("=" * 60)
    print("Redis 连接配置检查工具")
    print("=" * 60)
    
    # 从环境变量或参数获取连接信息
    host = os.getenv('REDIS_HOST', 'localhost')
    port = int(os.getenv('REDIS_PORT', 6379))
    password = os.getenv('REDIS_PASSWORD', '')
    
    print(f"\n连接信息:")
    print(f"  主机: {host}")
    print(f"  端口: {port}")
    print(f"  密码: {'***' if password else '未设置'}")
    
    try:
        checker = RedisConfigChecker(host=host, port=port, password=password)
        
        # 执行所有检查
        results = checker.check_all()
        
        # 检查运行信息
        checker.check_info()
        
        # 测试连接稳定性
        checker.test_connection_stability(iterations=5)
        
        # 打印建议
        checker.print_recommendations(results)
        
        print("\n" + "=" * 60)
        print("检查完成！")
        print("=" * 60)
        
        checker.close()
        
    except KeyboardInterrupt:
        print("\n\n用户中断")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ 检查过程中出错: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
