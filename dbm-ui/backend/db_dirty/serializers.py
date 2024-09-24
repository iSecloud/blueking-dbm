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
from rest_framework import serializers

from backend.db_dirty.constants import PoolType
from backend.db_dirty.mock import DIRTY_MACHINE_LIST
from backend.db_dirty.models import DirtyMachine, MachineEvent
from backend.db_meta.models import AppCache
from backend.ticket.constants import TicketType
from backend.ticket.models import Ticket


class QueryDirtyMachineSerializer(serializers.Serializer):
    ip_list = serializers.CharField(help_text=_("过滤的主机IP列表，以逗号分隔"), required=False)
    ticket_id = serializers.IntegerField(help_text=_("过滤的单据ID"), required=False)
    task_id = serializers.CharField(help_text=_("过滤的任务ID"), required=False)
    ticket_type = serializers.ChoiceField(help_text=_("过滤的单据类型"), choices=TicketType.get_choices(), required=False)
    operator = serializers.CharField(help_text=_("操作人"), required=False)

    def validate(self, attrs):
        if "ip_list" in attrs:
            attrs["ip_list"] = attrs["ip_list"].split(",")

        return attrs


class QueryDirtyMachineResponseSerializer(serializers.Serializer):
    class Meta:
        swagger_schema_fields = {"example": DIRTY_MACHINE_LIST}


class TransferDirtyMachineSerializer(serializers.Serializer):
    bk_host_ids = serializers.ListField(child=serializers.IntegerField(), help_text=_("待转移的主机ID列表"))
    source = serializers.ChoiceField(help_text=_("主机来源"), choices=PoolType.get_choices())
    target = serializers.ChoiceField(help_text=_("主机去向"), choices=PoolType.get_choices())


class DeleteDirtyMachineSerializer(serializers.Serializer):
    bk_host_ids = serializers.ListField(child=serializers.IntegerField(), help_text=_("待删除的污点池记录主机ID"))


class ListMachineEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = MachineEvent
        fields = "__all__"

    @property
    def biz_map(self):
        if not hasattr(self, "_biz_map"):
            biz_ids = [event.bk_biz_id for event in self.instance]
            biz_map = {biz.bk_biz_id: biz for biz in AppCache.objects.filter(bk_biz_id__in=biz_ids)}
            setattr(self, "_biz_map", biz_map)
        return self._biz_map

    @property
    def ticket_cluster_map(self):
        if not hasattr(self, "_ticket_cluster_map"):
            ticket_ids = [event.ticket.id for event in self.instance if event.ticket]
            tickets = Ticket.objects.filter(id__in=ticket_ids)
            ticket_cluster_map = {ticket.id: ticket.details.get("clusters", {}).values() for ticket in tickets}
            setattr(self, "_ticket_cluster_map", ticket_cluster_map)
        return self._ticket_cluster_map

    def to_representation(self, instance):
        biz, ticket_data = self.biz_map[instance.bk_biz_id], self.ticket_cluster_map.get(instance.ticket_id, [])
        instance = super().to_representation(instance)
        instance.update(bk_biz_name=biz.bk_biz_name, db_app_abbr=biz.db_app_abbr, clusters=ticket_data)
        return instance


class ListMachineEventResponseSerializer(serializers.Serializer):
    class Meta:
        swagger_schema_fields = {"example": {}}


class ListMachinePoolSerializer(serializers.ModelSerializer):
    class Meta:
        model = DirtyMachine
        fields = "__all__"


class ListMachinePoolResponseSerializer(serializers.Serializer):
    class Meta:
        swagger_schema_fields = {"example": {}}
