from typing import List, Dict, Any, Optional
from ..base.interfaces import BaseGameRepository
from ..base.session_manager import SessionManager
from ..models import Game


class GameRepository(BaseGameRepository):
    """桌游目录数据访问对象"""

    def __init__(self, session_manager: SessionManager):
        self.session_manager = session_manager

    def add_game(self, name: str, min_players: int, max_players: int, duration_min: int,
                 needs_host: bool, allowed_host_types: List[str]) -> int:
        with self.session_manager.session_scope() as session:
            game = Game(
                name=name,
                min_players=min_players,
                max_players=max_players,
                duration_min=duration_min,
                needs_host=needs_host,
                allowed_host_types=allowed_host_types,
            )
            session.add(game)
            session.flush()
            return game.id

    def get_all_games(self) -> List[Dict[str, Any]]:
        with self.session_manager.session_scope() as session:
            games = session.query(Game).order_by(Game.id).all()
            return [self._game_to_dict(game) for game in games]

    def get_game_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        with self.session_manager.session_scope() as session:
            game = session.query(Game).filter(Game.name == name).first()
            return self._game_to_dict(game) if game else None

    def _game_to_dict(self, game: Game) -> Dict[str, Any]:
        return {
            "id": game.id,
            "name": game.name,
            "min_players": game.min_players,
            "max_players": game.max_players,
            "duration_min": game.duration_min,
            "needs_host": bool(game.needs_host),
            "allowed_host_types": list(game.allowed_host_types or []),
        }
