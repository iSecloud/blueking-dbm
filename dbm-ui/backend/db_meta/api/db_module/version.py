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
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from django.utils.translation import gettext_lazy as _

from backend.db_meta.dataclass import DBModuleComponentVersion
from backend.db_meta.enums import MachineType
from backend.db_meta.exceptions import DBModuleVersionException
from backend.db_meta.models.db_version import DBVersion
from backend.db_package.models import Package
from backend.flow.consts import MediumEnum

# 组件绑定的介质包类型。TenDBCluster 的存储/接入介质在发行版上挂的 db_type 也是 MySQL。
MODULE_COMPONENT_PKG_TYPE: Dict[str, str] = {
    MachineType.SINGLE.value: MediumEnum.MySQL.value,
    MachineType.BACKEND.value: MediumEnum.MySQL.value,
    MachineType.REMOTE.value: MediumEnum.MySQL.value,
    MachineType.PROXY.value: MediumEnum.MySQLProxy.value,
    MachineType.SPIDER.value: MediumEnum.Spider.value,
}


def validate_components(components: Mapping[str, DBModuleComponentVersion]) -> None:
    for component, layer in components.items():
        validate_component_version(component, layer)


def validate_component_version(component: str, layer: DBModuleComponentVersion) -> None:
    db_version = DBVersion.objects.filter(pk=layer.db_version_id).first()
    if not db_version:
        raise DBModuleVersionException(message=_("版本 {} 不存在").format(layer.db_version_id))
    if not db_version.enable:
        raise DBModuleVersionException(message=_("版本 {} 未启用").format(layer.db_version_id))

    # 校验绑定的介质版本符合类型
    pkg_type = (db_version.distribution_snapshot or {}).get("pkg_type", "")
    expected_pkg = MODULE_COMPONENT_PKG_TYPE.get(component)
    if expected_pkg and pkg_type != expected_pkg:
        raise DBModuleVersionException(
            message=_("组件 {} 不能绑定介质类型 {} 的版本 {}").format(component, pkg_type, layer.db_version_id)
        )

    # 校验合法的操作系统
    os_map = enabled_package_permit_os([layer.db_version_id])
    if layer.os_key not in os_map:
        raise DBModuleVersionException(
            message=_("版本 {} 没有 {} 类型的已启用介质包").format(layer.db_version_id, layer.permit_os_type)
        )

    package_os = os_map[layer.os_key]
    rejected = [name for name in layer.permit_os if name not in package_os]
    if rejected:
        raise DBModuleVersionException(
            message=_("操作系统 {} 不在版本 {} 当前已启用介质包的范围内").format(",".join(rejected), layer.db_version_id)
        )


def enabled_package_permit_os(db_version_ids: Iterable[int]) -> Dict[Tuple[int, str], List[str]]:
    """查询版本下已启用介质包支持的操作系统，按 (版本ID, 操作系统类型) 合并去重。

    返回示例: {(1, "Linux"): ["tlinux-3.2", "tlinux-4"]}
    某个版本没有已启用的介质包时，结果里不会出现它。
    """
    packages = (
        Package.objects.filter(db_version_id__in=set(db_version_ids), enable=True)
        .order_by("id")
        .values_list("db_version_id", "permit_os_type", "permit_os")
    )

    os_map: Dict[Tuple[int, str], List[str]] = {}
    for db_version_id, os_type, package_os in packages:
        os_list = os_map.setdefault((db_version_id, os_type), [])
        for os_name in package_os or []:
            if os_name not in os_list:
                os_list.append(os_name)
    return os_map


def get_component_permit_os(db_module, component: str) -> Optional[Tuple[str, List[str]]]:
    """查询模块某个组件当前允许的操作系统。

    返回 (操作系统类型, 操作系统列表)，例如 ("Linux", ["tlinux-3.2", "tlinux-4"])。
    该组件还没有设置版本时返回 None。
    """
    layer = db_module.current_db_version.get(component)
    if not layer:
        return None

    # 固定范围：直接用模块上保存的列表
    if not layer.follow_package:
        return layer.permit_os_type, list(layer.permit_os)

    # 跟随版本包：查该版本下已启用介质包的操作系统
    os_map = enabled_package_permit_os([layer.db_version_id])
    return layer.permit_os_type, os_map.get(layer.os_key, [])


def describe_module_version(module) -> Dict[str, Dict]:
    return describe_modules_version([module]).get(module.db_module_id, {})


def describe_modules_version(modules: Sequence) -> Dict[int, Dict[str, Dict]]:
    """批量展开模块各组件的版本信息，给接口展示用。

    返回示例: {模块ID: {"proxy": {...}, "backend": {...}}}，未设置版本的模块对应空字典。
    """
    # 1. 收集所有模块的组件版本，以及涉及到的版本ID
    layers_by_module = {}
    version_ids = set()
    for module in modules:
        layers = module.current_db_version
        layers_by_module[module.db_module_id] = layers
        for layer in layers.values():
            version_ids.add(layer.db_version_id)

    # 2. 一次性查出版本信息和介质包操作系统，避免逐个模块查库
    versions = DBVersion.objects.select_related("version_series").in_bulk(version_ids)
    os_map = enabled_package_permit_os(version_ids)

    # 3. 逐个组件拼装展示结构
    result = {}
    for module_id, layers in layers_by_module.items():
        result[module_id] = {}
        for component, layer in layers.items():
            if layer.follow_package:
                effective_os = os_map.get(layer.os_key, [])
            else:
                effective_os = list(layer.permit_os)
            db_version = versions.get(layer.db_version_id)
            result[module_id][component] = _describe_layer(layer, db_version, effective_os)
    return result


def _describe_layer(layer: DBModuleComponentVersion, db_version: Optional[DBVersion], effective_os: List[str]) -> Dict:
    info = {
        "db_version_id": layer.db_version_id,
        "permit_os_type": layer.permit_os_type,
        "permit_os": list(layer.permit_os),
        "follow_package": layer.follow_package,
        "effective_permit_os": effective_os,
        "distribution": "",
        "version_series": "",
        "version_name": "",
        "full_version": "",
    }
    # 版本已被删除时只返回模块上保存的字段
    if not db_version:
        return info

    info["distribution"] = (db_version.distribution_snapshot or {}).get("name", "")
    info["version_series"] = db_version.version_series.name if db_version.version_series else ""
    info["version_name"] = db_version.name
    info["full_version"] = db_version.full_version
    return info
