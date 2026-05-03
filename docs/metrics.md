# 評価指標の計算定義（凍結版 v1）

本ドキュメントは fxbot の評価指標を確定するもの。
**全ての指標はここで定義された計算式・期間・条件に厳密に従って算出すること。**
本仕様の変更は破壊的変更として扱う。

---

## 設計原則

1. **主要KPIは一意に定まる単純平均で定義する**（恣意性排除）
2. **層別分析は診断（diagnostic）として主指標と分離する**
3. **判定は段階制とし、サンプル数に応じた信頼度で扱う**
4. **p値だけでなく効果量（effect size）も必須評価する**
5. **実エントリーと仮想エントリーは同一計算式で評価し、差分を比較する**

---

## 指標一覧

| 階層 | 指標 | 用途 |
|------|------|------|
| **主要KPI** | ΔE[R] | コンフルエンスの純粋な期待値寄与 |
| **主要KPI** | 最大ドローダウン（全期間・ローリング30日） | 分布安定性 |
| **主要KPI** | 連敗クラスタ最大長・95パーセンタイル | テールリスク |
| 副指標 | ATR帯別 ΔE[R] | レジーム依存性の診断 |
| 副指標 | 時間帯別 ΔE[R] | 時間帯依存性の診断 |
| 副指標 | 戦略別貢献度 | どの戦略がコンフルエンスを引き起こしているか |
| 副指標 | 平均約定遅延・実現RR分布 | 執行品質の診断 |
| 統計検定 | Mann-Whitney U検定 p値 | 差分の統計的有意性 |
| 統計検定 | Bootstrap 95% CI | 差分の信頼区間 |
| 統計検定 | Cliff's delta | 効果量（実質的な優位性の大きさ） |

---

## 早期撤退条件 / Early Stop Criteria

### 目的

早期撤退条件は、2週間サイクルの終了を待たずに、明らかな崩壊・実装バグ・市場条件不一致・フィルタ過剰を検知するための運用ルールである。

これは利益最大化のための条件ではなく、誤った実装や壊れた仮説を長期間放置しないための安全装置である。

---

## 資金前提

OANDA JapanのREST API利用条件として、NYサーバー口座残高25万円以上が必要となる。

そのため、初期入金目安は30万円とする。

ただし、30万円全額をリスク資金とは扱わない。

```text
30万円 = API利用条件維持のための拘束残高25万円 + 実験バッファ5万円
```

25万円部分はAPI維持ラインとして扱う。  
初期段階における実質的な損失許容枠は、差額部分である約5万円を中心に考える。

この前提により、通常の損益評価とは別に、API維持ラインを脅かす損失を強く警戒する。

---

## 2週間評価サイクル

標準サイクルは以下とする。

```text
Day 1〜7   : dry-run / practice観測、データ蓄積に専念
Day 8〜11  : 継続稼働、サンプル数監視
Day 12     : 中間分析（n=100〜150想定）
Day 13     : 判定
Day 14     : 次サイクルへのアクション決定
```

Day 14時点で、以下を評価する。

- `mean(R_confluence)`
- `mean(R_baseline_random)`
- `ΔE[R]`
- Bootstrap CI
- Mann-Whitney U
- Cliff's delta
- 最大ドローダウン
- 連敗分布
- entry_rejections.reason分布
- spread_too_high拒否率
- 戦略別シグナル発生数
- 時間帯別シグナル発生数

---

## 早期撤退条件

以下の条件に該当した場合、Day 14を待たずに現行ロジックの見直しへ移行する。

### 1. baseline_randomへの明確な劣後

```text
Day 3以降
かつ n >= 30
かつ ΔE[R] <= -0.5R
```

この条件を満たした場合、コンフルエンス判定が条件付きランダムベースラインより明確に劣っている可能性が高い。

n<30ではノイズが大きいため、この条件では停止判断しない。

### 2. 連敗の異常発生

```text
連敗数 > 15
```

連敗が15回を超えた場合、以下のいずれかを疑う。

- エントリー条件が市場に合っていない
- フィルタが不十分
- シグナル方向が逆に機能している
- 実装バグ
- スプレッド・約定条件が想定より悪い

### 3. 同一エラーによる連続失敗

```text
同一エラーによるエントリー失敗 >= 10回連続
```

対象例：

- `env_mismatch`
- `spread_too_high`
- `currency_exposure`
- `exposure_api_failed`
- `size_below_minimum`
- `conflicting_signals`

同一理由で10回連続して拒否される場合、設定・実装・市場条件のいずれかに偏りがあるため、サイクル継続より原因調査を優先する。

### 4. 戦略の半数以上が0シグナル

```text
実装済み戦略の半数以上が0シグナル
```

これは戦略仮説の失敗というより、以下の可能性が高い。

- 戦略がmain loopに登録されていない
- 対象ペアが一致していない
- 市場時間判定が過剰
- candles取得または価格取得が失敗している
- evaluate() が常にNoneを返している
- timezone処理が誤っている

この条件に該当した場合、パフォーマンス評価ではなく実装検証へ戻る。

### 5. スプレッドフィルタ拒否率の過剰

```text
spread_too_high による拒否率 > 80%
```

スプレッドフィルタ拒否率が80%を超える場合、以下を疑う。

- HARD_SPREAD_CAP が厳しすぎる
- p95算出に必要なサンプルが不足している
- 時間帯と対象ペアが合っていない
- OANDAの実スプレッドが想定より広い
- spread単位の扱いが誤っている

この条件に該当した場合、売買ロジックより先にspread_historyとフィルタ閾値を確認する。

---

## 早期撤退時の対応

早期撤退条件が発動した場合、以下の順で確認する。

```text
1. entry_rejections.reason 分布
2. spread_history
3. signals の戦略別件数
4. signals の時間帯別件数
5. confluence成立件数
6. conflicting_signals件数
7. baseline_randomとの差分
8. DB欠損・重複・時刻ズレ
9. OANDA APIエラー
10. 実装変更履歴
```

早期撤退後は、即座にlive運用へ進まない。

修正後、再度dry-runまたはpractice観測から2週間サイクルを開始する。

---

## 判定上の注意

早期撤退条件は、統計的優位性を証明する条件ではない。

早期撤退条件は、以下を検出するための実務的な停止条件である。

- 明らかな劣後
- 連敗の異常
- 実装バグ
- 設定不備
- フィルタ過剰
- 市場条件不一致
- API条件維持ラインを脅かす損失

統計的な採用判断は、累積サンプル数が十分に増えた後、通常の評価指標に基づいて行う。

---

## 1. 主要KPI

### 1.1 R-multiple

全てのトレード（実・仮想）は**R-multiple単位**で評価する。

```
R = pnl / risk_amount
```

- `risk_amount`：エントリー時の口座通貨建てリスク額（`opens.risk_amount`）
- 仮想エントリーの`risk_amount`は、実エントリーと同一のリスク率（`risk_per_trade(equity)`）を用いて計算する
- **TP到達**：R ≈ +2.0（ATR_TP_MULT=2.0想定）
- **SL到達**：R ≈ -1.0
- **早期決済**：中間値

### 1.2 ΔE[R]（主指標）

主要評価値はこれ。**単純平均のみ**で計算し、層別加重平均は採用しない。

```
ΔE[R] = mean(R_confluence) − mean(R_baseline)
```

ベースラインは3種類存在し、それぞれと別々に比較する：

| 比較対象 | 計算 | 解釈 |
|---------|------|------|
| ΔE[R]_vs_random | mean(R_confluence) − mean(R_random) | コンフルエンスの**純粋な寄与**（最重要） |
| ΔE[R]_vs_solo | mean(R_confluence) − mean(R_solo) | 単独シグナル比の優位性 |
| ΔE[R]_vs_intraclass | mean(R_confluence) − mean(R_intraclass) | 構造クラス間 vs 同一クラス内の差 |

**計算上のルール：**

- 母集団は同期間内のサンプルに揃える（同じ時刻範囲のデータのみで計算）
- 集計対象期間は累積（運用開始から現在まで）
- 早期決済（manual・timeout）も含める

### 1.3 最大ドローダウン（DD）

#### 1.3.1 全期間DD

```
cumulative_pnl(t) = Σ pnl(0..t)
peak(t) = max(cumulative_pnl(0..t))
drawdown(t) = (cumulative_pnl(t) - peak(t)) / peak(t)   # peak > 0 のとき
            = cumulative_pnl(t) - peak(t)               # peak ≤ 0 のとき（絶対額）

max_drawdown_alltime = min(drawdown(t)) for all t
```

- **解像度**：日次ベース（その日の終値時点で計算）
- intra-dayの一時的なDDは別途`intraday_dd`として記録するが、主要KPIには含めない

#### 1.3.2 ローリング30日DD

```
rolling_dd_30d = max_drawdown calculated over the last 30 calendar days
```

- 30日窓を1日ずつスライド
- 戦略劣化の早期検出に用いる
- 直近30日のDDが累積DDの50%を超えたら警戒水準

### 1.4 連敗クラスタ

#### 1.4.1 定義

連敗クラスタ＝**連続損失トレード数**（トレード単位）

```python
# 疑似コード
def losing_streaks(trades):
    streaks = []
    current = 0
    for t in trades_ordered_by_exit_time:
        if t.pnl < 0:
            current += 1
        else:
            if current > 0:
                streaks.append(current)
            current = 0
    if current > 0:
        streaks.append(current)
    return streaks
```

#### 1.4.2 主要指標

| 指標 | 計算 |
|------|------|
| max_streak | max(streaks) |
| streak_p95 | 経験分布の95パーセンタイル |

**95パーセンタイルの算出：**

- 全クラスタを長さでソート
- インデックス `floor(0.95 * len(streaks))` の値を取る
- Bootstrapリサンプリングは行わない（経験分布そのまま）
- サンプル数 n < 20 のときは「N/A」と表示し、判定には使わない

---

## 2. 副指標（診断的分析）

主要KPIと**並列で計算**するが、最終判定には用いない。
「どの市場状態でコンフルエンスが効いているか」を分解分析するために使用。

### 2.1 ATR帯別 ΔE[R]

`atr_ratio` を3層に分割して各層の ΔE[R] を計算。

| 層 | 範囲 |
|------|------|
| low_vol | atr_ratio < 0.7 |
| mid_vol | 0.7 ≤ atr_ratio < 1.3 |
| high_vol | atr_ratio ≥ 1.3 |

各層内で `mean(R_confluence) - mean(R_random)` を計算し、レポートする。

### 2.2 時間帯別 ΔE[R]

UTCを4区間に分割して各区間のΔE[R]を計算。

| 区間 | UTC時間 | 主な市場 |
|------|---------|---------|
| asia | 0:00-7:00 | 東京 |
| london | 7:00-13:00 | ロンドン |
| ny_overlap | 13:00-17:00 | ロンドン・NY重複 |
| late | 17:00-24:00 | NY後半 |

### 2.3 戦略別貢献度

各戦略について、その戦略が一致に含まれていたエントリーの数と平均Rを集計。

```sql
SELECT
    source AS strategy,
    COUNT(*) AS n_entries,
    AVG(R) AS avg_r
FROM opens
JOIN closes ON opens.trade_id = closes.trade_id
JOIN signals ON ...   -- 一致戦略の展開
GROUP BY source
```

### 2.4 執行品質

| 指標 | 計算 | 期待値 |
|------|------|------|
| 平均約定遅延 | mean(latency.confluence_to_fill_ms) | < 500ms |
| 実現RR平均 | mean(closes.actual_rr) | TPで2.0、SLで-1.0 |
| MFE/TP到達率 | count(mfe_pips ≥ tp_pips) / total | 高いほど良い |
| MAE分布 | quantiles(mae_pips) | 25/50/75/95% |

これらは「想定通りに動いているか」の確認用。

---

## 3. 統計検定

### 3.1 段階的判定基準

サンプル数に応じて判定の重みを変える。

| サンプル数 n | ステータス | 用途 |
|----|---|------|
| n < 50 | データ蓄積中 | 数値表示のみ、判断には使わない |
| 50 ≤ n < 100 | **参考表示（informational）** | 傾向確認、判断は保留 |
| 100 ≤ n < 200 | **暫定判断（provisional）** | 仮説支持/反証の暫定評価 |
| n ≥ 200 | **最終判断（final）** | Phase 1の合否判定に使用 |

### 3.2 統計検定（n ≥ 50で実施）

R-multipleの分布は正規ではない（裾が厚い）ため、ノンパラメトリック手法を採用。

#### Mann-Whitney U検定

- 2つの独立サンプルの分布の優位性を検定
- 帰無仮説：`R_confluence` と `R_baseline_random` は同じ分布から抽出
- p値 < 0.05 で帰無仮説棄却

```python
from scipy.stats import mannwhitneyu
stat, p = mannwhitneyu(R_confluence, R_baseline_random, alternative='greater')
```

#### Bootstrap 95% 信頼区間

- 経験分布から差分の信頼区間を計算
- リサンプリング回数：10,000回
- 95% CIが0より上にあれば有意な優位性

```python
def bootstrap_diff_ci(R_a, R_b, n_iter=10_000, ci=0.95):
    diffs = []
    for _ in range(n_iter):
        a = np.random.choice(R_a, size=len(R_a), replace=True)
        b = np.random.choice(R_b, size=len(R_b), replace=True)
        diffs.append(np.mean(a) - np.mean(b))
    lower = np.percentile(diffs, (1-ci)/2 * 100)
    upper = np.percentile(diffs, (1+ci)/2 * 100)
    return lower, upper
```

### 3.3 効果量（必須指標）

p値だけでは「統計的に有意だが実質無意味」な結果を排除できないため、効果量を必須化。

#### Cliff's delta

ノンパラメトリック効果量。R-multipleのような非正規分布データに適切。

```python
def cliffs_delta(a, b):
    """
    a, b: array-like
    Returns: float in [-1, +1]
        +1: aが完全にbより大きい
         0: 両群が同等
        -1: bが完全にaより大きい
    """
    n_a, n_b = len(a), len(b)
    greater = sum(1 for x in a for y in b if x > y)
    less    = sum(1 for x in a for y in b if x < y)
    return (greater - less) / (n_a * n_b)
```

#### 解釈基準（Romano et al., 2006）

| |Cliff's delta| | 効果量 | 実用解釈 |
|---|---|---|
| < 0.147 | negligible | 無視できるレベル（実用上は無関係） |
| 0.147 - 0.33 | small | 小さいが意味あり |
| 0.33 - 0.474 | medium | 明確な優位性 |
| ≥ 0.474 | large | 強い優位性 |

**重要：** Mann-Whitney U の p < 0.05 でも、Cliff's delta < 0.147 なら**実質的に意味のある優位性ではない**と判定する。

---

## 4. 集計期間と報告タイミング

### 4.1 日次レポート（UTC 00:00台）

毎日1回、Slack に配信。

```
📊 Daily Report 2026-MM-DD

== 当日 ==
Entries:       N
Win rate:      XX.X%
Avg R:         +X.XX
Pnl:           +X.XX (account_currency)

== 累積（n=NNN） ==
Win rate:      XX.X%
Avg R:         +X.XX
Max DD:        -X.X% (alltime)
Rolling 30d DD:-X.X%
Max streak:    N
Streak P95:    N

== ベースライン差分（n≥50 で表示） ==
ΔE[R]_vs_random:    +X.XX  [CI: +X.XX, +X.XX]  Cliff's δ: +X.XX (small/medium/large)
ΔE[R]_vs_solo:      +X.XX
ΔE[R]_vs_intraclass:+X.XX

== 執行品質 ==
Avg latency:   XXXms
Avg actual RR: +X.XX
MFE/TP rate:   XX.X%
```

### 4.2 週次レポート（毎週月曜UTC 00:00）

過去7日のローリング統計と層別分析を配信。

```
📈 Weekly Report (Week of YYYY-MM-DD)

== 7-day rolling ==
n=NN entries, Win XX.X%, Avg R +X.XX

== ATR帯別 ΔE[R]_vs_random ==
low_vol  (n=NN): +X.XX  [Cliff's δ: +X.XX]
mid_vol  (n=NN): +X.XX  [Cliff's δ: +X.XX]
high_vol (n=NN): +X.XX  [Cliff's δ: +X.XX]

== 時間帯別 ΔE[R]_vs_random ==
asia       (n=NN): +X.XX
london     (n=NN): +X.XX
ny_overlap (n=NN): +X.XX
late       (n=NN): +X.XX

== 戦略別貢献度（top 5） ==
strategy_name (involved in N entries): avg R +X.XX
...
```

### 4.3 最終判定（Phase 1終了時）

Phase 2移行の合否判定。**累積n≥200**を必須とする。

#### 合格条件（全て満たす場合のみPhase 2移行）

```
1. 累積 n ≥ 200
2. ΔE[R]_vs_random > 0
   かつ Mann-Whitney U p < 0.05
   かつ Cliff's delta ≥ 0.147（small以上）
3. 最大DDの絶対値が baseline_random の最大DD より小さい
4. 連敗P95 が baseline_random の連敗P95 より小さい
```

#### 部分合格（Phase 1.5として継続）

```
- 上記2は満たすが3または4が満たされない
- レジーム依存性が強く、特定のATR帯/時間帯のみで優位
- → ロジック調整（フィルター追加・対象時間帯絞り込み）の上で継続
```

#### 不合格（仮説反証）

```
- 上記2が満たされない
- 戦略・コンフルエンスロジックの根本見直し
- もしくは「個人レベルではコンフルエンス機構をもってしても市場構造の壁を越えられない」という反証として記録
```

---

## 5. 計算実装上の注意

### 5.1 仮想決済の扱い

`baseline_*`テーブルの`virtual_*`カラムは**バッチ処理で後段に埋める**（schema.md参照）。
このバッチ処理は **UTC 00:00台に1回**実行する。

仮想決済の計算は実エントリーと完全に同じロジックで行う：

```python
def simulate_exit(entry_price, direction, atr, future_candles):
    sl = entry_price - atr * ATR_SL_MULT  if direction == "buy" else entry_price + atr * ATR_SL_MULT
    tp = entry_price + atr * ATR_TP_MULT  if direction == "buy" else entry_price - atr * ATR_TP_MULT

    for candle in future_candles:
        high, low = candle.high, candle.low
        if direction == "buy":
            if low  <= sl:  return candle.time, sl, "sl"
            if high >= tp:  return candle.time, tp, "tp"
        else:
            if high >= sl:  return candle.time, sl, "sl"
            if low  <= tp:  return candle.time, tp, "tp"

    # 24時間以内に決済しなければtimeout扱い
    return future_candles[-1].time, future_candles[-1].close, "timeout"
```

**注意：** 1分足で同じバー内にSLとTPの両方が含まれる場合は、保守的に「先にSLに到達した」と仮定する。

### 5.2 母集団の整合性

ΔE[R]を計算する際、`R_confluence` と `R_baseline_random` は **`paired_trade_id` で紐付いた同条件のサンプル**で比較する。

```sql
SELECT
    AVG(c.actual_rr) AS r_confluence,
    AVG(br.virtual_rr) AS r_random
FROM closes c
JOIN opens o ON c.trade_id = o.trade_id
JOIN baseline_random br ON br.paired_trade_id = o.trade_id
WHERE c.exit_reason != 'manual'
  AND br.virtual_exit_reason IS NOT NULL
```

母集団がずれると比較が歪むため、必ずペアリング済みのサンプルのみで計算する。

### 5.3 早期決済の扱い

| `exit_reason` | 主指標に含めるか | 補足 |
|---------------|--------------|------|
| `tp` | ✓ | TP到達 |
| `sl` | ✓ | SL到達 |
| `timeout` | ✓ | 24時間経過（仮想決済のみ） |
| `manual` | ✗ | 手動介入は分析対象外 |

`manual`決済は集計時にWHERE句で除外する。


