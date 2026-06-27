# SalesPilot AI Streamlit MVP

OpenAI APIを使う前提の、SalesPilot AIのStreamlit版MVPです。

## できること

- 新規案件登録
- 進行中案件ダッシュボード
- 案件概要の編集
- 商談前リサーチ
- ヒアリング設計
- 商談メモ分析
- お礼メール生成
- 提案資料骨子生成
- タイムライン日付管理
- 受注・失注分析
- 月30案件 / AI利用300クレジットの利用制限

## ローカル起動

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Secrets設定

`.streamlit/secrets.toml` を作り、以下を設定します。

```toml
OPENAI_API_KEY = "sk-..."
OPENAI_MODEL_HIGH = "gpt-5.4"
OPENAI_MODEL_LIGHT = "gpt-5.4-mini"
MONTHLY_DEAL_LIMIT = 30
MONTHLY_AI_LIMIT = 300
APP_PASSWORD = "任意の招待制パスコード"
```

`secrets.toml` はGitHubにpushしないでください。

## Streamlit Community Cloud公開

1. このフォルダをGitHubにpushします。
2. Streamlit Community Cloudで `Create app` を押します。
3. GitHubリポジトリ、ブランチ、`app.py` を選びます。
4. Advanced settings の Secrets に上記の値を貼ります。
5. Deployします。

公開URLは `https://任意の名前.streamlit.app` になります。

## 注意

この初期版は `data/app_db.json` に保存します。Streamlit Cloudの再起動や再デプロイで保存データが消える可能性があります。
ベータ運用で顧客データを扱う場合は、Google SheetsまたはSupabase保存へ差し替えてください。

入力された情報は、ユーザーへのレスポンス生成にのみ活用し、ほかのユーザーへの回答や提案内容に再利用しない運用を前提にしてください。
