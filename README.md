# ゲームバックログ管理アプリ

積みゲー・プレイ中・クリア済みのゲームを記録するための、個人用のシンプルなWebアプリ。
Flask + SQLite で作ったMVP版です。

## 機能

- ゲームの登録(タイトル・ステータス・評価1〜5・メモ)
- ステータス(積みゲー/プレイ中/クリア済み)ごとの絞り込み表示
- 編集・削除

## 必要なもの

- Python 3.9以上

## セットアップ

```bash
# 1. このフォルダに移動
cd game-backlog-app

# 2. (推奨) 仮想環境を作る
python3 -m venv venv
source venv/bin/activate      # Windowsの場合: venv\Scripts\activate

# 3. 依存パッケージをインストール
pip install -r requirements.txt

# 4. データベースを初期化(初回のみ。games.db が作られる)
flask --app app init-db
```

## 起動

```bash
flask --app app run --debug
```

起動したら http://127.0.0.1:5000 をブラウザで開く。

## フォルダ構成

```
game-backlog-app/
├── app.py            # Flaskアプリ本体(ルーティング・保存処理)
├── db.py             # DB接続まわりのヘルパー
├── schema.sql         # テーブル定義
├── requirements.txt
├── templates/
│   ├── base.html
│   └── games/
│       ├── list.html  # 一覧ページ
│       └── form.html  # 追加・編集フォーム
└── static/css/style.css
```

## 今後の拡張アイデア

- RAWG API と連携してタイトル検索・カバー画像自動取得
- プレイ時間の記録
- ソート機能(評価順・登録日順)
- 検索ボックス

## 注意

`games.db` は `flask init-db` を実行すると**中身が空の状態で作り直される**(既存データは消える)。
再実行する時は気をつけて。
