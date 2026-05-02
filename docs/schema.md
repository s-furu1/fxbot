# ログスキーマ仕様（凍結版 v1.2）

本ドキュメントは fxbot の SQLite データベース（`/data/trades.db`）における全テーブルのスキーマを確定するもの。
**実装はこの仕様に厳密に従うこと**。本仕様の変更は破壊的変更として扱い、マイグレーション手順を別途定義する。

## 改訂履歴

| バージョン | 変更内容 |
|----------|---------|
| v1.0 | 初版凍結（signals / opens / closes / latency / position_tracking / baseline_* / currency_exposure_snapshots / spread_history） |
| v1.1 | `entry_rejections` テーブルを正式追加（フィルタ拒否理由の分析） |
| v1.2 | `entry_rejections.reason` に `conflicting_signals` を追加 |

---

## 設計原則

1. **実エントリーと仮想エントリーは物理的に分離する**（`opens` と `baseline_*` を混在させない）
2. **時刻は全てISO 8601形式・UTC で保存する**（タイムゾーン情報を含む）
3. **層化が必要な値は連続値で保存し、層化は後段で動的に行う**（`atr_ratio`等）
4. **MFE/MAEは自前トラッキングで取得する**（API依存を排除し再現性を担保）
5. **すべての金額系カラムは口座通貨建てで統一する**（換算済みの値）

---

## テーブル一覧

| テーブル | 役割 | 1日あたりの想定行数 |
|---------|------|----------------|
| `signals` | 全戦略のシグナル発行履歴（採用/非採用問わず） | 100〜500 |
| `opens` | 実エントリー（構造クラス間60秒同期成立時） | 5〜20 |
| `closes` | 決済とMFE/MAE | 5〜20（opens相当） |
| `latency` | シグナル発火→約定の遅延 | opens相当 |
| `position_tracking` | 保有中ポジションの価格モニタリング（MFE/MAE算出用） | opensごとに数十行 |
| `baseline_solo` | 単独シグナルの仮想エントリー | 100〜500 |
| `baseline_intraclass` | 同一クラス内一致の仮想エントリー | 5〜30 |
| `baseline_random` | 条件付きランダムベースライン | opens相当 |
| `currency_exposure_snapshots` | 通貨単位のネットエクスポージャー時系列 | エントリー判定ごとに記録 |
| `spread_history` | スプレッド時系列（フィルタ閾値の動的計算用） | 1分ごと×ペア数 |
| `entry_rejections` | フィルタによるエントリー拒否の記録（v1.1追加） | 拒否ごと |

---

## DDL

````sql
-- ============================================================
-- signals: 全戦略のシグナル発行履歴
-- ============================================================
CREATE TABLE IF NOT EXISTS signals (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       TEXT    NOT NULL,    -- ISO 8601 UTC
    pair            TEXT    NOT NULL,    -- 例: "EUR_USD"
    source          TEXT    NOT NULL,    -- 戦略名 例: "tokyo_fixing"
    structure_class TEXT    NOT NULL,    -- "volatility" | "flow" | "reversion"
    direction       TEXT    NOT NULL,    -- "buy" | "sell"
    price           REAL    NOT NULL,    -- 発行時のmid価格
    atr             REAL    NOT NULL,    -- 発行時のATR(14)
    atr_ratio       REAL    NOT NULL,    -- atr / atr_50bar_mean（連続値）
    spread          REAL    NOT NULL     -- 発行時のスプレッド（quote通貨建て）
);
CREATE INDEX IF NOT EXISTS idx_signals_pair_ts ON signals(pair, timestamp);
CREATE INDEX IF NOT EXISTS idx_signals_source ON signals(source);

-- ============================================================
-- opens: 実エントリー（cross-class confluence成立時のみ）
-- ============================================================
CREATE TABLE IF NOT EXISTS opens (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_id            TEXT    NOT NULL UNIQUE,
    pair                TEXT    NOT NULL,
    direction           TEXT    NOT NULL,
    units               INTEGER NOT NULL,
    first_signal_time   TEXT    NOT NULL,
    last_signal_time    TEXT    NOT NULL,
    entry_time          TEXT    NOT NULL,
    entry_price         REAL    NOT NULL,
    atr                 REAL    NOT NULL,
    atr_ratio           REAL    NOT NULL,
    spread              REAL    NOT NULL,
    risk_ratio          REAL    NOT NULL,
    risk_amount         REAL    NOT NULL,
    sl_price            REAL    NOT NULL,
    tp_price            REAL    NOT NULL,
    confluence_type     TEXT    NOT NULL,
    signal_count        INTEGER NOT NULL,
    classes             TEXT    NOT NULL,
    strategies          TEXT    NOT NULL,
    response            TEXT
);
CREATE INDEX IF NOT EXISTS idx_opens_trade_id ON opens(trade_id);
CREATE INDEX IF NOT EXISTS idx_opens_entry_time ON opens(entry_time);

-- ============================================================
-- closes: 決済とMFE/MAE
-- ============================================================
CREATE TABLE IF NOT EXISTS closes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_id        TEXT    NOT NULL UNIQUE,
    exit_time       TEXT    NOT NULL,
    exit_price      REAL    NOT NULL,
    exit_reason     TEXT    NOT NULL,
    pnl             REAL    NOT NULL,
    actual_rr       REAL    NOT NULL,
    mfe             REAL    NOT NULL,
    mae             REAL    NOT NULL,
    holding_seconds INTEGER NOT NULL,
    FOREIGN KEY (trade_id) REFERENCES opens(trade_id)
);
CREATE INDEX IF NOT EXISTS idx_closes_trade_id ON closes(trade_id);
CREATE INDEX IF NOT EXISTS idx_closes_exit_time ON closes(exit_time);

-- ============================================================
-- latency: シグナル発火→約定の遅延
-- ============================================================
CREATE TABLE IF NOT EXISTS latency (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_id                 TEXT    NOT NULL UNIQUE,
    confluence_to_fill_ms    INTEGER NOT NULL,
    first_signal_to_fill_ms  INTEGER NOT NULL,
    FOREIGN KEY (trade_id) REFERENCES opens(trade_id)
);

-- ============================================================
-- position_tracking: 保有中ポジションの価格モニタリング
-- ============================================================
CREATE TABLE IF NOT EXISTS position_tracking (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_id    TEXT    NOT NULL,
    timestamp   TEXT    NOT NULL,
    bid         REAL    NOT NULL,
    ask         REAL    NOT NULL,
    mid         REAL    NOT NULL,
    FOREIGN KEY (trade_id) REFERENCES opens(trade_id)
);
CREATE INDEX IF NOT EXISTS idx_position_tracking_trade_id ON position_tracking(trade_id);
CREATE INDEX IF NOT EXISTS idx_position_tracking_ts ON position_tracking(timestamp);

-- ============================================================
-- baseline_solo: 単独シグナル仮想エントリー
-- ============================================================
CREATE TABLE IF NOT EXISTS baseline_solo (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       TEXT    NOT NULL,
    pair            TEXT    NOT NULL,
    source          TEXT    NOT NULL,
    structure_class TEXT    NOT NULL,
    direction       TEXT    NOT NULL,
    price           REAL    NOT NULL,
    atr             REAL    NOT NULL,
    atr_ratio       REAL    NOT NULL,
    spread          REAL    NOT NULL,
    virtual_exit_time   TEXT,
    virtual_exit_price  REAL,
    virtual_pnl         REAL,
    virtual_rr          REAL,
    virtual_mfe         REAL,
    virtual_mae         REAL,
    virtual_exit_reason TEXT
);
CREATE INDEX IF NOT EXISTS idx_baseline_solo_ts ON baseline_solo(timestamp);

-- ============================================================
-- baseline_intraclass: 同一クラス内一致の仮想エントリー
-- ============================================================
CREATE TABLE IF NOT EXISTS baseline_intraclass (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       TEXT    NOT NULL,
    pair            TEXT    NOT NULL,
    structure_class TEXT    NOT NULL,
    direction       TEXT    NOT NULL,
    strategies      TEXT    NOT NULL,
    price           REAL    NOT NULL,
    atr             REAL    NOT NULL,
    atr_ratio       REAL    NOT NULL,
    spread          REAL    NOT NULL,
    virtual_exit_time   TEXT,
    virtual_exit_price  REAL,
    virtual_pnl         REAL,
    virtual_rr          REAL,
    virtual_mfe         REAL,
    virtual_mae         REAL,
    virtual_exit_reason TEXT
);
CREATE INDEX IF NOT EXISTS idx_baseline_intraclass_ts ON baseline_intraclass(timestamp);

-- ============================================================
-- baseline_random: 条件付きランダムベースライン
-- ============================================================
CREATE TABLE IF NOT EXISTS baseline_random (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       TEXT    NOT NULL,
    pair            TEXT    NOT NULL,
    direction       TEXT    NOT NULL,
    price           REAL    NOT NULL,
    atr             REAL    NOT NULL,
    atr_ratio       REAL    NOT NULL,
    spread          REAL    NOT NULL,
    virtual_exit_time   TEXT,
    virtual_exit_price  REAL,
    virtual_pnl         REAL,
    virtual_rr          REAL,
    virtual_mfe         REAL,
    virtual_mae         REAL,
    virtual_exit_reason TEXT,
    paired_trade_id     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_baseline_random_ts ON baseline_random(timestamp);
CREATE INDEX IF NOT EXISTS idx_baseline_random_paired ON baseline_random(paired_trade_id);

-- ============================================================
-- currency_exposure_snapshots: 通貨単位ネットエクスポージャー時系列
-- ============================================================
CREATE TABLE IF NOT EXISTS currency_exposure_snapshots (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   TEXT    NOT NULL,
    currency    TEXT    NOT NULL,
    net_ratio   REAL    NOT NULL,
    equity      REAL    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_currency_exposure_ts ON currency_exposure_snapshots(timestamp);

-- ============================================================
-- spread_history: スプレッド時系列
-- ============================================================
CREATE TABLE IF NOT EXISTS spread_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   TEXT    NOT NULL,
    pair        TEXT    NOT NULL,
    bid         REAL    NOT NULL,
    ask         REAL    NOT NULL,
    spread      REAL    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_spread_history_pair_ts ON spread_history(pair, timestamp);

-- ============================================================
-- entry_rejections: フィルタによるエントリー拒否の記録（v1.1）
-- ============================================================
CREATE TABLE IF NOT EXISTS entry_rejections (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp        TEXT    NOT NULL,
    pair             TEXT    NOT NULL,
    direction        TEXT    NOT NULL,
    reason           TEXT    NOT NULL,
    spread           REAL,
    spread_threshold REAL,
    atr              REAL,
    atr_ratio        REAL,
    confluence_kind  TEXT,
    agreed           TEXT,
    classes          TEXT,
    extra            TEXT
);
CREATE INDEX IF NOT EXISTS idx_entry_rejections_ts ON entry_rejections(timestamp);
CREATE INDEX IF NOT EXISTS idx_entry_rejections_reason ON entry_rejections(reason);
CREATE INDEX IF NOT EXISTS idx_entry_rejections_pair ON entry_rejections(pair);
CREATE INDEX IF NOT EXISTS idx_entry_rejections_pair_reason ON entry_rejections(pair, reason);
````

---

## カラム定義の補足

### `atr_ratio`（連続値層化のため）

```text
atr_ratio = atr_14 / atr_50bar_mean
```

- `atr_14`：直近14本の真の値幅平均（M1足）
- `atr_50bar_mean`：直近50本のATR(14)の平均
- **期間50は固定**：本仕様でハードコードし、変更時は破壊的変更として扱う

### `actual_rr`（実現リスクリワード比）

```text
buy:  actual_rr = (exit_price - entry_price) / (entry_price - sl_price)
sell: actual_rr = (entry_price - exit_price) / (sl_price - entry_price)
```

- 利確到達なら理論値（≒2.0）に近い値
- 損切なら -1.0 付近
- 早期決済（manual等）の場合は中間値

### `mfe` / `mae`（自前トラッキング）

```text
buy:  mfe = max(mid in tracking) - entry_price
buy:  mae = entry_price - min(mid in tracking)
sell: mfe = entry_price - min(mid in tracking)
sell: mae = max(mid in tracking) - entry_price
```

両方とも**常に正の値で記録**する（方向は`opens.direction`で判別可能）。
`position_tracking`テーブルから集計し、`closes`に確定値を書き込む。

### `confluence_type`

`opens`テーブルでは固定値 `"cross-class"` のみ。

`single`（単独シグナル）と `intra-class`（同一クラス内一致）はそれぞれ `baseline_solo` / `baseline_intraclass` に記録するため、`opens` には現れない。

---

## 実装仕様（補足）

### 1. `position_tracking` のサンプリング粒度

| 項目 | 仕様 |
|------|------|
| サンプリング間隔 | **1秒固定** |
| サンプリング方式 | OANDAの`/v3/accounts/{account}/pricing` への定期ポーリング |
| ティックベース不採用の理由 | ブローカー依存で再現性が崩れるため |
| 監視対象 | 保有中ポジションが存在するペアのみ |

### 2. `spread` の単位統一

全テーブルで**価格差そのまま（quote通貨の実数値）で保存**する。

| テーブル | spread カラム | 値の例（EUR/USD） | 値の例（USD/JPY） |
|---------|-------------|------------------|------------------|
| `signals` | spread | 0.00012 | 0.012 |
| `opens` | spread | 0.00012 | 0.012 |
| `spread_history` | spread | 0.00012 | 0.012 |

ルール：
- **内部保存**：常に `ask - bid` の生値（quote通貨建て）
- **レポート時のみpips換算**：`pip_size(pair)` で割って表示する

### 3. `currency_exposure_snapshots` の記録トリガー

| トリガー | 頻度 | 用途 |
|---------|------|------|
| **エントリー時** | 都度 | 新規ポジションによる増加を捕捉 |
| **クローズ時** | 都度 | ポジション減少を捕捉 |
| **定期スナップショット** | **1分間隔** | ギャップなしの時系列分析 |

保有ポジションがゼロのときも `net_ratio = 0` で記録する。

### 4. `entry_rejections` の拒否理由コード（v1.1）

`reason` カラムには以下の固定文字列を使用する。新しい拒否理由を追加する場合は仕様変更として扱う。

| reason | 発生条件 | 対応箇所 |
|--------|--------|--------|
| `market_closed` | 市場閉場時 | filters.md §6 step 1 |
| `max_open_pos` | 同時保有ペア数上限到達 | filters.md §6 step 2 |
| `pair_already_open` | 当該ペアの既保有ポジションあり | filters.md §6 step 3 |
| `max_portfolio_risk` | ポートフォリオ総リスク上限到達 | filters.md §6 step 4 |
| `no_confluence` | コンフルエンス非成立（通常は記録しない） | filters.md §6 step 5 |
| `intraclass_only` | 同一クラス内一致のみ（cross-class非成立） | confluence派生 |
| `spread_too_high` | スプレッド閾値超過 | filters.md §1 / §6 step 6 |
| `size_below_minimum` | ポジションサイズが最小取引単位未満 | filters.md §6 step 7 |
| `currency_exposure` | 通貨単位エクスポージャー超過 | filters.md §2 / §6 step 8 |
| `exposure_api_failed` | エクスポージャー取得APIが失敗し、安全側で拒否 | filters.md §2.6 |
| `env_mismatch` | 起動時・定期・エントリー直前の環境整合性チェック失敗 | startup_checks.py |
| `kill_switch` | 安全装置発動 | 将来用 |
| `conflicting_signals` | buy/sell 双方でcross-class confluenceが同時成立し、方向を一意に決定できない | confluence派生 |

実装上の注意：
- `no_confluence` は頻発するため、デフォルトでは記録しない（`signals`テーブルから事後集計可能）
- `intraclass_only` は同一クラス内一致が観測された場合に記録する
- `spread_too_high` 時は `spread` と `spread_threshold` を必ずセットで記録する
- コンフルエンス成立後の拒否（`size_below_minimum` / `currency_exposure` 等）は `classes` と `agreed` を埋める
- `extra` は JSON 文字列で、必要に応じて追加情報を格納する

起動時の `ConfigError` は Slack 通知を優先する。DB初期化済みで記録可能な場合のみ `entry_rejections` に `reason="env_mismatch"` として記録する。DBパス不整合・DB未作成・マウント失敗時はDBへ記録できないため、Slack通知とstderrログのみとする。

---

## ライフサイクル

```text
[戦略 evaluate()] → signals に1行追加
                     ↓
                  全戦略の発火を集約
                     ↓
       ┌─────────────┼─────────────┐
       ↓                             ↓
  cross-class成立              非成立
       ↓                             ↓
  opens に追加                  baseline_solo/intraclass に追加
       ↓
  baseline_random に同条件1行追加
       ↓
  position_tracking で価格モニタリング開始
       ↓
  決済時に closes に追加（mfe/mae確定）
```

---

## 仮想決済の計算方針

`baseline_*`テーブルの`virtual_*`カラムは**バッチ処理で後段に埋める**。
理由：エントリー時に確定できる値ではなく、未来の価格推移が必要なため。

このバッチは1日1回（UTC 00:00台）に実行する。
