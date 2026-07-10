# SideBiz Autopilot MVP

ゲーム・AI・創作を中心に、毎日1件の成果物候補をAIが作成し、GitHub Issueで人間が承認したものだけGitHub Pagesへ公開する無料優先のMVPです。

## このMVPでできること

1. 毎朝7:00（日本時間）にGitHub Actionsが起動
2. GitHub Modelsで記事・SNS文・ショート動画台本・確認項目を生成
3. `drafts/` に下書きを保存
4. GitHub Issueに「本日の確認候補」を1件作成
5. あなたがスマホまたはPCで確認
6. Issueに `approve` ラベルを付ける
7. 承認済み記事だけ `docs/posts/` に移動
8. GitHub Pagesへ自動公開

## 重要な設計方針

- 無確認の自動公開はしません。
- 毎日の確認対象は原則1件です。
- 画像確認、権利確認、数値・出典確認を優先表示します。
- AI APIが失敗した場合は、テンプレート下書きを作り、ワークフロー自体は止めません。
- マスコット「ピコロン」をサイト案内役として採用しています。
- 初期段階では記事公開までを自動化し、YouTube投稿や外部販売は第2段階で追加します。

## マスコット：ピコロン

小さなダンジョン探索ロボット。丸いコンパス型の胴体、アンテナ、短い手足、背中に小さな巻物ケースを持っています。

役割：
- サイトとサムネイルの統一感を作る
- 記事カテゴリーを表情や持ち物で示す
- 画像生成時の確認対象を固定し、チェック時間を減らす
- 将来のゲーム、漫画、動画、グッズへ横展開する

初期版には簡易SVGロゴを同梱しています。正式な三面図・表情差分・ポーズ集は、運用開始後に制作してください。

## 初期設定

### 1. GitHubで新しいリポジトリを作る

例：`sidebiz-autopilot`

このフォルダの中身をすべてアップロードします。

### 2. GitHub Pagesを有効化

`Settings` → `Pages` → `Build and deployment` → `Source` を `GitHub Actions` にします。

### 3. Actionsの権限を設定

`Settings` → `Actions` → `General` → `Workflow permissions`

`Read and write permissions` を選びます。

### 4. ラベルを作る

Issuesで次のラベルを作成します。

- `review`
- `approve`
- `reject`
- `needs-fix`

### 5. GitHub Modelsの利用

ワークフローはリポジトリの `GITHUB_TOKEN` を使います。GitHub Modelsの無料利用枠が利用できるアカウントでは追加APIキー不要です。

既定モデルは `openai/gpt-4.1-mini` です。利用できない場合は `config/settings.json` の `model` を、GitHub Modelsカタログで利用可能なモデルIDへ変更してください。

## 毎日の使い方

1. GitHubの `Issues` を開く
2. `review` ラベルのIssueを1件確認
3. タイトル、要約、画像確認項目、出典確認項目を見る
4. 問題なければ `approve` ラベルを追加
5. 修正が必要ならコメントを書き、`needs-fix` を追加
6. 公開しない場合は `reject` を追加

承認後、`Publish approved content` ワークフローを手動実行するか、次の定期実行を待ちます。

## 収益化の追加場所

`config/settings.json` の `affiliate_disclosure` と `default_cta` を編集します。

記事本文のアフィリエイト候補はAIが提案しますが、実際のリンクは必ずあなたが契約済みの正規リンクへ置き換えてください。

## 第2段階で追加する機能

- Google Search Consoleの実績取得
- YouTube動画の自動生成・限定公開アップロード
- 承認画面からの修正指示再生成
- WordPressへの自動投稿
- Kindle原稿の月次編集
- BOOTH商品説明・ZIP商品の自動作成
- マスコットの正式画像セット
- 売上・クリック実績によるテーマ自動改善

## 注意

GitHub Modelsの無料枠は試作向けで、レート制限があります。運用が伸びた場合は、利用量を抑えるか、有料APIへ切り替える設計にしてください。

GitHub Pagesは静的サイトです。会員機能、決済、秘密情報の保存には使わないでください。
