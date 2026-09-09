"""
CBR Test Analyzer — Streamlit front end

Modelled on a real project lab-report template (4 worksheets):
  1. General compaction (standard Proctor)  -> OMC / MDD
  2. CBR compaction at several compactive efforts (e.g. 56/25/10 blows)
  3. Soaked / unsoaked penetration testing, per specimen -> CBR @ 2.5 & 5.0 mm
  4. Design CBR summary -> CBR vs %MDD curve, read off at target compaction levels

Run locally:   streamlit run app.py
Deploy:        push this folder to a GitHub repo and connect it on
               https://share.streamlit.io  (Streamlit Community Cloud).
               See README.md for the full walkthrough.
"""

from datetime import date
from html import escape as _esc

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import streamlit as st

from cbr_engine import (
    STD_LOAD_2_5_MM, STD_LOAD_5_0_MM, PLUNGER_AREA_MM2, DEFAULT_TARGET_PCTS,
    wet_density_kgm3, moisture_content_pct, dry_density_from_wet, relative_compaction_pct,
    fit_compaction, compute_cbr, swell_percent, fit_cbr_vs_compaction, eval_design_cbr,
)
from report import build_pdf_report

BRASS = "#8C6A24"
GRAPHITE = "#2E4B54"
INK = "#1B231E"
INK_SOFT = "#57645C"
GOOD = "#2F6B3D"
WARN = "#A6331F"
LINE = "#D6DCD3"
OLIVE = "#6E8F5C"
SLATE = "#5C6E8F"
PALETTE = [BRASS, GRAPHITE, OLIVE, "#A6331F", SLATE, "#8F5C6E"]

# The 4 lab stages, in order, with the accent color and in-page anchor id used
# by both the header's jump-to-section strip and each stage's section head.
STAGES = [
    ("1", "Compaction", "stage-1", BRASS),
    ("2", "CBR Compaction", "stage-2", GRAPHITE),
    ("3", "Penetration", "stage-3", OLIVE),
    ("4", "Design CBR", "stage-4", SLATE),
]

st.set_page_config(page_title="CBR Test Analyzer", page_icon="📐", layout="wide")

st.markdown(
    f"""
    <style>
      .stMetric {{ background: #FFFFFF; border: 1px solid {LINE}; border-radius: 10px;
                   padding: 0.7rem 0.9rem; box-shadow: 0 1px 3px rgba(27,35,30,0.06); }}
      div[data-testid="stMetricLabel"] {{ font-size: 0.72rem; text-transform: uppercase;
                   letter-spacing: .06em; color: {INK_SOFT}; }}
      div[data-testid="stMetricValue"] {{ color: {INK}; }}
      h1, h2, h3 {{ color: {INK}; }}
      div[data-testid="stDataFrame"] {{ border: 1px solid {LINE}; border-radius: 10px;
                   overflow: hidden; }}

      /* ---- Hero header ---- */
      .cbr-hero-wrap {{ padding-bottom: 2px; }}
      .cbr-hero-row {{ display: flex; align-items: center; gap: 18px; }}
      .cbr-hero-icon {{
          flex: 0 0 auto; width: 64px; height: 64px; border-radius: 16px;
          background: linear-gradient(135deg, {BRASS} 0%, {GRAPHITE} 100%);
          display: flex; align-items: center; justify-content: center;
          font-size: 2rem; box-shadow: 0 4px 10px rgba(27,35,30,0.18);
      }}
      .cbr-hero-eyebrow {{ font-family: monospace; font-size: 0.72rem; letter-spacing: .12em;
                      text-transform: uppercase; color: {INK_SOFT}; margin: 0 0 2px 0; }}
      .cbr-hero-title {{ font-size: 2rem; font-weight: 800; color: {INK}; margin: 0; line-height: 1.15; }}
      .cbr-hero-subtitle {{ color: {INK_SOFT}; font-size: 0.95rem; margin: 4px 0 0 0; max-width: 640px; }}
      .cbr-hero-rule {{
          height: 4px; width: 100%; margin: 14px 0 12px 0; border-radius: 3px;
          background: linear-gradient(90deg, {BRASS} 0%, {GRAPHITE} 55%, {OLIVE} 100%);
      }}

      /* ---- Jump-to-section stage strip ---- */
      .cbr-stage-strip {{ display: flex; flex-wrap: wrap; gap: 10px; margin: 2px 0 4px 0; }}
      .cbr-stage-chip {{
          display: inline-flex; align-items: center; gap: 8px; text-decoration: none;
          background: #FFFFFF; border: 1px solid {LINE}; border-radius: 999px;
          padding: 5px 14px 5px 6px; font-size: 0.82rem; color: {INK}; font-weight: 600;
      }}
      .cbr-stage-num {{
          width: 20px; height: 20px; border-radius: 50%; color: #FFFFFF; font-size: 0.7rem;
          display: flex; align-items: center; justify-content: center; font-weight: 700;
      }}

      .cbr-banner {{
          display: inline-flex; align-items: center; gap: 8px; border: 1px dashed #B7C0B3;
          border-radius: 999px; padding: .4rem 1rem; font-size: .85rem; color: {INK_SOFT};
          background: #FFFFFF;
      }}

      /* ---- Section heads (numbered stage chip, or a neutral icon chip) ---- */
      .cbr-section-head {{ display: flex; align-items: center; gap: 10px; margin: 4px 0 2px 0; }}
      .cbr-section-chip {{
          width: 30px; height: 30px; min-width: 30px; border-radius: 9px; color: #FFFFFF;
          display: flex; align-items: center; justify-content: center; font-weight: 700; font-size: 0.95rem;
      }}
      .cbr-section-icon {{
          width: 30px; height: 30px; min-width: 30px; border-radius: 9px; background: #EEF1EB;
          display: flex; align-items: center; justify-content: center; font-size: 1.05rem;
      }}
      .cbr-section-title {{ font-size: 1.35rem; font-weight: 700; color: {INK}; margin: 0; }}

      /* ---- Per-specimen input card label (stage 3) ---- */
      .cbr-specimen-badge {{
          display: inline-flex; align-items: center; gap: 8px; font-weight: 700; color: {INK};
          font-size: 1.05rem; margin: 2px 0 6px 0;
      }}
      .cbr-specimen-num {{
          width: 26px; height: 26px; border-radius: 50%; color: #FFFFFF;
          display: flex; align-items: center; justify-content: center; font-size: 0.8rem; font-weight: 700;
      }}
    </style>
    """,
    unsafe_allow_html=True,
)

# Shared modern chart chrome (facecolor, title, grid, legend, spines) so every
# matplotlib chart below looks consistent without repeating the styling calls
# in each chart block. Purely cosmetic -- no effect on any computed value.
plt.rcParams.update({
    "font.size": 9,
    "axes.edgecolor": INK_SOFT,
    "axes.labelcolor": INK,
    "xtick.color": INK_SOFT,
    "ytick.color": INK_SOFT,
})


def _style_chart(fig, ax, title, legend_fontsize=8):
    fig.patch.set_facecolor("#FFFFFF")
    ax.set_facecolor("#FCFBF7")
    if title:
        ax.set_title(title, fontsize=11, fontweight="bold", color=INK, loc="left", pad=10)
    ax.grid(color=LINE, linewidth=0.6)
    handles, _ = ax.get_legend_handles_labels()
    if handles:
        ax.legend(fontsize=legend_fontsize, frameon=False)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    for spine in ("left", "bottom"):
        ax.spines[spine].set_color(INK_SOFT)

PEN_DEPTHS = [0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 5.5, 6.0, 6.5, 7.0, 7.5]

# ---------------------------------------------------------------------------
# Example / blank datasets
# ---------------------------------------------------------------------------

def example_project():
    return dict(
        name="Rehabilitation of Ofankor - Nsawam (Dual Carriageway) Road",
        material="Lateritic gravel (sub-base)", sampled_from="Borrow pit BP-4",
        layer="Sub-base", test_code="SB-014", sampled_date=date(2026, 7, 22),
        test_date=date(2026, 8, 14), technician="E. Owusu",
        prepared_by="Contractor's Materials Engineer", approved_by="Consultant's Materials Engineer",
        condition="Soaked (96 h)", surcharge=4.5, soak_hours=96,
        std_load_2_5=13.344, std_load_5_0=20.016, load_ring_factor=0.0242,
    )


def blank_project():
    return dict(
        name="", material="", sampled_from="", layer="", test_code="",
        sampled_date=date.today(), test_date=date.today(), technician="",
        prepared_by="", approved_by="",
        condition="Soaked (96 h)", surcharge=4.5, soak_hours=96,
        std_load_2_5=STD_LOAD_2_5_MM, std_load_5_0=STD_LOAD_5_0_MM, load_ring_factor=0.01,
    )


def _num_col(name, fmt="%.2f"):
    return name, st.column_config.NumberColumn(name, format=fmt)


COMP_COLS = ["Trial", "Air-dry sample (g)", "Approx. MC (%)", "Mould No.", "Mould Factor",
             "Mould mass (g)", "Mould+wet soil (g)", "Pan No.", "Pan (g)", "Pan+wet (g)", "Pan+dry (g)"]
COMP_TEXT_COLS = {"Mould No.", "Pan No."}


def example_compaction_df():
    return pd.DataFrame({
        "Trial": [1, 2, 3, 4, 5],
        "Air-dry sample (g)": [6000, 6000, 6000, 6000, 6000],
        "Approx. MC (%)": [4.0, 6.0, 8.0, 10.0, 12.0],
        "Mould No.": ["M-1", "M-2", "M-3", "M-4", "M-5"],
        "Mould Factor": [0.488, 0.488, 0.488, 0.488, 0.488],
        "Mould mass (g)": [6183, 6165, 6190, 6172, 6178],
        "Mould+wet soil (g)": [10471, 10650, 10802, 10869, 10780],
        "Pan No.": ["P-1", "P-2", "P-3", "P-4", "P-5"],
        "Pan (g)": [293, 288, 301, 296, 290],
        "Pan+wet (g)": [897, 912, 935, 968, 940],
        "Pan+dry (g)": [872.6, 872.4, 883.2, 900.5, 862.0],
    })


def blank_compaction_df(n=5):
    return pd.DataFrame({
        "Trial": pd.array(list(range(1, n + 1)), dtype="Int64"),
        "Air-dry sample (g)": pd.array([None] * n, dtype="Float64"),
        "Approx. MC (%)": pd.array([None] * n, dtype="Float64"),
        "Mould No.": pd.array([""] * n, dtype="string"),
        "Mould Factor": pd.array([None] * n, dtype="Float64"),
        "Mould mass (g)": pd.array([None] * n, dtype="Float64"),
        "Mould+wet soil (g)": pd.array([None] * n, dtype="Float64"),
        "Pan No.": pd.array([""] * n, dtype="string"),
        "Pan (g)": pd.array([None] * n, dtype="Float64"),
        "Pan+wet (g)": pd.array([None] * n, dtype="Float64"),
        "Pan+dry (g)": pd.array([None] * n, dtype="Float64"),
    })


CBR_COMP_COLS = ["Specimen", "Air-dry sample (g)", "Mould No.", "Mould Factor",
                  "Mould+base (g)", "Mould+wet+base (g)", "Pan No.", "Pan (g)", "Pan+wet (g)", "Pan+dry (g)"]


def example_cbr_comp_df():
    return pd.DataFrame({
        "Specimen": ["56 Blows", "25 Blows", "10 Blows"],
        "Air-dry sample (g)": [6000, 6000, 6000],
        "Mould No.": ["8", "C9", "E1"],
        "Mould Factor": [0.4235, 0.412, 0.412],
        "Mould+base (g)": [10820, 10510, 10480],
        "Mould+wet+base (g)": [16240, 15690, 15410],
        "Pan No.": ["A1", "A2", "A3"],
        "Pan (g)": [290, 285, 288],
        "Pan+wet (g)": [905, 900, 895],
        "Pan+dry (g)": [878, 868, 858],
    })


def blank_cbr_comp_df(labels):
    n = len(labels)
    return pd.DataFrame({
        "Specimen": pd.array(list(labels), dtype="string"),
        "Air-dry sample (g)": pd.array([None] * n, dtype="Float64"),
        "Mould No.": pd.array([""] * n, dtype="string"),
        "Mould Factor": pd.array([None] * n, dtype="Float64"),
        "Mould+base (g)": pd.array([None] * n, dtype="Float64"),
        "Mould+wet+base (g)": pd.array([None] * n, dtype="Float64"),
        "Pan No.": pd.array([""] * n, dtype="string"),
        "Pan (g)": pd.array([None] * n, dtype="Float64"),
        "Pan+wet (g)": pd.array([None] * n, dtype="Float64"),
        "Pan+dry (g)": pd.array([None] * n, dtype="Float64"),
    })


def example_pen_df():
    # Roughly-shaped example curves for the three compactive-effort specimens.
    scale = {"56 Blows": 1.0, "25 Blows": 0.78, "10 Blows": 0.64}
    base = [0, 1.1, 2.3, 3.6, 4.9, 6.3, 7.5, 8.6, 9.6, 10.5, 11.3, 12.0, 12.6, 13.1, 13.5, 13.9]
    return {lbl: pd.DataFrame({
        "Penetration (mm)": PEN_DEPTHS,
        "Load (kN)": [round(v * f, 3) for v in base],
    }) for lbl, f in scale.items()}


def blank_pen_df():
    n = len(PEN_DEPTHS)
    return pd.DataFrame({
        "Penetration (mm)": pd.array(PEN_DEPTHS, dtype="Float64"),
        "Load (kN)": pd.array([None] * n, dtype="Float64"),
    })


def coerce_numeric(df, cols):
    for c in cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def resize_rows(df, n, blank_row_fn):
    """Pad/truncate a per-specimen dataframe to exactly n rows."""
    if len(df) == n:
        return df.reset_index(drop=True)
    if len(df) > n:
        return df.iloc[:n].reset_index(drop=True)
    extra = blank_row_fn(n - len(df))
    return pd.concat([df, extra], ignore_index=True)


def init_state():
    if "initialized" not in st.session_state:
        st.session_state.initialized = True
        st.session_state.is_example = True
        st.session_state.data_version = 0
        st.session_state.project = example_project()
        st.session_state.comp_df = example_compaction_df()
        st.session_state.n_specimens = 3
        st.session_state.specimen_labels = ["56 Blows", "25 Blows", "10 Blows"]
        st.session_state.cbr_comp_df = example_cbr_comp_df()
        st.session_state.cbr_comp_live = example_cbr_comp_df()
        st.session_state.specimen_version = 0
        st.session_state.target_mc_override = None  # None -> use fitted OMC
        st.session_state.pen_dfs = example_pen_df()
        st.session_state.pen_dfs_live = example_pen_df()
        st.session_state.load_modes = {lbl: "Direct load (kN)" for lbl in st.session_state.specimen_labels}
        st.session_state.manual_corr_on = {lbl: False for lbl in st.session_state.specimen_labels}
        st.session_state.manual_corr = {lbl: 0.0 for lbl in st.session_state.specimen_labels}
        st.session_state.apply_correction = False
        st.session_state.swell = {lbl: dict(init=0.0, final=1.5, height=127.0) for lbl in st.session_state.specimen_labels}
        st.session_state.mdd_override = None  # None -> use fitted MDD
        st.session_state.targets_text = "93, 95, 98, 100"


init_state()
dv = st.session_state.data_version  # bump this to force-reset all keyed widgets below

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------

hcol1, hcol2 = st.columns([3, 1])
with hcol1:
    st.markdown(
        """
        <div class="cbr-hero-wrap">
          <div class="cbr-hero-row">
            <div class="cbr-hero-icon">📐</div>
            <div>
              <p class="cbr-hero-eyebrow">BS 1377-4:1990 · Cl.7 · Compaction &amp; CBR laboratory report</p>
              <p class="cbr-hero-title">CBR Test Analyzer</p>
              <p class="cbr-hero-subtitle">Compaction through design CBR in one guided workflow — enter lab
              readings, get fitted curves, governing CBR per specimen, and a branded PDF report.</p>
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
with hcol2:
    st.write("")
    st.write("")
    b1, b2 = st.columns(2)
    if b1.button("New blank test", use_container_width=True):
        st.session_state.is_example = False
        st.session_state.data_version += 1
        st.session_state.project = blank_project()
        st.session_state.comp_df = blank_compaction_df()
        labels = st.session_state.specimen_labels
        st.session_state.cbr_comp_df = blank_cbr_comp_df(labels)
        st.session_state.cbr_comp_live = blank_cbr_comp_df(labels)
        st.session_state.pen_dfs = {lbl: blank_pen_df() for lbl in labels}
        st.session_state.pen_dfs_live = {lbl: blank_pen_df() for lbl in labels}
        st.session_state.specimen_version += 1
        st.session_state.manual_corr_on = {lbl: False for lbl in labels}
        st.session_state.manual_corr = {lbl: 0.0 for lbl in labels}
        st.session_state.swell = {lbl: dict(init=None, final=None, height=127.0) for lbl in labels}
        st.session_state.mdd_override = None
        st.session_state.target_mc_override = None
        st.rerun()
    if b2.button("Load example", use_container_width=True):
        st.session_state.is_example = True
        st.session_state.data_version += 1
        st.session_state.project = example_project()
        st.session_state.comp_df = example_compaction_df()
        st.session_state.n_specimens = 3
        st.session_state.specimen_labels = ["56 Blows", "25 Blows", "10 Blows"]
        st.session_state.cbr_comp_df = example_cbr_comp_df()
        st.session_state.cbr_comp_live = example_cbr_comp_df()
        st.session_state.pen_dfs = example_pen_df()
        st.session_state.pen_dfs_live = example_pen_df()
        st.session_state.specimen_version += 1
        st.session_state.manual_corr_on = {lbl: False for lbl in st.session_state.specimen_labels}
        st.session_state.manual_corr = {lbl: 0.0 for lbl in st.session_state.specimen_labels}
        st.session_state.swell = {lbl: dict(init=0.0, final=1.5, height=127.0) for lbl in st.session_state.specimen_labels}
        st.session_state.mdd_override = None
        st.session_state.target_mc_override = None
        st.rerun()

st.markdown(
    '<div class="cbr-stage-strip">'
    + "".join(
        f'<a class="cbr-stage-chip" href="#{anchor}">'
        f'<span class="cbr-stage-num" style="background:{color};">{num}</span>{name}</a>'
        for num, name, anchor, color in STAGES
    )
    + "</div>",
    unsafe_allow_html=True,
)
st.markdown('<div class="cbr-hero-rule"></div>', unsafe_allow_html=True)

if st.session_state.is_example:
    st.markdown(
        '<p class="cbr-banner">📁 Showing example data modelled on a real project template — edit any field '
        'below, or click "New blank test" to start your own.</p>', unsafe_allow_html=True)

readout = st.container()
st.divider()

# ---------------------------------------------------------------------------
# Project header (shared across all 4 stages)
# ---------------------------------------------------------------------------

st.markdown(
    '<div class="cbr-section-head"><span class="cbr-section-icon">🗂️</span>'
    '<span class="cbr-section-title">Project &amp; sample</span></div>',
    unsafe_allow_html=True,
)
p = st.session_state.project
c1, c2, c3 = st.columns(3)
with c1:
    p["name"] = st.text_input("Project", p["name"], key=f"name_{dv}")
    p["material"] = st.text_input("Material type", p["material"], key=f"material_{dv}")
    p["sampled_from"] = st.text_input("Sampled from", p["sampled_from"], key=f"sampled_from_{dv}")
with c2:
    p["layer"] = st.text_input("Layer", p["layer"], key=f"layer_{dv}")
    p["test_code"] = st.text_input("Test code", p["test_code"], key=f"test_code_{dv}")
    p["technician"] = st.text_input("Technician", p["technician"], key=f"technician_{dv}")
with c3:
    p["sampled_date"] = st.date_input("Sampled date", p["sampled_date"], key=f"sampled_date_{dv}")
    p["test_date"] = st.date_input("Test date", p["test_date"], key=f"test_date_{dv}")
    p["condition"] = st.selectbox("Condition", ["Soaked (96 h)", "Unsoaked"],
                                   index=0 if p["condition"].startswith("Soaked") else 1, key=f"condition_{dv}")
c4, c5, c6, c7 = st.columns(4)
with c4:
    p["surcharge"] = st.number_input("Surcharge mass (kg)", value=float(p["surcharge"]), step=0.1, key=f"surcharge_{dv}")
with c5:
    p["soak_hours"] = st.number_input("Soak period (hours)", value=int(p["soak_hours"]), step=1, key=f"soak_hours_{dv}")
with c6:
    p["std_load_2_5"] = st.number_input("Standard load @ 2.5 mm (kN)", value=float(p["std_load_2_5"]),
                                          step=0.001, format="%.3f", key=f"std25_{dv}")
with c7:
    p["std_load_5_0"] = st.number_input("Standard load @ 5.0 mm (kN)", value=float(p["std_load_5_0"]),
                                          step=0.001, format="%.3f", key=f"std50_{dv}")

nsp1, nsp2 = st.columns([1, 3])
with nsp1:
    st.session_state.n_specimens = st.number_input("Number of CBR compactive efforts", min_value=2, max_value=6,
                                                     value=int(st.session_state.n_specimens), step=1, key=f"nsp_{dv}")
with nsp2:
    labels_text = st.text_input("Specimen labels (comma-separated)",
                                 ", ".join(st.session_state.specimen_labels), key=f"labels_{dv}")

n = int(st.session_state.n_specimens)
labels = [s.strip() for s in labels_text.split(",") if s.strip()][:n]
while len(labels) < n:
    labels.append(f"Specimen {len(labels) + 1}")
if labels != st.session_state.specimen_labels:
    st.session_state.specimen_labels = labels
    # Resize from the *live* mirror (this render's latest edited data, kept up to
    # date every time the section-2/3 editors below run) rather than the seed fed
    # to those editors -- otherwise a resize would discard whatever the user just
    # typed since the seed was last (re)established. See the note above the
    # section-2/3 editors for why the seed and live mirror are kept separate.
    cbr_comp_source = st.session_state.get("cbr_comp_live", st.session_state.cbr_comp_df)
    st.session_state.cbr_comp_df = resize_rows(cbr_comp_source, n, lambda k: blank_cbr_comp_df([f"Specimen {i}" for i in range(k)]))
    st.session_state.cbr_comp_df["Specimen"] = labels
    st.session_state.cbr_comp_live = st.session_state.cbr_comp_df.copy()
    pen_source = st.session_state.get("pen_dfs_live", st.session_state.pen_dfs)
    new_pen = {}
    for lbl in labels:
        new_pen[lbl] = pen_source.get(lbl, blank_pen_df())
    st.session_state.pen_dfs = new_pen
    st.session_state.pen_dfs_live = {lbl: df.copy() for lbl, df in new_pen.items()}
    # A resize reshapes the underlying data (rows/labels), so give the section-2/3
    # editors a fresh widget identity below -- reusing the same key while the data
    # shape changes underneath them is exactly the kind of external-data-change
    # that triggers Streamlit's data_editor double-input lag (see below).
    st.session_state.specimen_version = st.session_state.get("specimen_version", 0) + 1
    for d in (st.session_state.load_modes, st.session_state.manual_corr_on, st.session_state.manual_corr, st.session_state.swell):
        for lbl in labels:
            if lbl not in d:
                d[lbl] = d.get(lbl, None)
    st.session_state.load_modes = {lbl: st.session_state.load_modes.get(lbl, "Direct load (kN)") for lbl in labels}
    st.session_state.manual_corr_on = {lbl: st.session_state.manual_corr_on.get(lbl, False) for lbl in labels}
    st.session_state.manual_corr = {lbl: st.session_state.manual_corr.get(lbl, 0.0) for lbl in labels}
    st.session_state.swell = {lbl: st.session_state.swell.get(lbl, dict(init=0.0, final=0.0, height=127.0)) for lbl in labels}
labels = st.session_state.specimen_labels
specimen_version = st.session_state.get("specimen_version", 0)

st.divider()

# ---------------------------------------------------------------------------
# The 4 stages, as one continuous scrolling page (not tabs).
#
# Streamlit's st.tabs() has a long-standing, widely-reported bug: it snaps
# back to the first tab on *every* rerun -- i.e. every time any widget
# anywhere on the page is edited -- because tab selection lives only in the
# frontend and is not preserved across a script rerun. For a data-entry-heavy
# form like this one, that made every field edit feel like it "took a step
# backward". A single scrolling page with numbered section headers has no
# such navigation state to lose, so it cannot exhibit that bug at all.
#
# The `st.data_editor` calls below have a separate, also well-documented
# Streamlit bug: `st.session_state.x = st.data_editor(st.session_state.x)`
# -- feeding the editor's own just-returned dataframe back in as next
# render's seed, under the same key -- makes every edit lag by one rerun,
# i.e. you have to enter a value twice before it "sticks". The fix is to
# never feed a data_editor its own output back under an unchanged key: each
# editor below is seeded from a value that stays frozen except on an
# explicit reset/resize (which also gets a fresh key via dv/specimen_version,
# so the remount is clean), while a separately named "_live" mirror -- never
# fed back into the editor -- tracks the latest edits for anything that
# needs to read them (resize-preservation, the readout, the PDF report).
# ---------------------------------------------------------------------------

# --- Stage 1: general compaction -> OMC / MDD ------------------------------

st.markdown(
    f'<div class="cbr-section-head" id="stage-1"><span class="cbr-section-chip" '
    f'style="background:{BRASS};">1</span><span class="cbr-section-title">Compaction (Proctor)</span></div>',
    unsafe_allow_html=True,
)
st.caption("Standard Proctor compaction: each trial is a fresh sample compacted at a different moisture "
           "content. Dry density is fitted against moisture content to locate OMC and MDD.")
comp_df = st.data_editor(
    st.session_state.comp_df, num_rows="dynamic", use_container_width=True,
    key=f"comp_editor_{dv}",
    column_config={
        "Trial": st.column_config.NumberColumn("Trial", format="%d", step=1),
        "Air-dry sample (g)": st.column_config.NumberColumn("Air-dry sample (g)", format="%.1f"),
        "Approx. MC (%)": st.column_config.NumberColumn("Approx. MC (%)", format="%.2f"),
        "Mould Factor": st.column_config.NumberColumn("Mould Factor", format="%.4f"),
        "Mould mass (g)": st.column_config.NumberColumn("Mould mass (g)", format="%.1f"),
        "Mould+wet soil (g)": st.column_config.NumberColumn("Mould+wet soil (g)", format="%.1f"),
        "Pan (g)": st.column_config.NumberColumn("Pan (g)", format="%.1f"),
        "Pan+wet (g)": st.column_config.NumberColumn("Pan+wet (g)", format="%.1f"),
        "Pan+dry (g)": st.column_config.NumberColumn("Pan+dry (g)", format="%.1f"),
    },
)
comp_df = coerce_numeric(comp_df, [c for c in COMP_COLS if c not in COMP_TEXT_COLS])
# Intentionally NOT writing this back to st.session_state.comp_df: that would
# feed the editor's own output back in as next render's seed under the same
# key, which is what causes the double-input lag (see the note above). The
# seed only ever changes on an explicit reset, further up.

comp_calc = comp_df.copy()
wet_soil = comp_calc["Mould+wet soil (g)"] - comp_calc["Mould mass (g)"]
comp_calc["Wet density (kg/m3)"] = [wet_density_kgm3(w, mf) for w, mf in zip(wet_soil, comp_calc["Mould Factor"])]
comp_calc["Moisture (%)"] = [moisture_content_pct(pan, pw, pd_) for pan, pw, pd_ in
                              zip(comp_calc["Pan (g)"], comp_calc["Pan+wet (g)"], comp_calc["Pan+dry (g)"])]
comp_calc["Dry density (kg/m3)"] = [dry_density_from_wet(w, m) for w, m in
                                     zip(comp_calc["Wet density (kg/m3)"], comp_calc["Moisture (%)"])]

st.dataframe(
    comp_calc[["Trial", "Moisture (%)", "Wet density (kg/m3)", "Dry density (kg/m3)"]].round(2),
    use_container_width=True, hide_index=True,
)

fit = None
usable = comp_calc.dropna(subset=["Moisture (%)", "Dry density (kg/m3)"])
if len(usable) >= 3:
    fit = fit_compaction(usable["Moisture (%)"].tolist(), usable["Dry density (kg/m3)"].tolist())

fig_comp, ax_comp = plt.subplots(figsize=(7, 3.2))
if len(usable):
    ax_comp.scatter(usable["Moisture (%)"], usable["Dry density (kg/m3)"], color=GRAPHITE, zorder=3, label="Trial points")
if fit:
    xs = np.linspace(usable["Moisture (%)"].min() - 3, usable["Moisture (%)"].max() + 3, 100)
    ys = fit.a * xs ** 2 + fit.b * xs + fit.c
    ax_comp.plot(xs, ys, color=BRASS, linewidth=2, label="Fitted curve")
    ax_comp.scatter([fit.omc], [fit.mdd], color=BRASS, edgecolor=INK, s=90, marker="D", zorder=4, label="OMC / MDD")
    st.success(f"Fitted maximum dry density **{fit.mdd:.1f} kg/m³** ({fit.mdd / 1000:.3f} g/cm³) at optimum "
               f"moisture content **{fit.omc:.1f}%** (least-squares parabola, {fit.n_points} trials).")
elif len(usable) < 3:
    st.info("Add at least 3 trials (with density and moisture) to fit a compaction curve.")
else:
    st.warning("Points do not show a clear peak — check moisture/density values, or add trials either side of the optimum.")
ax_comp.set_xlabel("Moisture content (%)"); ax_comp.set_ylabel("Dry density (kg/m³)")
_style_chart(fig_comp, ax_comp, "Compaction curve")
st.pyplot(fig_comp, use_container_width=True)

st.divider()

# --- Stage 2: CBR compaction (multiple compactive efforts) ----------------

st.markdown(
    f'<div class="cbr-section-head" id="stage-2"><span class="cbr-section-chip" '
    f'style="background:{GRAPHITE};">2</span><span class="cbr-section-title">CBR Compaction</span></div>',
    unsafe_allow_html=True,
)
st.caption("Specimens compacted at the optimum moisture content using different compactive efforts, to span "
           "a range of densities for the Design CBR curve in stage 4.")

mo1, mo2 = st.columns(2)
with mo1:
    mdd_default = fit.mdd if fit else None
    use_manual_mdd = st.checkbox("Override MDD from stage 1", value=st.session_state.mdd_override is not None,
                                  key=f"mdd_on_{dv}")
    if use_manual_mdd:
        st.session_state.mdd_override = st.number_input(
            "MDD (kg/m3)", value=float(st.session_state.mdd_override or mdd_default or 2000.0),
            step=1.0, key=f"mdd_val_{dv}")
    else:
        st.session_state.mdd_override = None
mdd = st.session_state.mdd_override if st.session_state.mdd_override is not None else (fit.mdd if fit else None)
with mo2:
    omc_default = fit.omc if fit else None
    use_manual_mc = st.checkbox("Override target moisture content (OMC) from stage 1",
                                 value=st.session_state.target_mc_override is not None, key=f"mc_on_{dv}")
    if use_manual_mc:
        st.session_state.target_mc_override = st.number_input(
            "Target moisture content (%)", value=float(st.session_state.target_mc_override or omc_default or 10.0),
            step=0.1, key=f"mc_val_{dv}")
    else:
        st.session_state.target_mc_override = None
target_mc = st.session_state.target_mc_override if st.session_state.target_mc_override is not None else omc_default

if mdd is None:
    st.info("MDD not yet available — fit a compaction curve in stage 1, or override it above.")
else:
    st.caption(f"Using MDD = {mdd:.1f} kg/m³" + (f", target moisture content = {target_mc:.1f}%" if target_mc else ""))

cbr_comp_seed = st.session_state.cbr_comp_df.copy()
cbr_comp_seed["Specimen"] = labels
cbr_comp_df = st.data_editor(
    cbr_comp_seed, num_rows="fixed", use_container_width=True,
    key=f"cbr_comp_editor_{dv}_{specimen_version}",
    column_config={
        "Specimen": st.column_config.TextColumn("Specimen", disabled=True),
        "Air-dry sample (g)": st.column_config.NumberColumn("Air-dry sample (g)", format="%.1f"),
        "Mould Factor": st.column_config.NumberColumn("Mould Factor", format="%.4f"),
        "Mould+base (g)": st.column_config.NumberColumn("Mould+base (g)", format="%.1f"),
        "Mould+wet+base (g)": st.column_config.NumberColumn("Mould+wet+base (g)", format="%.1f"),
        "Pan (g)": st.column_config.NumberColumn("Pan (g)", format="%.1f"),
        "Pan+wet (g)": st.column_config.NumberColumn("Pan+wet (g)", format="%.1f"),
        "Pan+dry (g)": st.column_config.NumberColumn("Pan+dry (g)", format="%.1f"),
    },
)
cbr_comp_df = coerce_numeric(cbr_comp_df, [c for c in CBR_COMP_COLS if c not in {"Specimen", "Mould No.", "Pan No."}])
# Mirror for cross-section use (resize-preservation, PDF report) only -- never
# fed back into the editor above as its seed; see the note further up.
st.session_state.cbr_comp_live = cbr_comp_df

cbr_comp_calc = cbr_comp_df.copy()
wet_soil2 = cbr_comp_calc["Mould+wet+base (g)"] - cbr_comp_calc["Mould+base (g)"]
cbr_comp_calc["Wet density (kg/m3)"] = [wet_density_kgm3(w, mf) for w, mf in
                                         zip(wet_soil2, cbr_comp_calc["Mould Factor"])]
cbr_comp_calc["Moisture (%)"] = [moisture_content_pct(pan, pw, pd_) for pan, pw, pd_ in
                                  zip(cbr_comp_calc["Pan (g)"], cbr_comp_calc["Pan+wet (g)"], cbr_comp_calc["Pan+dry (g)"])]
cbr_comp_calc["Dry density (kg/m3)"] = [dry_density_from_wet(w, m) for w, m in
                                         zip(cbr_comp_calc["Wet density (kg/m3)"], cbr_comp_calc["Moisture (%)"])]
cbr_comp_calc["Relative compaction (%)"] = [relative_compaction_pct(d, mdd) for d in cbr_comp_calc["Dry density (kg/m3)"]]

st.dataframe(
    cbr_comp_calc[["Specimen", "Moisture (%)", "Dry density (kg/m3)", "Relative compaction (%)"]].round(2),
    use_container_width=True, hide_index=True,
)
st.session_state["cbr_comp_calc_cache"] = cbr_comp_calc

st.divider()

# --- Stage 3: penetration testing, per specimen ----------------------------

st.markdown(
    f'<div class="cbr-section-head" id="stage-3"><span class="cbr-section-chip" '
    f'style="background:{OLIVE};">3</span><span class="cbr-section-title">Penetration Testing</span></div>',
    unsafe_allow_html=True,
)
st.caption(f"Default standard loads: {p['std_load_2_5']:.3f} kN @ 2.5 mm and {p['std_load_5_0']:.3f} kN @ 5.0 mm, "
           f"on a {PLUNGER_AREA_MM2} mm² plunger. Governing CBR = MAX(CBR@2.5mm, CBR@5.0mm).")
st.session_state.apply_correction = st.checkbox(
    "Apply BS1377 curve-origin correction (advisory — the source template does not use this; leave off to "
    "match it exactly)", value=st.session_state.apply_correction, key=f"apply_corr_{dv}")

cbr_results = {}
figs_pen = {}
for i, lbl in enumerate(labels):
    st.markdown(
        f'<div class="cbr-specimen-badge"><span class="cbr-specimen-num" '
        f'style="background:{PALETTE[i % len(PALETTE)]};">{i + 1}</span>Specimen: {_esc(str(lbl))}</div>',
        unsafe_allow_html=True,
    )
    with st.container(border=True):
        lm1, lm2 = st.columns([2, 1])
        with lm1:
            st.session_state.load_modes[lbl] = st.radio(
                "Load input mode", ["Direct load (kN)", "Proving ring dial reading"],
                index=0 if st.session_state.load_modes.get(lbl, "Direct load (kN)") == "Direct load (kN)" else 1,
                horizontal=True, key=f"load_mode_{lbl}_{dv}")
        with lm2:
            calib_key = f"calibration_{lbl}_{dv}"
            calibration = p.get("load_ring_factor", 0.0242)
            if st.session_state.load_modes[lbl] == "Proving ring dial reading":
                calibration = st.number_input("Load ring factor (kN/division)", value=float(calibration),
                                               step=0.0001, format="%.4f", key=calib_key)

        col_label = "Load (kN)" if st.session_state.load_modes[lbl] == "Direct load (kN)" else "Dial reading (division)"
        seed = st.session_state.pen_dfs.get(lbl, blank_pen_df()).rename(columns={"Load (kN)": col_label})
        df = st.data_editor(seed, num_rows="dynamic", use_container_width=True,
                             key=f"pen_editor_{lbl}_{dv}_{specimen_version}",
                             column_config={
                                 "Penetration (mm)": st.column_config.NumberColumn("Penetration (mm)", format="%.2f"),
                                 col_label: st.column_config.NumberColumn(col_label, format="%.3f"),
                             })
        df["Penetration (mm)"] = pd.to_numeric(df["Penetration (mm)"], errors="coerce")
        df[col_label] = pd.to_numeric(df[col_label], errors="coerce")
        calc = df.dropna(subset=["Penetration (mm)", col_label]).copy()
        if st.session_state.load_modes[lbl] == "Proving ring dial reading":
            calc["Load (kN)"] = calc[col_label] * calibration
        else:
            calc["Load (kN)"] = calc[col_label]
        df = df.rename(columns={col_label: "Load (kN)"})
        # Mirror for cross-section use only (resize-preservation) -- never fed
        # back into the editor above as its seed; see the note further up.
        st.session_state.pen_dfs_live[lbl] = df[["Penetration (mm)", "Load (kN)"]]

        points = list(zip(calc["Penetration (mm)"].tolist(), calc["Load (kN)"].tolist()))

        oc1, oc2 = st.columns(2)
        with oc1:
            st.session_state.manual_corr_on[lbl] = st.checkbox(
                "Manual correction override", value=st.session_state.manual_corr_on.get(lbl, False),
                key=f"manual_corr_on_{lbl}_{dv}")
        with oc2:
            st.session_state.manual_corr[lbl] = st.number_input(
                "Correction (mm)", value=float(st.session_state.manual_corr.get(lbl, 0.0)), step=0.01,
                disabled=not st.session_state.manual_corr_on[lbl], key=f"manual_corr_{lbl}_{dv}")

        manual = st.session_state.manual_corr[lbl] if st.session_state.manual_corr_on[lbl] else None
        res = compute_cbr(points, std_load_2_5=p["std_load_2_5"], std_load_5_0=p["std_load_5_0"],
                           manual_correction=manual, apply_correction=st.session_state.apply_correction)
        cbr_results[lbl] = res

        if res.anomaly:
            st.warning(f"CBR@5.0mm ({res.cbr_5_0:.1f}%) exceeds CBR@2.5mm ({res.cbr_2_5:.1f}%) — "
                       f"governing value taken as the higher (5.0 mm) result, per project convention.")

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("CBR @ 2.5 mm", f"{res.cbr_2_5:.1f}%" if res.cbr_2_5 is not None else "—")
        m2.metric("CBR @ 5.0 mm", f"{res.cbr_5_0:.1f}%" if res.cbr_5_0 is not None else "—")
        m3.metric("Governing CBR", f"{res.selected_cbr:.1f}%" if res.selected_cbr is not None else "—", res.governing_mm)
        rc = st.session_state.get("cbr_comp_calc_cache")
        rc_val = None
        if rc is not None:
            row = rc[rc["Specimen"] == lbl]
            if len(row):
                rc_val = row["Relative compaction (%)"].iloc[0]
        m4.metric("Relative compaction", f"{rc_val:.1f}%" if pd.notna(rc_val) else "—")

        fig, ax = plt.subplots(figsize=(6.5, 3))
        if points:
            raw = sorted(points)
            corr_pts = [(max(0, x - res.correction_mm), y) for x, y in raw]
            ax.plot(*zip(*raw), color=INK_SOFT, linestyle="--", linewidth=1.2, label="Raw curve")
            if res.correction_mm:
                ax.plot(*zip(*corr_pts), color=BRASS, linewidth=2.2, label="Corrected curve")
            markers_x, markers_y = [], []
            if res.cbr_2_5 is not None:
                markers_x.append(2.5); markers_y.append(res.cbr_2_5 / 100 * p["std_load_2_5"])
            if res.cbr_5_0 is not None:
                markers_x.append(5.0); markers_y.append(res.cbr_5_0 / 100 * p["std_load_5_0"])
            if markers_x:
                ax.scatter(markers_x, markers_y, color=GRAPHITE, edgecolor="white", s=70, zorder=5, label="2.5 / 5.0 mm")
        ax.set_xlabel("Penetration (mm)"); ax.set_ylabel("Load (kN)")
        _style_chart(fig, ax, f"Load–penetration — {lbl}", legend_fontsize=7.5)
        st.pyplot(fig, use_container_width=True)
        figs_pen[lbl] = fig

        if p["condition"].startswith("Soaked"):
            sw = st.session_state.swell.setdefault(lbl, dict(init=0.0, final=0.0, height=127.0))
            sw1, sw2, sw3, sw4 = st.columns(4)
            with sw1:
                sw["init"] = st.number_input("Initial dial (mm)", value=float(sw.get("init") or 0.0), step=0.01,
                                              key=f"swell_init_{lbl}_{dv}")
            with sw2:
                sw["final"] = st.number_input("Final dial (mm)", value=float(sw.get("final") or 0.0), step=0.01,
                                               key=f"swell_final_{lbl}_{dv}")
            with sw3:
                sw["height"] = st.number_input("Specimen height (mm)", value=float(sw.get("height") or 127.0),
                                                 step=0.1, key=f"swell_height_{lbl}_{dv}")
            with sw4:
                sw_pct = swell_percent(sw["init"], sw["final"], sw["height"])
                st.metric("Swell", f"{sw_pct:.2f}%" if sw_pct is not None else "—")
    st.write("")

st.session_state["cbr_results_cache"] = cbr_results

st.divider()

# --- Stage 4: Design CBR summary -------------------------------------------

st.markdown(
    f'<div class="cbr-section-head" id="stage-4"><span class="cbr-section-chip" '
    f'style="background:{SLATE};">4</span><span class="cbr-section-title">Design CBR</span></div>',
    unsafe_allow_html=True,
)
st.caption("CBR vs relative compaction across the tested specimens, fitted with a smooth curve and read off "
           "at target compaction levels — replaces manually reading values off a plotted chart.")

rc_df = st.session_state.get("cbr_comp_calc_cache")
cbr_results = st.session_state.get("cbr_results_cache", {})

summary_rows = []
for lbl in labels:
    rel = None
    if rc_df is not None:
        row = rc_df[rc_df["Specimen"] == lbl]
        if len(row):
            rel = row["Relative compaction (%)"].iloc[0]
    res = cbr_results.get(lbl)
    cbr_val = res.selected_cbr if res else None
    summary_rows.append({"Specimen": lbl, "Relative compaction (%)": rel, "CBR (%)": cbr_val})
summary_df = pd.DataFrame(summary_rows)
st.dataframe(summary_df.round(2), use_container_width=True, hide_index=True)

usable_pts = summary_df.dropna(subset=["Relative compaction (%)", "CBR (%)"])
design_fit = None
if len(usable_pts) >= 2:
    design_fit = fit_cbr_vs_compaction(usable_pts["Relative compaction (%)"].tolist(), usable_pts["CBR (%)"].tolist())

targets_text = st.text_input("Target compaction levels (% of MDD, comma-separated)",
                              st.session_state.targets_text, key=f"targets_{dv}")
st.session_state.targets_text = targets_text
try:
    targets = sorted({float(t.strip()) for t in targets_text.split(",") if t.strip()})
except ValueError:
    targets = list(DEFAULT_TARGET_PCTS)
    st.warning("Could not parse target list — using defaults 93, 95, 98, 100%.")

if design_fit is None:
    st.info("Need at least 2 specimens with both relative compaction and CBR to fit a Design CBR curve.")
else:
    design_rows = []
    for t in targets:
        val, extrap = eval_design_cbr(design_fit, t)
        design_rows.append({"Target (% MDD)": t, "Design CBR (%)": val,
                             "Note": "extrapolated beyond tested range" if extrap else ""})
    design_df = pd.DataFrame(design_rows)
    st.dataframe(design_df.round(2), use_container_width=True, hide_index=True)
    st.session_state["design_df_cache"] = design_df

    fig_design, ax_d = plt.subplots(figsize=(7, 3.4))
    ax_d.scatter(usable_pts["Relative compaction (%)"], usable_pts["CBR (%)"], color=GRAPHITE, s=70,
                 zorder=4, label="Tested specimens")
    xs = np.linspace(min(usable_pts["Relative compaction (%)"].min(), min(targets) - 2),
                      max(usable_pts["Relative compaction (%)"].max(), max(targets) + 2), 100)
    ys = np.polyval(design_fit.coeffs, xs)
    ax_d.plot(xs, ys, color=BRASS, linewidth=2, label="Fitted curve")
    target_vals = [eval_design_cbr(design_fit, t)[0] for t in targets]
    ax_d.scatter(targets, target_vals, color=WARN, edgecolor="white", s=80, marker="D", zorder=5, label="Design targets")
    for t, v in zip(targets, target_vals):
        ax_d.annotate(f"{t:.0f}%→{v:.1f}%", (t, v), textcoords="offset points", xytext=(4, 4), fontsize=7.5)
    ax_d.set_xlabel("Relative compaction (% MDD)"); ax_d.set_ylabel("CBR (%)")
    _style_chart(fig_design, ax_d, "Design CBR vs. relative compaction")
    st.pyplot(fig_design, use_container_width=True)
    st.session_state["fig_design_cache"] = fig_design

# ---------------------------------------------------------------------------
# Readout (filled last, rendered first)
# ---------------------------------------------------------------------------

design_df = st.session_state.get("design_df_cache")
best_design = None
if design_df is not None and len(design_df):
    target_row = design_df.iloc[(design_df["Target (% MDD)"] - 95).abs().argsort()[:1]]
    if len(target_row):
        best_design = (target_row["Target (% MDD)"].iloc[0], target_row["Design CBR (%)"].iloc[0])

with readout:
    cols = st.columns(6)
    cols[0].metric("MDD / OMC", f"{fit.mdd/1000:.3f} g/cm³" if fit else "—", f"at {fit.omc:.1f}% OMC" if fit else None)
    cols[1].metric("Specimens tested", f"{len(labels)}")
    best_specimen = max(cbr_results.items(), key=lambda kv: kv[1].selected_cbr or -1) if cbr_results else None
    cols[2].metric("Highest specimen CBR", f"{best_specimen[1].selected_cbr:.1f}%" if best_specimen and best_specimen[1].selected_cbr is not None else "—",
                    best_specimen[0] if best_specimen else None)
    cols[3].metric(f"Design CBR @ {best_design[0]:.0f}% MDD" if best_design else "Design CBR",
                    f"{best_design[1]:.1f}%" if best_design else "—")
    cols[4].metric("Condition", p["condition"])
    cols[5].metric("Test code", p["test_code"] or "—")

st.divider()

# ---------------------------------------------------------------------------
# PDF report
# ---------------------------------------------------------------------------

st.markdown(
    '<div class="cbr-section-head"><span class="cbr-section-icon">📄</span>'
    '<span class="cbr-section-title">Report</span></div>',
    unsafe_allow_html=True,
)
st.caption("This tool assists calculation and curve fitting; results should still be reviewed by a qualified "
           "geotechnical engineer before use in pavement design.")

pdf_bytes = build_pdf_report(
    project=p, comp_calc=comp_calc, fit=fit, fig_comp=fig_comp,
    cbr_comp_calc=st.session_state.get("cbr_comp_calc_cache"),
    cbr_results=st.session_state.get("cbr_results_cache", {}), figs_pen=figs_pen,
    design_df=st.session_state.get("design_df_cache"), fig_design=st.session_state.get("fig_design_cache"),
)
st.download_button("⬇ Download PDF report", data=pdf_bytes,
                    file_name=f"CBR_report_{p['test_code'] or 'test'}.pdf".replace(" ", "_").replace("/", "-"),
                    mime="application/pdf")
