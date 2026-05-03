# fxbot 実装計画

本ドキュメントは fxbot の実装順序とPR分割を定義する作業計画書である。
`docs/schema.md`、`docs/metrics.md`、`docs/filters.md`、`docs/migration.md` は凍結仕様書として扱い、本ドキュメントはそれらを実装へ落とすための工程表とする。

## 原則

- `~/projects/fxbot` はアプリケーション本体のみを管理する
- `~/homeserver/docker/fxbot` は compose.yaml / .env / data のみを管理する
- サーバーにアプリケーションソースを置かない
- practice/live混同防止を最優先する
- 実発注は最後に実装する
- 各PRは小さく分割する
- 凍結仕様書はCodexに勝手に変更させない

## Phase 1: Runtime skeleton / 起動ガード / DB基盤

### 目的

売買ロジックに入る前に、起動時整合性チェック、DB初期化、heartbeat、dry-run skeletonを実装する。

### 実装対象

- `pyproject.toml`
- `src/fxbot/config.py`
- `src/fxbot/startup_checks.py`
- `src/fxbot/heartbeat.py`
- `src/fxbot/db.py`
- `src/fxbot/logger.py`
- `src/fxbot/main.py`
- `tests/`

### 必須要件

- `main.py` の最初で `run_startup_checks(client, DB_PATH)` を呼ぶ
- `ConfigError` 発生時は売買ロジックへ進まない
- DB初期化済みで記録可能な場合のみ `entry_rejections` に `reason="env_mismatch"` を記録する
- DB不整合・DB未初期化時はstderrログのみでよい
- `/tmp/fxbot_heartbeat` を更新できる
- `--check-only` モードを実装する
- `DRY_RUN=true` を前提にする
- 実発注コードは実装しない

### 完了条件

- `pytest` が通る
- `ruff check .` が通る
- `python -m fxbot.main --check-only` が実行可能
- 実発注処理が存在しない
- 凍結仕様書と矛盾しない

## Phase 2: OANDA read-only client

### 目的

OANDA APIの読み取り専用処理を実装し、起動チェックと市場データ取得の土台を作る。

### 実装対象

- `src/fxbot/oanda_client.py`
- AccountSummary取得
- openPositions取得
- candles取得
- pricing取得
- `main.py --check-only` でAccountSummaryとopenPositions確認

### 禁止事項

- 注文発注
- ポジション変更
- 取引作成

### 完了条件

- practiceの `.env` で `--check-only` が通る
- openPositionsが0でない場合は起動拒否
- テストが追加されている

## Phase 3: Filters / logging

### 目的

エントリー拒否の理由を分析可能にし、スプレッド・エクスポージャー・市場時間フィルタの土台を作る。

### 実装対象

- `src/fxbot/filters/market_hours.py`
- `src/fxbot/filters/spread.py`
- `src/fxbot/filters/exposure.py`
- `spread_history` 記録
- `entry_rejections` 記録
- HARD_SPREAD_CAP
- spreadサンプル不足時はHARD_SPREAD_CAPを返す
- exposure取得失敗時は安全側で拒否

### 禁止事項

- 個別戦略実装
- 注文発注

### 完了条件

- spread filterの単体テスト
- exposure fallbackの単体テスト
- entry_rejectionsのinsertテスト

## Phase 4: Signal / Strategy base / Confluence

### 目的

個別戦略の中身に入る前に、シグナル発行・保存・コンフルエンス判定の基盤を作る。

### 実装対象

- `src/fxbot/strategies/base.py`
- `src/fxbot/signal_bus.py`
- `src/fxbot/confluence.py`
- signalsテーブルへの記録
- 60秒以内の有効シグナル取得
- 異なるstructure_classが2種類以上ならcross-class成立
- 同一class内一致は実エントリー対象外
- buy/sell双方成立時は矛盾として拒否

### 禁止事項

- 個別戦略の売買ロジック
- 注文発注

### 完了条件

- confluence単体テスト
- 同一クラス一致がentry対象外になるテスト
- 矛盾シグナル拒否テスト

## Phase 5: Execution dry-run

### 目的

発注処理のインターフェースだけを作り、dry-runで確実に止める。

### 実装対象

- `src/fxbot/execution.py`
- `place_order(..., dry_run=True)`
- SL/TP同時発注に必要な引数設計
- エントリー直前の `is_environment_verified()` チェック

### 禁止事項

- `DRY_RUN=true` で実発注される実装
- SL/TPなしの成行注文

### 完了条件

- dry-run時に注文APIが呼ばれない
- environment未検証時は `env_mismatch` で拒否
- テストが追加されている

## Phase 6: Docker / CI / GHCR

### 目的

ローカル実装をDockerイメージ化し、GHCRへ固定タグでpushできるようにする。

### 実装対象

- `Dockerfile`
- `.github/workflows/docker.yml`
- `ghcr.io/s-furu1/fxbot:latest`
- `ghcr.io/s-furu1/fxbot:vX.Y.Z`

### 運用条件

- homeserver側では `latest` を使わない
- `compose.yaml` は固定タグを参照する

## Phase 7: Homeserver deployment

### 目的

自宅サーバー側にcompose/env/dataのみを配置し、GHCRイメージをpullして稼働させる。

### 配置先

`~/homeserver/docker/fxbot/`

### 構成

- `compose.yaml`
- `.env.example`
- `.env.practice`
- `.env.live`
- `.env -> .env.practice`
- `scripts/switch-env.sh`
- `data/practice/`
- `data/live/`

### 起動方法

必ず以下を使う。

```bash
./scripts/switch-env.sh practice
./scripts/switch-env.sh live
```
素の `docker compose up -d` は使用しない。

## Phase 8: API-enabled dry-run / practice observation

### 目的

APIトークン取得後、実発注に進む前に、API疎通・DB記録・heartbeat・signals・entry_rejections・baseline比較の土台が正常に動くことを確認する。

OANDA JapanのREST API利用条件として、NYサーバー口座残高25万円以上が必要となるため、初期入金目安は30万円とする。

ただし、30万円全額をリスク資金とは扱わない。

```text
30万円 = API利用条件維持のための拘束残高25万円 + 実験バッファ5万円
```

25万円はAPI維持ラインとして扱い、初期段階の損失許容枠は差額部分を中心に考える。

### Phase 8A: API-enabled dry-run

#### 条件

- OANDA REST APIトークン取得済み
- OANDA Account ID取得済み
- `.env.practice` またはローカル `.env` に必要値を設定済み
- `DRY_RUN=true`
- 実発注なし
- `python -m fxbot.main --check-only` が設定不整合なしで通る
- openPositions が0である

#### 確認項目

- AccountSummary が取得できる
- openPositions が取得できる
- DB初期化が成功する
- heartbeat が更新される
- healthcheck が healthy になる
- `spread_history` が記録される
- `signals` が記録される
- `entry_rejections` が記録される
- `env_mismatch` が発生していない
- `data/practice/trades.db` のみに書き込まれる
- `.env` / `.env.practice` / `.env.live` / DB がGit管理対象になっていない

#### 期間

最初の1〜3日は `DRY_RUN=true` のまま稼働させる。

この期間では、発注成績ではなく、以下を確認する。

```text
- API疎通
- ログ記録
- heartbeat
- healthcheck
- signals発生頻度
- entry_rejections.reason分布
- spread_historyの蓄積
- confluence発生率
```

### Phase 8B: 2週間評価サイクル

#### 標準サイクル

```text
Day 1〜7   : dry-run / practice観測、データ蓄積に専念
Day 8〜11  : 継続稼働、サンプル数監視
Day 12     : 中間分析（n=100〜150想定）
Day 13     : 判定
Day 14     : 次サイクルへのアクション決定
```

#### 評価対象

- シグナル発生数
- コンフルエンス成立数
- entry_rejections.reason分布
- spread_too_high拒否率
- intraclass_only発生率
- conflicting_signals発生率
- baseline_randomとの差分
- ΔE[R]
- ドローダウン
- 連敗分布
- 戦略別シグナル発生数
- 時間帯別シグナル発生数

#### 次サイクルへの判断

Day 13〜14で以下を判断する。

```text
継続:
  - ログ品質に問題がない
  - シグナルが十分に発生している
  - 拒否理由分布が異常でない
  - baseline_randomに対して明確な劣後がない

改善:
  - spread_too_high が過剰
  - 特定戦略が0シグナル
  - confluenceが極端に少ない
  - conflicting_signalsが多すぎる
  - entry_rejectionsが特定理由に偏っている

停止 / 見直し:
  - 早期撤退条件に該当
  - API条件維持ラインを脅かす損失が発生
  - 実装バグが疑われるログ欠損
```

### 早期撤退条件

以下のいずれかが発生した場合、Day 14を待たずに分析・改善へ移行する。

```text
Day 3以降かつ n>=30:
  - ΔE[R] <= -0.5R

Day 3以降:
  - 連敗が15回を超える
  - 同一エラーによるエントリー失敗が10回連続
  - 実装済み戦略の半数以上が0シグナル
  - spread_too_high による拒否率が80%超
```

早期撤退条件は、損失回避だけでなく、実装バグ・市場条件不一致・フィルタ過剰・シグナル欠落を早期に検出するためのものである。

### 次段階

最低1〜2日dry-runでログ品質を確認し、その後2週間サイクルで評価する。

practice発注またはlive最小ロット運用へ進む場合は、以下を満たすこと。

- openPositions が0
- `env_mismatch` が発生していない
- heartbeat が安定している
- DB記録が欠損していない
- signals / entry_rejections / spread_history が蓄積されている
- API維持ライン25万円を下回らない資金管理になっている

## Phase 9: Live migration

### 条件

- practiceで最低1週間稼働
- live dry-runを最低1日実施
- live口座に未決済ポジションがない
- `.env.live` の `EXPECTED_*` が一致している
- `data/live/trades.db` にpractice履歴が混ざっていない

### 起動

```bash
./scripts/switch-env.sh live
```

live切替時は確認文字列 `I CONFIRM FXBOT LIVE` を入力する。
