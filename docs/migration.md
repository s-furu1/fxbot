# 環境移行仕様（凍結版 v1）

本ドキュメントは fxbot のpractice → live移行を含む環境切替の仕様を確定するもの。
移行ミスは金銭的損失に直結するため、**手順ではなくガード（自動検証）で主要な混同事故を構造的に抑止する設計**とする。

---

## 設計原則

1. **`.env` は symlink 専用、本体編集禁止**
2. **環境切替は `scripts/switch-env.sh` 経由のみ許可**
3. **検証は宣言値の一致で行い、推定（残高ベース等）は使わない**
4. **検証失敗時に現在の稼働環境を壊さない順序で操作する**
5. **DBは環境ごとに物理分離する**（混在は評価指標を破壊するため）

practice/live混同、DB混在、誤った口座IDでの起動といった主要事故は、手順依存ではなく自動検証によって構造的に抑止する。ただし、APIキー自体の取り違え、OANDA側の権限設定ミス、手動決済忘れなど、外部操作に起因する事故はゼロにはできない。

---

## ファイル構成

```
~/homeserver/docker/fxbot/
├── compose.yaml
├── .env -> .env.practice         # symlink（本体編集禁止）
├── .env.practice                 # practice用環境変数
├── .env.live                     # live用環境変数
├── .env.example
└── data/
    ├── practice/
    │   └── trades.db             # practice用DB
    └── live/
        └── trades.db             # live用DB
```

`.env.practice` と `.env.live` の内容は `OANDA_API_KEY` / `OANDA_ACCOUNT_ID` / `OANDA_ENV` / `FXBOT_MODE` / `FXBOT_EXPECTED_*` がそれぞれ完全に分離される。

---

## .env ファイルの仕様

### 必須キー一覧

| キー | 用途 |
|------|------|
| `FXBOT_MODE` | アプリ動作モード `practice` / `live` |
| `OANDA_ENV` | OANDA SDKに渡す環境名 `practice` / `live` |
| `OANDA_API_KEY` | 該当環境のAPIキー |
| `OANDA_ACCOUNT_ID` | 該当環境のアカウントID |
| `FXBOT_EXPECTED_MODE` | 期待される動作モード（整合性チェック用） |
| `FXBOT_EXPECTED_ACCOUNT_ID` | 期待されるアカウントID（整合性チェック用） |
| `FXBOT_DB_ENV` | 使用するDBディレクトリ名（`practice` / `live`） |
| `SLACK_WEBHOOK_URL` | Slack通知URL |
| `TZ` | コンテナタイムゾーン（**UTC固定**） |
| `LOG_LEVEL` | ログレベル `INFO` / `DEBUG` 等 |

### .env.practice の例

```
FXBOT_MODE=practice
OANDA_ENV=practice
OANDA_API_KEY=xxxxxxxxxxxxxxxxxxxx-xxxxxxxxxxxxxxxxxxxx
OANDA_ACCOUNT_ID=101-001-12345678-001

FXBOT_EXPECTED_MODE=practice
FXBOT_EXPECTED_ACCOUNT_ID=101-001-12345678-001
FXBOT_DB_ENV=practice

SLACK_WEBHOOK_URL=https://hooks.slack.com/services/xxxxx
TZ=UTC
LOG_LEVEL=INFO
```

### .env.live の例

```
FXBOT_MODE=live
OANDA_ENV=live
OANDA_API_KEY=yyyyyyyyyyyyyyyyyyyy-yyyyyyyyyyyyyyyyyyyy
OANDA_ACCOUNT_ID=001-001-87654321-001

FXBOT_EXPECTED_MODE=live
FXBOT_EXPECTED_ACCOUNT_ID=001-001-87654321-001
FXBOT_DB_ENV=live

SLACK_WEBHOOK_URL=https://hooks.slack.com/services/yyyyy
TZ=UTC
LOG_LEVEL=INFO
```

`EXPECTED_*` と `OANDA_*` は同じ値を冗長に記載する。これは**手動編集ミスの検出**を目的とした設計で、自動取得していると検証として機能しない。

### .envファイルのフォーマット制限

`scripts/switch-env.sh` は `.env.{mode}` を `KEY=value` 形式として読み取る。安全性と単純性を優先し、以下の形式に固定する。

許可：

```env
KEY=value
```

禁止：

```env
export KEY=value
KEY = value
KEY="value"
KEY=value # comment
```

値に空白・引用符・インラインコメントを含めない。`.env` は常に symlink とし、直接編集しない。

---

## switch-env.sh の処理順序

`scripts/switch-env.sh` は環境切替の唯一の正規ルート。
**検証失敗時に現在の稼働環境を壊さない順序**で操作する。

```
1. 引数 mode を検証（practice | live のみ許可）
2. .env.{mode} の存在確認
3. .env.{mode} を一時読み込み（symlinkは触らない）
4. EXPECTED_MODE と OANDA_ENV の整合性検証
5. EXPECTED_ACCOUNT_ID と OANDA_ACCOUNT_ID の整合性検証
6. OANDA APIで対象口座の未決済ポジション 0 を確認
7. data/{mode}/ ディレクトリを作成
8. liveの場合のみ確認文字列「I CONFIRM FXBOT LIVE」入力を要求
9. .env symlink を .env.{mode} に張り替え
10. FXBOT_MODE={mode} export して docker compose up -d
```

### live切替時の確認プロンプト

操作対象を明示してから入力させる：

```
Switching environment to LIVE.

current env  : .env.practice
target env   : .env.live
db dir       : ./data/live
account id   : ***-1234

Type 'I CONFIRM FXBOT LIVE' to continue:
```

---

## 起動時整合性チェック（startup_checks.py）

botの`main()`の最初で必ず実行。失敗時は `ConfigError` を raise し、起動を中止する。

### 検証項目

```
1. 必須環境変数が全て設定されているか
2. FXBOT_MODE が practice | live のいずれか
3. FXBOT_EXPECTED_MODE == OANDA_ENV
4. FXBOT_EXPECTED_ACCOUNT_ID == OANDA_ACCOUNT_ID
5. FXBOT_DB_ENV == FXBOT_MODE
6. OANDA APIで AccountSummary 取得成功
7. account.id == FXBOT_EXPECTED_ACCOUNT_ID
8. 該当口座に未決済ポジションが存在しない
9. DBファイルパスが /data/trades.db で、適切なディレクトリにマウントされている
```

### 失敗時の動作

- `startup_checks.py` は `ConfigError` を raise してプロセスを終了させる
- Slack通知とDB記録は `main.py` 側の責務とする
- `main.py` は `ConfigError` をcatchし、Slack に「環境整合性チェック失敗」と理由を通知する
- DB初期化済みで記録可能な場合のみ、`entry_rejections` に `reason="env_mismatch"` で記録する
- DBパス不整合・DB未作成・マウント失敗時はDB記録不能であるため、Slack通知とstderrログのみとする
- Docker の restart policy が `unless-stopped` のため、設定が正しくならない限り再起動ループする

これは意図した動作。**設定不整合のまま稼働させない**ことが目的。

### 既存ポジションの扱い

v1では、起動時に対象口座の未決済ポジションが1つでもある場合は起動拒否する。bot再起動時に既存ポジションを引き継いで管理する運用は非対応。既存ポジションはOANDA管理画面で手動決済してから起動する。

---

## 定期整合性チェック

### 間隔：1時間ごと

メインループから別スレッドで実行。

### 検証項目

```
1. OANDA APIで AccountSummary 取得成功
2. account.id == FXBOT_EXPECTED_ACCOUNT_ID（変わっていないこと）
3. メモリ上の verified_mode == 起動時の検証済みモード
```

### 失敗時の動作

- **エントリー直前用フラグ `verified` を False に倒す**
- Slack に異常通知
- 次のエントリー判定時に拒否される（`reason="env_mismatch"`）
- 自動復旧は行わない（手動対応を要求）

### 通知ポリシー

正常時はSlack通知しない。**異常時のみ通知**することで通知ノイズを抑える。

---

## エントリー直前のメモリ確認

エントリー判定の最初で、メモリ上の `verified` フラグのみ確認する。
**API再取得は行わない**（レイテンシ悪化を避ける）。

```python
def can_enter(...):
    if not verification_state.verified:
        log_rejection(pair, direction, "env_mismatch")
        return False, "env_mismatch"
    # ... 既存のフィルタチェック
```

---

## 移行手順（practice → live）

### 前提条件

- live口座開設・APIキー取得済み
- live口座への入金完了
- `.env.live` 作成済み・全項目正しく記入済み

### 手順

```bash
cd ~/homeserver/docker/fxbot

# 1. 現在のpractice運用を停止
docker compose stop fxbot

# 2. practice側の未決済ポジションが0であることを確認
#    （switch-env.sh内でも確認するが、目視でも確認）

# 3. 環境切替（自動でlive側の整合性検証が走る）
./scripts/switch-env.sh live

# プロンプト表示後、I CONFIRM FXBOT LIVE を入力
```

### switch-env.sh が自動で行うこと

- `.env.live` を一時読み込みして整合性検証
- live口座の未決済ポジション0を確認
- 確認文字列入力を要求
- `.env` symlink を `.env.live` に張り替え
- `FXBOT_MODE=live docker compose up -d` でコンテナ起動

### 起動後の確認

```bash
# Slackに「FX bot started. Mode: live」が届くことを確認
docker compose logs -f fxbot
```

---

## 移行手順（live → practice）

緊急時の戻し手順。確認文字列なしで切り替え可能。

```bash
cd ~/homeserver/docker/fxbot

# 1. live運用を停止
docker compose stop fxbot

# 2. live側の未決済ポジションを手動で全決済（OANDA管理画面）

# 3. practiceに戻す
./scripts/switch-env.sh practice
```

---

## 緊急停止

bot稼働中に異常を検知した場合、または手動でポジション操作が必要な場合：

```bash
cd ~/homeserver/docker/fxbot

# stop（down ではない）
# down はネットワーク・コンテナ再作成を伴うため、緊急停止には不適切
docker compose stop fxbot
```

その後、必要に応じてOANDA管理画面で手動決済する。

**重要：** 本実装ではエントリー時に SL/TP を OANDA 側に同時発注している。
そのため、コンテナ停止後もOANDA側でSL/TP決済は機能する。
ただし**早期決済や条件付きエグジットの判断はbotに依存しない**ため、長時間停止する場合は手動でポジションを閉じることを推奨。

---

## バックアップ

### バックアップ取得

```bash
# practice側
cp ~/homeserver/docker/fxbot/data/practice/trades.db \
   ~/backup/fxbot/practice_$(date +%Y%m%d_%H%M%S).db

# live側
cp ~/homeserver/docker/fxbot/data/live/trades.db \
   ~/backup/fxbot/live_$(date +%Y%m%d_%H%M%S).db
```

ホームサーバー全体の定期バックアップ（`scripts/backup.sh`）に組み込む。

### 復元手順

```bash
cd ~/homeserver/docker/fxbot

# 1. 停止
docker compose stop fxbot

# 2. 該当環境のDB差し替え（practice の例）
cp ~/backup/fxbot/practice_20260315_120000.db ./data/practice/trades.db

# 3. 起動。素の docker compose up -d は使わない
./scripts/switch-env.sh practice
docker compose logs -f fxbot
```

---

## 観測

### entry_rejections による移行運用の監視

`entry_rejections` テーブルに `reason="env_mismatch"` のレコードが発生した場合は、環境設定に問題がある兆候。
週次レポートで以下を集計する：

```sql
SELECT reason, COUNT(*) AS n
FROM entry_rejections
WHERE timestamp >= datetime('now', '-7 days')
GROUP BY reason
ORDER BY n DESC;
```

`env_mismatch` が頻発している場合は、`.env` ファイルの整合性を再確認する。

---

## 関連ドキュメント

- [`docs/schema.md`](./schema.md) v1.1：`entry_rejections` テーブルのDDLと拒否理由コード
- [`docs/filters.md`](./filters.md)：フィルタ拒否理由の定義
- [`scripts/switch-env.sh`](../scripts/switch-env.sh)：環境切替スクリプト本体
- [`src/startup_checks.py`](../src/startup_checks.py)：起動時整合性チェック実装
