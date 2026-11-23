"""
主持人查找器

按主持类型、专长和档期查找主持人。自助场次不走这里。
"""

from typing import Optional, Dict, Any, Callable, List
from datetime import datetime, timedelta
from services.text_embedding import find_best_match_indices
from config.constants import is_known, host_type_label


class HostFinder:
    """主持人查找器"""

    def parse_time_and_duration(self, start_time_str: str, duration_str: str) -> tuple:
        if not is_known(start_time_str) or not is_known(duration_str):
            return None, None, None
        try:
            from config.time_config import time_config
            start_time = time_config.parse_datetime(start_time_str)
            if start_time is None:
                return None, None, None
            duration_min = int("".join(ch for ch in str(duration_str) if ch.isdigit()))
            if duration_min <= 0:
                return None, None, None
            end_time = start_time + timedelta(minutes=duration_min)
            return start_time, end_time, duration_min
        except Exception:
            return None, None, None

    def find_specific_host(self, host_name: str, start_time: datetime, end_time: datetime,
                           yield_func: Optional[Callable] = None) -> Optional[Dict]:
        from services.appointment_service import AppointmentService
        appointment_service = AppointmentService()

        if yield_func:
            yield_func(f"[THOUGHT][预约机器人] 用户指定了主持人：{host_name}，正在查询档期...\n")

        host = appointment_service.get_host_by_name(host_name)
        if not host:
            if yield_func:
                yield_func(f"[THOUGHT][预约机器人] 未找到名为「{host_name}」的主持人\n")
            return None

        if appointment_service.is_host_available(host["id"], start_time, end_time):
            if yield_func:
                yield_func(f"[THOUGHT][预约机器人] {host_name}在指定时间有空\n")
            return host

        if yield_func:
            yield_func(f"[THOUGHT][预约机器人] {host_name}在指定时间不空闲\n")
        return None

    def find_similar_available_host(self, target_host: Dict[str, Any], host_type: Optional[str],
                                    start_time: datetime, end_time: datetime,
                                    yield_func: Optional[Callable] = None) -> Optional[Dict]:
        from services.appointment_service import AppointmentService
        appointment_service = AppointmentService()

        if yield_func:
            yield_func(f"[THOUGHT][预约机器人] 正在按{target_host['name']}的专长寻找同类型主持人...\n")

        others = [
            host for host in appointment_service.get_all_hosts()
            if host["id"] != target_host["id"] and self._supports_type(host, host_type, target_host)
        ]
        if not others:
            return None

        target_specialty = target_host.get("specialty") or ""
        if not target_specialty:
            ordered = others
        else:
            specialties = [host.get("specialty") or "" for host in others]
            indices = find_best_match_indices(target_specialty, specialties)
            ordered = [others[index] for index in indices]

        for host in ordered:
            if appointment_service.is_host_available(host["id"], start_time, end_time):
                if yield_func:
                    yield_func(f"[THOUGHT][预约机器人] 找到同类型且有空的主持人：{host['name']}\n")
                return host

        if yield_func:
            yield_func("[THOUGHT][预约机器人] 没有找到同类型且有空的主持人\n")
        return None

    def filter_hosts_by_type(self, hosts: List[Dict[str, Any]], host_type: str) -> List[Dict[str, Any]]:
        if not host_type:
            return hosts
        return [host for host in hosts if host_type in (host.get("host_types") or [])]

    def filter_hosts_by_preference(self, hosts: List[Dict[str, Any]], preference: str) -> List[Dict[str, Any]]:
        if not preference or preference in ("无", "未知"):
            return hosts
        specialties = [host.get("specialty") or "" for host in hosts]
        indices = find_best_match_indices(preference, specialties)
        return [hosts[index] for index in indices]

    def find_available_host(self, ranked_hosts: list, pool: list, start_time: datetime,
                            end_time: datetime, preference: str,
                            yield_func: Optional[Callable] = None) -> Optional[Dict]:
        from services.appointment_service import AppointmentService
        appointment_service = AppointmentService()

        if yield_func:
            yield_func("[THOUGHT][预约机器人] 正在查找空闲主持人...\n")

        for host in ranked_hosts:
            if appointment_service.is_host_available(host["id"], start_time, end_time):
                if yield_func:
                    yield_func(f"[THOUGHT][预约机器人] 找到空闲主持人：{host['name']}\n")
                return host

        if preference and preference not in ("无", "未知") and ranked_hosts != pool:
            if yield_func:
                yield_func("[THOUGHT][预约机器人] 偏好主持人无空闲，改为在同类型主持人里查找...\n")
            for host in pool:
                if appointment_service.is_host_available(host["id"], start_time, end_time):
                    if yield_func:
                        yield_func(f"[THOUGHT][预约机器人] 找到空闲主持人：{host['name']}\n")
                    return host

        if yield_func:
            yield_func("[THOUGHT][预约机器人] 没有找到空闲主持人\n")
        return None

    def find_host_with_thought(self, appointment_history: Dict[str, Any],
                               yield_func: Optional[Callable] = None) -> Optional[Dict]:
        from services.appointment_service import AppointmentService
        appointment_service = AppointmentService()

        preference = appointment_history.get("preference")
        host_type = appointment_history.get("host_type")
        start_time_str = appointment_history.get("start_time")
        duration_str = appointment_history.get("duration")
        host_name = appointment_history.get("host_name")

        start_time, end_time, _ = self.parse_time_and_duration(start_time_str, duration_str)
        if not start_time or not end_time:
            if yield_func:
                yield_func("[THOUGHT][预约机器人] 预约时间或时长不完整，无法检索主持人\n")
            return None

        if yield_func:
            label = host_type_label(host_type) or "未指定"
            yield_func(f"[THOUGHT][预约机器人] 正在按主持类型「{label}」检索档期...\n")

        if is_known(host_name):
            specific = self.find_specific_host(host_name, start_time, end_time, yield_func)
            if specific:
                return specific

            target = appointment_service.get_host_by_name(host_name)
            if target:
                similar = self.find_similar_available_host(target, host_type, start_time, end_time, yield_func)
                if similar:
                    return {
                        "is_recommendation": True,
                        "original_host": target,
                        "recommended_host": similar,
                        "requires_confirmation": True,
                    }
            return None

        all_hosts = appointment_service.get_all_hosts()
        if not all_hosts:
            if yield_func:
                yield_func("[THOUGHT][预约机器人] 没有主持人数据\n")
            return None

        typed_hosts = self.filter_hosts_by_type(all_hosts, host_type)
        if yield_func:
            yield_func(f"[THOUGHT][预约机器人] 该主持类型有 {len(typed_hosts)} 位主持人\n")
        if not typed_hosts:
            return None

        ranked = self.filter_hosts_by_preference(typed_hosts, preference)
        return self.find_available_host(ranked, typed_hosts, start_time, end_time, preference, yield_func)

    def _supports_type(self, host: Dict[str, Any], host_type: Optional[str], target_host: Dict[str, Any]) -> bool:
        types = host.get("host_types") or []
        if host_type:
            return host_type in types
        target_types = [item for item in (target_host.get("host_types") or []) if item != "self_play"]
        return any(item in types for item in target_types)
