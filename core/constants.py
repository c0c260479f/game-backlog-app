"""表示ラベル・並び替え条件・外部API設定など、複数のBlueprintで参照する定数。"""

import os

RAWG_API_KEY = os.environ.get("RAWG_API_KEY")
RAWG_SEARCH_URL = "https://api.rawg.io/api/games"

STATUS_LABELS = {
    "backlog": "積みゲー",
    "playing": "プレイ中",
    "completed": "クリア済み",
}
VALID_STATUSES = set(STATUS_LABELS.keys())

SORT_OPTIONS = {
    "updated_desc": ("更新日が新しい順", "g.updated_at DESC, g.id DESC"),
    "created_desc": ("登録日が新しい順", "g.created_at DESC, g.id DESC"),
    "rating_desc": ("評価が高い順", "g.rating IS NULL, g.rating DESC, g.id DESC"),
    "title_asc": ("タイトル順", "g.title COLLATE NOCASE ASC, g.id ASC"),
    "playtime_desc": ("プレイ時間が長い順", "total_minutes DESC, g.id DESC"),
}
DEFAULT_SORT = "updated_desc"

ACTIVITY_KIND_LABELS = {
    "added": "を積みゲーに追加したよ",
    "completed": "をクリアしたよ",
    "rated": "を評価したよ",
}

DIRECTORY_SORT_OPTIONS = {
    "new": ("新着順", "u.created_at DESC, u.id DESC"),
    "popular": ("人気順", "follower_count DESC, u.id DESC"),
    "name": ("名前順", "u.username COLLATE NOCASE ASC"),
}
DEFAULT_DIRECTORY_SORT = "new"

MEMO_MAX_LENGTH = 2000


def format_minutes(total_minutes):
    """分数を「12時間30分」のような表示用文字列に変換する"""
    if not total_minutes:
        return None
    hours, minutes = divmod(total_minutes, 60)
    if hours and minutes:
        return f"{hours}時間{minutes}分"
    if hours:
        return f"{hours}時間"
    return f"{minutes}分"
