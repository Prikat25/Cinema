"""Reusable Streamlit presentation helpers for CineSupervisor."""

from html import escape
from pathlib import Path

import streamlit as st
import sys
sys.path.append(str(Path(__file__).resolve().parent.parent))

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


def render_scene(scene: dict) -> None:
    """Render a production scene as a readable call-sheet style breakdown."""
    number = escape(str(scene.get("scene_number", "-")))
    location = escape(str(scene.get("location", "Unassigned location")))
    environment = escape(str(scene.get("interior_exterior", "-")))
    time_of_day = escape(str(scene.get("time_of_day", "-")))
    characters = ", ".join(str(item) for item in scene.get("characters", [])) or "Unassigned"
    props = ", ".join(str(item) for item in scene.get("props", [])) or "None listed"

    st.markdown(
        (
            '<div class="scene-title"><span>SCENE ' + number + "</span>" + location
            + "</div>"
            + '<div class="scene-meta">' + environment + "  |  " + time_of_day + "</div>"
        ),
        unsafe_allow_html=True,
    )
    st.caption(f"Cast: {characters}")
    st.caption(f"Props: {props}")

    shots = scene.get("shots", [])
    if shots:
        st.dataframe(
            [
                {
                    "Shot": shot.get("shot_number", "-"),
                    "Coverage": shot.get("shot_type", "Unspecified"),
                    "Requirement": shot.get(
                        "requirements", shot.get("shot_requirements", "Unspecified")
                    ),
                }
                for shot in shots
            ],
            hide_index=True,
            use_container_width=True,
        )

    wardrobe = scene.get("wardrobe", [])
    if wardrobe:
        st.caption("Wardrobe: " + "; ".join(str(item) for item in wardrobe))