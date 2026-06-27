from __future__ import annotations

import html
import hashlib
import hmac
import json
import re
import secrets as py_secrets
import string
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
NAV_KEY = "active_page"
NAV_REQUEST_KEY = "requested_page"
FOCUS_ACTION_KEY = "focus_action"
DETAIL_VIEW_KEY = "detail_view"
PAGE_QUERY_KEY = "page"
PUBLIC_PAGES = ["サービス登録", "ログイン"]
PROTECTED_PAGES = ["マイページ", "ダッシュボード", "新規案件登録", "案件詳細", "過去案件分析", "利用状況", "公開手順"]
PLAN_NAME = "SalesPilot AI スタータープラン"
PLAN_PRICE_YEN = 1500
PLAN_INTERVAL = "月額"


def get_secret(name: str, default: Any = None) -> Any:
    try:
        return st.secrets.get(name, default)
    except Exception:
        return default


MONTHLY_DEAL_LIMIT = int(get_secret("MONTHLY_DEAL_LIMIT", 30))
MONTHLY_AI_LIMIT = int(get_secret("MONTHLY_AI_LIMIT", 300))
HIGH_MODEL = get_secret("OPENAI_MODEL_HIGH", "gpt-5.4")
LIGHT_MODEL = get_secret("OPENAI_MODEL_LIGHT", "gpt-5.4-mini")
MAX_PROMPT_CHARS = int(get_secret("MAX_PROMPT_CHARS", 24_000))
LONG_PROMPT_SUMMARY_CHARS = int(get_secret("LONG_PROMPT_SUMMARY_CHARS", 18_000))
SHORT_INPUT_CONFIRM_CHARS = int(get_secret("SHORT_INPUT_CONFIRM_CHARS", 12_000))
DEFAULT_QUALITY_MODE = get_secret("DEFAULT_QUALITY_MODE", "標準")

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
    "output_refinement": 1,
}

AI_LABELS = {
    "product_summary": "商材概要生成",
    "research": "商談前リサーチ",
    "hearing": "ヒアリング設計",
    "meeting_analysis": "商談メモ分析",
    "email": "メール生成",
    "proposal_outline": "提案資料骨子",
    "win_loss_analysis": "受注・失注分析",
    "output_refinement": "出力の整形・部分修正",
}

OUTPUT_TOKEN_LIMITS = {
    "product_summary": 260,
    "research": 1500,
    "hearing": 1600,
    "meeting_analysis": 1600,
    "email": 750,
    "proposal_outline": 2600,
    "win_loss_analysis": 1200,
    "output_refinement": 900,
}

QUALITY_MODES = ["エコノミー", "標準", "高品質"]

ACTION_TO_TAB = {
    "商談前リサーチ": "商談前リサーチ",
    "ヒアリング設計": "ヒアリング設計",
    "商談メモ分析": "商談メモ分析",
    "メール生成": "メール生成",
    "提案資料骨子": "提案資料骨子",
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
    return {"deals": [], "ai_outputs": [], "usage": {}, "url_cache": {}, "ai_cache": {}, "users": [], "subscription_events": []}


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
    data.setdefault("url_cache", {})
    data.setdefault("ai_cache", {})
    data.setdefault("users", [])
    data.setdefault("subscription_events", [])
    return data


def save_db(db: dict[str, Any]) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    with DB_PATH.open("w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)


def current_user_id() -> str | None:
    return st.session_state.get("user_id")


def current_user(db: dict[str, Any]) -> dict[str, Any] | None:
    user_id = current_user_id()
    if not user_id:
        return None
    return next((user for user in db.get("users", []) if user.get("id") == user_id), None)


def usage_key() -> str:
    user_id = current_user_id()
    return f"{month_key()}:{user_id}" if user_id else month_key()


def generate_user_id(db: dict[str, Any]) -> str:
    existing = {user.get("login_id") for user in db.get("users", [])}
    alphabet = string.ascii_uppercase + string.digits
    while True:
        suffix = "".join(py_secrets.choice(alphabet) for _ in range(6))
        login_id = f"SP-{date.today().strftime('%y%m')}-{suffix}"
        if login_id not in existing:
            return login_id


def generate_initial_password() -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(py_secrets.choice(alphabet) for _ in range(12))


def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    salt = salt or py_secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120_000)
    return salt, digest.hex()


def verify_password(password: str, salt: str, password_hash: str) -> bool:
    _, candidate = hash_password(password, salt)
    return hmac.compare_digest(candidate, password_hash)


def find_user_by_login(db: dict[str, Any], login: str) -> dict[str, Any] | None:
    normalized = login.strip().lower()
    return next(
        (
            user
            for user in db.get("users", [])
            if user.get("login_id", "").lower() == normalized or user.get("email", "").lower() == normalized
        ),
        None,
    )


def user_data_visible(deal: dict[str, Any]) -> bool:
    user_id = current_user_id()
    if st.session_state.get("admin_authenticated"):
        return True
    if not user_id:
        return False
    return deal.get("owner_user_id") == user_id


def get_usage(db: dict[str, Any]) -> dict[str, int]:
    usage = db.setdefault("usage", {}).setdefault(usage_key(), {"deals": 0, "ai_credits": 0})
    usage.setdefault("deals", 0)
    usage.setdefault("ai_credits", 0)
    return usage


def active_deals(db: dict[str, Any]) -> list[dict[str, Any]]:
    return [deal for deal in db["deals"] if deal.get("status") == "active" and user_data_visible(deal)]


def past_deals(db: dict[str, Any]) -> list[dict[str, Any]]:
    return [deal for deal in db["deals"] if deal.get("status") in {"won", "lost"} and user_data_visible(deal)]


def status_for_phase(phase: str, current_status: str = "active") -> str:
    if phase == "受注":
        return "won"
    if phase == "失注":
        return "lost"
    if phase != "ペンディング":
        return "active"
    return current_status or "active"


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


def normalize_url(url: str) -> str:
    return url.strip().rstrip("/")


def create_deal(db: dict[str, Any], deal: dict[str, Any]) -> dict[str, Any]:
    created = {
        "id": str(uuid.uuid4()),
        "owner_user_id": current_user_id(),
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
            "owner_user_id": current_user_id(),
            "type": output_type,
            "input_text": prompt,
            "output_text": output_text,
            "model": model,
            "credits": credits,
            "created_at": now_iso(),
        },
    )


def cache_key_for(output_type: str, prompt: str, quality: str, max_output_tokens: int | None) -> str:
    raw = json.dumps(
        {
            "type": output_type,
            "quality": quality,
            "max_output_tokens": max_output_tokens,
            "user_id": current_user_id() or "public",
            "prompt": trim_prompt(prompt),
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def get_cached_ai_output(db: dict[str, Any], key: str) -> dict[str, Any] | None:
    return db.setdefault("ai_cache", {}).get(key)


def set_cached_ai_output(db: dict[str, Any], key: str, output_text: str, model: str) -> None:
    db.setdefault("ai_cache", {})[key] = {
        "output_text": output_text,
        "model": model,
        "created_at": now_iso(),
    }


def trim_prompt(prompt: str) -> str:
    if len(prompt) <= MAX_PROMPT_CHARS:
        return prompt
    head = prompt[:4000]
    tail = prompt[-(MAX_PROMPT_CHARS - 4300):]
    return (
        f"{head}\n\n"
        "[注: 入力が長いため、中央部分を省略しています。重要な判断は残っている情報をもとに行ってください。]\n\n"
        f"{tail}"
    )


def compact_text(text: str, limit: int = 1200) -> str:
    text = re.sub(r"\n{3,}", "\n\n", text or "").strip()
    if len(text) <= limit:
        return text
    head = text[: int(limit * 0.68)].rstrip()
    tail = text[-int(limit * 0.22):].lstrip()
    return f"{head}\n\n[中略]\n\n{tail}"


def quality_from_mode(output_type: str, default_quality: str = "high") -> str:
    mode = st.session_state.get("quality_mode", DEFAULT_QUALITY_MODE)
    if mode == "エコノミー":
        return "light"
    if mode == "高品質":
        return default_quality
    return "high" if output_type in {"meeting_analysis", "proposal_outline"} else "light"


def token_limit_for(output_type: str) -> int:
    mode = st.session_state.get("quality_mode", DEFAULT_QUALITY_MODE)
    base = OUTPUT_TOKEN_LIMITS.get(output_type, 1200)
    if mode == "エコノミー":
        return max(240, int(base * 0.7))
    if mode == "高品質":
        return int(base * 1.15)
    return base


def short_input_enabled(key: str, text: str) -> bool:
    if len(text or "") <= SHORT_INPUT_CONFIRM_CHARS:
        return True
    return st.checkbox(
        "入力が長いため、AIに渡す前に自動短縮して原価を抑える",
        value=True,
        key=key,
    )


def run_openai(prompt: str, quality: str = "high", max_output_tokens: int | None = None) -> tuple[str, str]:
    api_key = get_secret("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEYが未設定です。StreamlitのSecretsにAPIキーを登録してください。")

    from openai import OpenAI

    model = HIGH_MODEL if quality == "high" else LIGHT_MODEL
    client = OpenAI(api_key=api_key)
    response = client.responses.create(
        model=model,
        instructions=SYSTEM_INSTRUCTIONS,
        input=trim_prompt(prompt),
        max_output_tokens=max_output_tokens or (2400 if quality == "high" else 900),
    )
    text = getattr(response, "output_text", None)
    if not text:
        text = str(response)
    return text, model


def needs_long_prompt_summary(prompt: str, output_type: str) -> bool:
    return len(prompt) > LONG_PROMPT_SUMMARY_CHARS and output_type in {"meeting_analysis", "proposal_outline", "win_loss_analysis"}


def summarize_long_prompt_if_needed(prompt: str, output_type: str) -> tuple[str, str | None]:
    if not needs_long_prompt_summary(prompt, output_type):
        return prompt, None
    summary_prompt = f"""
以下はAI生成に渡す入力ですが、長すぎます。
重要な事実、顧客ニーズ、日付、決裁条件、次回アクション、懸念、提案材料を落とさず、後続の営業支援AIが使いやすい要約にしてください。

入力:
{trim_prompt(prompt)}
""".strip()
    summary, model = run_openai(
        summary_prompt,
        quality="light",
        max_output_tokens=1400,
    )
    return (
        "以下は長文入力を事前要約したものです。この要約を根拠に出力してください。\n\n"
        f"{summary}",
        model,
    )


def run_ai_and_store(
    db: dict[str, Any],
    deal: dict[str, Any],
    output_type: str,
    prompt: str,
    quality: str = "high",
) -> str:
    quality = quality_from_mode(output_type, quality)
    max_output_tokens = token_limit_for(output_type)
    cache_key = cache_key_for(output_type, prompt, quality, max_output_tokens)
    cached = get_cached_ai_output(db, cache_key)
    if cached:
        add_ai_output(db, deal["id"], output_type, f"[キャッシュ再利用]\n\n{prompt}", cached["output_text"], f"cache:{cached['model']}", 0)
        update_deal_context_summary(db, deal["id"])
        save_db(db)
        return cached["output_text"]

    credits = AI_CREDIT_COSTS[output_type]
    if needs_long_prompt_summary(prompt, output_type):
        credits += AI_CREDIT_COSTS["output_refinement"]
    if not can_use_ai(db, credits):
        raise RuntimeError(
            f"今月のAI利用上限を超えます。現在 {get_usage(db)['ai_credits']} / {MONTHLY_AI_LIMIT} クレジット利用済みです。"
        )

    prompt_for_generation, summary_model = summarize_long_prompt_if_needed(prompt, output_type)
    output_text, model = run_openai(
        prompt_for_generation,
        quality=quality,
        max_output_tokens=max_output_tokens,
    )
    stored_prompt = prompt
    if summary_model:
        stored_prompt = f"[長文入力を{summary_model}で要約後に生成]\n\n{prompt}"
    register_ai_usage(db, credits)
    add_ai_output(db, deal["id"], output_type, stored_prompt, output_text, model, credits)
    set_cached_ai_output(db, cache_key, output_text, model)
    update_deal_context_summary(db, deal["id"])
    save_db(db)
    return output_text


def refine_output(db: dict[str, Any], deal: dict[str, Any], output: dict[str, Any], mode: str, instruction: str) -> str:
    credits = AI_CREDIT_COSTS["output_refinement"]
    prompt = f"""
以下のAI出力を、指定された目的に合わせて整えてください。
全文を作り直さず、必要な範囲だけを直してください。元の重要情報は保持してください。

目的: {mode}
追加指示: {instruction or "なし"}

案件情報:
{deal_context(deal, db)}

元の出力:
{output.get("output_text")}
""".strip()
    max_output_tokens = token_limit_for("output_refinement")
    cache_key = cache_key_for("output_refinement", prompt, "light", max_output_tokens)
    cached = get_cached_ai_output(db, cache_key)
    if cached:
        add_ai_output(db, deal["id"], output["type"], f"[キャッシュ再利用]\n\n{prompt}", cached["output_text"], f"cache:{cached['model']}", 0)
        save_db(db)
        return cached["output_text"]

    if not can_use_ai(db, credits):
        raise RuntimeError(
            f"今月のAI利用上限を超えます。現在 {get_usage(db)['ai_credits']} / {MONTHLY_AI_LIMIT} クレジット利用済みです。"
        )
    refined_text, model = run_openai(
        prompt,
        quality="light",
        max_output_tokens=max_output_tokens,
    )
    register_ai_usage(db, credits)
    add_ai_output(db, deal["id"], output["type"], prompt, refined_text, model, credits)
    set_cached_ai_output(db, cache_key, refined_text, model)
    update_deal_context_summary(db, deal["id"])
    save_db(db)
    return refined_text


def format_date(value: str | None) -> str:
    return value if value else "未設定"


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def due_bucket(deal: dict[str, Any]) -> str:
    due = parse_date(deal.get("next_meeting_date")) or parse_date(deal.get("target_close_date"))
    if not due:
        return "準備待ち"
    today = date.today()
    if due < today:
        return "期限切れ"
    if due == today:
        return "今日やること"
    return "今後の予定"


def current_timeline_phase(deal: dict[str, Any]) -> str:
    phase_alias = {"受注": "受注/失注", "失注": "受注/失注", "ペンディング": "フォロー"}
    current_phase = phase_alias.get(deal.get("phase"), deal.get("phase"))
    return current_phase if current_phase in TIMELINE_PHASES else "コンタクト前"


def timeline_phase_index(phase: str) -> int:
    return TIMELINE_PHASES.index(phase) if phase in TIMELINE_PHASES else 0


def extract_schedule_dates(text: str, reference: date | None = None) -> list[date]:
    if not text:
        return []
    reference = reference or date.today()
    candidates: list[date] = []
    patterns = [
        r"(?P<year>20\d{2})[-/年.](?P<month>\d{1,2})[-/月.](?P<day>\d{1,2})日?",
        r"(?P<month>\d{1,2})月(?P<day>\d{1,2})日",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            year = int(match.groupdict().get("year") or reference.year)
            month = int(match.group("month"))
            day = int(match.group("day"))
            try:
                candidate = date(year, month, day)
            except ValueError:
                continue
            if "year" not in match.groupdict() and candidate < reference - timedelta(days=30):
                try:
                    candidate = date(reference.year + 1, month, day)
                except ValueError:
                    continue
            candidates.append(candidate)
    return sorted(set(candidates))


def source_text_for_schedule(db: dict[str, Any], deal: dict[str, Any]) -> str:
    latest_analysis = latest_output(db, deal["id"], "meeting_analysis")
    parts = [
        latest_analysis["output_text"] if latest_analysis else "",
        deal.get("memo") or "",
    ]
    return "\n".join(part for part in parts if part)


def build_auto_schedule_patch(db: dict[str, Any], deal: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    today = date.today()
    dates = dict(deal.get("timeline_dates") or {})
    parsed_dates = [item for item in extract_schedule_dates(source_text_for_schedule(db, deal), today) if item >= today - timedelta(days=7)]
    current_phase = current_timeline_phase(deal)
    current_index = timeline_phase_index(current_phase)
    base_date = parse_date(deal.get("next_meeting_date")) or (parsed_dates[0] if parsed_dates else today + timedelta(days=3))
    target_date = parse_date(deal.get("target_close_date"))
    if not target_date:
        target_date = next((item for item in reversed(parsed_dates) if item >= base_date), None)
    if not target_date or target_date <= base_date:
        target_date = base_date + timedelta(days=35)

    schedule_dates: dict[str, date] = {}
    for index, phase in enumerate(TIMELINE_PHASES):
        if index < current_index:
            continue
        if phase == "受注/失注":
            schedule_dates[phase] = target_date
        elif phase == current_phase:
            schedule_dates[phase] = base_date
        elif phase == "フォロー":
            schedule_dates[phase] = target_date + timedelta(days=7)
        else:
            schedule_dates[phase] = base_date + timedelta(days=max(7, (index - current_index) * 7))

    changes: list[str] = []
    for phase, value in schedule_dates.items():
        if not dates.get(phase):
            dates[phase] = value.isoformat()
            changes.append(f"{phase}: {dates[phase]}")

    patch: dict[str, Any] = {"timeline_dates": dates}
    if not deal.get("next_meeting_date"):
        patch["next_meeting_date"] = base_date.isoformat()
        changes.append(f"次回予定日: {patch['next_meeting_date']}")
    if not deal.get("target_close_date"):
        patch["target_close_date"] = target_date.isoformat()
        changes.append(f"導入予定日（受注目標日）: {patch['target_close_date']}")
    return patch, changes


def auto_schedule_deal(db: dict[str, Any], deal: dict[str, Any]) -> list[str]:
    patch, changes = build_auto_schedule_patch(db, deal)
    if not changes:
        return []
    update_deal(db, deal["id"], patch)
    save_db(db)
    return changes


def render_schedule_auto_button(db: dict[str, Any], deal: dict[str, Any], key_prefix: str, label: str = "スケジュール自動作成") -> None:
    if st.button(label, key=f"{key_prefix}-auto-schedule-{deal['id']}"):
        changes = auto_schedule_deal(db, deal)
        if changes:
            st.success("スケジュールを自動作成しました: " + " / ".join(changes[:4]))
        else:
            st.info("未設定の期限はありません。")
        st.rerun()


def navigate_to(page: str, detail_view: str | None = None, selected_deal_id: str | None = None, focus_action: str | None = None) -> None:
    st.session_state[NAV_REQUEST_KEY] = page
    st.query_params[PAGE_QUERY_KEY] = page
    if detail_view:
        st.session_state[DETAIL_VIEW_KEY] = detail_view
    if selected_deal_id:
        st.session_state["selected_deal_id"] = selected_deal_id
    if focus_action:
        st.session_state[FOCUS_ACTION_KEY] = focus_action
    st.rerun()


def open_detail_view(view_name: str) -> None:
    navigate_to("案件詳細", detail_view=view_name, focus_action=view_name)


def render_onboarding_guide(has_deals: bool) -> None:
    st.subheader("まずやること")
    steps = [
        ("1", "案件を登録", "顧客名・商材・概要を入れて案件を作ります。", "新規案件登録"),
        ("2", "商談前リサーチ", "顧客に刺さる機能・運用・訴求を整理します。", "商談前リサーチ"),
        ("3", "商談メモ分析", "商談後に次回アクションと提案材料を抽出します。", "商談メモ分析"),
    ]
    cols = st.columns(3)
    for col, (num, title, body, target) in zip(cols, steps):
        with col:
            with st.container(border=True):
                st.markdown(f"### {num}. {title}\n{body}")
                disabled = target != "新規案件登録" and not has_deals
                if st.button(title, type="primary" if num == "1" else "secondary", disabled=disabled, key=f"onboarding-{target}"):
                    if target == "新規案件登録":
                        navigate_to("新規案件登録")
                    open_detail_view(target)
                if disabled:
                    st.caption("先に案件を登録してください。")


def update_deal_context_summary(db: dict[str, Any], deal_id: str) -> None:
    deal = find_deal(db, deal_id)
    if not deal:
        return
    parts = [
        f"案件名: {deal.get('title')}",
        f"顧客: {deal.get('customer_name')} / 業界: {deal.get('customer_industry')} / 規模: {deal.get('customer_size')}",
        f"部署・担当: {deal.get('department_name')} / {deal.get('contact_name') or '未設定'} / {deal.get('contact_role')}",
        f"商材: {deal.get('product_name')}",
        f"商材概要: {compact_text(deal.get('product_description') or '', 500)}",
        f"フェーズ: {deal.get('phase')} / 温度感: {deal.get('temperature')} / 予算: {deal.get('budget')}",
        f"次回予定日: {format_date(deal.get('next_meeting_date'))} / 受注目標: {format_date(deal.get('target_close_date'))}",
    ]
    if deal.get("competitor_info"):
        parts.append(f"競合情報: {compact_text(deal.get('competitor_info'), 300)}")
    if deal.get("memo"):
        parts.append(f"メモ: {compact_text(deal.get('memo'), 500)}")
    for output_type in ["research", "meeting_analysis", "proposal_outline", "win_loss_analysis"]:
        output = latest_output(db, deal_id, output_type)
        if output:
            parts.append(f"{AI_LABELS.get(output_type, output_type)}要約:\n{compact_text(output.get('output_text') or '', 900)}")
    deal["ai_context_summary"] = "\n\n".join(part for part in parts if part)
    deal["ai_context_summary_updated_at"] = now_iso()


def deal_context(deal: dict[str, Any], db: dict[str, Any] | None = None) -> str:
    if deal.get("ai_context_summary"):
        return deal["ai_context_summary"]
    latest_research_output = latest_output(db, deal["id"], "research") if db else None
    latest_analysis_output = latest_output(db, deal["id"], "meeting_analysis") if db else None
    latest_research = compact_text(latest_research_output["output_text"], 900) if latest_research_output else ""
    latest_analysis = compact_text(latest_analysis_output["output_text"], 900) if latest_analysis_output else ""
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
    current_phase = current_timeline_phase(deal)
    current_index = timeline_phase_index(current_phase)
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


def timeline_items_for_deal(deal: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for phase, value in (deal.get("timeline_dates") or {}).items():
        parsed = parse_date(value)
        if parsed:
            items.append({"date": parsed, "label": phase, "type": "task"})
    next_meeting = parse_date(deal.get("next_meeting_date"))
    if next_meeting:
        items.append({"date": next_meeting, "label": "次回予定", "type": "next"})
    target_close = parse_date(deal.get("target_close_date"))
    if target_close:
        items.append({"date": target_close, "label": "受注目標", "type": "target"})
    return sorted(items, key=lambda item: (item["date"], item["type"]))


def render_timeline_visualization(deals: list[dict[str, Any]]) -> None:
    deal_items = [(deal, timeline_items_for_deal(deal)) for deal in deals]
    dated_items = [item for _deal, items in deal_items for item in items]
    if not dated_items:
        st.info("日付が入ると、ここに案件別のタイムスケジュールが表示されます。")
        return

    today = date.today()
    min_date = min([today] + [item["date"] for item in dated_items])
    max_date = max([today + timedelta(days=42)] + [item["date"] for item in dated_items])
    start = min_date - timedelta(days=min_date.weekday())
    weeks = []
    cursor = start
    while cursor <= max_date:
        weeks.append((cursor, cursor + timedelta(days=6)))
        cursor += timedelta(days=7)

    type_class = {"task": "task", "next": "next", "target": "target"}
    rows_html = []
    for deal, items in deal_items:
        cells = []
        for week_start, week_end in weeks:
            in_week = [item for item in items if week_start <= item["date"] <= week_end]
            pills = []
            for item in in_week:
                marker = "★" if item["type"] == "target" else "●"
                label = html.escape(f"{marker} {item['label']} {item['date'].strftime('%m/%d')}")
                pills.append(f"<span class='pill {type_class.get(item['type'], 'task')}'>{label}</span>")
            today_class = " today" if week_start <= today <= week_end else ""
            cells.append(f"<td class='week{today_class}'>{''.join(pills)}</td>")
        rows_html.append(
            "<tr>"
            f"<th class='deal'>{html.escape(deal.get('title') or deal.get('customer_name') or '未設定')}</th>"
            + "".join(cells)
            + "</tr>"
        )

    header_html = "".join(
        f"<th class='week-head'>{week_start.strftime('%m/%d')}週</th>"
        for week_start, _week_end in weeks
    )
    st.markdown(
        f"""
<style>
.timeline-scroll {{ overflow-x: auto; border: 1px solid #e2e8f0; border-radius: 8px; }}
.timeline-table {{ border-collapse: collapse; min-width: {max(760, 132 * len(weeks))}px; width: 100%; font-size: .88rem; }}
.timeline-table th, .timeline-table td {{ border-bottom: 1px solid #e2e8f0; border-right: 1px solid #eef2f7; padding: 8px; vertical-align: top; }}
.timeline-table thead th {{ background: #f8fafc; color: #334155; font-weight: 700; }}
.timeline-table .deal {{ position: sticky; left: 0; z-index: 1; min-width: 220px; max-width: 260px; background: #ffffff; text-align: left; }}
.timeline-table .week-head {{ min-width: 120px; text-align: left; }}
.timeline-table .week {{ min-height: 54px; background: #ffffff; }}
.timeline-table .week.today {{ background: #fff7ed; }}
.timeline-table .pill {{ display: block; margin: 3px 0; padding: 4px 6px; border-radius: 6px; line-height: 1.25; white-space: normal; }}
.timeline-table .pill.task {{ background: #e0f2fe; color: #075985; }}
.timeline-table .pill.next {{ background: #dcfce7; color: #166534; }}
.timeline-table .pill.target {{ background: #fee2e2; color: #991b1b; font-weight: 700; }}
</style>
<div class="timeline-scroll">
  <table class="timeline-table">
    <thead><tr><th class="deal">案件</th>{header_html}</tr></thead>
    <tbody>{"".join(rows_html)}</tbody>
  </table>
</div>
        """,
        unsafe_allow_html=True,
    )


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


def build_email_template(deal: dict[str, Any], db: dict[str, Any]) -> str:
    meeting_analysis = latest_output(db, deal["id"], "meeting_analysis")
    analysis_note = compact_text(meeting_analysis["output_text"], 700) if meeting_analysis else "商談メモ分析はまだありません。商談で合意した内容を追記してください。"
    next_action = "、".join(recommended_next_actions(db, deal)[:2])
    return f"""
# お礼メール案（テンプレート）
## 件名
{deal.get("customer_name")}様 / 本日のお打ち合わせのお礼と次回の進め方

## 本文
{deal.get("customer_name")}
{deal.get("contact_name") or "ご担当者"} 様

本日はお時間をいただき、ありがとうございました。
お話しいただいた内容を踏まえ、{deal.get("product_name")}のご提案に向けて、下記の通り整理しました。

## 本日の確認内容
{analysis_note}

## 次回アクション
- 次に進めること: {next_action or "次回アクションの確認"}
- 次回予定日: {format_date(deal.get("next_meeting_date"))}
- 導入予定日（受注目標日）: {format_date(deal.get("target_close_date"))}

引き続きよろしくお願いいたします。
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


def create_user(db: dict[str, Any], profile: dict[str, Any]) -> tuple[dict[str, Any], str]:
    initial_password = generate_initial_password()
    salt, password_hash = hash_password(initial_password)
    user = {
        "id": str(uuid.uuid4()),
        "login_id": generate_user_id(db),
        "email": profile["email"].strip().lower(),
        "name": profile["name"].strip(),
        "company": profile["company"].strip(),
        "role": profile.get("role", "").strip(),
        "team_size": profile.get("team_size", ""),
        "source": profile.get("source", ""),
        "use_case": profile.get("use_case", "").strip(),
        "plan_name": PLAN_NAME,
        "plan_price_yen": PLAN_PRICE_YEN,
        "plan_interval": PLAN_INTERVAL,
        "subscription_status": "active",
        "subscription_started_at": now_iso(),
        "next_billing_label": "登録日から1か月ごと",
        "cancel_requested_at": "",
        "password_salt": salt,
        "password_hash": password_hash,
        "terms_accepted_at": now_iso(),
        "privacy_accepted_at": now_iso(),
        "ai_policy_accepted_at": now_iso(),
        "commercial_terms_accepted_at": now_iso(),
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    db.setdefault("users", []).insert(0, user)
    db.setdefault("subscription_events", []).insert(
        0,
        {
            "id": str(uuid.uuid4()),
            "user_id": user["id"],
            "event": "created",
            "detail": f"{PLAN_NAME} / {PLAN_INTERVAL}{PLAN_PRICE_YEN:,}円",
            "created_at": now_iso(),
        },
    )
    save_db(db)
    return user, initial_password


def login_user(user: dict[str, Any]) -> None:
    st.session_state["user_id"] = user["id"]
    st.session_state["account_authenticated"] = True
    st.session_state.pop("admin_authenticated", None)
    st.session_state.pop("issued_credentials", None)


def logout_user() -> None:
    for key in ["user_id", "account_authenticated", "admin_authenticated", "authenticated"]:
        st.session_state.pop(key, None)


def render_policy_summary() -> None:
    st.markdown(
        f"""
**登録前の確認事項**

- プランは **{PLAN_NAME} / {PLAN_INTERVAL}{PLAN_PRICE_YEN:,}円（税込想定）** です。
- 入力した案件情報・商談メモは、本人の営業支援機能を提供する目的で利用します。
- AI生成結果は営業判断を補助するもので、最終確認と顧客への送信判断はユーザー側で行います。
- クレジット上限は月{MONTHLY_AI_LIMIT}クレジット、案件登録上限は月{MONTHLY_DEAL_LIMIT}件です。
- 機密情報、個人番号、決済情報、パスワードなどの入力は避けてください。
- 解約はマイページから申請できます。実決済連携後は決済事業者の請求サイクルに従います。
"""
    )


def render_signup(db: dict[str, Any]) -> None:
    st.title("SalesPilot登録")
    st.caption("SNSやnoteから来た方向けの月額プラン登録画面です。")
    render_policy_summary()
    st.divider()

    issued = st.session_state.get("issued_credentials")
    if issued:
        st.success("登録が完了しました。以下のID/PASSはこの画面で一度だけ控えてください。")
        col1, col2 = st.columns(2)
        col1.code(issued["login_id"], language=None)
        col2.code(issued["password"], language=None)
        st.info("控えたら、ログイン画面からマイページへ進んでください。")
        if st.button("ログイン画面へ進む", type="primary"):
            st.session_state[NAV_REQUEST_KEY] = "ログイン"
            st.rerun()
        return

    col1, col2 = st.columns(2)
    with col1:
        name = st.text_input("氏名", placeholder="山田 太郎")
        company = st.text_input("会社名/屋号", placeholder="株式会社〇〇")
        email = st.text_input("メールアドレス", placeholder="name@example.com")
        role = st.text_input("役職/担当", placeholder="代表、営業担当、営業責任者など")
    with col2:
        team_size = st.selectbox("営業チーム規模", ["1人", "2～5人", "6～10人", "11人以上"])
        source = st.selectbox("流入元", ["note", "X", "Threads", "紹介", "その他"])
        use_case = st.text_area("使いたい目的", placeholder="商談メモ整理、提案資料骨子作成、次アクション管理など", height=120)

    accept_terms = st.checkbox("利用規約、料金、解約条件を確認しました")
    accept_privacy = st.checkbox("プライバシーポリシーとAI利用時のデータ取扱いを確認しました")
    accept_commercial = st.checkbox(f"{PLAN_NAME}が{PLAN_INTERVAL}{PLAN_PRICE_YEN:,}円の有料サービスであることを確認しました")
    submitted = st.button("登録してID/PASSを発行", type="primary")

    if submitted:
        if not name or not company or not email:
            st.error("氏名、会社名/屋号、メールアドレスを入力してください。")
            return
        if "@" not in email:
            st.error("メールアドレスの形式を確認してください。")
            return
        if find_user_by_login(db, email):
            st.error("このメールアドレスは登録済みです。ログイン画面へ進んでください。")
            return
        if not (accept_terms and accept_privacy and accept_commercial):
            st.error("登録前の確認事項に同意してください。")
            return
        user, password = create_user(
            db,
            {
                "name": name,
                "company": company,
                "email": email,
                "role": role,
                "team_size": team_size,
                "source": source,
                "use_case": use_case,
            },
        )
        st.session_state["issued_credentials"] = {"login_id": user["login_id"], "password": password}
        st.rerun()


def render_login(db: dict[str, Any]) -> None:
    st.title("ログイン")
    st.caption("登録時に発行されたID/PASSでログインしてください。")
    login = st.text_input("ログインIDまたはメールアドレス")
    password = st.text_input("パスワード", type="password")
    col1, col2 = st.columns(2)
    if col1.button("ログイン", type="primary"):
        user = find_user_by_login(db, login)
        if user and verify_password(password, user.get("password_salt", ""), user.get("password_hash", "")):
            login_user(user)
            st.session_state[NAV_REQUEST_KEY] = "マイページ"
            st.rerun()
        st.error("IDまたはパスワードが違います。")
    if col2.button("新規登録へ"):
        st.session_state[NAV_REQUEST_KEY] = "サービス登録"
        st.rerun()

    admin_password = get_secret("APP_PASSWORD")
    if admin_password:
        with st.expander("運営用ログイン"):
            entered = st.text_input("運営パスコード", type="password", key="admin-passcode")
            if st.button("運営ログイン"):
                if entered == admin_password:
                    st.session_state["admin_authenticated"] = True
                    st.session_state["account_authenticated"] = True
                    st.session_state[NAV_REQUEST_KEY] = "ダッシュボード"
                    st.rerun()
                st.error("パスコードが違います。")


def render_mypage(db: dict[str, Any]) -> None:
    user = current_user(db)
    if not user:
        render_login(db)
        return
    st.title("マイページ")
    st.caption(f"{user['company']} / {user['name']} 様")

    col1, col2, col3 = st.columns(3)
    col1.metric("契約プラン", user.get("plan_name", PLAN_NAME))
    col2.metric("月額", f"{user.get('plan_price_yen', PLAN_PRICE_YEN):,}円")
    col3.metric("契約状態", "解約申請中" if user.get("cancel_requested_at") else "利用中")

    st.subheader("契約情報")
    st.table(
        pd.DataFrame(
            [
                {"項目": "ログインID", "内容": user.get("login_id")},
                {"項目": "メールアドレス", "内容": user.get("email")},
                {"項目": "開始日", "内容": user.get("subscription_started_at")},
                {"項目": "次回請求", "内容": user.get("next_billing_label")},
                {"項目": "月間上限", "内容": f"案件{MONTHLY_DEAL_LIMIT}件 / AI{MONTHLY_AI_LIMIT}クレジット"},
            ]
        )
    )

    st.subheader("契約管理")
    if user.get("cancel_requested_at"):
        st.warning(f"解約申請を受け付けています: {user['cancel_requested_at']}")
        if st.button("解約申請を取り消す"):
            user["cancel_requested_at"] = ""
            user["subscription_status"] = "active"
            user["updated_at"] = now_iso()
            db.setdefault("subscription_events", []).insert(0, {"id": str(uuid.uuid4()), "user_id": user["id"], "event": "cancel_request_revoked", "detail": "解約申請取り消し", "created_at": now_iso()})
            save_db(db)
            st.rerun()
    else:
        st.info("プラン変更、請求先変更、領収書発行は正式決済連携後にこの画面へ追加します。")
        if st.button("解約を申請する", type="secondary"):
            user["cancel_requested_at"] = now_iso()
            user["subscription_status"] = "cancel_requested"
            user["updated_at"] = now_iso()
            db.setdefault("subscription_events", []).insert(0, {"id": str(uuid.uuid4()), "user_id": user["id"], "event": "cancel_requested", "detail": "マイページから解約申請", "created_at": now_iso()})
            save_db(db)
            st.rerun()

    st.subheader("利用開始")
    col_start1, col_start2 = st.columns(2)
    if col_start1.button("ダッシュボードへ", type="primary"):
        navigate_to("ダッシュボード")
    if col_start2.button("新規案件を登録"):
        navigate_to("新規案件登録")


def require_account(db: dict[str, Any], page: str) -> bool:
    if page in PUBLIC_PAGES:
        return True
    if st.session_state.get("admin_authenticated") or current_user(db):
        return True
    render_login(db)
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


def render_output_tools(output: dict[str, Any], db: dict[str, Any] | None, deal: dict[str, Any] | None, key_prefix: str) -> None:
    st.text_area(
        "コピー用テキスト",
        value=output["output_text"],
        height=180,
        key=f"copy-text-{key_prefix}-{output['id']}",
    )
    if db is None or deal is None:
        return
    mode = st.selectbox(
        "整形方法",
        ["指定部分だけ修正", "短く要約", "提案資料向けに整える"],
        key=f"refine-mode-{key_prefix}-{output['id']}",
    )
    instruction = st.text_area(
        "追加指示",
        placeholder="例: 3つの箇条書きにする / 料金部分だけ柔らかくする",
        height=90,
        key=f"refine-instruction-{key_prefix}-{output['id']}",
    )
    if st.button("この出力を整える", key=f"refine-output-{key_prefix}-{output['id']}"):
        try:
            with st.spinner("出力を整えています..."):
                refine_output(db, deal, output, mode, instruction)
            st.success("整えた出力を保存しました。")
            st.rerun()
        except Exception as exc:
            st.error(str(exc))


def render_output(
    output: dict[str, Any] | None,
    db: dict[str, Any] | None = None,
    deal: dict[str, Any] | None = None,
    tools_in_expander: bool = True,
    key_prefix: str = "output",
) -> None:
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
        key=f"download-{key_prefix}-{output['id']}",
    )
    if tools_in_expander:
        with st.expander("コピー・再整形"):
            render_output_tools(output, db, deal, key_prefix)
    else:
        st.markdown("**コピー・再整形**")
        with st.container(border=True):
            render_output_tools(output, db, deal, key_prefix)


def render_dashboard(db: dict[str, Any]) -> None:
    st.title("進行中案件ダッシュボード")
    render_usage_banner(db)

    deals = active_deals(db)
    render_onboarding_guide(bool(deals))
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
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
    render_timeline_visualization(deals)

    with st.expander("タイムスケジュールから自動作成"):
        st.caption("期限が未設定の案件だけ補完します。議事メモ分析に日付があれば優先し、読み取れない場合は今日を基準に自動設定します。")
        for deal in deals:
            with st.container(border=True):
                left, middle, right = st.columns([3, 1, 1])
                with left:
                    st.markdown(f"**{deal['title']}**")
                    st.caption(f"次回予定: {format_date(deal.get('next_meeting_date'))} / 受注目標: {format_date(deal.get('target_close_date'))}")
                with middle:
                    render_schedule_auto_button(db, deal, key_prefix="dashboard", label="自動作成")
                with right:
                    if st.button("開く", key=f"dashboard-open-timeline-{deal['id']}"):
                        navigate_to("案件詳細", detail_view="タイムライン", selected_deal_id=deal["id"], focus_action="スケジュール自動作成")

    st.subheader("優先度別ネクストアクション")
    for bucket in ["期限切れ", "今日やること", "準備待ち", "今後の予定"]:
        bucket_deals = [deal for deal in deals if due_bucket(deal) == bucket]
        if not bucket_deals:
            continue
        st.markdown(f"#### {bucket}")
        for deal in bucket_deals:
            next_actions = recommended_next_actions(db, deal)
            with st.container(border=True):
                left, right = st.columns([3, 1])
                with left:
                    st.markdown(f"**{deal['title']}**")
                    st.write(f"フェーズ: {deal['phase']} / 次回予定: {format_date(deal.get('next_meeting_date'))}")
                    st.write("次にやること: " + " → ".join(next_actions))
                with right:
                    if st.button("開く", key=f"open-{deal['id']}"):
                        focus_action = next_actions[0] if next_actions else ""
                        navigate_to(
                            "案件詳細",
                            detail_view=ACTION_TO_TAB.get(focus_action, "概要") if focus_action else "概要",
                            selected_deal_id=deal["id"],
                            focus_action=focus_action,
                        )


def render_new_deal(db: dict[str, Any]) -> None:
    st.title("新規案件登録")
    usage = get_usage(db)
    st.caption(f"今月の登録数: {usage['deals']} / {MONTHLY_DEAL_LIMIT}")
    if not can_create_deal(db):
        st.error("今月の案件登録上限に達しています。")
        return

    if "new_product_description" not in st.session_state:
        st.session_state["new_product_description"] = ""
    if st.session_state.pop("reset_new_deal_form", False):
        for key in [
            "new_customer_name",
            "new_customer_industry",
            "new_customer_size",
            "new_department_name",
            "new_contact_name",
            "new_contact_role",
            "new_product_name",
            "new_product_url",
            "new_product_description",
            "new_phase",
            "new_temperature",
            "new_budget",
            "new_competitor_info",
            "new_memo",
            "new_next_meeting_date",
            "new_target_close_date",
        ]:
            st.session_state.pop(key, None)
        st.session_state["new_product_description"] = ""

    col1, col2 = st.columns(2)
    with col1:
        customer_name = st.text_input("顧客名", key="new_customer_name")
        customer_industry = st.text_input("顧客企業の業界", key="new_customer_industry")
        customer_size = st.selectbox("顧客企業規模", CUSTOMER_SIZES, index=3, key="new_customer_size")
        department_name = st.selectbox("部署名", DEPARTMENTS, index=DEPARTMENTS.index("営業部"), key="new_department_name")
        contact_name = st.text_input("担当者名", key="new_contact_name")
        contact_role = st.selectbox("担当者役職", CONTACT_ROLES, index=CONTACT_ROLES.index("担当者"), key="new_contact_role")
    with col2:
        product_name = st.text_input("提案商材名", key="new_product_name")
        title = f"{customer_name} × {product_name}" if customer_name and product_name else "顧客名 × 提案商材名"
        st.text_input("案件名（自動生成）", value=title, disabled=True)
        product_url = st.text_input("商材URL", placeholder="https://example.com/product", key="new_product_url")
        if st.button("商材URLから概要を自動作成", disabled=not product_url):
            try:
                cache_key = normalize_url(product_url)
                cached = db.setdefault("url_cache", {}).get(cache_key)
                if cached:
                    st.session_state["new_product_description"] = cached["summary"]
                    st.success("保存済みの商材概要を再利用しました。AIクレジットは消費していません。")
                    st.rerun()
                page_text = extract_url_text(product_url)
                prompt = build_product_summary_prompt(product_name, product_url, page_text)
                max_output_tokens = token_limit_for("product_summary")
                ai_cache_key = cache_key_for("product_summary", prompt, "light", max_output_tokens)
                cached_ai = get_cached_ai_output(db, ai_cache_key)
                if cached_ai:
                    summary = cached_ai["output_text"]
                    _model = cached_ai["model"]
                    reused_ai_cache = True
                else:
                    if not can_use_ai(db, AI_CREDIT_COSTS["product_summary"]):
                        st.error(
                            f"今月のAI利用上限を超えます。現在 {get_usage(db)['ai_credits']} / {MONTHLY_AI_LIMIT} クレジット利用済みです。"
                        )
                        return
                    summary, _model = run_openai(
                        prompt,
                        quality="light",
                        max_output_tokens=max_output_tokens,
                    )
                    register_ai_usage(db, AI_CREDIT_COSTS["product_summary"])
                    set_cached_ai_output(db, ai_cache_key, summary.strip(), _model)
                    reused_ai_cache = False
                db.setdefault("url_cache", {})[cache_key] = {
                    "summary": summary.strip(),
                    "product_name": product_name,
                    "updated_at": now_iso(),
                }
                save_db(db)
                st.session_state["new_product_description"] = summary.strip()
                st.success("保存済みの商材概要を再利用しました。AIクレジットは消費していません。" if reused_ai_cache else "商材概要を作成しました。")
            except Exception as exc:
                st.error(str(exc))
        st.text_area("提案商材の概要", key="new_product_description", height=100)
        phase = st.selectbox("商談フェーズ", PHASES, index=0, key="new_phase")
        temperature = st.selectbox("現在の温度感", TEMPERATURES, index=1, key="new_temperature")
        budget = st.selectbox("予算感", BUDGET_RANGES, index=0, key="new_budget")

    col3, col4 = st.columns(2)
    with col3:
        next_meeting_date = st.date_input("次回予定日", value=None, key="new_next_meeting_date")
    with col4:
        target_close_date = st.date_input("導入予定日（受注目標日）", value=None, key="new_target_close_date")

    competitor_info = st.text_area("競合情報", key="new_competitor_info")
    memo = st.text_area("メモ", key="new_memo")

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
        st.session_state["reset_new_deal_form"] = True
        st.success("案件を登録しました。")
        navigate_to("案件詳細", detail_view="概要", selected_deal_id=deal["id"], focus_action="商談前リサーチ")


def select_deal(db: dict[str, Any], include_past: bool = False) -> dict[str, Any] | None:
    deals = [deal for deal in db["deals"] if user_data_visible(deal)] if include_past else active_deals(db)
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
        key=f"deal-selector-{'past' if include_past else 'active'}",
    )
    st.session_state["selected_deal_id"] = selected["id"]
    return selected


def render_overview_tab(db: dict[str, Any], deal: dict[str, Any]) -> None:
    left, right = st.columns([2, 1])
    with left:
        with st.form(f"overview-{deal['id']}"):
            st.subheader("案件概要")
            title = st.text_input("案件名", value=deal["title"], key=f"overview-title-{deal['id']}")
            customer_name = st.text_input("顧客名", value=deal["customer_name"], key=f"overview-customer-{deal['id']}")
            customer_industry = st.text_input("業界", value=deal["customer_industry"], key=f"overview-industry-{deal['id']}")
            customer_size = st.selectbox("企業規模", CUSTOMER_SIZES, index=CUSTOMER_SIZES.index(deal.get("customer_size", "31～50")) if deal.get("customer_size") in CUSTOMER_SIZES else 0, key=f"overview-size-{deal['id']}")
            department_name = st.selectbox("部署", DEPARTMENTS, index=DEPARTMENTS.index(deal.get("department_name")) if deal.get("department_name") in DEPARTMENTS else 0, key=f"overview-department-{deal['id']}")
            contact_name = st.text_input("担当者", value=deal.get("contact_name") or "", key=f"overview-contact-{deal['id']}")
            contact_role = st.selectbox("担当者役職", CONTACT_ROLES, index=CONTACT_ROLES.index(deal.get("contact_role")) if deal.get("contact_role") in CONTACT_ROLES else 0, key=f"overview-role-{deal['id']}")
            product_name = st.text_input("提案商材", value=deal["product_name"], key=f"overview-product-{deal['id']}")
            product_url = st.text_input("商材URL", value=deal.get("product_url") or "", key=f"overview-url-{deal['id']}")
            product_description = st.text_area("提案商材の概要", value=deal.get("product_description") or "", height=100, key=f"overview-description-{deal['id']}")
            phase = st.selectbox("商談フェーズ", PHASES, index=PHASES.index(deal.get("phase")) if deal.get("phase") in PHASES else 0, key=f"overview-phase-{deal['id']}")
            temperature = st.selectbox("温度感", TEMPERATURES, index=TEMPERATURES.index(deal.get("temperature")) if deal.get("temperature") in TEMPERATURES else 1, key=f"overview-temperature-{deal['id']}")
            budget = st.selectbox("予算感", BUDGET_RANGES, index=BUDGET_RANGES.index(deal.get("budget")) if deal.get("budget") in BUDGET_RANGES else 0, key=f"overview-budget-{deal['id']}")
            next_meeting_date = st.text_input("次回予定日", value=deal.get("next_meeting_date") or "", placeholder="YYYY-MM-DD", key=f"overview-next-date-{deal['id']}")
            target_close_date = st.text_input("導入予定日（受注目標日）", value=deal.get("target_close_date") or "", placeholder="YYYY-MM-DD", key=f"overview-target-date-{deal['id']}")
            competitor_info = st.text_area("競合情報", value=deal.get("competitor_info") or "", key=f"overview-competitor-{deal['id']}")
            memo = st.text_area("メモ", value=deal.get("memo") or "", key=f"overview-memo-{deal['id']}")
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
                        "status": status_for_phase(phase, deal.get("status", "active")),
                        "temperature": temperature,
                        "budget": budget,
                        "next_meeting_date": next_meeting_date,
                        "target_close_date": target_close_date,
                        "competitor_info": competitor_info,
                        "memo": memo,
                    },
                )
                update_deal_context_summary(db, deal["id"])
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
        if col1.button("受注", key=f"status-won-{deal['id']}"):
            update_deal(db, deal["id"], {"status": "won", "phase": "受注"})
            save_db(db)
            st.rerun()
        if col2.button("失注", key=f"status-lost-{deal['id']}"):
            update_deal(db, deal["id"], {"status": "lost", "phase": "失注"})
            save_db(db)
            st.rerun()
        if col3.button("ペンディング", key=f"status-pending-{deal['id']}"):
            update_deal(db, deal["id"], {"phase": "ペンディング"})
            save_db(db)
            st.rerun()
        st.divider()
        st.subheader("案件タイムライン")
        st.dataframe(pd.DataFrame(timeline_status(deal)), width="stretch", hide_index=True)


def render_research_tab(db: dict[str, Any], deal: dict[str, Any]) -> None:
    left, right = st.columns([1, 2])
    with left:
        st.subheader("商談前情報")
        meeting_minutes = st.number_input("商談時間（分）", min_value=1, value=45, key=f"research-meeting-minutes-{deal['id']}")
        pre_meeting_info = st.text_area("事前情報", height=120, key=f"research-info-{deal['id']}")
        visible_needs = st.text_area("顕在化しているニーズ", height=120, key=f"research-needs-{deal['id']}")
        requirements = st.text_area("要件", height=120, key=f"research-requirements-{deal['id']}")
        if st.button("商談前リサーチを生成", type="primary", key=f"generate-research-{deal['id']}"):
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
        render_output(latest_output(db, deal["id"], "research"), db, deal, key_prefix="latest-research")


def render_hearing_tab(db: dict[str, Any], deal: dict[str, Any]) -> None:
    left, right = st.columns([1, 2])
    with left:
        st.subheader("ヒアリング時間配分")
        meeting_minutes = st.number_input("商談時間（分）", min_value=1, value=45, key=f"hearing-meeting-minutes-{deal['id']}")
        opening_minutes = st.number_input("うちアイスブレイク/冒頭ヒアリング時間（分）", min_value=0, value=5, key=f"hearing-opening-{deal['id']}")
        product_demo_minutes = st.number_input("うち製品説明時間（分）", min_value=0, value=15, key=f"hearing-demo-{deal['id']}")
        post_demo_hearing_minutes = st.number_input("うち紹介後ヒアリング時間（分）", min_value=0, value=15, key=f"hearing-post-demo-{deal['id']}")
        closing_minutes = st.number_input("うちクロージング/次回アクション合意時間（分）", min_value=0, value=10, key=f"hearing-closing-{deal['id']}")
        if st.button("ヒアリング設計を生成", type="primary", key=f"generate-hearing-{deal['id']}"):
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
        render_output(latest_output(db, deal["id"], "hearing"), db, deal, key_prefix="latest-hearing")


def render_meeting_tab(db: dict[str, Any], deal: dict[str, Any]) -> None:
    left, right = st.columns([1, 2])
    with left:
        st.subheader("商談メモ貼り付け")
        meeting_at = st.text_input("商談日時", placeholder="2026-07-01 10:00", key=f"meeting-at-{deal['id']}")
        meeting_type = st.selectbox("商談形式", MEETING_TYPES, index=1, key=f"meeting-type-{deal['id']}")
        duration_minutes = st.number_input("商談時間（分）", min_value=1, value=45, key=f"meeting-duration-{deal['id']}")
        participants = st.text_input("参加者", key=f"meeting-participants-{deal['id']}")
        transcript = st.text_area("商談メモ本文", height=260, key=f"meeting-transcript-{deal['id']}")
        use_short_transcript = short_input_enabled(f"short-meeting-transcript-{deal['id']}", transcript)
        supplemental_memo = st.text_area("補足メモ", height=100, key=f"meeting-supplement-{deal['id']}")
        if st.button("商談メモを分析", type="primary", key=f"generate-meeting-{deal['id']}"):
            if not transcript:
                st.error("商談メモ本文を入力してください。")
                return
            context = {
                "meeting_at": meeting_at,
                "meeting_type": meeting_type,
                "duration_minutes": duration_minutes,
                "participants": participants,
                "transcript": compact_text(transcript, 9000) if use_short_transcript else transcript,
                "supplemental_memo": supplemental_memo,
            }
            try:
                with st.spinner("商談メモを分析しています..."):
                    run_ai_and_store(db, deal, "meeting_analysis", build_meeting_analysis_prompt(deal, context, db), quality="high")
                update_deal(db, deal["id"], {"phase": "2回目以降面談前/運用提案前"})
                update_deal_context_summary(db, deal["id"])
                save_db(db)
                st.success("分析しました。フェーズを「2回目以降面談前/運用提案前」に更新しました。")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))
    with right:
        render_output(latest_output(db, deal["id"], "meeting_analysis"), db, deal, key_prefix="latest-meeting")


def render_email_tab(db: dict[str, Any], deal: dict[str, Any]) -> None:
    col1, col2 = st.columns(2)
    if col1.button("テンプレートで作成（無料）", type="secondary", key=f"template-email-{deal['id']}"):
        output_text = build_email_template(deal, db)
        add_ai_output(db, deal["id"], "email", "[テンプレート生成: AI未使用]", output_text, "template", 0)
        save_db(db)
        st.success("AIを使わずメールテンプレートを作成しました。")
        st.rerun()
    if col2.button("AIでお礼メールを生成", type="primary", key=f"generate-email-{deal['id']}"):
        try:
            with st.spinner("メール文面を生成しています..."):
                run_ai_and_store(db, deal, "email", build_email_prompt(deal, db), quality="light")
            st.success("生成しました。")
            st.rerun()
        except Exception as exc:
            st.error(str(exc))
    render_output(latest_output(db, deal["id"], "email"), db, deal, key_prefix="latest-email")


def render_proposal_tab(db: dict[str, Any], deal: dict[str, Any]) -> None:
    left, right = st.columns([1, 2])
    meeting_analysis = latest_output(db, deal["id"], "meeting_analysis")
    with left:
        st.subheader("提案資料作成条件")
        next_meeting_minutes = st.number_input("次回商談時間（分）", min_value=1, value=45, key=f"proposal-next-minutes-{deal['id']}")
        previous_meeting_analysis = st.text_area(
            "前回議事メモ分析入力",
            value=meeting_analysis["output_text"] if meeting_analysis else "",
            height=180,
            key=f"proposal-previous-analysis-{deal['id']}",
        )
        use_short_proposal_input = short_input_enabled(f"short-proposal-input-{deal['id']}", previous_meeting_analysis)
        proposal_purpose = st.selectbox("目的", ["決裁者面談", "運用提案", "稟議用資料"], index=1, key=f"proposal-purpose-{deal['id']}")
        expected_attendees = st.text_input("想定参加者/決裁者", placeholder="例: 部長、現場責任者、経営層", key=f"proposal-attendees-{deal['id']}")
        key_message = st.text_area("資料で最も伝えたいメッセージ", height=90, key=f"proposal-key-message-{deal['id']}")
        must_include_points = st.text_area("必ず入れたい項目/スライド", height=90, key=f"proposal-must-include-{deal['id']}")
        decision_criteria = st.text_area("判断基準", height=90, key=f"proposal-criteria-{deal['id']}")
        budget_or_approval_conditions = st.text_area("予算/稟議条件", height=90, key=f"proposal-budget-{deal['id']}")
        competitor_or_concerns = st.text_area("競合・懸念・反論されそうな点", height=90, key=f"proposal-concerns-{deal['id']}")
        desired_next_action = st.text_input("資料提示後に合意したい次回アクション", key=f"proposal-next-action-{deal['id']}")
        if st.button("提案資料骨子を生成", type="primary", key=f"generate-proposal-{deal['id']}"):
            context = {
                "next_meeting_minutes": next_meeting_minutes,
                "previous_meeting_analysis": compact_text(previous_meeting_analysis, 5000) if use_short_proposal_input else previous_meeting_analysis,
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
        render_output(latest_output(db, deal["id"], "proposal_outline"), db, deal, key_prefix="latest-proposal")
        st.info('上記メモをコピーし、ChatGPTで「メモを基にスライドをpptxで出力してください」と投稿してください（推奨モード：Thinking以上）')
        st.link_button("ChatGPTを開く", "https://chatgpt.com/")


def render_timeline_tab(db: dict[str, Any], deal: dict[str, Any]) -> None:
    st.subheader("タイムライン")
    st.caption("各フェーズに日付を入力できます。未設定の期限はスケジュール自動作成で補完できます。")
    dates = dict(deal.get("timeline_dates") or {})

    render_schedule_auto_button(db, deal, key_prefix="timeline-tab")

    with st.form(f"timeline-{deal['id']}"):
        for phase in TIMELINE_PHASES:
            dates[phase] = st.text_input(phase, value=dates.get(phase, ""), placeholder="YYYY-MM-DD", key=f"timeline-{deal['id']}-{phase}")
        if st.form_submit_button("タイムラインを保存", type="primary"):
            update_deal(db, deal["id"], {"timeline_dates": dates})
            save_db(db)
            st.success("タイムラインを保存しました。")
            st.rerun()

    st.dataframe(pd.DataFrame(timeline_status({**deal, "timeline_dates": dates})), width="stretch", hide_index=True)


def render_winloss_tab(db: dict[str, Any], deal: dict[str, Any]) -> None:
    col1, col2 = st.columns(2)
    result = "won" if col1.button("受注分析を生成", key=f"winloss-won-{deal['id']}") else None
    result = "lost" if col2.button("失注分析を生成", key=f"winloss-lost-{deal['id']}") else result
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
    render_output(latest_output(db, deal["id"], "win_loss_analysis"), db, deal, key_prefix="latest-winloss")


def render_detail(db: dict[str, Any]) -> None:
    st.title("案件詳細")
    deal = select_deal(db, include_past=True)
    if not deal:
        return
    st.caption(f"{deal['customer_name']} / {deal['product_name']} / フェーズ: {deal['phase']}")
    top_left, top_right = st.columns([3, 1])
    with top_right:
        render_schedule_auto_button(db, deal, key_prefix="detail-top")
    next_actions = recommended_next_actions(db, deal)
    if next_actions:
        focus_action = st.session_state.pop(FOCUS_ACTION_KEY, next_actions[0])
        st.info(
            f"次におすすめ: {focus_action}。必要な作業画面を開いています。"
        )
    detail_views = [
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
    requested_view = st.session_state.pop(DETAIL_VIEW_KEY, "概要")
    selected_view = st.radio(
        "作業メニュー",
        detail_views,
        index=detail_views.index(requested_view) if requested_view in detail_views else 0,
        horizontal=True,
    )
    if selected_view == "概要":
        render_overview_tab(db, deal)
    elif selected_view == "商談前リサーチ":
        render_research_tab(db, deal)
    elif selected_view == "ヒアリング設計":
        render_hearing_tab(db, deal)
    elif selected_view == "商談メモ分析":
        render_meeting_tab(db, deal)
    elif selected_view == "メール生成":
        render_email_tab(db, deal)
    elif selected_view == "提案資料骨子":
        render_proposal_tab(db, deal)
    elif selected_view == "タイムライン":
        render_timeline_tab(db, deal)
    elif selected_view == "受注・失注分析":
        render_winloss_tab(db, deal)
    else:
        for output in outputs_for_deal(db, deal["id"]):
            with st.expander(f"{AI_LABELS.get(output['type'], output['type'])} / {output['created_at']}"):
                render_output(output, db, deal, tools_in_expander=False, key_prefix="history")


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
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
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
APP_PASSWORD = "任意の運営用パスコード"
```

### 4. Deploy
公開URLは `https://任意の名前.streamlit.app` になります。

### 注意
この初期版は登録、ログイン、マイページ、解約申請をJSONファイル保存で動かします。
Streamlit Cloudの再起動や再デプロイで保存データが消える可能性があるため、実ユーザー運用に入る前にSupabaseなどのDBとStripeなどのサブスク決済へ差し替えてください。
"""
    )


def main() -> None:
    st.set_page_config(page_title=APP_NAME, layout="wide")
    st.markdown(
        """
        <style>
        .block-container { padding-top: 1.4rem; padding-bottom: 3rem; max-width: 1280px; }
        div[data-testid="stMetric"] { background: #f8fafc; border: 1px solid #e2e8f0; padding: 12px; border-radius: 8px; }
        div[data-testid="stVerticalBlockBorderWrapper"] { border-radius: 8px; }
        div[data-testid="stButton"] > button,
        div[data-testid="stDownloadButton"] > button,
        div[data-testid="stLinkButton"] > a { min-height: 2.5rem; border-radius: 8px; }
        div[data-baseweb="tab-list"] { gap: .15rem; flex-wrap: wrap; }
        div[data-baseweb="tab"] { padding: .55rem .75rem; white-space: nowrap; }
        div[data-testid="stDataFrame"] { border: 1px solid #e2e8f0; border-radius: 8px; }
        textarea { min-height: 5rem; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    db = load_db()
    st.sidebar.title(APP_NAME)
    st.sidebar.caption(f"{PLAN_INTERVAL}{PLAN_PRICE_YEN:,}円プラン")
    pages = PUBLIC_PAGES + PROTECTED_PAGES
    requested_page = st.session_state.pop(NAV_REQUEST_KEY, None)
    query_page = st.query_params.get(PAGE_QUERY_KEY)
    user = current_user(db)
    if requested_page in pages:
        default_page = requested_page
    elif query_page in pages:
        default_page = query_page
    elif not user and not st.session_state.get("admin_authenticated"):
        default_page = "サービス登録"
    else:
        default_page = "ダッシュボード"
    page = st.sidebar.radio(
        "メニュー",
        pages,
        index=pages.index(default_page) if default_page in pages else 0,
        key=f"{NAV_KEY}_{pages.index(default_page) if default_page in pages else 0}",
    )
    if st.query_params.get(PAGE_QUERY_KEY) != page:
        st.query_params[PAGE_QUERY_KEY] = page
    st.sidebar.divider()
    if user:
        st.sidebar.success(f"{user['name']}さんでログイン中")
        if st.sidebar.button("ログアウト"):
            logout_user()
            st.session_state[NAV_REQUEST_KEY] = "ログイン"
            st.rerun()
        st.sidebar.divider()
    elif st.session_state.get("admin_authenticated"):
        st.sidebar.success("運営モード")
        if st.sidebar.button("ログアウト"):
            logout_user()
            st.session_state[NAV_REQUEST_KEY] = "ログイン"
            st.rerun()
        st.sidebar.divider()

    if page not in PUBLIC_PAGES:
        st.sidebar.selectbox(
            "AI品質モード",
            QUALITY_MODES,
            index=QUALITY_MODES.index(DEFAULT_QUALITY_MODE) if DEFAULT_QUALITY_MODE in QUALITY_MODES else 1,
            key="quality_mode",
            help="エコノミーは原価優先、標準は重要生成だけ高品質、高品質は品質優先です。",
        )
        st.sidebar.divider()
        st.sidebar.caption("セキュリティ/注意事項")
        st.sidebar.write("入力情報は、ログイン中ユーザーへのAIレスポンス生成にのみ利用します。")

    if not require_account(db, page):
        return

    if page == "サービス登録":
        render_signup(db)
    elif page == "ログイン":
        render_login(db)
    elif page == "マイページ":
        render_mypage(db)
    elif page == "ダッシュボード":
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

