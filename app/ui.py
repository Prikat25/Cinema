"""Reusable Streamlit presentation helpers for CineSupervisor."""

from pathlib import Path

import streamlit as st

APP_DIR = Path(__file__).resolve().parent


def load_styles() -> None:
    """Load the application stylesheet from the app directory."""
    css_path = APP_DIR / "style.css"
    if css_path.exists():
        st.markdown(f"<style>{css_path.read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)


def page_header(title: str, subtitle: str) -> None:
    """Render the shared cinematic page header."""
    st.markdown(f'<div class="main-header">{title}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="sub-header">{subtitle}</div>', unsafe_allow_html=True)


def status_badge(text: str, variant: str = "active") -> None:
    """Render a consistent status badge."""
    variant = variant if variant in {"pass", "fail", "active"} else "active"
    st.markdown(f'<span class="status-badge badge-{variant}">{text}</span>', unsafe_allow_html=True)


def render_metric_row(metrics: list[tuple[str, str]]) -> None:
    """Render a row of Streamlit metrics."""
    columns = st.columns(len(metrics))
    for column, (label, value) in zip(columns, metrics):
        column.metric(label, value)
