from __future__ import annotations

import html
import json
import re
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

import pandas as pd
import streamlit as st


APP_NAME = "SalesPilot AI"
DATA_DIR = Path("data")
DB_PATH = DATA_DIR / "app_db.json"


def get_secret(name: str, default: Any = None) -> Any:
    try:
        return st.secrets.get(name, default)
    except Exception:
        return default


MONTHLY_DEAL_LIMIT = int(get_secret("MONTHLY_DEAL_LIMIT", 30))
MONTHLY_AI_LIMIT = int(get_secret("MONTHLY_AI_LIMIT", 300))
HIGH_MODEL = get_secret("OPENAI_MODEL_HIGH", "gpt-5.4")
LIGHT_MODEL = get_secret("OPENAI_MODEL_LIGHT", "gpt-5.4-mini")

PHASES = [
    "コンタクト前",
    "初回商談/製品説明前",
    "2回目以降面談前/運用提案前",
    "検証/お試し/仮契約",
    "稟議",
    "受注",
    "失注",
    "ペンディング",
]

TIMELINE_PHASES = [
    "コンタクト前",
    "初回商談/製品説明前",
    "2回目以降面談前/運用提案前",
    "検証/お試し/仮契約",
    "稟議",
    "受注/失注",
    "フォロー",
]

CUSTOMER_SIZES = [
    "1～5",
    "6～10",
    "11～30",
    "31～50",
    "51～100",
    "101～300",
    "301～500",
    "501～1000",
    "1001～3000",
    "3000～5000",
    "5001～10000",
    "10000以上",
]

DEPARTMENTS = [
    "営業部",
    "経理部",
    "総務部",
    "人事部",
    "管理部",
    "企画部",
    "マーケティング部",
    "広報部",
    "情報システム部",
    "法務部",
    "財務部",
    "カスタマーサポート部",
    "事業部",
    "商品企画部",
    "開発部",
    "技術部",
    "製造部",
    "購買部",
    "物流部",
    "品質管理部",
    "その他",
]

CONTACT_ROLES = [
    "担当者",
    "主任",
    "係長",
    "課長",
    "次長",
    "部長",
    "本部長",
    "執行役員",
    "取締役",
    "代表取締役",
    "個人事業主",
    "その他",
]

BUDGET_RANGES = [
    "未定",
    "10万円未満",
    "10万～30万円",
    "30万～50万円",
    "50万～100万円",
    "100万～300万円",
    "300万～500万円",
    "500万～1000万円",
    "1000万円以上",
    "確認中",
]

TEMPERATURES = ["高い", "普通", "低い", "不明"]
MEETING_TYPES = ["訪問", "Web会議", "電話", "メール", "その他"]

AI_CREDIT_COSTS = {
    "product_summary": 1,
    "research": 1,
    "hearing": 1,
    "meeting_analysis": 1,
    "email": 1,
    "proposal_outline": 3,
    "win_loss_analysis": 2,
}

AI_LABELS = {
    "product_summary": "商材概要生成",
    "research": "商談前リサーチ",
    "hearing": "ヒアリング設計",
    "meeting_analysis": "商談メモ分析",
    "email": "メール生成",
    "proposal_outline": "提案資料骨子",
    "win_loss_analysis": "受注・失注分析",
}

SYSTEM_INSTRUCTIONS = """
あなたはBtoB法人営業に精通した営業戦略コンサルタントです。
日本語で、顧客にそのまま使える具体度で出力してください。

重要方針:
- ありきたりな一般論ではなく、企業規模、部署、担当者役職、ニーズ、予算、商談フェーズに合わせて戦略を作る。
- 製品を顧客に最も魅力的に見せるため、どの機能、どの運用、どの導入順が刺さるかを明確にする。
- 成果を断定しすぎず、未確認事項は未確認として明示する。
- "category" や "industry_issues" のような英語キーは使わず、日本人営業担当者に読みやすい見出しにする。
- 出力はMarkdownで、見出し・箇条書き・表を使って読みやすくする。
"""


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def month_key() -> str:
    return date.today().strftime("%Y-%m")


def empty_db() -> dict[str, Any]:
    return {"deals": [], "ai_outputs": [], "usage": {}}


def load_db() -> dict[str, Any]:
    DATA_DIR.mkdir(exist_ok=True)
    if not DB_PATH.exists():
        return empty_db()
    try:
        with DB_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError:
        return empty_db()
    data.setdefault("deals", [])
    data.setdefault("ai_outputs", [])
    data.setdefault("usage", {})
    return data


def save_db(db: dict[str, Any]) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    with DB_PATH.open("w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)


def get_usage(db: dict[str, Any]) -> dict[str, int]:
    usage = db.setdefault("usage", {}).setdefault(month_key(), {"deals": 0, "ai_credits": 0})
    usage.setdefault("deals", 0)
    usage.setdefault("ai_credits", 0)
    return usage


def active_deals(db: dict[str, Any]) -> list[dict[str, Any]]:
    return [deal for deal in db["deals"] if deal.get("status") == "active"]


def past_deals(db: dict[str, Any]) -> list[dict[str, Any]]:
    return [deal for deal in db["deals"] if deal.get("status") in {"won", "lost"}]


def find_deal(db: dict[str, Any], deal_id: str | None) -> dict[str, Any] | None:
    if not deal_id:
        return None
    return next((deal for deal in db["deals"] if deal["id"] == deal_id), None)


def update_deal(db: dict[str, Any], deal_id: str, patch: dict[str, Any]) -> None:
    deal = find_deal(db, deal_id)
    if not deal:
        return
    deal.update(patch)
    deal["updated_at"] = now_iso()


def latest_output(db: dict[str, Any], deal_id: str, output_type: str) -> dict[str, Any] | None:
    outputs = [
        output
        for output in db["ai_outputs"]
        if output["deal_id"] == deal_id and output["type"] == output_type
    ]
    return sorted(outputs, key=lambda item: item["created_at"], reverse=True)[0] if outputs else None


def outputs_for_deal(db: dict[str, Any], deal_id: str) -> list[dict[str, Any]]:
    outputs = [output for output in db["ai_outputs"] if output["deal_id"] == deal_id]
    return sorted(outputs, key=lambda item: item["created_at"], reverse=True)


def can_create_deal(db: dict[str, Any]) -> bool:
    return get_usage(db)["deals"] < MONTHLY_DEAL_LIMIT


def can_use_ai(db: dict[str, Any], credits: int) -> bool:
    return get_usage(db)["ai_credits"] + credits <= MONTHLY_AI_LIMIT


def register_ai_usage(db: dict[str, Any], credits: int) -> None:
    usage = get_usage(db)
    usage["ai_credits"] += credits


def register_deal_usage(db: dict[str, Any]) -> None:
    usage = get_usage(db)
    usage["deals"] += 1


def create_deal(db: dict[str, Any], deal: dict[str, Any]) -> dict[str, Any]:
    created = {
        "id": str(uuid.uuid4()),
        "title": f"{deal['customer_name']} × {deal['product_name']}",
        "status": "active",
        "win_probability": None,
        "timeline_dates": {},
        "created_at": now_iso(),
        "updated_at": now_iso(),
        **deal,
    }
    db["deals"].insert(0, created)
    register_deal_usage(db)
    save_db(db)
    return created


def add_ai_output(
    db: dict[str, Any],
    deal_id: str,
    output_type: str,
    prompt: str,
    output_text: str,
    model: str,
    credits: int,
) -> None:
    db["ai_outputs"].insert(
        0,
        {
            "id": str(uuid.uuid4()),
            "deal_id": deal_id,
            "type": output_type,
            "input_text": prompt,
            "output_text": output_text,
            "model": model,
            "credits": credits,
            "created_at": now_iso(),
        },
    )


def run_openai(prompt: str, quality: str = "high") -> tuple[str, str]:
    api_key = get_secret("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEYが未設定です。StreamlitのSecretsにAPIキーを登録してください。")

    from openai import OpenAI

    model = HIGH_MODEL if quality == "high" else LIGHT_MODEL
    client = OpenAI(api_key=api_key)
    response = client.responses.create(
        model=model,
        instructions=SYSTEM_INSTRUCTIONS,
        input=prompt,
    )
    text = getattr(response, "output_text", None)
    if not text:
        text = str(response)
    return text, model


def run_ai_and_store(
    db: dict[str, Any],
    deal: dict[str, Any],
    output_type: str,
    prompt: str,
    quality: str = "high",
) -> str:
    credits = AI_CREDIT_COSTS[output_type]
    if not can_use_ai(db, credits):
        raise RuntimeError(
            f"今月のAI利用上限を超えます。現在 {get_usage(db)['ai_credits']} / {MONTHLY_AI_LIMIT} クレジット利用済みです。"
        )

    output_text, model = run_openai(prompt, quality=quality)
    register_ai_usage(db, credits)
    add_ai_output(db, deal["id"], output_type, prompt, output_text, model, credits)
    save_db(db)
    return output_text


def format_date(value: str | None) -> str:
    return value if value else "未設定"


def deal_context(deal: dict[str, Any], db: dict[str, Any] | None = None) -> str:
    latest_research = latest_output(db, deal["id"], "research")["output_text"] if db and latest_output(db, deal["id"], "research") else ""
    latest_analysis = latest_output(db, deal["id"], "meeting_analysis")["output_text"] if db and latest_output(db, deal["id"], "meeting_analysis") else ""
    timeline = "\n".join(
        f"- {phase}: {date_value}"
        for phase, date_value in (deal.get("timeline_dates") or {}).items()
        if date_value
    )
    return f"""
案件名: {deal.get("title")}
顧客名: {deal.get("customer_name")}
業界: {deal.get("customer_industry")}
企業規模: {deal.get("customer_size")}
部署: {deal.get("department_name")}
担当者: {deal.get("contact_name")}
担当者役職: {deal.get("contact_role")}
提案商材: {deal.get("product_name")}
商材URL: {deal.get("product_url")}
提案商材概要: {deal.get("product_description")}
商談フェーズ: {deal.get("phase")}
温度感: {deal.get("temperature")}
予算感: {deal.get("budget")}
競合情報: {deal.get("competitor_info")}
次回予定日: {format_date(deal.get("next_meeting_date"))}
導入予定日（受注目標日）: {format_date(deal.get("target_close_date"))}
メモ: {deal.get("memo")}
タイムライン日付:
{timeline or "- 未設定"}

直近の商談前リサーチ:
{latest_research or "なし"}

直近の商談メモ分析:
{latest_analysis or "なし"}
""".strip()


def recommended_next_actions(db: dict[str, Any], deal: dict[str, Any]) -> list[str]:
    has_meeting_analysis = latest_output(db, deal["id"], "meeting_analysis") is not None
    if has_meeting_analysis or deal.get("phase") == "2回目以降面談前/運用提案前":
        return ["メール生成", "提案資料骨子"]
    if deal.get("phase") in {"コンタクト前", "初回商談/製品説明前"}:
        return ["商談前リサーチ", "ヒアリング設計", "商談メモ分析"]
    return ["商談メモ分析", "メール生成", "提案資料骨子"]


def timeline_status(deal: dict[str, Any]) -> list[dict[str, str]]:
    phase_alias = {"受注": "受注/失注", "失注": "受注/失注", "ペンディング": "フォロー"}
    current_phase = phase_alias.get(deal.get("phase"), deal.get("phase"))
    current_index = TIMELINE_PHASES.index(current_phase) if current_phase in TIMELINE_PHASES else 0
    dates = deal.get("timeline_dates") or {}
    rows = []
    for index, phase in enumerate(TIMELINE_PHASES):
        if index < current_index:
            status = "完了"
        elif index == current_index:
            status = "現在"
        else:
            status = "未着手"
        rows.append({"フェーズ": phase, "状態": status, "日付": dates.get(phase, "")})
    return rows


def extract_url_text(url: str) -> str:
    request = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 SalesPilotAI/1.0",
        },
    )
    try:
        with urlopen(request, timeout=8) as response:
            raw = response.read(300_000)
    except (URLError, TimeoutError, ValueError) as exc:
        raise RuntimeError(f"URLの取得に失敗しました: {exc}") from exc

    text = raw.decode("utf-8", errors="ignore")
    title = re.search(r"<title[^>]*>(.*?)</title>", text, re.I | re.S)
    description = re.search(
        r'<meta[^>]+name=["\']description["\'][^>]+content=["\'](.*?)["\']',
        text,
        re.I | re.S,
    )
    text = re.sub(r"<script.*?</script>|<style.*?</style>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    pieces = []
    if title:
        pieces.append(html.unescape(title.group(1)).strip())
    if description:
        pieces.append(html.unescape(description.group(1)).strip())
    pieces.append(text[:6000])
    return "\n".join(piece for piece in pieces if piece)


def build_product_summary_prompt(product_name: str, url: str, page_text: str) -> str:
    return f"""
以下の商材URLとページ本文から、BtoB営業の案件登録に使う「提案商材の概要」を100字程度で作成してください。
誇張せず、顧客に説明しやすい日本語にしてください。

商材名: {product_name}
商材URL: {url}
ページ本文:
{page_text}
""".strip()


def build_research_prompt(deal: dict[str, Any], context: dict[str, Any], db: dict[str, Any]) -> str:
    return f"""
以下の案件について、商談前リサーチではなく「商談戦略ノート」を作成してください。
目的は、提案商材を顧客に最も魅力的に見せることです。

特に、この企業規模・部署・顕在ニーズには、どの機能・運用・導入順が刺さるのかを具体化してください。

{deal_context(deal, db)}

追加情報:
- 商談時間: {context.get("meeting_minutes") or "未設定"}分
- 事前情報: {context.get("pre_meeting_info") or "未入力"}
- 顕在化しているニーズ: {context.get("visible_needs") or "未入力"}
- 要件: {context.get("requirements") or "未入力"}

出力形式:
# 商談戦略ノート
## 顧客の見立て
## 刺さる課題仮説
## 強く訴求すべき機能・運用
## 商談での打ち出し方
## 確認すべき質問
## 避けるべき言い方
## 推奨商談フロー
""".strip()


def build_hearing_prompt(deal: dict[str, Any], context: dict[str, Any], db: dict[str, Any]) -> str:
    return f"""
以下の案件について、ヒアリング設計を作成してください。
商談前リサーチ結果、時間配分、顧客の規模・部署・ニーズを反映し、質問のタイミングと優先順位が一目でわかるようにしてください。

{deal_context(deal, db)}

時間配分:
- 商談時間: {context.get("meeting_minutes") or "未設定"}分
- アイスブレイク/冒頭ヒアリング: {context.get("opening_minutes") or "未設定"}分
- 製品説明: {context.get("product_demo_minutes") or "未設定"}分
- 紹介後ヒアリング: {context.get("post_demo_hearing_minutes") or "未設定"}分
- クロージング/次回アクション合意: {context.get("closing_minutes") or "未設定"}分

出力形式:
# ヒアリング設計
## 商談全体の進め方
## 時間配分
## 優先質問リスト
各質問は「聞くタイミング」「優先度」「質問」「聞く意図」「想定回答」「深掘り返し」を含める。
## 製品説明前に必ず確認すること
## 製品説明後に確認すること
## クロージングで合意すること
""".strip()


def build_meeting_analysis_prompt(deal: dict[str, Any], context: dict[str, Any], db: dict[str, Any]) -> str:
    return f"""
以下の案件と商談メモを分析してください。
商談後に営業担当がすぐ次の行動に移れるよう、顧客ニーズ、受注確度、失注リスク、次回アクションを具体化してください。

{deal_context(deal, db)}

商談情報:
- 商談日時: {context.get("meeting_at") or "未設定"}
- 商談形式: {context.get("meeting_type") or "未設定"}
- 商談時間: {context.get("duration_minutes") or "未設定"}分
- 参加者: {context.get("participants") or "未入力"}
- 補足メモ: {context.get("supplemental_memo") or "未入力"}

商談メモ本文:
{context.get("transcript")}

出力形式:
# 商談メモ分析
## 要約
## 顧客ニーズ
## 顧客の反応
## 前向きなシグナル
## 失注リスクと対策
## 未確認事項
## 次回アクション
期日候補、優先度、誰がやるかを含める。
## 提案資料に入れるべき材料
## 営業アドバイス
## 受注確度の仮説
""".strip()


def build_email_prompt(deal: dict[str, Any], db: dict[str, Any]) -> str:
    return f"""
以下の案件について、商談後のお礼メールを作成してください。
丁寧版と簡潔版の2パターンを出してください。
顧客が次に動きやすいよう、次回アクションと添付資料候補を明確にしてください。

{deal_context(deal, db)}

出力形式:
# お礼メール案
## 丁寧版
- 件名
- 本文
- 添付資料候補
## 簡潔版
- 件名
- 本文
- 添付資料候補
""".strip()


def build_proposal_prompt(deal: dict[str, Any], context: dict[str, Any], db: dict[str, Any]) -> str:
    return f"""
以下の案件について、提案資料骨子を作成してください。
このアウトプットをChatGPTにそのまま貼り付ければ、提案資料が8割完成する粒度にしてください。

{deal_context(deal, db)}

提案資料作成条件:
- 次回商談時間: {context.get("next_meeting_minutes") or "未設定"}分
- 前回議事メモ分析入力: {context.get("previous_meeting_analysis") or "未入力"}
- 目的: {context.get("proposal_purpose") or "運用提案"}
- 想定参加者/決裁者: {context.get("expected_attendees") or "未入力"}
- 資料で最も伝えたいメッセージ: {context.get("key_message") or "未入力"}
- 必ず入れたい項目/スライド: {context.get("must_include_points") or "未入力"}
- 判断基準: {context.get("decision_criteria") or "未入力"}
- 予算/稟議条件: {context.get("budget_or_approval_conditions") or "未入力"}
- 競合・懸念・反論されそうな点: {context.get("competitor_or_concerns") or "未入力"}
- 資料提示後に合意したい次回アクション: {context.get("desired_next_action") or "未入力"}

出力形式:
# 提案資料骨子
## 資料タイトル案
## 今回の提案目的
## 課題の分析
案件概要、前回内容、顧客規模、部署、タイムラインをもとに、仮説で具体的に書く。
## 提案方針
## 今後のスケジュール
案件概要、導入予定日、タイムラインをもとに仮説で具体的に書く。
## スライド構成
各スライドごとに必ず以下を入れる。
- スライドタイトル
- 乗せる文章の骨子
- 実際に記載する内容
- 図解案
- 営業トーク
- 顧客に刺さる訴求ポイント
## 決裁者向け補足
## 競合・懸念への返し
## ChatGPTへの依頼文
この骨子からPowerPoint本文を作るための依頼文を最後に付ける。
""".strip()


def build_win_loss_prompt(deal: dict[str, Any], result_type: str, db: dict[str, Any]) -> str:
    result_label = "受注" if result_type == "won" else "失注"
    return f"""
以下の案件について、{result_label}理由を分析してください。
過去案件として再利用できる学び、次回提案に活かす改善点を明確にしてください。

{deal_context(deal, db)}

出力形式:
# {result_label}分析
## 結果の要約
## 主な要因
## 顧客が評価した/評価しなかったポイント
## 営業プロセス上の学び
## 次回以降の改善アクション
## 再アプローチ余地
""".strip()


def require_passcode() -> bool:
    password = get_secret("APP_PASSWORD")
    if not password:
        return True
    if st.session_state.get("authenticated"):
        return True
    st.title(APP_NAME)
    st.caption("招待制ベータ版")
    entered = st.text_input("パスコード", type="password")
    if st.button("ログイン"):
        if entered == password:
            st.session_state["authenticated"] = True
            st.rerun()
        st.error("パスコードが違います。")
    return False


def render_usage_banner(db: dict[str, Any]) -> None:
    usage = get_usage(db)
    deal_rate = min(usage["deals"] / MONTHLY_DEAL_LIMIT, 1.0)
    ai_rate = min(usage["ai_credits"] / MONTHLY_AI_LIMIT, 1.0)
    col1, col2 = st.columns(2)
    with col1:
        st.metric("今月の案件数", f"{usage['deals']} / {MONTHLY_DEAL_LIMIT}")
        st.progress(deal_rate)
    with col2:
        st.metric("今月のAI利用", f"{usage['ai_credits']} / {MONTHLY_AI_LIMIT} クレジット")
        st.progress(ai_rate)


def render_output(output: dict[str, Any] | None) -> None:
    if not output:
        st.info("まだ生成結果がありません。")
        return
    st.caption(f"モデル: {output.get('model')} / 消費: {output.get('credits')}クレジット / 生成日時: {output.get('created_at')}")
    st.markdown(output["output_text"])
    st.download_button(
        "Markdownとしてダウンロード",
        output["output_text"],
        file_name=f"{output['type']}_{output['created_at'].replace(':', '-')}.md",
        mime="text/markdown",
    )


def render_dashboard(db: dict[str, Any]) -> None:
    st.title("進行中案件ダッシュボード")
    render_usage_banner(db)

    deals = active_deals(db)
    if not deals:
        st.info("進行中案件はまだありません。左メニューの「新規案件登録」から追加してください。")
        return

    rows = []
    for deal in deals:
        next_actions = recommended_next_actions(db, deal)
        row = {
            "案件名": deal["title"],
            "顧客": deal["customer_name"],
            "商材": deal["product_name"],
            "フェーズ": deal["phase"],
            "次回アクション": " → ".join(next_actions),
            "次回予定": format_date(deal.get("next_meeting_date")),
            "受注目標": format_date(deal.get("target_close_date")),
        }
        dates = deal.get("timeline_dates") or {}
        for phase in TIMELINE_PHASES:
            row[phase] = dates.get(phase, "未設定")
        rows.append(row)

    st.subheader("案件別タイムスケジュール")
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    st.subheader("ネクストアクション")
    for deal in deals:
        with st.container(border=True):
            st.markdown(f"**{deal['title']}**")
            st.write(f"フェーズ: {deal['phase']} / 次回予定: {format_date(deal.get('next_meeting_date'))}")
            st.write("次にやること: " + " → ".join(recommended_next_actions(db, deal)))
            if st.button("この案件を開く", key=f"open-{deal['id']}"):
                st.session_state["selected_deal_id"] = deal["id"]
                st.session_state["page"] = "案件詳細"
                st.rerun()


def render_new_deal(db: dict[str, Any]) -> None:
    st.title("新規案件登録")
    usage = get_usage(db)
    st.caption(f"今月の登録数: {usage['deals']} / {MONTHLY_DEAL_LIMIT}")
    if not can_create_deal(db):
        st.error("今月の案件登録上限に達しています。")
        return

    if "new_product_description" not in st.session_state:
        st.session_state["new_product_description"] = ""

    col1, col2 = st.columns(2)
    with col1:
        customer_name = st.text_input("顧客名")
        customer_industry = st.text_input("顧客企業の業界")
        customer_size = st.selectbox("顧客企業規模", CUSTOMER_SIZES, index=3)
        department_name = st.selectbox("部署名", DEPARTMENTS, index=DEPARTMENTS.index("営業部"))
        contact_name = st.text_input("担当者名")
        contact_role = st.selectbox("担当者役職", CONTACT_ROLES, index=CONTACT_ROLES.index("担当者"))
    with col2:
        product_name = st.text_input("提案商材名")
        title = f"{customer_name} × {product_name}" if customer_name and product_name else "顧客名 × 提案商材名"
        st.text_input("案件名（自動生成）", value=title, disabled=True)
        product_url = st.text_input("商材URL", placeholder="https://example.com/product")
        if st.button("商材URLから概要を自動作成", disabled=not product_url):
            try:
                if not can_use_ai(db, AI_CREDIT_COSTS["product_summary"]):
                    st.error(
                        f"今月のAI利用上限を超えます。現在 {get_usage(db)['ai_credits']} / {MONTHLY_AI_LIMIT} クレジット利用済みです。"
                    )
                    return
                page_text = extract_url_text(product_url)
                prompt = build_product_summary_prompt(product_name, product_url, page_text)
                summary, _model = run_openai(prompt, quality="light")
                register_ai_usage(db, AI_CREDIT_COSTS["product_summary"])
                save_db(db)
                st.session_state["new_product_description"] = summary.strip()
                st.success("商材概要を作成しました。")
            except Exception as exc:
                st.error(str(exc))
        st.text_area("提案商材の概要", key="new_product_description", height=100)
        phase = st.selectbox("商談フェーズ", PHASES, index=0)
        temperature = st.selectbox("現在の温度感", TEMPERATURES, index=1)
        budget = st.selectbox("予算感", BUDGET_RANGES, index=0)

    col3, col4 = st.columns(2)
    with col3:
        next_meeting_date = st.date_input("次回予定日", value=None)
    with col4:
        target_close_date = st.date_input("導入予定日（受注目標日）", value=None)

    competitor_info = st.text_area("競合情報")
    memo = st.text_area("メモ")

    if st.button("案件を登録", type="primary"):
        if not customer_name or not customer_industry or not product_name or not st.session_state["new_product_description"]:
            st.error("顧客名、業界、提案商材名、提案商材の概要は必須です。")
            return
        deal = create_deal(
            db,
            {
                "customer_name": customer_name,
                "customer_industry": customer_industry,
                "customer_size": customer_size,
                "department_name": department_name,
                "contact_name": contact_name,
                "contact_role": contact_role,
                "product_name": product_name,
                "product_description": st.session_state["new_product_description"],
                "product_url": product_url,
                "phase": phase,
                "purpose": "案件の次回アクションを明確にする",
                "temperature": temperature,
                "budget": budget,
                "competitor_info": competitor_info,
                "next_meeting_date": next_meeting_date.isoformat() if next_meeting_date else "",
                "target_close_date": target_close_date.isoformat() if target_close_date else "",
                "memo": memo,
            },
        )
        st.session_state["selected_deal_id"] = deal["id"]
        st.session_state["page"] = "案件詳細"
        st.success("案件を登録しました。")
        st.rerun()


def select_deal(db: dict[str, Any], include_past: bool = False) -> dict[str, Any] | None:
    deals = db["deals"] if include_past else active_deals(db)
    if not deals:
        st.info("表示できる案件がありません。")
        return None
    selected_id = st.session_state.get("selected_deal_id")
    ids = [deal["id"] for deal in deals]
    index = ids.index(selected_id) if selected_id in ids else 0
    selected = st.selectbox(
        "案件を選択",
        deals,
        index=index,
        format_func=lambda deal: f"{deal['title']}（{deal['phase']}）",
    )
    st.session_state["selected_deal_id"] = selected["id"]
    return selected


def render_overview_tab(db: dict[str, Any], deal: dict[str, Any]) -> None:
    left, right = st.columns([2, 1])
    with left:
        with st.form(f"overview-{deal['id']}"):
            st.subheader("案件概要")
            title = st.text_input("案件名", value=deal["title"])
            customer_name = st.text_input("顧客名", value=deal["customer_name"])
            customer_industry = st.text_input("業界", value=deal["customer_industry"])
            customer_size = st.selectbox("企業規模", CUSTOMER_SIZES, index=CUSTOMER_SIZES.index(deal.get("customer_size", "31～50")) if deal.get("customer_size") in CUSTOMER_SIZES else 0)
            department_name = st.selectbox("部署", DEPARTMENTS, index=DEPARTMENTS.index(deal.get("department_name")) if deal.get("department_name") in DEPARTMENTS else 0)
            contact_name = st.text_input("担当者", value=deal.get("contact_name") or "")
            contact_role = st.selectbox("担当者役職", CONTACT_ROLES, index=CONTACT_ROLES.index(deal.get("contact_role")) if deal.get("contact_role") in CONTACT_ROLES else 0)
            product_name = st.text_input("提案商材", value=deal["product_name"])
            product_url = st.text_input("商材URL", value=deal.get("product_url") or "")
            product_description = st.text_area("提案商材の概要", value=deal.get("product_description") or "", height=100)
            phase = st.selectbox("商談フェーズ", PHASES, index=PHASES.index(deal.get("phase")) if deal.get("phase") in PHASES else 0)
            temperature = st.selectbox("温度感", TEMPERATURES, index=TEMPERATURES.index(deal.get("temperature")) if deal.get("temperature") in TEMPERATURES else 1)
            budget = st.selectbox("予算感", BUDGET_RANGES, index=BUDGET_RANGES.index(deal.get("budget")) if deal.get("budget") in BUDGET_RANGES else 0)
            next_meeting_date = st.text_input("次回予定日", value=deal.get("next_meeting_date") or "", placeholder="YYYY-MM-DD")
            target_close_date = st.text_input("導入予定日（受注目標日）", value=deal.get("target_close_date") or "", placeholder="YYYY-MM-DD")
            competitor_info = st.text_area("競合情報", value=deal.get("competitor_info") or "")
            memo = st.text_area("メモ", value=deal.get("memo") or "")
            submitted = st.form_submit_button("概要を保存", type="primary")
            if submitted:
                update_deal(
                    db,
                    deal["id"],
                    {
                        "title": title,
                        "customer_name": customer_name,
                        "customer_industry": customer_industry,
                        "customer_size": customer_size,
                        "department_name": department_name,
                        "contact_name": contact_name,
                        "contact_role": contact_role,
                        "product_name": product_name,
                        "product_url": product_url,
                        "product_description": product_description,
                        "phase": phase,
                        "temperature": temperature,
                        "budget": budget,
                        "next_meeting_date": next_meeting_date,
                        "target_close_date": target_close_date,
                        "competitor_info": competitor_info,
                        "memo": memo,
                    },
                )
                save_db(db)
                st.success("案件概要を保存しました。")
                st.rerun()

    with right:
        st.subheader("次回アクション")
        for index, action in enumerate(recommended_next_actions(db, deal), start=1):
            st.write(f"{index}. {action}")
        st.divider()
        st.subheader("ステータス変更")
        col1, col2, col3 = st.columns(3)
        if col1.button("受注"):
            update_deal(db, deal["id"], {"status": "won", "phase": "受注"})
            save_db(db)
            st.rerun()
        if col2.button("失注"):
            update_deal(db, deal["id"], {"status": "lost", "phase": "失注"})
            save_db(db)
            st.rerun()
        if col3.button("ペンディング"):
            update_deal(db, deal["id"], {"phase": "ペンディング"})
            save_db(db)
            st.rerun()
        st.divider()
        st.subheader("案件タイムライン")
        st.dataframe(pd.DataFrame(timeline_status(deal)), use_container_width=True, hide_index=True)


def render_research_tab(db: dict[str, Any], deal: dict[str, Any]) -> None:
    left, right = st.columns([1, 2])
    with left:
        st.subheader("商談前情報")
        meeting_minutes = st.number_input("商談時間（分）", min_value=1, value=45)
        pre_meeting_info = st.text_area("事前情報", height=120)
        visible_needs = st.text_area("顕在化しているニーズ", height=120)
        requirements = st.text_area("要件", height=120)
        if st.button("商談前リサーチを生成", type="primary"):
            context = {
                "meeting_minutes": meeting_minutes,
                "pre_meeting_info": pre_meeting_info,
                "visible_needs": visible_needs,
                "requirements": requirements,
            }
            try:
                with st.spinner("商談戦略ノートを生成しています..."):
                    run_ai_and_store(db, deal, "research", build_research_prompt(deal, context, db), quality="high")
                st.success("生成しました。")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))
    with right:
        render_output(latest_output(db, deal["id"], "research"))


def render_hearing_tab(db: dict[str, Any], deal: dict[str, Any]) -> None:
    left, right = st.columns([1, 2])
    with left:
        st.subheader("ヒアリング時間配分")
        meeting_minutes = st.number_input("商談時間（分）", min_value=1, value=45)
        opening_minutes = st.number_input("うちアイスブレイク/冒頭ヒアリング時間（分）", min_value=0, value=5)
        product_demo_minutes = st.number_input("うち製品説明時間（分）", min_value=0, value=15)
        post_demo_hearing_minutes = st.number_input("うち紹介後ヒアリング時間（分）", min_value=0, value=15)
        closing_minutes = st.number_input("うちクロージング/次回アクション合意時間（分）", min_value=0, value=10)
        if st.button("ヒアリング設計を生成", type="primary"):
            context = {
                "meeting_minutes": meeting_minutes,
                "opening_minutes": opening_minutes,
                "product_demo_minutes": product_demo_minutes,
                "post_demo_hearing_minutes": post_demo_hearing_minutes,
                "closing_minutes": closing_minutes,
            }
            try:
                with st.spinner("ヒアリング設計を生成しています..."):
                    run_ai_and_store(db, deal, "hearing", build_hearing_prompt(deal, context, db), quality="high")
                st.success("生成しました。")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))
    with right:
        render_output(latest_output(db, deal["id"], "hearing"))


def render_meeting_tab(db: dict[str, Any], deal: dict[str, Any]) -> None:
    left, right = st.columns([1, 2])
    with left:
        st.subheader("商談メモ貼り付け")
        meeting_at = st.text_input("商談日時", placeholder="2026-07-01 10:00")
        meeting_type = st.selectbox("商談形式", MEETING_TYPES, index=1)
        duration_minutes = st.number_input("商談時間（分）", min_value=1, value=45)
        participants = st.text_input("参加者")
        transcript = st.text_area("商談メモ本文", height=260)
        supplemental_memo = st.text_area("補足メモ", height=100)
        if st.button("商談メモを分析", type="primary"):
            if not transcript:
                st.error("商談メモ本文を入力してください。")
                return
            context = {
                "meeting_at": meeting_at,
                "meeting_type": meeting_type,
                "duration_minutes": duration_minutes,
                "participants": participants,
                "transcript": transcript,
                "supplemental_memo": supplemental_memo,
            }
            try:
                with st.spinner("商談メモを分析しています..."):
                    run_ai_and_store(db, deal, "meeting_analysis", build_meeting_analysis_prompt(deal, context, db), quality="high")
                update_deal(db, deal["id"], {"phase": "2回目以降面談前/運用提案前"})
                save_db(db)
                st.success("分析しました。フェーズを「2回目以降面談前/運用提案前」に更新しました。")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))
    with right:
        render_output(latest_output(db, deal["id"], "meeting_analysis"))


def render_email_tab(db: dict[str, Any], deal: dict[str, Any]) -> None:
    if st.button("お礼メールを生成", type="primary"):
        try:
            with st.spinner("メール文面を生成しています..."):
                run_ai_and_store(db, deal, "email", build_email_prompt(deal, db), quality="light")
            st.success("生成しました。")
            st.rerun()
        except Exception as exc:
            st.error(str(exc))
    render_output(latest_output(db, deal["id"], "email"))


def render_proposal_tab(db: dict[str, Any], deal: dict[str, Any]) -> None:
    left, right = st.columns([1, 2])
    meeting_analysis = latest_output(db, deal["id"], "meeting_analysis")
    with left:
        st.subheader("提案資料作成条件")
        next_meeting_minutes = st.number_input("次回商談時間（分）", min_value=1, value=45)
        previous_meeting_analysis = st.text_area(
            "前回議事メモ分析入力",
            value=meeting_analysis["output_text"] if meeting_analysis else "",
            height=180,
        )
        proposal_purpose = st.selectbox("目的", ["決裁者面談", "運用提案", "稟議用資料"], index=1)
        expected_attendees = st.text_input("想定参加者/決裁者", placeholder="例: 部長、現場責任者、経営層")
        key_message = st.text_area("資料で最も伝えたいメッセージ", height=90)
        must_include_points = st.text_area("必ず入れたい項目/スライド", height=90)
        decision_criteria = st.text_area("判断基準", height=90)
        budget_or_approval_conditions = st.text_area("予算/稟議条件", height=90)
        competitor_or_concerns = st.text_area("競合・懸念・反論されそうな点", height=90)
        desired_next_action = st.text_input("資料提示後に合意したい次回アクション")
        if st.button("提案資料骨子を生成", type="primary"):
            context = {
                "next_meeting_minutes": next_meeting_minutes,
                "previous_meeting_analysis": previous_meeting_analysis,
                "proposal_purpose": proposal_purpose,
                "expected_attendees": expected_attendees,
                "key_message": key_message,
                "must_include_points": must_include_points,
                "decision_criteria": decision_criteria,
                "budget_or_approval_conditions": budget_or_approval_conditions,
                "competitor_or_concerns": competitor_or_concerns,
                "desired_next_action": desired_next_action,
            }
            try:
                with st.spinner("提案資料骨子を生成しています..."):
                    run_ai_and_store(db, deal, "proposal_outline", build_proposal_prompt(deal, context, db), quality="high")
                st.success("生成しました。")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))
    with right:
        render_output(latest_output(db, deal["id"], "proposal_outline"))
        st.link_button("ChatGPTを開く", "https://chatgpt.com/")


def render_timeline_tab(db: dict[str, Any], deal: dict[str, Any]) -> None:
    st.subheader("タイムライン")
    st.caption("各フェーズに日付を入力できます。商談メモ分析後は、次回予定日や受注目標日を自動反映できます。")
    dates = dict(deal.get("timeline_dates") or {})

    if st.button("商談メモから期日を自動反映"):
        current_phase = deal.get("phase") if deal.get("phase") in TIMELINE_PHASES else "2回目以降面談前/運用提案前"
        if deal.get("next_meeting_date"):
            dates[current_phase] = deal["next_meeting_date"]
        if deal.get("target_close_date"):
            dates["受注/失注"] = deal["target_close_date"]
        update_deal(db, deal["id"], {"timeline_dates": dates})
        save_db(db)
        st.success("日付を反映しました。")
        st.rerun()

    with st.form(f"timeline-{deal['id']}"):
        for phase in TIMELINE_PHASES:
            dates[phase] = st.text_input(phase, value=dates.get(phase, ""), placeholder="YYYY-MM-DD")
        if st.form_submit_button("タイムラインを保存", type="primary"):
            update_deal(db, deal["id"], {"timeline_dates": dates})
            save_db(db)
            st.success("タイムラインを保存しました。")
            st.rerun()

    st.dataframe(pd.DataFrame(timeline_status({**deal, "timeline_dates": dates})), use_container_width=True, hide_index=True)


def render_winloss_tab(db: dict[str, Any], deal: dict[str, Any]) -> None:
    col1, col2 = st.columns(2)
    result = "won" if col1.button("受注分析を生成") else None
    result = "lost" if col2.button("失注分析を生成") else result
    if result:
        try:
            with st.spinner("過去案件分析を生成しています..."):
                run_ai_and_store(db, deal, "win_loss_analysis", build_win_loss_prompt(deal, result, db), quality="high")
            update_deal(db, deal["id"], {"status": result, "phase": "受注" if result == "won" else "失注"})
            save_db(db)
            st.success("分析しました。")
            st.rerun()
        except Exception as exc:
            st.error(str(exc))
    render_output(latest_output(db, deal["id"], "win_loss_analysis"))


def render_detail(db: dict[str, Any]) -> None:
    st.title("案件詳細")
    deal = select_deal(db, include_past=True)
    if not deal:
        return
    st.caption(f"{deal['customer_name']} / {deal['product_name']} / フェーズ: {deal['phase']}")
    tabs = st.tabs(
        [
            "概要",
            "商談前リサーチ",
            "ヒアリング設計",
            "商談メモ分析",
            "メール生成",
            "提案資料骨子",
            "タイムライン",
            "受注・失注分析",
            "生成履歴",
        ]
    )
    with tabs[0]:
        render_overview_tab(db, deal)
    with tabs[1]:
        render_research_tab(db, deal)
    with tabs[2]:
        render_hearing_tab(db, deal)
    with tabs[3]:
        render_meeting_tab(db, deal)
    with tabs[4]:
        render_email_tab(db, deal)
    with tabs[5]:
        render_proposal_tab(db, deal)
    with tabs[6]:
        render_timeline_tab(db, deal)
    with tabs[7]:
        render_winloss_tab(db, deal)
    with tabs[8]:
        for output in outputs_for_deal(db, deal["id"]):
            with st.expander(f"{AI_LABELS.get(output['type'], output['type'])} / {output['created_at']}"):
                render_output(output)


def render_past_deals(db: dict[str, Any]) -> None:
    st.title("過去案件分析")
    deals = past_deals(db)
    if not deals:
        st.info("受注または失注に変更した案件がここに表示されます。")
        return
    rows = [
        {
            "案件名": deal["title"],
            "結果": "受注" if deal["status"] == "won" else "失注",
            "顧客": deal["customer_name"],
            "商材": deal["product_name"],
            "予算感": deal.get("budget"),
            "更新日": deal.get("updated_at"),
        }
        for deal in deals
    ]
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    st.divider()
    deal = select_deal({"deals": deals, "ai_outputs": db["ai_outputs"], "usage": db["usage"]}, include_past=True)
    if deal:
        render_winloss_tab(db, deal)


def render_usage(db: dict[str, Any]) -> None:
    st.title("利用状況")
    render_usage_banner(db)
    st.write("料金設計の前提: Proプラン 月30案件 / AI利用300クレジット")
    st.table(
        pd.DataFrame(
            [
                {"AI機能": AI_LABELS[key], "消費クレジット": value}
                for key, value in AI_CREDIT_COSTS.items()
            ]
        )
    )
    st.info(
        "このツール内で入力された情報は、入力したユーザーへのレスポンス生成にのみ利用する前提です。"
        "ほかのユーザーへの回答や提案内容に再利用しない運用で公開してください。"
    )


def render_deploy_guide() -> None:
    st.title("公開までの手順")
    st.markdown(
        """
### 1. GitHubにアップロード
この `salespilot-streamlit` フォルダをGitHubリポジトリにpushします。

### 2. Streamlit Community Cloudでアプリ作成
Streamlitにログインして、GitHubリポジトリ、ブランチ、`app.py` を選びます。

### 3. Secretsを設定
StreamlitのAdvanced settingsに以下を登録します。

```toml
OPENAI_API_KEY = "sk-..."
OPENAI_MODEL_HIGH = "gpt-5.4"
OPENAI_MODEL_LIGHT = "gpt-5.4-mini"
MONTHLY_DEAL_LIMIT = 30
MONTHLY_AI_LIMIT = 300
APP_PASSWORD = "任意の招待制パスコード"
```

### 4. Deploy
公開URLは `https://任意の名前.streamlit.app` になります。

### 注意
この初期版はJSONファイル保存です。Streamlit Cloudの再起動や再デプロイで保存データが消える可能性があります。
実ユーザー運用に入る前に、Google SheetsまたはSupabase保存へ差し替えるのがおすすめです。
"""
    )


def main() -> None:
    st.set_page_config(page_title=APP_NAME, layout="wide")
    st.markdown(
        """
        <style>
        .block-container { padding-top: 1.6rem; }
        div[data-testid="stMetric"] { background: #f8fafc; border: 1px solid #e2e8f0; padding: 12px; border-radius: 8px; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    if not require_passcode():
        return

    db = load_db()
    st.sidebar.title(APP_NAME)
    st.sidebar.caption("Streamlit MVP")
    pages = ["ダッシュボード", "新規案件登録", "案件詳細", "過去案件分析", "利用状況", "公開手順"]
    default_page = st.session_state.get("page", "ダッシュボード")
    page = st.sidebar.radio("メニュー", pages, index=pages.index(default_page) if default_page in pages else 0, key="page")
    st.sidebar.divider()
    st.sidebar.caption("セキュリティ/注意事項")
    st.sidebar.write("入力情報は、このユーザーへのAIレスポンス生成にのみ利用する前提です。")

    if page == "ダッシュボード":
        render_dashboard(db)
    elif page == "新規案件登録":
        render_new_deal(db)
    elif page == "案件詳細":
        render_detail(db)
    elif page == "過去案件分析":
        render_past_deals(db)
    elif page == "利用状況":
        render_usage(db)
    else:
        render_deploy_guide()


if __name__ == "__main__":
    main()
