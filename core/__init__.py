"""複数のBlueprintで共有する定数とヘルパー関数。

このパッケージの中身はconstants.py/games.py/social.pyに分かれているが、
呼び出し側(blueprints/*)は今まで通り `import core` して `core.xxx` の形で
使えるように、ここで全部まとめて再エクスポートしている。
"""

from .constants import (
    ACTIVITY_KIND_LABELS,
    DEFAULT_DIRECTORY_SORT,
    DEFAULT_SORT,
    DIRECTORY_SORT_OPTIONS,
    RAWG_API_KEY,
    RAWG_SEARCH_URL,
    SORT_OPTIONS,
    STATUS_LABELS,
    VALID_STATUSES,
    format_minutes,
)
from .games import fetch_games, save_game, save_session
from .social import activity_visible, is_blocked, log_activity, notify

__all__ = [
    "ACTIVITY_KIND_LABELS",
    "DEFAULT_DIRECTORY_SORT",
    "DEFAULT_SORT",
    "DIRECTORY_SORT_OPTIONS",
    "RAWG_API_KEY",
    "RAWG_SEARCH_URL",
    "SORT_OPTIONS",
    "STATUS_LABELS",
    "VALID_STATUSES",
    "format_minutes",
    "fetch_games",
    "save_game",
    "save_session",
    "activity_visible",
    "is_blocked",
    "log_activity",
    "notify",
]
