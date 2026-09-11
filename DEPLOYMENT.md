# PythonAnywhereへのデプロイ手順

このアプリを [PythonAnywhere](https://www.pythonanywhere.com/) の無料プランにデプロイする手順。

## 前提

- コードに変更は不要(`db.py`のDB接続先は実行ファイルからの相対パスで解決しているため、どこに置いても動く)
- RAWG API(`api.rawg.io`)は無料プランのアウトバウンド許可リストに入っていないため、そのままだとタイトル自動補完・カバー画像取得だけが動かない(他の機能は問題なく動作する)。対処法は手順6を参照

## 1. アカウント作成

https://www.pythonanywhere.com/registration/register/beginner/ から無料アカウント(Beginner)を作成する。

## 2. コードを取得する

PythonAnywhereの「Consoles」タブから Bash コンソールを開き、GitHubリポジトリをclone する。

**リポジトリが非公開のままの場合**、通常の `git clone` は認証が求められて失敗する。以下のどちらかで対応する。

- リポジトリをGitHub上でPublicに切り替える(コードに秘密情報は含まれていないので問題ない)
- [Personal Access Token](https://github.com/settings/tokens) を発行し、`git clone https://<token>@github.com/c0c260479f/game-backlog-app.git` の形でclone する

```bash
git clone https://github.com/c0c260479f/game-backlog-app.git
cd game-backlog-app
```

## 3. 仮想環境の作成と依存パッケージのインストール

```bash
mkvirtualenv --python=/usr/bin/python3.10 game-backlog-venv
pip install -r requirements.txt
```

(`mkvirtualenv`はPythonAnywhereの仮想環境作成コマンド。以後このコンソールでは自動的にこの仮想環境に入っている)

## 4. `.env` の作成

```bash
cp .env.example .env
nano .env
```

`SECRET_KEY` はランダムな値を生成して設定する。

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

`RAWG_API_KEY` はお持ちのキーがあれば設定する(手順6が完了するまでは効果が出ない)。

## 5. Web アプリの設定(「Web」タブ)

1. 「Add a new web app」→ **Manual configuration** → Python 3.10 を選択(Flaskのボタンではなく、必ずManual configurationを選ぶこと。自動生成されるサンプルコードが上書きされてしまうため)
2. **Virtualenv** 欄に `/home/<ユーザー名>/.virtualenvs/game-backlog-venv` を設定
3. **Code** → **WSGI configuration file** を開き、中身を全て消して以下に置き換える

```python
import sys

path = "/home/<ユーザー名>/game-backlog-app"
if path not in sys.path:
    sys.path.insert(0, path)

from app import app as application
```

4. **Static files** に以下を追加(CSSが正しく配信されるようにするため)
   - URL: `/static/`
   - Directory: `/home/<ユーザー名>/game-backlog-app/static/`
5. ページ上部の緑の **Reload** ボタンを押す

これで `https://<ユーザー名>.pythonanywhere.com` でアプリが動くはず。初回アクセス時にDBのテーブルが自動生成される(`flask init-db`は不要)。

## 6. RAWG APIのアウトバウンド許可申請(任意)

RAWG連携を使いたい場合、PythonAnywhereの [Allowlist Request](https://www.pythonanywhere.com/whitelist/) ページから `api.rawg.io` の追加を申請する(「Anaconda Notebooks/PythonAnywhere Allow List Request」を選択)。承認されるまでは自動補完・カバー画像は空のまま返ってくるだけで、他の機能には影響しない。

## 7. コードを更新したいとき

```bash
cd ~/game-backlog-app
git pull
workon game-backlog-venv
pip install -r requirements.txt
```

その後「Web」タブの **Reload** ボタンを押す。

## 制限事項(無料プラン、2026年1月の規約変更後)

- 独自ドメイン不可(`<ユーザー名>.pythonanywhere.com`固定)。使うなら有料プラン($5〜/月)が必要
- 1日あたり100 CPU秒の上限あり。個人〜数人での利用なら通常は問題にならない
- **Webアプリを1ヶ月使わないと期限切れになる**(2026年1月の変更で3ヶ月→1ヶ月に短縮された)。月1回はアクセスするか、ログインして手動でreloadしておくこと
- 無料プランへの個別サポートは提供されない(困ったときはフォーラムでの相談になる)
