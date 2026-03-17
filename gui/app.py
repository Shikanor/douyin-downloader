"""
gui/app.py — 抖音下载器可视化界面（Streamlit）

运行方式：
    streamlit run gui/app.py

依赖安装：
    pip install streamlit pyyaml
"""

import os
import queue
import subprocess
import sys
import threading
from pathlib import Path

import streamlit as st
import yaml

# ── 路径常量 ───────────────────────────────────────────────────────────────────
_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent  # 项目根目录
_CONFIG_PATH = _ROOT / "config.yml"
_POST_PROCESSOR = _ROOT / "tools" / "post_processor.py"
_RUN_PY = _ROOT / "run.py"

# ── 配置读写 ───────────────────────────────────────────────────────────────────

def load_config() -> dict:
    if not _CONFIG_PATH.exists():
        return {}
    with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def save_config(cfg: dict) -> None:
    with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.dump(cfg, f, allow_unicode=True, default_flow_style=False, sort_keys=False)


# ── 子进程流式读取 ─────────────────────────────────────────────────────────────

def _stream_proc(proc: subprocess.Popen, out_q: queue.Queue) -> None:
    """在线程中读取子进程 stdout+stderr，推入队列。"""
    for line in proc.stdout:
        out_q.put(line)
    proc.wait()
    out_q.put(None)  # 结束哨兵


def run_subprocess(cmd: list, cwd: Path):
    """启动子进程并以生成器方式产出每行输出。"""
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(cwd),
        env=env,
    )
    q: queue.Queue = queue.Queue()
    t = threading.Thread(target=_stream_proc, args=(proc, q), daemon=True)
    t.start()
    while True:
        line = q.get()
        if line is None:
            break
        yield line.rstrip()
    t.join()
    return proc.returncode


# ── 页面：下载配置 ─────────────────────────────────────────────────────────────

def tab_config():
    st.header("下载配置")

    cfg = load_config()

    st.subheader("基本设置")
    path = st.text_input("保存路径 (path)", value=cfg.get("path", ""))

    raw_links = cfg.get("link", [])
    if isinstance(raw_links, str):
        raw_links = [raw_links]
    links_text = st.text_area(
        "下载链接（每行一个）",
        value="\n".join(raw_links),
        height=120,
    )

    st.subheader("下载模式")
    all_modes = ["post", "like", "allmix", "mix", "music", "collect", "collectmix"]
    current_modes = cfg.get("mode", ["post"])
    if isinstance(current_modes, str):
        current_modes = [current_modes]
    selected_modes = st.multiselect("模式", options=all_modes, default=current_modes)

    st.subheader("数量限制（0 = 不限）")
    number_cfg = cfg.get("number", {})
    cols = st.columns(3)
    number_fields = {}
    for i, mode_key in enumerate(["post", "like", "allmix", "mix", "music", "collect"]):
        with cols[i % 3]:
            number_fields[mode_key] = st.number_input(
                mode_key, min_value=0, value=int(number_cfg.get(mode_key, 0)), step=1
            )

    st.subheader("附件选项")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        music = st.checkbox("下载音乐", value=bool(cfg.get("music", True)))
    with c2:
        cover = st.checkbox("下载封面", value=bool(cfg.get("cover", True)))
    with c3:
        avatar = st.checkbox("下载头像", value=bool(cfg.get("avatar", True)))
    with c4:
        json_flag = st.checkbox("保存 JSON", value=bool(cfg.get("json", True)))

    st.subheader("其他设置")
    c5, c6 = st.columns(2)
    with c5:
        thread = st.number_input("并发线程数", min_value=1, max_value=20, value=int(cfg.get("thread", 5)), step=1)
    with c6:
        retry = st.number_input("重试次数", min_value=0, max_value=10, value=int(cfg.get("retry_times", 3)), step=1)

    proxy = st.text_input("代理地址（留空则不用代理）", value=cfg.get("proxy", ""))

    if st.button("💾 保存配置", type="primary"):
        links_list = [ln.strip() for ln in links_text.splitlines() if ln.strip()]
        cfg["path"] = path
        cfg["link"] = links_list
        cfg["mode"] = selected_modes
        cfg["number"] = {**cfg.get("number", {}), **number_fields}
        cfg["music"] = music
        cfg["cover"] = cover
        cfg["avatar"] = avatar
        cfg["json"] = json_flag
        cfg["thread"] = thread
        cfg["retry_times"] = retry
        cfg["proxy"] = proxy
        save_config(cfg)
        st.success("配置已保存！")


# ── 页面：运行下载 ─────────────────────────────────────────────────────────────

def tab_download():
    st.header("运行下载")

    cfg = load_config()
    path_val = cfg.get("path", "（未配置）")
    links = cfg.get("link", [])
    if isinstance(links, str):
        links = [links]

    st.info(f"保存路径：`{path_val}`\n\n当前链接数：{len(links)} 条")

    if not links:
        st.warning("请先在「下载配置」中填写下载链接。")
        return

    if st.button("▶ 开始下载", type="primary"):
        cmd = [sys.executable, str(_RUN_PY), "-c", str(_CONFIG_PATH)]
        log_box = st.empty()
        lines: list[str] = []

        with st.spinner("下载中…"):
            for line in run_subprocess(cmd, cwd=_ROOT):
                lines.append(line)
                log_box.code("\n".join(lines[-200:]), language="")

        st.success("下载完成！")
        st.code("\n".join(lines), language="")


# ── 页面：后处理 ───────────────────────────────────────────────────────────────

def tab_postprocess():
    st.header("后处理 — 整理视频文件")

    cfg = load_config()
    root_path = cfg.get("path", "")

    st.info(
        f"将把 `{root_path}` 下所有子文件夹中的 `.mp4` 文件移动到根目录，"
        "并删除子文件夹（封面、音乐、JSON 等附件一并清除）。"
    )

    override_path = st.text_input("覆盖路径（留空则使用配置文件中的 path）", value="")
    target_path = override_path.strip() or root_path

    if not target_path:
        st.warning("未找到路径，请在「下载配置」中设置 path 或在上方填写覆盖路径。")
        return

    col1, col2 = st.columns(2)

    with col1:
        if st.button("🔍 预览（不修改文件）"):
            cmd = [
                sys.executable, str(_POST_PROCESSOR),
                "--path", target_path,
                "--dry-run",
            ]
            log_box = st.empty()
            lines: list[str] = []
            with st.spinner("扫描中…"):
                for line in run_subprocess(cmd, cwd=_ROOT):
                    lines.append(line)
                    log_box.code("\n".join(lines), language="")
            st.info("预览完成，上方为将会执行的操作，点击「执行整理」以实际运行。")

    with col2:
        if st.button("✅ 执行整理", type="primary"):
            cmd = [
                sys.executable, str(_POST_PROCESSOR),
                "--path", target_path,
            ]
            log_box = st.empty()
            lines2: list[str] = []
            with st.spinner("整理中…"):
                for line in run_subprocess(cmd, cwd=_ROOT):
                    lines2.append(line)
                    log_box.code("\n".join(lines2), language="")
            st.success("整理完成！")


# ── 主布局 ─────────────────────────────────────────────────────────────────────

def main():
    st.set_page_config(
        page_title="抖音下载器",
        page_icon="🎵",
        layout="wide",
    )
    st.title("🎵 抖音批量下载工具")

    tab1, tab2, tab3 = st.tabs(["⚙️ 下载配置", "▶ 运行下载", "🗂 后处理"])

    with tab1:
        tab_config()

    with tab2:
        tab_download()

    with tab3:
        tab_postprocess()


if __name__ == "__main__":
    main()
