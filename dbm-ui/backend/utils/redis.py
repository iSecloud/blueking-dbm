# -*- coding: utf-8 -*-
"""
TencentBlueKing is pleased to support the open source community by making 蓝鲸智云-DB管理系统(BlueKing-BK-DBM) available.
Copyright (C) 2017-2023 THL A29 Limited, a Tencent company. All rights reserved.
Licensed under the MIT License (the "License"); you may not use this file except in compliance with the License.
You may obtain a copy of the License at https://opensource.org/licenses/MIT
Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on
an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the License for the
specific language governing permissions and limitations under the License.
"""
import ipaddress
import json

from django.core.serializers.json import DjangoJSONEncoder
from django_redis import get_redis_connection
from django_redis.pool import ConnectionFactory as Factory
from django_redis.serializers.base import BaseSerializer


class JSONSerializer(BaseSerializer):
    """
    自定义JSON序列化器用于redis序列化
    django-redis的默认JSON序列化器假定`decode_responses`被禁用。
    """

    def dumps(self, value):
        return json.dumps(value, cls=DjangoJSONEncoder)

    def loads(self, value):
        return json.loads(value)


class ConnectionFactory(Factory):
    """
    自定义ConnectionFactory以注入decode_responses参数和连接健康检查
    """

    def make_connection_params(self, url):
        kwargs = super().make_connection_params(url)
        kwargs["decode_responses"] = True
        # 添加连接健康检查配置，防止使用已关闭的连接
        kwargs["health_check_interval"] = 30  # 每30秒检查一次连接健康状态
        # 设置socket keepalive选项，维持长连接
        kwargs["socket_keepalive"] = True
        kwargs["socket_keepalive_options"] = {
            # TCP_KEEPIDLE: 连接闲置多久后开始发送keepalive探测包(秒)
            1: 60,  # 60秒
            # TCP_KEEPINTVL: keepalive探测包的发送间隔(秒)
            2: 10,  # 10秒
            # TCP_KEEPCNT: 最大keepalive探测次数
            3: 3,   # 3次
        }
        # 设置socket超时，避免无限等待
        if "socket_timeout" not in kwargs or kwargs["socket_timeout"] is None:
            kwargs["socket_timeout"] = 5  # 默认5秒超时
        if "socket_connect_timeout" not in kwargs or kwargs["socket_connect_timeout"] is None:
            kwargs["socket_connect_timeout"] = 5  # 连接超时5秒
        # 启用连接池的连接检查
        kwargs["retry_on_timeout"] = True  # 超时时自动重试
        return kwargs


# 定义redis的原生客户端
RedisConn = get_redis_connection("default")


def is_valid_ip(ip_address):
    """是否是合法的ip"""
    try:
        ipaddress.ip_address(ip_address)
        return True
    except ipaddress.AddressValueError:
        return False
    except Exception:
        return False
