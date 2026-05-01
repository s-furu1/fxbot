# fxbot

OANDA v20 APIを利用した24時間稼働のFXアルゴリズムトレードbot。
複数の独立戦略を並列稼働させ、**異なる構造クラスを跨いだ60秒以内の同期発火（コンフルエンス）**を機械的に検知してエントリーする設計。
ホームサーバー上でDockerコンテナとして稼働させる。

> このリポジトリはアプリケーション本体です。
> サーバー上での稼働設定は `homeserver/docker/fxbot/` を参照してください。

---

## 設計思想

「人間の脳では把握しきれない複数戦略の同期発火を機械的に検知することで、勝率と分布安定性を両面で改善できるか」を検証する。

機械の本質的な強みを「速度」や「24時間稼働」ではなく、**人間の認知容量を超えた次元の同時並列監視能力**と定義する。

本リポジトリは単なる自動売買botではなく、**条件付き期待値の比較実験**として設計されている。実エントリーしないシグナルもすべて記録し、コンフルエンス機構の寄与を勝率・分布両面で定量的に証明できる構造とする。

---

## コンセプト

本プロジェクトでは、複数の独立した売買シグナルを並列に監視し、一定時間内に同方向のシグナルが重なった場合の優位性を検証します。

単にシグナル発生時にエントリーするのではなく、以下を重視します。

- 実エントリーしなかったシグナルも記録する
- 実エントリーと条件付きランダムベースラインを比較する
- 勝率だけでなく、期待値・ドローダウン・連敗分布も評価する
- practice / live の環境混同を構造的に防ぐ
- dry-run → practice → live の段階的な移行を前提にする


---

## Features

- OANDA v20 API integration
- Docker / GHCR によるコンテナ配布
- SQLite による取引・シグナル・拒否理由ログ
- practice / live の環境分離
- 起動時の環境整合性チェック
- heartbeat によるコンテナ healthcheck
- dry-run / practice / live の段階的運用
- 条件付きランダムベースラインとの比較
- entry rejection logging
- R-multiple を基準にした評価
- ノンパラメトリック統計検定を用いた評価設計

---

## Safety Design

金銭リスクを持つシステムであるため、実装上は安全側の制約を優先します。

- `.env` はソースコードと分離する
- practice / live の環境不一致を起動時に検出する
- live切替時は明示的な確認文字列を要求する
- DBは環境ごとに物理的に分離する
- 起動時に既存ポジションがある場合、v1では起動を拒否する
- heartbeatにより、プロセス停止を外部監視できるようにする
- 実取引ログ・実パラメータ・実測成績はコミットしない

---

## Repository Scope

このリポジトリに含めるもの：

- アプリケーション本体
- シグナル監視基盤
- コンフルエンス判定基盤
- 起動時ガード
- ログスキーマ
- 評価指標定義
- フィルタ設計
- migration設計
- dry-run前提の実装
- Docker / CI 設定
- テストコード

このリポジトリに含めないもの：

- APIキー
- Account ID
- Slack Webhook URL
- `.env`
- 実取引ログ
- SQLite DB
- 本番運用ログ
- 実損益レポート
- 実測で優位性が出た条件
- 本番で使う正確なパラメータ
- live運用設定

---

## Documents

| Document | Purpose |
|---|---|
| `docs/schema.md` | SQLiteログスキーマ |
| `docs/metrics.md` | 評価指標・統計判定 |
| `docs/filters.md` | フィルタ・閾値ロジック |
| `docs/migration.md` | practice/live 環境移行 |
| `docs/implementation-plan.md` | 実装順序・PR分割 |
| `docs/publication-policy.md` | 公開範囲・非公開範囲 |
| `docs/internal-design.md` | 内部設計メモ |

`docs/internal-design.md` には、公開範囲の判断が必要な内部設計情報を含みます。  
Phase 8以降、実測で優位性が確認された場合、またはlive運用に移行する場合は、private化または削除を検討します。

---

## Directory Structure

```text
fxbot/
├── docs/
│   ├── schema.md
│   ├── metrics.md
│   ├── filters.md
│   ├── migration.md
│   ├── implementation-plan.md
│   ├── publication-policy.md
│   └── internal-design.md
├── src/
│   └── fxbot/
├── scripts/
├── tests/
├── Dockerfile
├── pyproject.toml
├── .env.example
└── README.md
```

---

## Deployment Policy

アプリケーション本体とサーバー運用定義は分離します。

```text
~/projects/fxbot
  アプリケーション本体・Dockerfile・テスト・仕様書

~/homeserver/docker/fxbot
  compose.yaml・環境変数・データボリューム
```

自宅サーバー上では、GHCRから固定タグのDockerイメージをpullして起動します。  
サーバー側にアプリケーションソースは置きません。

---

## Status

Experimental / under development.

Phase 1〜7では、主に実装基盤・安全設計・dry-run運用を対象とします。  
Phase 8以降のpractice運用、Phase 9以降のlive移行では、公開範囲を再確認します。