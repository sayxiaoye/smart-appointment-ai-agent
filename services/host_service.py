from typing import List, Dict, Any, Optional
from db.db_router import DatabaseRouter
import logging

logger = logging.getLogger(__name__)


class HostService:
    """主持人服务：种子数据与档期查询"""

    def __init__(self, db_path: str = "sqlite:///data/smart_appointment.db"):
        self.db = DatabaseRouter(db_path)
        # 陈屿与林可的专长故意接近，供指定主持人没空时做相似推荐
        self.default_hosts = [
            {
                "name": "陈屿",
                "gender": "男",
                "host_types": ["pro_host"],
                "specialty": "擅长社交推理与剧本杀控场，规则讲解清晰，适合血染钟楼、阿瓦隆等重策略局",
            },
            {
                "name": "林可",
                "gender": "女",
                "host_types": ["pro_host"],
                "specialty": "擅长社交推理与剧本杀控场，规则讲解清晰，适合重策略和阵营对抗局",
            },
            {
                "name": "周宁",
                "gender": "男",
                "host_types": ["staff_guide", "pro_host"],
                "specialty": "店员带玩经验丰富，适合卡卡颂、璀璨宝石等入门德式，节奏轻快",
            },
            {
                "name": "苏晚",
                "gender": "女",
                "host_types": ["staff_guide"],
                "specialty": "擅长聚会类和轻策略，能带新手快速开局，语气活泼",
            },
            {
                "name": "何安",
                "gender": "男",
                "host_types": ["kids_host"],
                "specialty": "少儿向主持，擅长恐龙小镇等儿童桌游，节奏慢、规则口语化",
            },
            {
                "name": "赵朗",
                "gender": "男",
                "host_types": ["kids_host", "staff_guide"],
                "specialty": "少儿与家庭局都能带，耐心讲解，适合亲子",
            },
            {
                "name": "马哲",
                "gender": "男",
                "host_types": ["pro_host", "staff_guide"],
                "specialty": "策略德式与阵营游戏都能控场，适合中等复杂度",
            },
            {
                "name": "许清",
                "gender": "女",
                "host_types": ["staff_guide"],
                "specialty": "聚会破冰和轻量桌游，适合朋友局的轻度带领",
            },
        ]

    def initialize_default_hosts(self) -> bool:
        try:
            existing = self.db.hosts.get_all_hosts()
            if existing:
                logger.info("数据库中已有 %s 位主持人，跳过初始化", len(existing))
                self._fill_missing_genders()
                return True

            logger.info("开始初始化默认主持人")
            for host_data in self.default_hosts:
                self.db.hosts.add_host(
                    name=host_data["name"],
                    host_types=host_data["host_types"],
                    specialty=host_data["specialty"],
                    gender=host_data["gender"],
                )
            logger.info("主持人初始化完成，共 %s 位", len(self.db.hosts.get_all_hosts()))
            return True
        except Exception as exc:
            logger.error("主持人初始化失败: %s", exc)
            return False

    def _fill_missing_genders(self) -> None:
        genders = {item["name"]: item["gender"] for item in self.default_hosts}
        for host in self.db.hosts.get_all_hosts():
            if host.get("gender"):
                continue
            gender = genders.get(host["name"])
            if gender:
                self.db.hosts.update_host(host["id"], gender=gender)

    def get_all_hosts(self) -> List[Dict[str, Any]]:
        self.initialize_default_hosts()
        return self.db.hosts.get_all_hosts()

    def get_host_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        self.initialize_default_hosts()
        return self.db.hosts.get_host_by_name(name)

    def get_host_by_id(self, host_id: int) -> Optional[Dict[str, Any]]:
        self.initialize_default_hosts()
        return self.db.hosts.get_host_by_id(host_id)

    def get_hosts_by_type(self, host_type: str) -> List[Dict[str, Any]]:
        self.initialize_default_hosts()
        return self.db.hosts.get_hosts_by_type(host_type)

    def get_host_schedules(self, host_id: int, date) -> List[Dict[str, Any]]:
        return self.db.hosts.get_host_schedules(host_id, date)

    def is_host_available(self, host_id: int, start_time, end_time) -> bool:
        return self.db.hosts.is_host_available(host_id, start_time, end_time)

    def get_hosts_count(self) -> int:
        return len(self.get_all_hosts())
