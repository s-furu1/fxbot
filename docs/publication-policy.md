# 公開方針 / Publication Policy

本ドキュメントは、fxbot リポジトリをポートフォリオとして公開する際の公開範囲・非公開範囲を定義する。

## 基本方針

このリポジトリは、以下を示すための公開リポジトリとする。

- 複数戦略のコンフルエンス仮説を検証する実験基盤
- 人間の認知容量を超えた同時並列監視の実装
- 条件付きランダムベースラインとの比較実験設計
- R-multiple / ΔE[R] / Cliff's delta / Bootstrap CI などの評価設計
- SQLite による検証可能なログ設計
- entry_rejections による拒否理由分析
- 金銭リスクを持つ常駐システムの安全設計
- practice/live 混同防止の仕組み
- Docker / GHCR / homeserver 分離運用
- heartbeat / healthcheck / startup guard による運用監視
- dry-run → practice → live の段階的移行フロー

このリポジトリの価値は、単に「安全なbotを作る」ことではない。  
**人間では継続困難な複数戦略の同期発火検知を機械化し、個人レベルで統計的優位性を得られるかを検証すること**にある。

安全設計・環境分離・dry-run運用は、検証と実運用を壊さないための前提条件として扱う。

## 公開してよいもの

以下は公開してよい。

- `README.md`
- `docs/schema.md`
- `docs/metrics.md`
- `docs/filters.md`
- `docs/migration.md`
- `docs/implementation-plan.md`
- `docs/publication-policy.md`
- `Dockerfile`
- GitHub Actions
- `startup_checks.py`
- `heartbeat.py`
- `db.py`
- `logger.py`
- `confluence.py` の抽象ロジック
- `strategies/base.py`
- ダミー戦略 / サンプル戦略 / toy strategy
- テストコード
- `.env.example`
- `configs/*.example.yaml`
- `configs/*.example.yml`

## 公開しないもの

以下は公開しない。

- OANDA APIキー
- OANDA Account ID
- Slack Webhook URL
- `.env`
- `.env.practice`
- `.env.live`
- 実取引ログ
- SQLite DB
- 本番運用ログ
- 実損益レポート
- 実測勝率
- 実測期待値
- 実測で優位性が出たペア
- 実測で優位性が出た時間帯
- 実測で優位性が出たATR帯
- 本番で使っている正確なパラメータ
- 完成版の戦略ロジック
- liveで使用するstrategy implementation
- 実測で優位性が確認されたstrategy pair
- 実測で優位性が確認されたtimeband / pair / ATR条件
- strategy selection / allocationの採用ルール
- live用strategy registry
- バックテスト結果の詳細
- live運用設定

## 公開に注意が必要なもの

以下は、公開前に内容を確認する。

- `filters.md` の閾値
- `strategies/` 配下の個別戦略
- `configs/` 配下の設定ファイル
- `reports/`
- `notebooks/`
- `backtests/`
- `exports/`
- `practice-results/`
- `live-results/`

実測で優位性が確認された後は、具体的な条件を含む情報を公開しない。

## Strategy implementation policy

公開リポジトリには、戦略の抽象基底クラス・Signal型・confluence判定・ログ基盤・評価基盤のみを含める。

実測で優位性が確認された、またはlive運用に使う個別戦略実装は、公開リポジトリに置かない。

本命戦略は以下のいずれかで管理する。

```text
- private repository: fxbot-private
- local-only directory: ~/projects/fxbot-private
- homeserver-only runtime mount
```

公開リポジトリに置いてよい戦略は、以下に限定する。

```text
- sample strategy
- dummy strategy
- toy strategy
- docs用の簡略化されたstrategy
```

公開リポジトリに置かないものは以下。

```text
- liveで使用するstrategy implementation
- 実測で優位性が確認されたstrategy pair
- 実測で優位性が確認されたtimeband / pair / ATR条件
- strategy selection / allocationの採用ルール
- live用strategy registry
- 実測レポート
- 実測ログ
```

## Strategy configuration policy

戦略有効化リスト、対象ペア、対象時間帯、実パラメータ、selection / allocation rule は利益源泉になり得るため、原則として公開しない。

公開する場合は、実運用と無関係な example のみに限定する。

公開してよい例：

```text
configs/strategy_registry.example.yaml
configs/allocation_rules.example.yaml
```

公開しない例：

```text
configs/strategy_registry.live.yaml
configs/strategy_registry.private.yaml
configs/allocation_rules.live.yaml
configs/allocation_rules.private.yaml
configs/live/
configs/private/
```

## パブリックリポジトリで見せる範囲

パブリックリポジトリでは、以下を主に見せる。

```text
- 設計思想
- コンフルエンス仮説
- 条件付きランダムベースラインとの比較
- DBスキーマ
- 評価指標
- フィルタ設計
- ログ設計
- 安全な環境切替
- 起動時整合性チェック
- dry-run前提の段階的運用
- テスト
- Docker化
- GHCR配布
```

具体的な売買条件や実測優位性ではなく、  
**仮説を検証可能な形に落とし込み、金銭リスクを持つ常駐システムとして安全に運用する設計力**を示す。

## 非公開化の判断基準

以下のいずれかを満たした場合、戦略ロジック・パラメータ・実測レポートは非公開化する。

- practiceで明確な期待値改善が確認された
- `ΔE[R] > 0` が継続した
- Cliff's delta が small 以上になった
- 特定ペア・時間帯・ATR帯に優位性が偏っていることが分かった
- live運用に移行する
- SNS / Zenn / note などで拡散され始めた
- third party が同一ロジックを再現可能な状態になった

## 避ける表現

以下の表現は使わない。

```text
勝てるFX bot
自動で稼ぐbot
期待値プラス戦略
実運用で利益が出た
誰でも儲かる
放置で稼ぐ
```

## 使う表現

以下の表現を使う。

```text
複数戦略のコンフルエンス仮説を検証する実験基盤
人間の認知容量を超えた同時並列監視の実験
practice/live混同防止を重視した常駐取引システム
条件付きランダムベースラインとの比較による評価設計
検証可能性・安全性・運用分離を重視したFX bot実験基盤
```

## .gitignore 方針

以下は必ず `.gitignore` に含める。

```gitignore
# secrets
.env
.env.*
!.env.example

# runtime data
data/
*.db
*.sqlite
*.sqlite3

# reports / actual performance
reports/
notebooks/
exports/
backtests/
live-results/
practice-results/

# private strategy implementations
src/fxbot/strategies/private/
src/fxbot/strategies/*_private.py
src/fxbot/strategies/*_live.py
src/fxbot/strategies/*_edge.py

# private / live strategy configuration
configs/private/
configs/live/
configs/*private*.yaml
configs/*private*.yml
configs/*live*.yaml
configs/*live*.yml
configs/*edge*.yaml
configs/*edge*.yml
!configs/*.example.yaml
!configs/*.example.yml

# strategy selection / allocation outputs
strategy-selection/
allocation-reports/
selection-reports/

# experiment outputs / local research notes
experiments/
research-notes/

# logs
*.log
```

## 最終判断

Phase 1〜7 は public でよい。

Phase 8 practice operation も public のままでよいが、実測ログ・実測成績は commit しない。

Phase 9 live migration 以降は、戦略ロジック・実パラメータ・実測レポートの公開範囲を再判断する。

本当に実測で優位性が出始めた場合は、戦略ロジックだけ private 化する。

長期的には、public repository は framework / sample strategy / tests / safety infrastructure を示す場所として維持し、本命strategy implementation、live strategy registry、allocation rule、実測レポートは private repository または local-only 管理へ分離する。
