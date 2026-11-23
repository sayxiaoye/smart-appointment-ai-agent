from typing import Dict, Any, List, Optional
from db.db_router import DatabaseRouter
from config.constants import HOST_TYPE_LABELS, HostType, host_type_label
import logging

logger = logging.getLogger(__name__)


class GameCatalogService:
    """桌游目录：种子数据、名称解析、人数与主持类型校验"""

    def __init__(self, db_path: str = "sqlite:///data/smart_appointment.db"):
        self.db = DatabaseRouter(db_path)
        self.default_games = [
            {
                "name": "血染钟楼",
                "min_players": 5,
                "max_players": 12,
                "duration_min": 90,
                "needs_host": True,
                "allowed_host_types": ["pro_host"],
            },
            {
                "name": "卡卡颂",
                "min_players": 2,
                "max_players": 5,
                "duration_min": 45,
                "needs_host": False,
                "allowed_host_types": ["self_play", "staff_guide"],
            },
            {
                "name": "晴日岛",
                "min_players": 2,
                "max_players": 4,
                "duration_min": 60,
                "needs_host": False,
                "allowed_host_types": ["self_play", "staff_guide", "pro_host"],
            },
            {
                "name": "阿瓦隆",
                "min_players": 5,
                "max_players": 10,
                "duration_min": 45,
                "needs_host": True,
                "allowed_host_types": ["pro_host", "staff_guide"],
            },
            {
                "name": "璀璨宝石",
                "min_players": 2,
                "max_players": 4,
                "duration_min": 30,
                "needs_host": False,
                "allowed_host_types": ["self_play", "staff_guide"],
            },
            {
                "name": "恐龙小镇",
                "min_players": 2,
                "max_players": 5,
                "duration_min": 40,
                "needs_host": True,
                "allowed_host_types": ["kids_host"],
            },
        ]

    def initialize_default_games(self) -> bool:
        try:
            existing = self.db.games.get_all_games()
            if existing:
                logger.info("数据库中已有 %s 款游戏，跳过初始化", len(existing))
                return True
            for game in self.default_games:
                self.db.games.add_game(**game)
            logger.info("游戏目录初始化完成，共 %s 款", len(self.default_games))
            return True
        except Exception as exc:
            logger.error("游戏目录初始化失败: %s", exc)
            return False

    def list_games(self) -> List[Dict[str, Any]]:
        self.initialize_default_games()
        return self.db.games.get_all_games()

    def list_game_names(self) -> List[str]:
        return [game["name"] for game in self.list_games()]

    def resolve_game(self, name: str) -> Optional[Dict[str, Any]]:
        """按全名或包含关系匹配目录中的一款游戏。"""
        if not name or str(name).strip() in ("未知", "无"):
            return None
        cleaned = str(name).strip().strip("《》\"' ")
        if len(cleaned) < 2:
            return None
        games = self.list_games()
        for game in games:
            if game["name"] == cleaned:
                return game
        matches = [game for game in games if cleaned in game["name"] or game["name"] in cleaned]
        if len(matches) == 1:
            return matches[0]
        return None

    def validate_selection(self, game: Dict[str, Any], player_count: Optional[int], host_type: Optional[str]) -> Dict[str, Any]:
        """校验人数区间，以及主持类型是否被该游戏允许。"""
        invalid_fields: List[str] = []
        messages: List[str] = []
        allowed = game.get("allowed_host_types") or []
        allowed_labels = "、".join(host_type_label(item) for item in allowed)

        if player_count is not None:
            if player_count < game["min_players"] or player_count > game["max_players"]:
                invalid_fields.append("player_count")
                messages.append(
                    f"《{game['name']}》适合 {game['min_players']}–{game['max_players']} 人，"
                    f"当前 {player_count} 人不在范围内。"
                )

        if host_type:
            if host_type not in allowed:
                invalid_fields.append("host_type")
                if game.get("needs_host") and host_type == HostType.SELF_PLAY.value:
                    messages.append(f"《{game['name']}》需要有人带玩，不能自助。可选：{allowed_labels}。")
                else:
                    messages.append(f"《{game['name']}》不支持这种主持方式，可选：{allowed_labels}。")
            elif game.get("needs_host") and host_type == HostType.SELF_PLAY.value:
                invalid_fields.append("host_type")
                messages.append(f"《{game['name']}》需要有人带玩，不能自助。可选：{allowed_labels}。")

        return {
            "valid": not invalid_fields,
            "invalid_fields": invalid_fields,
            "clarify_question": "".join(messages),
        }

    def allowed_labels(self, game: Dict[str, Any]) -> str:
        return "、".join(HOST_TYPE_LABELS.get(item, item) for item in (game.get("allowed_host_types") or []))
