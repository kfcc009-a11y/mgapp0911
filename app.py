"""MG Supabase 통합 CRUD 대시보드.

실행:
    pip install streamlit supabase pandas
    streamlit run streamlit_supabase_crud_dashboard.py

권장 Streamlit secrets (.streamlit/secrets.toml):
    SUPABASE_URL = "https://<project-ref>.supabase.co"
    SUPABASE_KEY = "sb_publishable_..."
"""

from __future__ import annotations

import base64
import json
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import pandas as pd
import streamlit as st
from supabase import Client, create_client


st.set_page_config(page_title="MG 통합 DB 관리", page_icon="🏦", layout="wide")


def field(label: str, kind: str = "text", options=None, nullable: bool = False):
    return {"label": label, "kind": kind, "options": options, "nullable": nullable}


TABLES = {
    "branches": {
        "label": "지점 관리",
        "pk": ["branch_id"],
        "fields": {
            "branch_id": field("지점 ID", "int"),
            "branch_name": field("지점명"),
            "region": field("지역"),
            "manager_name": field("관리자명"),
        },
    },
    "members": {
        "label": "조합원 관리",
        "pk": ["member_id"],
        "fields": {
            "member_id": field("조합원 번호", "int"),
            "name": field("이름"),
            "birth_date": field("생년월일", "date"),
            "gender": field("성별", "select", ["M", "F"]),
            "join_date": field("가입일", "date"),
            "branch_id": field("지점 ID", "int"),
            "phone": field("전화번호"),
        },
    },
    "deposit_accounts": {
        "label": "예·적금 관리",
        "pk": ["account_id"],
        "fields": {
            "account_id": field("계좌 ID", "int"),
            "member_id": field("조합원 번호", "int"),
            "branch_id": field("지점 ID", "int"),
            "account_type": field("계좌 종류", "select", ["보통예금", "정기예금", "정기적금", "자유적금"]),
            "open_date": field("개설일", "date"),
            "balance": field("잔액", "decimal"),
            "interest_rate": field("금리(%)", "decimal"),
        },
    },
    "loans": {
        "label": "대출 관리",
        "pk": ["loan_id"],
        "fields": {
            "loan_id": field("대출 ID", "int"),
            "member_id": field("조합원 번호", "int"),
            "branch_id": field("지점 ID", "int"),
            "loan_type": field("대출 종류", "select", ["신용대출", "전세자금대출", "담보대출"]),
            "loan_amount": field("대출금액", "decimal"),
            "interest_rate": field("금리(%)", "decimal"),
            "start_date": field("실행일", "date"),
            "due_date": field("만기일", "date"),
            "status": field("상태", "select", ["정상", "연체", "완제"]),
        },
    },
    "transactions": {
        "label": "거래내역 관리",
        "pk": ["transaction_id"],
        "fields": {
            "transaction_id": field("거래 ID", "int"),
            "account_id": field("계좌 ID", "int"),
            "transaction_date": field("거래일시", "datetime"),
            "transaction_type": field("거래 구분", "select", ["입금", "출금"]),
            "amount": field("거래금액", "decimal"),
            "balance_after": field("거래 후 잔액", "decimal"),
        },
    },
    "deposit_rate_research": {
        "label": "시장금리 관리",
        "pk": ["institution_name", "product_name"],
        "fields": {
            "institution_name": field("금융기관명"),
            "sector_category": field("권역 분류"),
            "product_name": field("대표 상품명"),
            "base_rate": field("기본금리(연%)", "decimal"),
            "maximum_rate": field("최고우대금리(연%)", "decimal"),
            "preferential_conditions": field("주요 우대 조건", "textarea", nullable=True),
        },
    },
}


@st.cache_resource(show_spinner=False)
def get_client(url: str, key: str) -> Client:
    return create_client(url, key)


def secret(name: str) -> str:
    try:
        return str(st.secrets.get(name, ""))
    except Exception:
        return ""


def reject_privileged_key(key: str) -> bool:
    if key.startswith("sb_secret_") or "service_role" in key:
        return True
    if key.startswith("eyJ"):
        try:
            payload = key.split(".")[1]
            payload += "=" * (-len(payload) % 4)
            claims = json.loads(base64.urlsafe_b64decode(payload))
            return claims.get("role") == "service_role"
        except (ValueError, json.JSONDecodeError):
            return False
    return False


def normalize(value: Any, kind: str, nullable: bool = False) -> Any:
    if value in (None, ""):
        return None if nullable else value
    if kind == "int":
        return int(value)
    if kind == "decimal":
        try:
            return float(Decimal(str(value).replace(",", "")))
        except InvalidOperation as exc:
            raise ValueError("숫자 형식이 올바르지 않습니다.") from exc
    if kind == "date":
        return value.isoformat() if hasattr(value, "isoformat") else str(value)
    if kind == "datetime":
        return value.isoformat(sep=" ") if hasattr(value, "isoformat") else str(value)
    return str(value).strip()


def default_value(kind: str):
    if kind == "date":
        return date.today()
    if kind == "datetime":
        return datetime.now().replace(second=0, microsecond=0)
    if kind == "int":
        return 0
    if kind == "decimal":
        return 0.0
    return ""


def parse_existing(value: Any, kind: str):
    if value is None:
        return default_value(kind)
    if kind == "date":
        return date.fromisoformat(str(value)[:10])
    if kind == "datetime":
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    if kind == "int":
        return int(value)
    if kind == "decimal":
        return float(value)
    return str(value).strip()


def input_widget(name: str, spec: dict, value: Any, disabled: bool, key: str):
    label, kind = spec["label"], spec["kind"]
    if kind == "select":
        options = spec["options"]
        index = options.index(value) if value in options else 0
        return st.selectbox(label, options, index=index, disabled=disabled, key=key)
    if kind == "textarea":
        return st.text_area(label, value=value, disabled=disabled, key=key)
    if kind == "date":
        return st.date_input(label, value=value, disabled=disabled, key=key)
    if kind == "datetime":
        return st.text_input(
            label, value=str(value), disabled=disabled, key=key,
            help="예: 2026-09-11 14:30:00",
        )
    if kind == "int":
        return st.number_input(label, value=int(value), step=1, disabled=disabled, key=key)
    if kind == "decimal":
        return st.number_input(label, value=float(value), step=0.01, format="%.2f", disabled=disabled, key=key)
    return st.text_input(label, value=value, disabled=disabled, key=key)


def filters_for(config: dict, row: dict):
    return [(pk, row[pk]) for pk in config["pk"]]


def apply_filters(query, filters):
    for column, value in filters:
        query = query.eq(column, value)
    return query


def next_numeric_id(client: Client, table: str, config: dict) -> int:
    if len(config["pk"]) != 1:
        return 0
    pk = config["pk"][0]
    if config["fields"][pk]["kind"] != "int":
        return 0
    result = client.table(table).select(pk).order(pk, desc=True).limit(1).execute()
    return int(result.data[0][pk]) + 1 if result.data else 1


def load_rows(client: Client, table: str, config: dict):
    return (
        client.table(table)
        .select("*")
        .order(config["pk"][0])
        .limit(1000)
        .execute()
        .data
    )


def editor_form(client: Client, table: str, config: dict, mode: str, selected: dict | None):
    is_create = mode == "신규 등록"
    values = {}
    with st.form(f"record_form_{table}_{mode}", clear_on_submit=is_create):
        columns = st.columns(2)
        for idx, (name, spec) in enumerate(config["fields"].items()):
            is_pk = name in config["pk"]
            if selected:
                initial = parse_existing(selected.get(name), spec["kind"])
            elif is_pk and spec["kind"] == "int":
                initial = next_numeric_id(client, table, config)
            else:
                initial = default_value(spec["kind"])
            with columns[idx % 2]:
                values[name] = input_widget(
                    name, spec, initial, disabled=(not is_create and is_pk),
                    key=f"{table}_{mode}_{name}",
                )
        submitted = st.form_submit_button("등록" if is_create else "수정 저장", type="primary")

    if not submitted:
        return
    payload = {}
    for name, spec in config["fields"].items():
        if not is_create and name in config["pk"]:
            continue
        payload[name] = normalize(values[name], spec["kind"], spec["nullable"])
    try:
        if is_create:
            client.table(table).insert(payload).execute()
            st.success("새 데이터를 등록했습니다.")
        else:
            query = client.table(table).update(payload)
            apply_filters(query, filters_for(config, selected)).execute()
            st.success("데이터를 수정했습니다.")
        st.cache_data.clear()
        st.rerun()
    except Exception as exc:
        st.error(f"저장 실패: {exc}")


def delete_panel(client: Client, table: str, config: dict, selected: dict | None):
    if not selected:
        st.info("삭제할 행을 먼저 선택하세요.")
        return
    pk_text = ", ".join(f"{pk}={selected[pk]}" for pk in config["pk"])
    st.warning(f"삭제 대상: {pk_text}\n\n외래키로 연결된 데이터가 있으면 삭제가 거부될 수 있습니다.")
    confirm = st.checkbox("삭제 대상과 영향을 확인했습니다.", key=f"delete_confirm_{table}")
    if st.button("영구 삭제", type="primary", disabled=not confirm, key=f"delete_{table}"):
        try:
            query = client.table(table).delete()
            apply_filters(query, filters_for(config, selected)).execute()
            st.success("데이터를 삭제했습니다.")
            st.rerun()
        except Exception as exc:
            st.error(f"삭제 실패: {exc}")


st.markdown("""
<style>
  .block-container {padding-top: 1.4rem; padding-bottom: 3rem;}
  [data-testid="stMetric"] {background:#f7faf8;border:1px solid #dfe9e2;border-radius:14px;padding:16px;}
  .security {padding:12px 16px;border-radius:10px;background:#fff4e5;border:1px solid #f5c26b;color:#714d00;}
</style>
""", unsafe_allow_html=True)

st.title("🏦 MG 통합 DB 관리 대시보드")
st.caption("Supabase public 스키마의 지점·조합원·예적금·대출·거래·시장금리 데이터 CRUD")

with st.sidebar:
    st.header("Supabase 연결")
    url = st.text_input("SUPABASE_URL", value=secret("SUPABASE_URL"), placeholder="https://...supabase.co")
    key = st.text_input("SUPABASE_KEY", value=secret("SUPABASE_KEY"), type="password", placeholder="sb_publishable_...")
    st.caption("배포 시 `.streamlit/secrets.toml` 또는 Streamlit Cloud Secrets 사용을 권장합니다.")
    selected_table = st.selectbox("관리 메뉴", list(TABLES), format_func=lambda x: TABLES[x]["label"])

if not url or not key:
    st.info("왼쪽 사이드바에 Supabase URL과 publishable/anon 키를 입력하세요.")
    st.stop()
if reject_privileged_key(key):
    st.error("보안을 위해 secret/service_role 키는 이 대시보드에서 사용할 수 없습니다.")
    st.stop()

client = get_client(url.rstrip("/"), key.strip())
config = TABLES[selected_table]

st.markdown(
    '<div class="security">⚠️ 운영 전 Supabase Auth와 테이블별 RLS 정책을 설정하세요. '
    '현재 프로젝트의 일부 테이블은 RLS가 비활성화되어 있습니다.</div>',
    unsafe_allow_html=True,
)

try:
    rows = load_rows(client, selected_table, config)
except Exception as exc:
    st.error(f"데이터 조회 실패: {exc}")
    st.stop()

metric_cols = st.columns(3)
metric_cols[0].metric("현재 메뉴", config["label"])
metric_cols[1].metric("조회 건수", f"{len(rows):,}건")
metric_cols[2].metric("조회 제한", "최대 1,000건")

st.subheader(config["label"])
search = st.text_input("현재 테이블 검색", placeholder="검색할 값을 입력하세요")
display_rows = rows
if search:
    needle = search.casefold()
    display_rows = [row for row in rows if any(needle in str(v).casefold() for v in row.values())]

labels = {name: spec["label"] for name, spec in config["fields"].items()}
frame = pd.DataFrame(display_rows)
if not frame.empty:
    frame = frame.rename(columns=labels)
st.dataframe(frame, use_container_width=True, hide_index=True, height=390)

row_options = list(range(len(rows)))
selected_index = st.selectbox(
    "수정·삭제할 행 선택",
    [None] + row_options,
    format_func=lambda i: "선택 안 함" if i is None else " | ".join(
        f"{labels.get(pk, pk)}: {rows[i].get(pk)}" for pk in config["pk"]
    ),
)
selected_row = rows[selected_index] if selected_index is not None else None

tab_create, tab_update, tab_delete = st.tabs(["➕ 신규 등록", "✏️ 수정", "🗑️ 삭제"])
with tab_create:
    editor_form(client, selected_table, config, "신규 등록", None)
with tab_update:
    if selected_row:
        editor_form(client, selected_table, config, "수정", selected_row)
    else:
        st.info("위에서 수정할 행을 선택하세요.")
with tab_delete:
    delete_panel(client, selected_table, config, selected_row)

with st.expander("실행 및 배포 안내"):
    st.code("pip install streamlit supabase pandas\nstreamlit run streamlit_supabase_crud_dashboard.py", language="bash")
    st.markdown(
        "Streamlit Cloud에서는 앱 설정의 **Secrets**에 `SUPABASE_URL`과 "
        "`SUPABASE_KEY`를 등록하세요. secret/service_role 키를 공개 저장소에 커밋하면 안 됩니다."
    )
