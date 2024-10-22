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

from django.utils.translation import ugettext_lazy as _
from django_filters import rest_framework
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from backend.bk_web import viewsets
from backend.bk_web.pagination import AuditedLimitOffsetPagination
from backend.bk_web.swagger import common_swagger_auto_schema
from backend.db_dirty.constants import SWAGGER_TAG
from backend.db_dirty.filters import DirtyMachineFilter, DirtyMachinePoolFilter, MachineEventFilter
from backend.db_dirty.handlers import DBDirtyMachineHandler
from backend.db_dirty.models import DirtyMachine, MachineEvent
from backend.db_dirty.serializers import (
    DeleteDirtyMachineSerializer,
    ListMachineEventResponseSerializer,
    ListMachineEventSerializer,
    ListMachinePoolResponseSerializer,
    ListMachinePoolSerializer,
    QueryDirtyMachineResponseSerializer,
    QueryDirtyMachineSerializer,
    TransferDirtyMachineSerializer,
)
from backend.iam_app.dataclass import ResourceEnum
from backend.iam_app.dataclass.actions import ActionEnum
from backend.iam_app.handlers.drf_perm.base import ResourceActionPermission
from backend.iam_app.handlers.permission import Permission


class DBDirtyMachineViewSet(viewsets.SystemViewSet):
    pagination_class = AuditedLimitOffsetPagination
    filter_class = None

    action_permission_map = {("query_operation_list",): []}
    default_permission_class = [ResourceActionPermission([ActionEnum.DIRTY_POLL_MANAGE])]

    @common_swagger_auto_schema(
        operation_summary=_("[TODO待删除]查询污点池列表"),
        responses={status.HTTP_200_OK: QueryDirtyMachineResponseSerializer()},
        tags=[SWAGGER_TAG],
    )
    @Permission.decorator_external_permission_field(
        param_field=lambda d: None,
        actions=[ActionEnum.DIRTY_POLL_MANAGE],
        resource_meta=None,
    )
    @Permission.decorator_permission_field(
        id_field=lambda d: d["task_id"],
        data_field=lambda d: d["results"],
        actions=[ActionEnum.FLOW_DETAIL],
        resource_meta=ResourceEnum.TASKFLOW,
    )
    @Permission.decorator_permission_field(
        id_field=lambda d: d["ticket_id"],
        data_field=lambda d: d["results"],
        actions=[ActionEnum.TICKET_VIEW],
        resource_meta=ResourceEnum.TICKET,
    )
    @action(
        detail=False,
        methods=["GET"],
        url_path="query_dirty_machines",
        serializer_class=QueryDirtyMachineSerializer,
        pagination_class=AuditedLimitOffsetPagination,
        filter_class=DirtyMachineFilter,
        filter_backends=(rest_framework.DjangoFilterBackend,),
        queryset=DirtyMachine.objects.all(),
    )
    def query_operation_list(self, request):
        dirty_machines = self.filter_queryset(self.get_queryset()).order_by("-ticket_id")
        page_dirty_machines = self.paginate_queryset(dirty_machines)
        dirty_machine_list = DBDirtyMachineHandler.query_dirty_machine_records(page_dirty_machines)
        return self.paginator.get_paginated_response(data=dirty_machine_list)

    @common_swagger_auto_schema(
        operation_summary=_("[TODO待删除]删除污点池记录"),
        request_body=DeleteDirtyMachineSerializer(),
        tags=[SWAGGER_TAG],
    )
    @action(
        detail=False,
        methods=["DELETE"],
        url_path="delete_dirty_records",
        serializer_class=DeleteDirtyMachineSerializer,
    )
    def delete_dirty_records(self, request):
        bk_host_ids = self.params_validate(self.get_serializer_class())["bk_host_ids"]
        DirtyMachine.objects.filter(bk_host_id__in=bk_host_ids).delete()
        return Response()

    @common_swagger_auto_schema(
        operation_summary=_("将主机转移至待回收/故障池模块"),
        request_body=TransferDirtyMachineSerializer(),
        tags=[SWAGGER_TAG],
    )
    @action(detail=False, methods=["POST"], serializer_class=TransferDirtyMachineSerializer)
    def transfer_hosts_to_pool(self, request):
        data = self.params_validate(self.get_serializer_class())
        DBDirtyMachineHandler.transfer_hosts_to_pool(operator=request.user.username, **data)
        return Response()

    @common_swagger_auto_schema(
        operation_summary=_("机器事件列表"),
        responses={status.HTTP_200_OK: ListMachineEventResponseSerializer()},
        tags=[SWAGGER_TAG],
    )
    @action(detail=False, methods=["GET"], filter_class=MachineEventFilter, queryset=MachineEvent.objects.all())
    def list_machine_events(self, request):
        events_qs = self.paginate_queryset(self.filter_queryset(self.get_queryset()))
        events_data = ListMachineEventSerializer(events_qs, many=True).data
        return self.paginator.get_paginated_response(data=events_data)

    @common_swagger_auto_schema(
        operation_summary=_("主机池查询"),
        responses={status.HTTP_200_OK: ListMachinePoolResponseSerializer()},
        tags=[SWAGGER_TAG],
    )
    @action(detail=False, methods=["GET"], filter_class=DirtyMachinePoolFilter, queryset=DirtyMachine.objects.all())
    def query_machine_pool(self, request):
        machine_qs = self.paginate_queryset(self.filter_queryset(self.get_queryset()))
        machine_data = ListMachinePoolSerializer(machine_qs, many=True).data
        return self.paginator.get_paginated_response(data=machine_data)
