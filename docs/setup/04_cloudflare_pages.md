# 手順4: Cloudflare Pagesでの記事・LP公開(フェーズ5で使用)

**この手順は今すぐ実行する必要はありません。** フェーズ5(比較記事・LP公開)に進むタイミングで
改めてお声がけします。ここでは、後で迷わないように方針だけ先に確定しておきます。

## 採用した方針(ご指定の条件を反映)

- GitHubリポジトリは **Private のまま**(Cloudflare PagesはPrivateリポジトリにも接続できます)。
- ホスティングは **GitHub Pagesではなく Cloudflare Pages の無料プラン** を使用。
- 新しいドメインは購入しない。まずは Cloudflare が無料で発行する
  `https://(プロジェクト名).pages.dev` というURLで動作確認する。
- サーバー費用はかけない(Cloudflare Pagesの静的ホスティングは無料枠内で完結)。
- HTTPSは自動的に有効になる(Cloudflareが自動でSSL証明書を発行)。
- **GitHubへの更新が反映されたら自動公開**する(Gitリポジトリ連携による自動ビルド・自動デプロイ)。
- **テスト環境と本番環境を分ける**: Cloudflare Pagesは標準機能として、
  - `main`ブランチへの反映 → 本番環境(Production)
  - それ以外のブランチやPull Request → プレビュー環境(Preview。専用の一時URLが自動発行される)
  という仕組みを持っているため、追加費用なくテスト/本番を分けられます。
- 独自ドメイン(`media.lifterworks.com`)への接続は、動作確認が済んだ後、
  DNS設定が必要になった時点で画面単位で案内します(ここでは実施しません)。

## フェーズ5で実施する手順(概要・実行はそのタイミングで)

1. `https://dash.cloudflare.com` でCloudflareアカウントを作成(無料)する。
2. 左メニューの「**Workers & Pages**」→「**Create application**」→「**Pages**」タブを開く。
3. 「**Connect to Git**」を選び、GitHubアカウントを連携する
   (Cloudflare用のGitHub Appのインストール画面が出るので、対象リポジトリを選択して許可する)。
4. このリポジトリ(`-ai-recruiting-media-agent`)を選択する。
5. ビルド設定で、公開するフォルダとして `site` を指定する(このフォルダに記事・LPのHTMLを置く)。
6. 「Production branch」が `main`(またはこのリポジトリの開発ブランチ)になっていることを確認する。
7. デプロイを実行し、発行された `xxxx.pages.dev` のURLにアクセスして表示を確認する。
8. 動作確認ができたら、独自サブドメイン `media.lifterworks.com` を接続するかどうかを判断する
   (接続する場合、`lifterworks.com` のDNS管理画面での設定が必要になるため、その時点で
   画面単位の手順を改めてお渡しします)。

## 確認方法(フェーズ5実施時)

- `main`ブランチに変更をpushしてから数分以内に、`xxxx.pages.dev` の内容が更新されることを確認する。
- 別ブランチにpushした場合は、本番URLではなく、Cloudflareが発行するプレビュー専用URLに
  反映されることを確認する(本番環境に影響しないことの確認)。
