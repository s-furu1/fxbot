# フィルタ・閾値ロジック仕様（凍結版 v1）

本ドキュメントは fxbot のフィルタ・閾値ロジックを確定するもの。
**実装はこの仕様に厳密に従うこと**。本仕様の変更は破壊的変更として扱う。

---

## 設計原則

1. **閾値は絶対値固定ではなく分布から動的に決定する**（市場条件への適応）
2. **ロバスト推定を優先する**（外れ値による閾値膨張を回避）
3. **判定ロジックには論理的な抜け道を設けない**（AND条件を基本とする）
4. **API依存処理は短TTLキャッシュで過負荷を防ぐ**
5. **データ蓄積に応じて精度を上げるフェーズ移行を組み込む**

---

## フィルタ一覧

| フィルタ | 用途 | 判定タイミング |
|---------|------|--------------|
| スプレッドフィルタ | 異常スプレッド時のエントリー回避 | エントリー判定時 |
| 通貨単位エクスポージャー | 通貨集中リスクの抑制 | エントリー判定時 |
| ペア単位ポジション数 | ペア分散の確保 | エントリー判定時 |
| ポートフォリオ総リスク | 全体リスク総量の上限 | エントリー判定時 |
| 市場開場 | 土日・週末ギャップ回避 | 全タイミング |
| シグナル有効期限 | 60秒同期窓の保証 | コンフルエンス判定時 |

---

## 1. スプレッドフィルタ

### 1.1 仕様

エントリー時のスプレッドが過去分布の95パーセンタイルを超える場合、エントリーを拒否する。

### 1.2 参照期間（フェーズ移行）

| 期間 | 参照データ |
|------|--------|
| Phase A（運用開始〜30日） | 過去24時間の同ペアのスプレッド全件 |
| Phase B（30日経過後〜） | 過去30日の同ペア・同曜日同時間帯（±30分窓）のスプレッド全件 |

切り替えタイミング：`spread_history`テーブルに30日分以上のデータが蓄積されたペアから個別に Phase B へ移行する。

### 1.3 閾値計算方式

**95パーセンタイル + 絶対上限の二重防御**を採用。標準偏差ベースは採用しない。

理由：
- スプレッド分布は対数正規に近くロングテール
- σベースだと外れ値で閾値が膨らむ
- パーセンタイルなら「上位5%の異常スプレッド時のみ除外」と直感的
- サンプル不足時でも絶対上限により異常値を遮断（後述）

#### HARD_SPREAD_CAP（絶対上限）

サンプル不足時のフェイルセーフ機構として、通貨ペアごとに絶対上限を定義する。
これは「平常時の最大スプレッドの約3倍」を目安とし、明らかな異常値（指標発表時の急拡大など）を確実に遮断する。

```python
# config.py
HARD_SPREAD_CAP = {
    "EUR_USD": 0.0005,   # 5.0 pips
    "USD_JPY": 0.05,     # 5.0 pips
    "AUD_USD": 0.0007,   # 7.0 pips
    "EUR_GBP": 0.0008,   # 8.0 pips
    "GBP_USD": 0.0008,   # 8.0 pips
}
```

これらの値は OANDA Japan の公開スプレッドおよび過去の指標発表時拡大幅から設定。
運用30日経過後にPhase Bデータをもとに再評価し、必要に応じて見直す。

```python
def calc_spread_threshold(pair: str, now: datetime) -> float:
    """
    指定ペアのスプレッド閾値を返す。
    Phase A: 過去24時間
    Phase B: 過去30日の同曜日同時間帯（±30分）
    フェイルセーフ: HARD_SPREAD_CAPを下限として保証
    """
    hard_cap = HARD_SPREAD_CAP[pair]

    if not _has_30days_data(pair):
        # Phase A
        cutoff = now - timedelta(hours=24)
        spreads = _query_spreads(pair, since=cutoff)
    else:
        # Phase B
        weekday = now.weekday()
        hour    = now.hour
        minute  = now.minute
        spreads = _query_spreads_by_timeband(
            pair, weekday, hour, minute,
            window_minutes=30,
            days=30,
        )

    if len(spreads) < 100:
        # サンプル不足時は HARD_SPREAD_CAP のみで判定
        # （統計的閾値が信頼できない時こそ絶対上限を適用）
        return hard_cap

    # 統計的閾値が信頼できる場合でも、HARD_SPREAD_CAPで上限を保証
    # （何らかのバグで95p値が異常に高くなっても、絶対値で歯止め）
    statistical_threshold = float(np.percentile(spreads, 95))
    return min(statistical_threshold, hard_cap)
```

**重要な変更点（v0からv1）：**
- v0：サンプル不足時は `float('inf')` を返してフィルタ実質無効化 → 採用不可
- v1：サンプル不足時は `HARD_SPREAD_CAP` を返す → 安全側動作

これにより：
- 運用初期（サンプル不足時）も絶対上限で異常スプレッドは遮断される
- 統計的閾値が利用可能になっても、`min(stat, hard_cap)` で異常な閾値膨張を防ぐ
- 「最も不安定な時期に最も危険なトレードを通す」リスクを排除

### 1.4 更新頻度

| 項目 | 仕様 |
|------|------|
| 計算頻度 | 5分ごとのバッチ更新 |
| キャッシュ先 | `spread_thresholds` テーブル |
| キャッシュ有効期限 | 5分 |

```sql
CREATE TABLE IF NOT EXISTS spread_thresholds (
    pair        TEXT    NOT NULL,
    computed_at TEXT    NOT NULL,
    threshold   REAL    NOT NULL,
    phase       TEXT    NOT NULL,    -- "A" | "B"
    sample_n    INTEGER NOT NULL,
    PRIMARY KEY (pair, computed_at)
);
```

### 1.5 判定ロジック

```python
def passes_spread_filter(pair: str, current_spread: float, now: datetime) -> bool:
    threshold = get_cached_threshold(pair, max_age_seconds=300)
    if threshold is None:
        threshold = calc_spread_threshold(pair, now)
        cache_threshold(pair, threshold)
    return current_spread <= threshold
```

エントリー判定時にこの関数を呼び、`False` ならエントリー拒否。
拒否したエントリーは `signals` には記録されているが、`opens` には現れない（`baseline_random` も発生しない）。

---

## 2. 通貨単位エクスポージャー

### 2.1 仕様

各通貨のネット・エクスポージャー絶対値が口座残高の **1.5%** を超える場合、新規エントリーを拒否する。

### 2.2 計算式

```
基準: ロング = base+, quote-
      ショート = base-, quote+

通貨Cのネットリスク = Σ(全保有ポジションのCに対するエクスポージャー)
                    × 各ポジションのSL距離 × ユニット数
                    ÷ 口座残高
```

### 2.3 取得ロジック（短TTLキャッシュ付き）

毎回API取得すると同時シグナル集中時にレイテンシが増加するため、**5秒のソフトキャッシュ**を設ける。

```python
class ExposureCache:
    def __init__(self, ttl_seconds: float = 5.0):
        self._ttl = ttl_seconds
        self._cached_at: Optional[datetime] = None
        self._cached_value: Optional[dict] = None

    def get(self, client, account_id, equity, now: datetime) -> dict:
        if (self._cached_at and
            (now - self._cached_at).total_seconds() < self._ttl):
            return self._cached_value

        # API取得
        try:
            value = current_currency_exposure(client, account_id, equity)
        except Exception:
            # フォールバック：API失敗時は前回値があれば使う
            if self._cached_value is not None:
                return self._cached_value
            # キャッシュもない場合は安全側（エントリー全停止）
            return {"_fallback": True}

        self._cached_at = now
        self._cached_value = value
        return value
```

### 2.4 換算レート

`exposure.py` 内でEUR・GBP等のリスクをUSD（口座通貨）建てに換算する際、**判定時の最新ミドルレート**を使う。

```python
def to_account_currency(amount: float, currency: str, account_currency: str,
                        prices: dict) -> float:
    """換算は判定時の最新ミドルレートで実施。"""
    if currency == account_currency:
        return amount
    key = f"{currency}_{account_currency}"
    if key in prices:
        return amount * prices[key]["mid"]
    inv = f"{account_currency}_{currency}"
    if inv in prices:
        return amount / prices[inv]["mid"]
    raise ValueError(f"No conversion rate for {currency} -> {account_currency}")
```

### 2.5 判定ロジック

```python
MAX_CURRENCY_RISK = 0.015  # 1.5%

def passes_exposure_filter(pair, direction, additional_risk_amount,
                            equity, exposure_cache, prices, now):
    exposure = exposure_cache.get(client, ACCOUNT_ID, equity, now)

    # APIフォールバック：データが取れなかった場合は安全側で全停止
    if exposure.get("_fallback"):
        return False

    base, quote = pair.split("_")
    sign = 1 if direction == "buy" else -1
    add_ratio = additional_risk_amount / equity if equity > 0 else 0

    new_base  = exposure.get(base,  0) + sign * add_ratio
    new_quote = exposure.get(quote, 0) - sign * add_ratio

    return (abs(new_base)  <= MAX_CURRENCY_RISK and
            abs(new_quote) <= MAX_CURRENCY_RISK)
```

### 2.6 API失敗時のフォールバック

| 状況 | 動作 |
|------|------|
| キャッシュあり（5秒以内） | キャッシュ値を使用 |
| キャッシュ古いがAPI成功 | 取得した値を使用・キャッシュ更新 |
| キャッシュ古い + API失敗・前回値あり | 前回値を使用（注意：劣化データだが流用） |
| キャッシュなし + API失敗 | **エントリー全停止**（安全側） |

API失敗が続く場合は Slack に警告通知を送る。

---

## 3. ATR_50bar_mean 計算詳細

### 3.1 仕様

`atr_ratio` の分母として `signals` / `opens` / `baseline_*` 全てで使用する。

```
atr_ratio = atr_14 / atr_50bar_mean
```

### 3.2 計算式

```
atr_14(t)        = mean(true_range(t-13..t))
atr_50bar_mean(t) = mean(atr_14(t-49..t))
```

つまり、現在を含む直近50本の各時点でのATR(14)の平均。

### 3.3 実装方針

**毎バー再計算（numpy）**を採用。インクリメンタル更新やキャッシュテーブルは採用しない。

```python
def calc_atr_ratio(candles: list) -> tuple[float, float, float]:
    """
    Returns: (atr_14, atr_50bar_mean, atr_ratio)
    candles: 最低63本必要（50本のATR平均にはATR(14)が50個必要、各ATRには14本のTR必要）
    """
    if len(candles) < 64:
        raise ValueError("Need at least 64 candles for atr_ratio")

    highs  = np.array([float(c["mid"]["h"]) for c in candles])
    lows   = np.array([float(c["mid"]["l"]) for c in candles])
    closes = np.array([float(c["mid"]["c"]) for c in candles])

    # 全期間のTrue Range
    trs = np.maximum.reduce([
        highs[1:] - lows[1:],
        np.abs(highs[1:] - closes[:-1]),
        np.abs(lows[1:]  - closes[:-1]),
    ])

    # 各時点のATR(14)系列
    atr_14_series = np.array([
        np.mean(trs[i-13:i+1]) for i in range(13, len(trs))
    ])

    atr_14         = float(atr_14_series[-1])
    atr_50bar_mean = float(np.mean(atr_14_series[-50:]))
    atr_ratio      = atr_14 / atr_50bar_mean if atr_50bar_mean > 0 else 1.0

    return atr_14, atr_50bar_mean, atr_ratio
```

### 3.4 計算頻度

- 毎分の足確定タイミングで全ペア計算
- シグナル発火時はその時点のキャッシュ値を参照（同一分内であれば再計算不要）

### 3.5 必要なローソク足本数

```
True Range計算: 64本目から計算可能（前日終値が必要）
ATR(14)系列  : 64本中の13〜63バー目を使い計51本のATR(14)を得る
50本平均     : 上記から最新50本を平均

→ 最低 64本（CANDLE_COUNT=500なら十分）
```

`config.py`の `CANDLE_COUNT = 500` で動作する。

---

## 4. Phase移行条件

### 4.1 Phase 1 → Phase 2 移行条件

**全条件AND**で評価する。1つでも欠ければ移行しない。

```
必須条件:
  1. 累積 n ≥ 200
  2. 各ATR帯（low/mid/high_vol）で n ≥ 50
  3. 各時間帯（asia/london/ny_overlap/late）で n ≥ 30
  4. ΔE[R]_vs_random > 0
  5. Mann-Whitney U p < 0.05
  6. Cliff's delta ≥ 0.147
  7. 最大DD ≤ baseline_random の最大DD
  8. 連敗P95 ≤ baseline_random の連敗P95
```

**重要：** 条件7・8はOR条件ではなくAND条件。

理由：
- DDのみ改善で連敗悪化、または連敗のみ改善でDD悪化のケースは実運用で不合格に近い
- 「分布両端の改善」を要求することで、片方の改善で他方が劣化する戦略を排除

### 4.2 緩和条件（参考）

Phase 1では緩和条件は採用しない。
仮にPhase 2以降で議論する場合の参考として：

```
(条件7 AND 条件8) OR (Cliff's delta ≥ 0.33)
```

「中効果量以上で実質的に強い優位性が確認できれば、片方の悪化は許容する」という設計。
**Phase 1では使わない**。

### 4.3 部分合格（Phase 1.5）

```
n ≥ 200 達成かつ 条件4〜6 を満たすが 条件7 または 条件8 を満たさない
  → Phase 1.5として継続
  → 個別戦略のパラメータ調整・問題戦略の除外で再評価
```

### 4.4 不合格（仮説反証）

```
n ≥ 400 達成かつ 条件4〜6 を継続的に満たさない
  → 仮説反証として記録
  → コンフルエンス機構の根本見直しまたはプロジェクト終了判定
```

### 4.5 Phase 2 → Phase 3 移行条件

```
1. Phase 2運用で n ≥ 500
2. 戦略ペア相関の安定性確認:
   上位10ペアの相関係数が直近100トレード単位で±0.1以内に収束
3. スコアリング方式が固定ルール（Phase 1）と比較して
   ΔE[R] が改善している（差分の Cliff's delta ≥ 0.147）
```

---

## 5. その他の固定パラメータ

### 5.1 シグナル有効期限

```
SIGNAL_EXPIRY_SEC = 60
```

`Signal.is_expired()` で判定。コンフルエンス成立判定の対象は「issued_atから60秒以内のシグナル」のみ。

### 5.2 同時保有ポジション

```
MAX_OPEN_POS = 3              # ペア単位
MAX_PORTFOLIO_RISK = 0.025    # ポートフォリオ総リスク 2.5%
MAX_CURRENCY_RISK = 0.015     # 通貨単位 1.5%
```

判定順：
1. 市場開場チェック → ✗ なら全停止
2. 同時保有ペア数 ≥ 3 → 新規エントリー拒否
3. ポートフォリオ総リスク ≥ 2.5% → 新規エントリー拒否
4. 当該ペアが既に保有中 → 新規エントリー拒否（重複防止）
5. スプレッドフィルタ → ✗ なら拒否
6. 通貨エクスポージャーフィルタ → ✗ なら拒否
7. 上記すべてOKならエントリー実行

### 5.3 リスク率スライド方式

```python
def risk_per_trade(equity: float) -> float:
    if equity < 30_000:
        return 0.01      # 1.0%
    elif equity < 100_000:
        return 0.005     # 0.5%
    else:
        return 0.0025    # 0.25%
```

口座通貨建ての残高で判定。

---

## 6. フィルタ評価の優先順位（実装上の順序）

エントリー判定の処理順を明確化する。早期リターンによる効率化のため、軽い判定から行う。

```python
def can_enter(pair, direction, signals, prices, equity, ...):
    # 1. 市場開場（軽量）
    if not is_market_open():
        return False, "market_closed"

    # 2. 同時保有数（軽量・キャッシュ可）
    if len(open_pairs) >= MAX_OPEN_POS:
        return False, "max_open_pos"

    # 3. 当該ペア既保有（軽量）
    if pair in open_pairs:
        return False, "pair_already_open"

    # 4. ポートフォリオ総リスク（API1回）
    if total_open_risk(equity) >= MAX_PORTFOLIO_RISK:
        return False, "max_portfolio_risk"

    # 5. コンフルエンス成立（CPU計算）
    conf = evaluate_confluence(signals)
    if not conf:
        return False, "no_confluence"

    # 6. スプレッドフィルタ（DBクエリ・キャッシュ可）
    if not passes_spread_filter(pair, current_spread, now):
        return False, "spread_too_high"

    # 7. ポジションサイズ計算
    units, risk_ratio, risk_amount = calc_units(...)
    if units <= 0:
        return False, "size_below_minimum"

    # 8. 通貨単位エクスポージャー（API1回・5秒キャッシュ）
    if not passes_exposure_filter(pair, direction, risk_amount, ...):
        return False, "currency_exposure"

    return True, "ok"
```

各拒否理由は `signals` テーブルとは別に **`entry_rejections`** テーブルに記録し、後段で「どのフィルタがどれくらい発動しているか」を分析できるようにする。

```sql
CREATE TABLE IF NOT EXISTS entry_rejections (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   TEXT    NOT NULL,
    pair        TEXT    NOT NULL,
    direction   TEXT    NOT NULL,
    reason      TEXT    NOT NULL,
    spread      REAL,
    atr_ratio   REAL
);
```

---

## 7. 次に確定すべき項目

このフィルタ確定をもって、ステップ3完了。

ステップ1〜3で観測系・評価系・フィルタ系の全仕様が凍結された。

次はステップ4「ドキュメント全面更新」に進む。
これまで凍結した3つの仕様（schema.md, metrics.md, filters.md）を写像として、`fxbot-app-README.md` および `fxbot-concept.md` を全面更新する。
