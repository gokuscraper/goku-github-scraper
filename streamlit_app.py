import io
import json
import os
import subprocess
import time
import html
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import altair as alt
import numpy as np
import pandas as pd
import requests
import streamlit as st


SETTINGS_FILE = "streamlit_ui_settings.json"
APP_DIR = Path(__file__).resolve().parent


def resolve_asset_path(file_name: str) -> str:
    candidates = [
        APP_DIR / file_name,
        Path.cwd() / file_name,
    ]
    for p in candidates:
        if p.exists():
            return str(p)
    return file_name


# -------------------------------
# 基础工具
# -------------------------------
def load_settings() -> Dict[str, Any]:
    if not os.path.exists(SETTINGS_FILE):
        return {
            "mode": "免登录",
            "output_dir": os.getcwd(),
        }

    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        mode_value = data.get("mode", "免登录")
        if mode_value == "匿名":
            mode_value = "免登录"
        return {
            "mode": mode_value,
            "output_dir": data.get("output_dir", os.getcwd()),
        }
    except Exception:
        return {
            "mode": "免登录",
            "output_dir": os.getcwd(),
        }


def save_settings(mode: str, output_dir: str) -> None:
    data = {
        "mode": mode,
        "output_dir": output_dir,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def extract_username(raw: str) -> Optional[str]:
    if not raw:
        return None
    value = raw.strip()
    if "github.com/" in value:
        try:
            suffix = value.split("github.com/")[1]
            username = suffix.split("?")[0].split("/")[0].strip()
            return username or None
        except Exception:
            return None
    if "/" in value or " " in value:
        return None
    return value


def build_headers(token: str) -> Dict[str, str]:
    headers = {
        "User-Agent": "Github-Collector-Streamlit-UI/1.0",
        "Accept": "application/vnd.github.v3+json",
    }
    if token:
        headers["Authorization"] = f"token {token.strip()}"
    return headers


def parse_rate_headers(resp: requests.Response) -> Dict[str, Optional[int]]:
    def _to_int(v: Optional[str]) -> Optional[int]:
        if v is None:
            return None
        try:
            return int(v)
        except Exception:
            return None

    return {
        "limit": _to_int(resp.headers.get("X-RateLimit-Limit")),
        "remaining": _to_int(resp.headers.get("X-RateLimit-Remaining")),
        "reset": _to_int(resp.headers.get("X-RateLimit-Reset")),
    }


def github_get(url: str, token: str, timeout: int = 20) -> Tuple[Optional[requests.Response], Optional[str]]:
    try:
        resp = requests.get(url, headers=build_headers(token), timeout=timeout)
        return resp, None
    except Exception as e:
        return None, str(e)


def to_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")


def write_csv_to_disk(df: pd.DataFrame, output_dir: str, file_name: str) -> str:
    os.makedirs(output_dir, exist_ok=True)
    full_path = os.path.join(output_dir, file_name)
    df.to_csv(full_path, index=False, encoding="utf-8-sig")
    return full_path


def to_datetime_safe(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, errors="coerce", utc=True)


def format_time_with_elapsed(value: Any) -> str:
    dt = pd.to_datetime(value, errors="coerce", utc=True)
    if pd.isna(dt):
        return "未设置"

    now = pd.Timestamp.now(tz="UTC")
    delta_days = max(0, int((now - dt).days))
    years = delta_days // 365
    months = (delta_days % 365) // 30
    days = (delta_days % 365) % 30

    time_str = dt.strftime("%Y年%m月%d日 %H:%M:%S")
    elapsed = f"距今{years}年{months}个月{days}天"
    return f"{time_str}（UTC，{elapsed}）"


def calc_repo_influence_score(df: pd.DataFrame) -> pd.DataFrame:
    scored = df.copy()
    star = pd.to_numeric(scored.get("Star数", 0), errors="coerce").fillna(0)
    fork = pd.to_numeric(scored.get("Fork数", 0), errors="coerce").fillna(0)
    issues = pd.to_numeric(scored.get("开放Issue数", 0), errors="coerce").fillna(0)

    pushed_at = to_datetime_safe(scored.get("最后推送", pd.Series([None] * len(scored))))
    now = pd.Timestamp.now(tz="UTC")
    days_since_push = (now - pushed_at).dt.days
    freshness = (1 - (days_since_push.fillna(3650).clip(lower=0, upper=3650) / 3650)).clip(lower=0, upper=1)

    # 归一化到 0-100：采用对数尺度，避免中小仓库被放大。
    # 让 Linux 这类超大仓库（高 Star/高 Fork）才接近高分。
    star_score = (np.log10(star + 1) / 5.3 * 100).clip(lower=0, upper=100)
    fork_score = (np.log10(fork + 1) / 4.2 * 100).clip(lower=0, upper=100)
    issues_score = (np.log10(issues + 1) / 3.0 * 100).clip(lower=0, upper=100)
    activity_score = (freshness * 100).clip(lower=0, upper=100)

    score = (
        star_score * 0.55
        + fork_score * 0.25
        + activity_score * 0.10
        + issues_score * 0.10
    ).clip(lower=0, upper=100)

    scored["仓库影响力评分"] = score.round(2)
    return scored


def render_bar_with_horizontal_labels(df: pd.DataFrame, x_col: str, y_col: str, y_title: str = "") -> None:
    chart = (
        alt.Chart(df)
        .mark_bar()
        .encode(
            x=alt.X(f"{x_col}:N", sort="-y", axis=alt.Axis(labelAngle=0, title=x_col)),
            y=alt.Y(f"{y_col}:Q", title=(y_title or y_col)),
            tooltip=[x_col, y_col],
        )
    )
    st.altair_chart(chart, use_container_width=True)


def render_line_with_horizontal_labels(df: pd.DataFrame, x_col: str, y_col: str, y_title: str = "") -> None:
    chart = (
        alt.Chart(df)
        .mark_line(point=True)
        .encode(
            x=alt.X(f"{x_col}:N", axis=alt.Axis(labelAngle=0, title=x_col)),
            y=alt.Y(f"{y_col}:Q", title=(y_title or y_col)),
            tooltip=[x_col, y_col],
        )
    )
    st.altair_chart(chart, use_container_width=True)


def render_time_info_card(title: str, value: Any, accent_color: str = "#2563eb") -> None:
    formatted = format_time_with_elapsed(value)
    main_time = formatted
    elapsed_text = ""

    if "（UTC，" in formatted and formatted.endswith("）"):
        parts = formatted.split("（UTC，", 1)
        main_time = parts[0].strip()
        elapsed_text = parts[1][:-1].strip()

    st.markdown(
        f"""
        <div style="
            border:1px solid #e5e7eb;
            border-left:4px solid {accent_color};
            border-radius:10px;
            padding:14px 16px;
            background:#ffffff;
            min-height:110px;
            box-shadow:0 1px 2px rgba(0,0,0,0.03);
        ">
            <div style="font-size:13px;color:#6b7280;margin-bottom:6px;">{html.escape(title)}</div>
            <div style="font-size:18px;font-weight:700;color:#111827;line-height:1.35;word-break:break-word;">{html.escape(main_time)}</div>
            <div style="font-size:13px;color:#4b5563;margin-top:8px;">{html.escape(elapsed_text or 'UTC')}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def choose_directory_dialog(initial_dir: str) -> Optional[str]:
    """打开本地文件夹选择弹窗。"""
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        selected = filedialog.askdirectory(
            initialdir=initial_dir or os.getcwd(),
            title="请选择导出目录",
        )
        root.destroy()
        return selected or None
    except Exception:
        pass

    if os.name == "nt":
        try:
            initial = str(Path(initial_dir or os.getcwd()).resolve()).replace("'", "''")
            ps_script = (
                "Add-Type -AssemblyName System.Windows.Forms; "
                "$d = New-Object System.Windows.Forms.FolderBrowserDialog; "
                f"$d.SelectedPath = '{initial}'; "
                "$d.Description = '请选择导出目录'; "
                "if ($d.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) { "
                "Write-Output $d.SelectedPath "
                "}"
            )
            completed = subprocess.run(
                ["powershell", "-NoProfile", "-STA", "-Command", ps_script],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            selected = (completed.stdout or "").strip()
            return selected or None
        except Exception as e:
            st.error(f"打开文件夹弹窗失败：{e}")
            return None

    return None


# -------------------------------
# GitHub 数据采集逻辑
# -------------------------------
def check_rate_limit(token: str) -> Tuple[bool, str, Dict[str, Optional[int]]]:
    url = "https://api.github.com/rate_limit"
    resp, err = github_get(url, token)
    if err:
        return False, f"网络异常：{err}", {"limit": None, "remaining": None, "reset": None}
    if resp is None:
        return False, "请求失败", {"limit": None, "remaining": None, "reset": None}

    rate = parse_rate_headers(resp)
    if resp.status_code == 200:
        return True, "额度检查成功", rate
    if resp.status_code == 401:
        return False, "Token 无效（401）", rate
    return False, f"额度检查失败，状态码：{resp.status_code}", rate


def get_user_profile(username: str, token: str) -> Tuple[Optional[Dict[str, Any]], str, Dict[str, Optional[int]]]:
    api_url = f"https://api.github.com/users/{username}"
    resp, err = github_get(api_url, token)
    if err:
        return None, f"网络异常：{err}", {"limit": None, "remaining": None, "reset": None}
    if resp is None:
        return None, "请求失败", {"limit": None, "remaining": None, "reset": None}

    rate = parse_rate_headers(resp)
    if resp.status_code != 200:
        if resp.status_code == 404:
            return None, "用户不存在（404）", rate
        if resp.status_code == 401:
            return None, "Token 无效（401）", rate
        return None, f"请求失败，状态码：{resp.status_code}", rate

    user_data = resp.json()
    result = {
        "登录名": user_data.get("login"),
        "昵称": user_data.get("name"),
        "个人简介": user_data.get("bio"),
        "所在地": user_data.get("location"),
        "博客/主页": user_data.get("blog"),
        "所属公司": user_data.get("company"),
        "邮箱": user_data.get("email"),
        "推特": user_data.get("twitter_username"),
        "公开项目数": user_data.get("public_repos"),
        "粉丝数": user_data.get("followers"),
        "账号创建时间": user_data.get("created_at"),
        "最后活跃时间": user_data.get("updated_at"),
    }
    return result, "查询成功", rate


def get_full_intelligence(username: str, token: str) -> Tuple[Optional[Dict[str, Any]], str, Dict[str, Optional[int]]]:
    user_api = f"https://api.github.com/users/{username}"

    resp_user, err_user = github_get(user_api, token)
    if err_user:
        return None, f"网络异常：{err_user}", {"limit": None, "remaining": None, "reset": None}
    if resp_user is None:
        return None, "请求失败", {"limit": None, "remaining": None, "reset": None}

    rate = parse_rate_headers(resp_user)
    if resp_user.status_code != 200:
        if resp_user.status_code == 404:
            return None, "用户不存在（404）", rate
        if resp_user.status_code == 401:
            return None, "Token 无效（401）", rate
        return None, f"无法调取档案，状态码：{resp_user.status_code}", rate

    user_data = resp_user.json()

    intelligence = {
        "用户名": user_data.get("login"),
        "昵称": user_data.get("name"),
        "个人简介": user_data.get("bio"),
        "所在地": user_data.get("location"),
        "主页/博客": user_data.get("blog"),
        "公司": user_data.get("company"),
        "邮箱": user_data.get("email"),
        "推特": user_data.get("twitter_username"),
        "公开项目数": user_data.get("public_repos"),
        "粉丝数": user_data.get("followers"),
        "关注数": user_data.get("following"),
        "创建时间": user_data.get("created_at"),
        "最后更新": user_data.get("updated_at"),
        "GitHub_ID": user_data.get("id"),
        "头像链接": user_data.get("avatar_url"),
    }
    return intelligence, "增强画像完成（同一用户API）", rate


def get_repos_master(username: str, token: str, only_original: bool = True) -> Tuple[Optional[pd.DataFrame], str, Dict[str, Optional[int]]]:
    repos_api = f"https://api.github.com/users/{username}/repos?per_page=100"
    resp, err = github_get(repos_api, token)
    if err:
        return None, f"网络异常：{err}", {"limit": None, "remaining": None, "reset": None}
    if resp is None:
        return None, "请求失败", {"limit": None, "remaining": None, "reset": None}

    rate = parse_rate_headers(resp)
    if resp.status_code != 200:
        if resp.status_code == 404:
            return None, "用户不存在（404）", rate
        if resp.status_code == 401:
            return None, "Token 无效（401）", rate
        return None, f"调取失败，状态码：{resp.status_code}", rate

    all_repos = resp.json()
    master_list = []
    for repo in all_repos:
        if only_original and repo.get("fork"):
            continue
        row = {
            "项目名称": repo.get("name"),
            "Star数": repo.get("stargazers_count"),
            "主要语言": repo.get("language"),
            "项目描述": repo.get("description"),
            "项目链接": repo.get("html_url"),
            "Fork数": repo.get("forks_count"),
            "项目大小(KB)": repo.get("size"),
            "核心标签": ", ".join(repo.get("topics", [])),
            "创建时间": repo.get("created_at"),
            "最后推送": repo.get("pushed_at"),
            "最后更新": repo.get("updated_at"),
            "许可证": repo.get("license").get("name") if repo.get("license") else "无",
            "开放Issue数": repo.get("open_issues_count"),
            "是否有Wiki": "是" if repo.get("has_wiki") else "否",
        }
        master_list.append(row)

    if not master_list:
        return pd.DataFrame(), "没有可导出的仓库数据", rate

    df = pd.DataFrame(master_list).sort_values(by="Star数", ascending=False)
    return df, f"仓库信息采集完成，共 {len(df)} 条", rate


def get_commits_from_repos_df(
    repos_df: pd.DataFrame,
    token: str,
    max_repos: int = 0,
    max_pages_per_repo: int = 1,
    max_retries: int = 3,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    all_commits_list = []
    stats = {
        "total_repos": 0,
        "done_repos": 0,
        "skipped_empty_size": 0,
        "skipped_409": 0,
        "failed_repos": 0,
    }

    if repos_df is None or repos_df.empty:
        return pd.DataFrame(), stats

    df_iter = repos_df.copy()
    if max_repos and max_repos > 0:
        df_iter = df_iter.head(max_repos)

    stats["total_repos"] = len(df_iter)

    bar = st.progress(0, text="等待开始...")
    log_box = st.empty()
    logs = []

    def push_log(msg: str) -> None:
        logs.append(msg)
        log_box.text("\n".join(logs[-15:]))

    for idx, row in df_iter.iterrows():
        repo_name = row.get("项目名称")
        repo_url = row.get("项目链接", "")
        repo_size = row.get("项目大小(KB)", 0)

        if pd.isna(repo_size):
            repo_size = 0

        done_count = stats["done_repos"] + stats["failed_repos"] + stats["skipped_empty_size"] + stats["skipped_409"]
        progress = min((done_count + 1) / max(stats["total_repos"], 1), 1.0)
        bar.progress(progress, text=f"处理仓库：{repo_name}")

        try:
            parts = str(repo_url).split("github.com/")[1].split("/")
            owner, repo = parts[0], parts[1]
        except Exception:
            stats["failed_repos"] += 1
            push_log(f"❌ [{repo_name}] 项目链接解析失败")
            continue

        if float(repo_size) == 0:
            stats["skipped_empty_size"] += 1
            push_log(f"⏭️ [{repo_name}] 大小为0KB，跳过")
            continue

        page = 1
        while True:
            if max_pages_per_repo > 0 and page > max_pages_per_repo:
                push_log(f"⏹️ [{repo_name}] 已达到页数上限（{max_pages_per_repo}页），停止该仓库")
                break

            api_url = f"https://api.github.com/repos/{owner}/{repo}/commits?per_page=100&page={page}"
            resp, err = None, None
            for attempt in range(1, max_retries + 1):
                resp, err = github_get(api_url, token)

                if err or resp is None:
                    if attempt < max_retries:
                        push_log(f"🔁 [{repo_name}] 第{page}页请求异常，重试 {attempt}/{max_retries}")
                        time.sleep(0.4 * attempt)
                        continue
                    break

                if resp.status_code in (200, 409):
                    break

                if attempt < max_retries:
                    push_log(f"🔁 [{repo_name}] 第{page}页状态码{resp.status_code}，重试 {attempt}/{max_retries}")
                    time.sleep(0.4 * attempt)
                    continue
                break

            if err:
                stats["failed_repos"] += 1
                push_log(f"💥 [{repo_name}] 网络异常（已重试{max_retries}次）：{err}")
                break
            if resp is None:
                stats["failed_repos"] += 1
                push_log(f"❌ [{repo_name}] 请求失败（已重试{max_retries}次）")
                break

            rate = parse_rate_headers(resp)

            if resp.status_code == 409:
                stats["skipped_409"] += 1
                push_log(f"⚠️ [{repo_name}] 无 Commit 历史（409），跳过")
                break

            if resp.status_code != 200:
                stats["failed_repos"] += 1
                push_log(f"❌ [{repo_name}] 抓取失败，状态码：{resp.status_code}")
                break

            commits = resp.json()
            if not commits:
                break

            push_log(f"📥 [{repo_name}] 第 {page} 页，累计 {len(all_commits_list)} 条")
            for c in commits:
                commit_obj = c.get("commit", {})
                message = commit_obj.get("message") or ""
                all_commits_list.append(
                    {
                        "所属仓库": repo_name,
                        "SHA": c.get("sha"),
                        "作者姓名": commit_obj.get("author", {}).get("name"),
                        "作者邮箱": commit_obj.get("author", {}).get("email"),
                        "提交日期": commit_obj.get("author", {}).get("date"),
                        "提交信息": message.replace("\n", " "),
                    }
                )

            if len(commits) < 100:
                break

            page += 1
            time.sleep(0.1)

        stats["done_repos"] += 1

    return pd.DataFrame(all_commits_list), stats


# -------------------------------
# 状态管理
# -------------------------------
def init_state() -> None:
    settings = load_settings()
    defaults = {
        "mode": settings.get("mode", "免登录"),
        "token": "",
        "raw_user_input": "",
        "username": "",
        "output_dir": settings.get("output_dir", os.getcwd()),
        "guard_checked": False,
        "guard_passed": False,
        "rate": {"limit": None, "remaining": None, "reset": None},
        "profile_data": None,
        "intelligence_data": None,
        "repos_df": None,
        "commits_df": None,
        "analysis_ready": False,
        "last_message": "",
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def update_rate(rate: Dict[str, Optional[int]]) -> None:
    st.session_state["rate"] = rate


def check_hard_guard_before_action() -> Tuple[bool, str]:
    if not st.session_state.get("guard_checked", False):
        return False, "请先在【配置与额度检查】页执行额度检查。"

    if not st.session_state.get("guard_passed", False):
        return False, "当前未通过校验，请先检查连接或填写有效 Token。"

    return True, ""


def render_rate_panel(target: Optional[Any] = None) -> None:
    rate = st.session_state.get("rate", {})
    mode = st.session_state.get("mode", "免登录")
    limit = rate.get("limit")
    remaining = rate.get("remaining")

    def _draw() -> None:
        c1, c2, c3 = st.columns(3)
        c1.metric("当前模式", mode)
        c2.metric("API总额度", "未知" if limit is None else str(limit))
        c3.metric("剩余额度", "未知" if remaining is None else str(remaining))

    if target is None:
        _draw()
    else:
        with target.container():
            _draw()


# -------------------------------
# UI
# -------------------------------
def main() -> None:
    st.set_page_config(
        page_title="悟空GitHub数据分析工具",
        page_icon=resolve_asset_path("logo.svg"),
        layout="wide",
        initial_sidebar_state="expanded",
    )
    init_state()

    st.sidebar.markdown("<h2 style='text-align: center; margin-bottom: 0.4rem;'>公众号与交流群</h2>", unsafe_allow_html=True)
    st.sidebar.image(resolve_asset_path("gzh.jpg"), caption="扫码加群", use_container_width=True)
    st.sidebar.markdown(
        "<div style='text-align: center; margin-top: 0.35rem; color: #4b5563; line-height: 1.6;'>"
        "让数据不仅被看见，更被读懂。<br>"
        "悟空爬虫提供从数据采集、多维分析到决策报告的全链路数据服务。"
        "</div>",
        unsafe_allow_html=True,
    )
    st.sidebar.markdown(
        "<div style='text-align: center; margin-top: 0.35rem;'><a href='https://gokuscraper.cn' target='_blank'>官网：gokuscraper.cn</a></div>",
        unsafe_allow_html=True,
    )

    title_col1, title_col2 = st.columns([1, 14])
    with title_col1:
        st.markdown("<div style='height:10px;'></div>", unsafe_allow_html=True)
        st.image(resolve_asset_path("logo.svg"), width=42)
    with title_col2:
        st.markdown("<h1 style='margin: 0; margin-left: -22px;'>悟空GitHub数据分析工具</h1>", unsafe_allow_html=True)
    st.caption("让数据不仅被看见，更被读懂。")

    rate_placeholder = st.empty()
    render_rate_panel(rate_placeholder)
    st.divider()

    tab_guard, tab_profile, tab_repos, tab_commits, tab_analysis = st.tabs(
        ["配置与额度检查", "基础信息采集", "仓库信息采集", "commit信息采集", "开发者画像分析"]
    )

    with tab_guard:
        st.subheader("步骤0：配置与额度检查")

        c1, c2 = st.columns([2, 1])
        with c1:
            raw_input = st.text_input(
                "GitHub 用户主页 URL 或用户名",
                value=st.session_state.get("raw_user_input", ""),
                placeholder="例如：https://github.com/gokuscraper 或 gokuscraper",
            )

            mode = st.radio(
                "运行模式",
                options=["免登录", "Token"],
                horizontal=True,
                index=0 if st.session_state.get("mode") == "免登录" else 1,
            )

            token = st.text_input(
                "GitHub Token（仅 Token 模式）",
                value=st.session_state.get("token", ""),
                type="password",
                disabled=(mode == "免登录"),
                placeholder="ghp_xxx",
            )

        with c2:
            output_col1, output_col2 = st.columns([3, 1])
            with output_col1:
                output_dir = st.text_input("导出目录", value=st.session_state.get("output_dir", os.getcwd()))
            with output_col2:
                st.write("")
                if st.button("选择", use_container_width=True):
                    picked_dir = choose_directory_dialog(st.session_state.get("output_dir", os.getcwd()))
                    if picked_dir:
                        st.session_state["output_dir"] = picked_dir
                        st.success(f"已选择导出目录：{picked_dir}")
                        st.rerun()

        st.info("提示：此处用于检查当前额度与Token有效性。")

        cc1, cc2, cc3 = st.columns([1, 1, 2])
        if cc1.button("保存配置", use_container_width=True):
            username = extract_username(raw_input)
            st.session_state["raw_user_input"] = raw_input
            st.session_state["username"] = username or ""
            st.session_state["mode"] = mode
            st.session_state["token"] = token.strip()
            st.session_state["output_dir"] = output_dir.strip() or os.getcwd()
            save_settings(mode, st.session_state["output_dir"])
            st.success("配置已保存。")

        if cc2.button("检查额度并执行校验", type="primary", use_container_width=True):
            username = extract_username(raw_input)
            st.session_state["raw_user_input"] = raw_input
            st.session_state["username"] = username or ""
            st.session_state["mode"] = mode
            st.session_state["token"] = token.strip()
            st.session_state["output_dir"] = output_dir.strip() or os.getcwd()
            save_settings(mode, st.session_state["output_dir"])

            if not st.session_state["username"]:
                st.session_state["guard_checked"] = False
                st.session_state["guard_passed"] = False
                st.error("用户名解析失败，请检查输入。")
            elif mode == "Token" and not st.session_state["token"]:
                st.session_state["guard_checked"] = True
                st.session_state["guard_passed"] = False
                st.error("你当前选择的是 Token 模式，请先填写 Token 再执行校验。")
            else:
                ok, msg, rate = check_rate_limit(st.session_state["token"] if mode == "Token" else "")
                update_rate(rate)
                render_rate_panel(rate_placeholder)
                st.session_state["guard_checked"] = True

                remaining = rate.get("remaining")
                if not ok:
                    st.session_state["guard_passed"] = False
                    st.error(msg)
                else:
                    st.session_state["guard_passed"] = True
                    if mode == "免登录":
                        st.success(f"校验通过：免登录模式可用，当前剩余额度 {remaining if remaining is not None else '未知'}。")
                    else:
                        st.success("校验通过：Token 模式已启用。")

        guard_text = "已通过" if st.session_state.get("guard_passed") else "未通过"
        st.write(f"当前用户名：`{st.session_state.get('username') or '未设置'}`")
        st.write(f"校验状态：**{guard_text}**")

    with tab_profile:
        st.subheader("步骤1：基础信息采集")
        st.caption("统一调用 /users/{username}。Token 模式下可能返回更多字段（如邮箱）。")
        ok, reason = check_hard_guard_before_action()
        if not ok:
            st.warning(reason)
        run_btn = st.button("开始基础信息采集", disabled=not ok)
        if run_btn:
            username = st.session_state.get("username", "")
            token = st.session_state.get("token", "") if st.session_state.get("mode") == "Token" else ""
            data, msg, rate = get_user_profile(username, token)
            update_rate(rate)
            render_rate_panel(rate_placeholder)
            if data is None:
                st.error(msg)
            else:
                st.session_state["profile_data"] = data
                st.success(msg)

        if st.session_state.get("profile_data"):
            df_profile = pd.DataFrame([st.session_state["profile_data"]])
            st.dataframe(df_profile, use_container_width=True)

            username = st.session_state.get("username", "unknown")
            file_name = f"基础信息采集_{username}.csv"
            st.download_button(
                "下载基础信息采集CSV",
                data=to_csv_bytes(df_profile),
                file_name=file_name,
                mime="text/csv",
                use_container_width=True,
            )

            if st.button("保存基础信息采集到导出目录"):
                try:
                    full_path = write_csv_to_disk(df_profile, st.session_state["output_dir"], file_name)
                    st.success(f"已保存：{full_path}")
                except Exception as e:
                    st.error(f"保存失败：{e}")

    with tab_repos:
        st.subheader("步骤2：仓库信息采集")
        ok, reason = check_hard_guard_before_action()
        if not ok:
            st.warning(reason)

        only_original = st.checkbox("仅保留原创仓库（fork=False）", value=True)
        run_btn = st.button("开始仓库信息采集", disabled=not ok)
        if run_btn:
            username = st.session_state.get("username", "")
            token = st.session_state.get("token", "") if st.session_state.get("mode") == "Token" else ""
            df, msg, rate = get_repos_master(username, token, only_original=only_original)
            update_rate(rate)
            render_rate_panel(rate_placeholder)
            if df is None:
                st.error(msg)
            else:
                st.session_state["repos_df"] = df
                if df.empty:
                    st.warning(msg)
                else:
                    st.success(msg)

        repos_df = st.session_state.get("repos_df")
        if isinstance(repos_df, pd.DataFrame) and not repos_df.empty:
            st.dataframe(repos_df, use_container_width=True, height=380)
            username = st.session_state.get("username", "unknown")
            file_name = f"仓库信息采集_{username}.csv"
            st.download_button(
                "下载仓库信息采集CSV",
                data=to_csv_bytes(repos_df),
                file_name=file_name,
                mime="text/csv",
                use_container_width=True,
            )

            if st.button("保存仓库信息采集到导出目录"):
                try:
                    full_path = write_csv_to_disk(repos_df, st.session_state["output_dir"], file_name)
                    st.success(f"已保存：{full_path}")
                except Exception as e:
                    st.error(f"保存失败：{e}")

    with tab_analysis:
        st.subheader("步骤4：开发者画像分析")
        ok, reason = check_hard_guard_before_action()
        if not ok:
            st.warning(reason)

        analysis_df = st.session_state.get("repos_df")
        profile_data = st.session_state.get("profile_data")

        pre1, pre2 = st.columns(2)
        if isinstance(analysis_df, pd.DataFrame) and not analysis_df.empty:
            pre1.success("已检测到仓库信息采集结果（必需）")
        else:
            pre1.error("未检测到仓库信息采集结果（必需）")

        if profile_data:
            pre2.success("已检测到基础信息采集结果（可选）")
        else:
            pre2.info("未检测到基础信息采集结果（可选，可跳过）")

        if st.button("开始开发者画像分析", type="primary", disabled=not ok):
            if analysis_df is None or not isinstance(analysis_df, pd.DataFrame) or analysis_df.empty:
                st.session_state["analysis_ready"] = False
                st.error("无法开始分析：请先完成【仓库信息采集】。")
            else:
                st.session_state["analysis_ready"] = True
                st.success("已开始开发者画像分析。")

        if not st.session_state.get("analysis_ready", False):
            st.info("点击“开始开发者画像分析”后，将生成画像分析结果。")
        elif analysis_df is not None and not analysis_df.empty:
            required_cols = {
                "项目名称", "Star数", "主要语言", "项目大小(KB)", "最后推送", "创建时间", "许可证", "Fork数", "开放Issue数"
            }
            if not required_cols.issubset(set(analysis_df.columns)):
                st.error("分析所需字段不完整，请使用“仓库信息采集”导出的CSV。")
            else:
                if profile_data:
                    st.markdown("### 基础信息")
                    profile_df = pd.DataFrame([profile_data])

                    r1c1, r1c2, r1c3 = st.columns(3)
                    r1c1.metric("昵称", str(profile_data.get("昵称") or "未设置"))
                    r1c2.metric("所在地", str(profile_data.get("所在地") or "未设置"))
                    r1c3.metric("所属公司", str(profile_data.get("所属公司") or "未设置"))

                    r2c1, r2c2, r2c3 = st.columns(3)
                    r2c1.metric("公开项目数", str(profile_data.get("公开项目数") if profile_data.get("公开项目数") is not None else "0"))
                    r2c2.metric("粉丝数", str(profile_data.get("粉丝数") if profile_data.get("粉丝数") is not None else "0"))
                    r2c3.metric("登录名", str(profile_data.get("登录名") or "未设置"))

                    t1, t2 = st.columns(2)
                    with t1:
                        render_time_info_card("账号创建时间", profile_data.get("账号创建时间"), "#2563eb")
                    with t2:
                        render_time_info_card("最后活跃时间", profile_data.get("最后活跃时间"), "#059669")

                scored_df = calc_repo_influence_score(analysis_df)

                star_series = pd.to_numeric(scored_df["Star数"], errors="coerce").fillna(0)
                size_kb_series = pd.to_numeric(scored_df["项目大小(KB)"], errors="coerce").fillna(0)
                pushed_at = to_datetime_safe(scored_df["最后推送"])
                created_at = to_datetime_safe(scored_df["创建时间"])

                now = pd.Timestamp.now(tz="UTC")
                active_180 = int(((now - pushed_at).dt.days <= 180).fillna(False).sum())

                m1, m2, m3, m4 = st.columns(4)
                m1.metric("仓库总量", str(len(scored_df)))
                m2.metric("Star总量", str(int(star_series.sum())))
                m3.metric("近180天活跃仓库", str(active_180))
                m4.metric("总存储占用(MB)", f"{size_kb_series.sum() / 1024:.2f}")

                st.markdown("### 技术栈画像")
                lang_dist = (
                    scored_df["主要语言"]
                    .fillna("未标注")
                    .astype(str)
                    .replace("", "未标注")
                    .value_counts()
                    .rename_axis("主要语言")
                    .reset_index(name="仓库数")
                )
                render_bar_with_horizontal_labels(lang_dist, "主要语言", "仓库数")

                st.markdown("### Star 总量与活跃度")
                c1, c2 = st.columns(2)
                with c1:
                    top_star = scored_df[["项目名称", "Star数"]].copy()
                    top_star["Star数"] = pd.to_numeric(top_star["Star数"], errors="coerce").fillna(0)
                    top_star = top_star.sort_values("Star数", ascending=False).head(10)
                    st.write("Top10 Star 仓库")
                    st.dataframe(top_star, use_container_width=True)
                with c2:
                    activity_df = pd.DataFrame(
                        {
                            "指标": ["近30天活跃", "近90天活跃", "近180天活跃"],
                            "仓库数": [
                                int(((now - pushed_at).dt.days <= 30).fillna(False).sum()),
                                int(((now - pushed_at).dt.days <= 90).fillna(False).sum()),
                                int(((now - pushed_at).dt.days <= 180).fillna(False).sum()),
                            ],
                        }
                    )
                    st.write("活跃度分层")
                    st.dataframe(activity_df, use_container_width=True)

                st.markdown("### 开发峰值")
                push_month = pushed_at.dt.to_period("M").astype(str)
                peak_df = (
                    push_month[push_month.notna()]
                    .value_counts()
                    .sort_index()
                    .rename_axis("月份")
                    .reset_index(name="推送仓库数")
                )
                if not peak_df.empty:
                    render_line_with_horizontal_labels(peak_df, "月份", "推送仓库数")
                    peak_row = peak_df.sort_values("推送仓库数", ascending=False).iloc[0]
                    st.info(f"开发峰值月份：{peak_row['月份']}（推送仓库数：{int(peak_row['推送仓库数'])}）")
                    peak_month = str(peak_row["月份"])
                    peak_count = int(peak_row["推送仓库数"])
                else:
                    st.info("暂无可用于计算开发峰值的时间数据。")
                    peak_month = "无"
                    peak_count = 0

                st.markdown("### 存储占用")
                size_df = scored_df[["项目名称", "项目大小(KB)"]].copy()
                size_df["项目大小(KB)"] = pd.to_numeric(size_df["项目大小(KB)"], errors="coerce").fillna(0)
                size_df = size_df.sort_values("项目大小(KB)", ascending=False).head(10)
                render_bar_with_horizontal_labels(size_df, "项目名称", "项目大小(KB)")

                st.markdown("### 仓库影响力评分")
                score_view = scored_df[["项目名称", "仓库影响力评分", "Star数", "Fork数", "开放Issue数", "最后推送"]].copy()
                score_view = score_view.sort_values("仓库影响力评分", ascending=False)
                st.dataframe(score_view.head(20), use_container_width=True)

                st.markdown("### 版权与合规性")
                license_series = scored_df["许可证"].fillna("无").astype(str)
                has_license = (~license_series.isin(["无", "", "None", "nan"]))
                compliance_rate = (has_license.sum() / len(scored_df) * 100) if len(scored_df) else 0
                cl1, cl2 = st.columns(2)
                cl1.metric("有许可证仓库占比", f"{compliance_rate:.1f}%")
                cl2.metric("未声明许可证仓库", str(int((~has_license).sum())))

                license_dist = (
                    license_series.replace({"": "无", "None": "无", "nan": "无"})
                    .value_counts()
                    .rename_axis("许可证")
                    .reset_index(name="仓库数")
                )
                st.dataframe(license_dist, use_container_width=True)

    with tab_commits:
        st.subheader("步骤3：commit信息采集")
        ok, reason = check_hard_guard_before_action()
        if not ok:
            st.warning(reason)

        c1, c2 = st.columns([2, 1])
        with c1:
            st.info("仓库来源：使用上一步【仓库信息采集】结果")
        with c2:
            max_repos = st.number_input("最多处理仓库数（0=全部）", min_value=0, max_value=1000, value=0, step=1)
            max_pages_per_repo = st.number_input("每个仓库最多处理页数（0=全部）", min_value=0, max_value=10000, value=1, step=1)

        run_btn = st.button("开始采集Commit", type="primary", disabled=not ok)
        if run_btn:
            repos_df = st.session_state.get("repos_df")
            if repos_df is None or not isinstance(repos_df, pd.DataFrame) or repos_df.empty:
                st.error("未检测到仓库信息采集结果，请先在上一页执行。")
                repos_df = None

            if repos_df is not None:
                required_cols = {"项目名称", "项目链接"}
                if not required_cols.issubset(set(repos_df.columns)):
                    st.error("CSV缺少必要列：项目名称、项目链接")
                else:
                    token = st.session_state.get("token", "") if st.session_state.get("mode") == "Token" else ""
                    df_commits, stats = get_commits_from_repos_df(
                        repos_df,
                        token=token,
                        max_repos=int(max_repos),
                        max_pages_per_repo=int(max_pages_per_repo),
                        max_retries=3,
                    )
                    st.session_state["commits_df"] = df_commits

                    total_repos = int(stats.get("total_repos", 0))
                    failed_repos = int(stats.get("failed_repos", 0))
                    done_repos = int(stats.get("done_repos", 0))

                    if total_repos > 0 and (failed_repos > 0 or done_repos < total_repos):
                        st.info("Commit采集部分完成：已有结果已保留，可查看统计后重试失败仓库。")
                    else:
                        st.success("Commit采集已完成。")

                    st.json(stats)

        commits_df = st.session_state.get("commits_df")
        if isinstance(commits_df, pd.DataFrame) and not commits_df.empty:
            st.dataframe(commits_df, use_container_width=True, height=420)
            username = st.session_state.get("username", "unknown")
            file_name = f"commit信息采集_{username}.csv"
            st.download_button(
                "下载commit信息采集CSV",
                data=to_csv_bytes(commits_df),
                file_name=file_name,
                mime="text/csv",
                use_container_width=True,
            )

            if st.button("保存commit信息采集到导出目录"):
                try:
                    full_path = write_csv_to_disk(commits_df, st.session_state["output_dir"], file_name)
                    st.success(f"已保存：{full_path}")
                except Exception as e:
                    st.error(f"保存失败：{e}")
        elif isinstance(commits_df, pd.DataFrame) and commits_df.empty:
            st.info("当前没有可展示的 Commit 记录。")

    st.divider()
    st.caption("说明：Token 仅保存在会话中，不会写入配置文件。配置文件仅保存模式、导出目录。")


if __name__ == "__main__":
    main()
