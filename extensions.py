"""app.py・blueprints間で使い回すFlask拡張のインスタンス(循環importを避けるため独立させている)。"""

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
