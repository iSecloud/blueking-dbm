# -*- coding: utf-8 -*-
"""
TencentBlueKing is pleased to support the open source community by making 蓝鲸智云-DB管理系统(BlueKing-BK-DBM) available.
Copyright (C) 2017-2022 THL A29 Limited, a Tencent company. All rights reserved.
Licensed under the MIT License (the "License"); you may not use this file except in compliance with the License.
You may obtain a copy of the License at https://opensource.org/licenses/MIT
Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on
an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the License for the
specific language governing permissions and limitations under the License.
"""

from typing import Any, Dict, List

from django.utils.translation import ugettext_lazy as _
from rest_framework.decorators import action
from rest_framework.response import Response

from backend.bk_web.swagger import common_swagger_auto_schema
from backend.configuration.handlers.password import DBPasswordHandler
from backend.db_proxy import nginxconf_tpl
from backend.db_proxy.constants import SWAGGER_TAG, ExtensionAccountEnum, ExtensionServiceStatus, ExtensionType
from backend.db_proxy.models import ClusterExtension, DBCloudProxy, DBExtension
from backend.db_proxy.views.cloud.serializers import InsertDBExtensionSerializer
from backend.db_proxy.views.serialiers import BaseProxyPassSerializer
from backend.db_proxy.views.views import BaseProxyPassViewSet
from backend.flow.consts import MySQLPrivComponent, UserName


class CloudProxyPassViewSet(BaseProxyPassViewSet):
    """
    云区域组件接口的透传视图
    """

    @common_swagger_auto_schema(
        operation_summary=_("[容器化]写入云区域组件记录"),
        request_body=InsertDBExtensionSerializer(),
        tags=[SWAGGER_TAG],
    )
    @action(methods=["POST"], serializer_class=InsertDBExtensionSerializer, detail=False)
    def insert(self, request, *args, **kwargs):
        data = self.params_validate(self.get_serializer_class())
        output_info = {}
        bk_cloud_id = data["bk_cloud_id"]

        if data["extension"] == ExtensionType.NGINX:
            # nginx需要写入代理信息
            ip = data["details"]["ip"]
            DBCloudProxy.objects.create(bk_cloud_id=data["bk_cloud_id"], internal_address=ip, external_address=ip)
        elif data["extension"] == ExtensionType.DRS:
            # drs随机生成账号/密码
            drs_account = ExtensionAccountEnum.generate_random_account(bk_cloud_id)
            webconsole_account = ExtensionAccountEnum.generate_random_account(bk_cloud_id)
            data["details"].update(
                use=drs_account["encrypt_user"],
                pwd=drs_account["encrypt_password"],
                webconsole_user=webconsole_account["encrypt_user"],
                webconsole_pwd=webconsole_account["encrypt_password"],
            )
            # drs proxy密码
            proxy_password = DBPasswordHandler.get_component_password(UserName.PROXY, MySQLPrivComponent.PROXY)
            output_info.update(
                drs_account=drs_account, webconsole_account=webconsole_account, proxy_password=proxy_password
            )
        elif data["extension"] == ExtensionType.DBHA:
            # dbha 随机生成账号/密码
            dbha_account = ExtensionAccountEnum.generate_random_account(bk_cloud_id)
            # 获取proxy密码和mysql os密码
            dbha_password_map = DBPasswordHandler.batch_query_components_password(
                components=[
                    {"username": UserName.PROXY, "component": MySQLPrivComponent.PROXY},
                    {"username": UserName.OS_MYSQL, "component": MySQLPrivComponent.MYSQL},
                ]
            )
            output_info.update(
                dbha_account=dbha_account,
                proxy_password=dbha_password_map[UserName.PROXY][MySQLPrivComponent.PROXY],
                mysql_os_password=dbha_password_map[UserName.OS_MYSQL][MySQLPrivComponent.MYSQL],
            )

        DBExtension(**data, status=ExtensionServiceStatus.RUNNING).save()
        return Response(output_info)

    @common_swagger_auto_schema(
        operation_summary=_("[容器化]获取云区域nginx子配置文件"),
        request_body=BaseProxyPassSerializer(),
        tags=[SWAGGER_TAG],
    )
    @action(methods=["POST"], detail=False, serializer_class=BaseProxyPassSerializer)
    def pull_nginx_conf(self, request, *args, **kwargs):
        bk_cloud_id = self.params_validate(self.get_serializer_class())["bk_cloud_id"]
        # 目前子配置只有大数据转发，并且考虑社区化部署集群量较少，这里就全量拉去更新
        cluster_extensions = ClusterExtension.objects.filter(bk_cloud_id=bk_cloud_id)
        proxy = DBCloudProxy.objects.filter(bk_cloud_id=bk_cloud_id).last()
        file_list: List[Dict[str, Any]] = []
        for extension in cluster_extensions:
            conf_tpl = getattr(nginxconf_tpl, f"{extension.db_type}_conf_tpl", None)
            # 当前组件无子配置，忽略
            if not conf_tpl:
                continue
            file_list.append(nginxconf_tpl.render_nginx_tpl(conf_tpl=conf_tpl, extension=extension, encode=False))
            # 保存访问地址
            if not extension.access_url:
                extension.save_access_url(nginx_url=f"{proxy.external_address}:{80}")
        return Response(file_list)
