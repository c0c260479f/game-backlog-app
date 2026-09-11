import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as app_module


@pytest.fixture
def app():
    """一時DBファイルを使う、本番のgames.dbとは完全に分離されたテスト用アプリ"""
    db_fd, db_path = tempfile.mkstemp()

    flask_app = app_module.create_app(
        {
            "TESTING": True,
            "DATABASE": db_path,
            "WTF_CSRF_ENABLED": True,
        }
    )

    yield flask_app

    os.close(db_fd)
    os.unlink(db_path)


@pytest.fixture
def client(app):
    return app.test_client()
