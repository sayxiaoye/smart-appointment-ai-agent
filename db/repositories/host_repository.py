from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from ..base.interfaces import BaseHostRepository, BaseScheduleRepository
from ..base.session_manager import SessionManager
from ..models import Host, HostSchedule


class HostRepository(BaseHostRepository, BaseScheduleRepository):
    """主持人信息与排班的数据访问对象"""

    def __init__(self, session_manager: SessionManager):
        self.session_manager = session_manager

    def add_host(self, name: str, host_types: Optional[List[str]] = None, specialty: Optional[str] = None) -> int:
        with self.session_manager.session_scope() as session:
            host = Host(name=name, host_types=host_types or [], specialty=specialty)
            session.add(host)
            session.flush()
            return host.id

    def get_host_by_id(self, host_id: int) -> Optional[Dict[str, Any]]:
        with self.session_manager.session_scope() as session:
            host = session.query(Host).filter(Host.id == host_id).first()
            return self._host_to_dict(host) if host else None

    def get_host_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        with self.session_manager.session_scope() as session:
            host = session.query(Host).filter(Host.name == name).first()
            return self._host_to_dict(host) if host else None

    def get_all_hosts(self) -> List[Dict[str, Any]]:
        with self.session_manager.session_scope() as session:
            hosts = session.query(Host).all()
            return [self._host_to_dict(host) for host in hosts]

    def get_all_specialties(self) -> List[str]:
        with self.session_manager.session_scope() as session:
            specialties = session.query(Host.specialty).distinct().all()
            return [item[0] for item in specialties if item[0]]

    def update_host(self, host_id: int, **updates) -> bool:
        with self.session_manager.session_scope() as session:
            host = session.query(Host).filter(Host.id == host_id).first()
            if not host:
                return False
            for key, value in updates.items():
                if hasattr(host, key):
                    setattr(host, key, value)
            return True

    def delete_host(self, host_id: int) -> bool:
        with self.session_manager.session_scope() as session:
            host = session.query(Host).filter(Host.id == host_id).first()
            if not host:
                return False
            session.delete(host)
            return True

    def get_hosts_by_type(self, host_type: str) -> List[Dict[str, Any]]:
        hosts = self.get_all_hosts()
        return [host for host in hosts if host_type in (host.get("host_types") or [])]

    def add_schedule(self, host_id: int, start_time: datetime, end_time: datetime,
                    status: str, appointment_id: Optional[int] = None) -> int:
        with self.session_manager.session_scope() as session:
            schedule = HostSchedule(
                host_id=host_id,
                start_time=start_time,
                end_time=end_time,
                status=status,
                appointment_id=appointment_id,
            )
            session.add(schedule)
            session.flush()
            return schedule.id

    def get_host_schedules(self, host_id: int, date: datetime) -> List[Dict[str, Any]]:
        with self.session_manager.session_scope() as session:
            start = datetime(date.year, date.month, date.day)
            end = start + timedelta(days=1)
            schedules = session.query(HostSchedule).filter(
                HostSchedule.host_id == host_id,
                HostSchedule.start_time >= start,
                HostSchedule.end_time < end,
            ).all()
            return [self._schedule_to_dict(schedule) for schedule in schedules]

    def is_host_available(self, host_id: int, start_time: datetime, end_time: datetime) -> bool:
        with self.session_manager.session_scope() as session:
            conflict = session.query(HostSchedule).filter(
                HostSchedule.host_id == host_id,
                HostSchedule.status == "busy",
                HostSchedule.start_time < end_time,
                HostSchedule.end_time > start_time,
            ).first()
            return conflict is None

    def update_schedule_status(self, schedule_id: int, status: str, appointment_id: Optional[int] = None) -> bool:
        with self.session_manager.session_scope() as session:
            schedule = session.query(HostSchedule).filter(HostSchedule.id == schedule_id).first()
            if not schedule:
                return False
            schedule.status = status
            if appointment_id is not None:
                schedule.appointment_id = appointment_id
            return True

    def delete_schedule(self, schedule_id: int) -> bool:
        with self.session_manager.session_scope() as session:
            schedule = session.query(HostSchedule).filter(HostSchedule.id == schedule_id).first()
            if not schedule:
                return False
            session.delete(schedule)
            return True

    def _host_to_dict(self, host: Host) -> Dict[str, Any]:
        return {
            "id": host.id,
            "name": host.name,
            "host_types": list(host.host_types or []),
            "specialty": host.specialty or "",
        }

    def _schedule_to_dict(self, schedule: HostSchedule) -> Dict[str, Any]:
        return {
            "id": schedule.id,
            "host_id": schedule.host_id,
            "start_time": schedule.start_time,
            "end_time": schedule.end_time,
            "status": schedule.status,
            "appointment_id": schedule.appointment_id,
        }
