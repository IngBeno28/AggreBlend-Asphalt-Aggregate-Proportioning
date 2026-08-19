"""
Asphalt Coarse Aggregate Proportioning Calculator
--------------------------------------------------
Automation_hub | Materials & Geotechnical Engineering Tools

Given the percent-passing gradation of 2-6 aggregate stockpiles, this tool
proposes three trial blends (coarse-leaning, balanced, fine-leaning) that
best satisfy a target job-mix gradation band, then reports the blended
gradation against the spec and exports a branded PDF/Excel report.

Spec source (default): Ghana Highway Authority, Standard Specification for
Road and Bridge Works - Grading Requirements for Asphalt
Concrete (Type I / Type II, Wearing / Binder Course).

Run locally with:  streamlit run app.py
"""

import io
from datetime import date

import numpy as np
import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt

from gradation_core import (
    SIEVES, SIEVE_LABELS, NMAS_MM, SPEC, available_courses,
    available_designations, get_target, optimize_blend_options, evaluate_blend,
    FILLER_TYPES, ACTIVE_FILLER_CAP_PCT, ACTIVE_FILLER_PHYSICAL_REQS,
    check_active_filler_cap,
)
from pdf_report import build_pdf_report, APP_NAME


def _dedupe(names):
    """Make a list of names unique, preserving order, by suffixing repeats."""
    seen = {}
    out = []
    for n in names:
        if n not in seen:
            seen[n] = 0
            out.append(n)
        else:
            seen[n] += 1
            out.append(f"{n} ({seen[n] + 1})")
    return out


st.set_page_config(page_title=APP_NAME, layout="wide", page_icon="🛣️")

# =======================================================================
# Hero styling
# =======================================================================
st.markdown("""
<style>
.hero-wrap { padding-bottom: 6px; }
.hero-row { display: flex; align-items: center; gap: 16px; margin-bottom: 2px; }
.hero-icon {
    font-size: 2.6rem; line-height: 1; background: #eef2ff; border-radius: 14px;
    width: 62px; height: 62px; display: flex; align-items: center; justify-content: center;
}
.hero-title { font-size: 2.1rem; font-weight: 800; color: #111827; margin: 0; }
.hero-subtitle { color: #6b7280; font-size: 1.02rem; margin: 4px 0 0 0; }
.hero-rule {
    height: 4px; width: 100%; margin: 16px 0 22px 0; border-radius: 3px;
    background: linear-gradient(90deg, #1a56db 0%, #4C78A8 55%, #93c5fd 100%);
}
.blend-card {
    border: 1px solid #e5e7eb; border-radius: 10px; padding: 14px 16px;
    background: #fafafa; height: 100%;
}
.blend-badge-pass { color: #15803d; font-weight: 700; }
.blend-badge-fail { color: #b91c1c; font-weight: 700; }
</style>
""", unsafe_allow_html=True)

st.markdown(f"""
<div class="hero-wrap">
  <div class="hero-row">
    <div class="hero-icon">🛣️</div>
    <div>
      <p class="hero-title">{APP_NAME}</p>
      <p class="hero-subtitle">Best-fit stockpile blending against Ghana Highway Authority
      Table 17.3 gradation bands — with coarse, balanced, and fine trial blends compared side by side.</p>
    </div>
  </div>
  <div class="hero-rule"></div>
</div>
""", unsafe_allow_html=True)

# =======================================================================
# Sidebar: Project Information
# =======================================================================
with st.sidebar:
    st.markdown("### Project Information")
    project_name = st.text_input("Project Name", placeholder="Unnamed Project")
    prepared_for = st.text_input("Prepared For (Client)", placeholder="e.g. Ghana Highway Authority")
    prepared_by = st.text_input("Prepared By", value="Automation_hub Engineering Group Limited")
    engineer_name = st.text_input("Engineer Name (for certification)",
                                   value="Ing. Bernard Wiafe Akenteng")
    report_date = st.date_input("Report Date", value=date.today())

project_info = {
    "project_name": project_name,
    "prepared_for": prepared_for,
    "prepared_by": prepared_by,
    "engineer_name": engineer_name,
    "report_date": report_date.strftime("%Y-%m-%d"),
}

# =======================================================================
# 1. Mix type / course / designation selection
# =======================================================================
st.header("1. Target mix")

col1, col2, col3 = st.columns(3)
with col1:
    mix_type = st.selectbox("Mix type", list(SPEC.keys()), help=(
        "Type I offers Wearing Course and Binder Course gradings. "
        "Type II (Table 17.3) offers Wearing Course only."
    ))
with col2:
    course = st.selectbox("Course", available_courses(mix_type))
with col3:
    designation = st.selectbox(
        "Grading designation", available_designations(mix_type, course),
        help="0/x = nominal maximum aggregate size of x mm.",
    )

target = get_target(mix_type, course, designation)
nmas = NMAS_MM.get(designation)
st.caption(
    f"Selected: **{mix_type} – {course} – {designation}**"
    + (f" (nominal maximum aggregate size ≈ {nmas} mm)" if nmas else "")
)

config_key = (mix_type, course, designation)
if st.session_state.get("_config_key") != config_key:
    st.session_state["_config_key"] = config_key
    st.session_state.pop("results", None)  # clear stale results on target change

with st.expander("View target gradation band"):
    band_rows = []
    for s in SIEVES:
        b = target.get(s)
        band_rows.append({
            "Sieve (mm)": s,
            "Lower % passing": b[0] if b else "-",
            "Upper % passing": b[1] if b else "-",
        })
    st.dataframe(pd.DataFrame(band_rows), hide_index=True, use_container_width=True)

# =======================================================================
# 2. Stockpile gradations
# =======================================================================
st.header("2. Aggregate stockpiles")

n_piles = st.slider("Number of stockpiles to blend", min_value=2, max_value=6, value=4)

default_names = [
    "Coarse chippings", "Crusher-run / dust", "Sand", "Mineral filler",
    "Stockpile 5", "Stockpile 6",
]
# "Mineral filler" is the only default stockpile likely to be an added
# active filler (e.g. hydrated lime) rather than plain aggregate.
default_filler_type = ["Aggregate", "Aggregate", "Aggregate", "Active filler",
                        "Aggregate", "Aggregate"]

with st.expander("Mineral filler — active filler cap "):
    st.caption(
        "Mark any stockpile added specifically for adhesion (e.g. hydrated lime) as "
        "**Active filler**. The Ghana High Way Authority Specification caps active filler at "
        f"**{ACTIVE_FILLER_CAP_PCT:.0f}% by mass of the total asphalt concrete**, unless a "
        "Special Specification states otherwise. Filler added only to correct gradation "
        "(e.g. rock/stone dust) should be marked **Inert filler** — it is not subject to "
        "this cap."
    )
    spec_override = st.checkbox(
        "A Special Specification permits a different active filler limit",
        value=False, key="filler_cap_override",
    )
    if spec_override:
        active_cap_pct = st.number_input(
            "Special Specification active filler limit (%)", min_value=0.0,
            max_value=100.0, value=ACTIVE_FILLER_CAP_PCT, step=0.1,
            key="filler_cap_value",
        )
    else:
        active_cap_pct = ACTIVE_FILLER_CAP_PCT
    st.markdown("**Physical property requirements for active filler material** (checked in the lab, not computed here):")
    for req in ACTIVE_FILLER_PHYSICAL_REQS:
        st.markdown(f"- {req}")

pile_names = []
min_pcts = []
max_pcts = []
filler_types = []

name_cols = st.columns(n_piles)
for i in range(n_piles):
    with name_cols[i]:
        nm = st.text_input(f"Stockpile {i + 1} name", value=default_names[i], key=f"name_{i}")
        pile_names.append(nm if nm.strip() else f"Stockpile {i + 1}")
        ftype = st.selectbox(
            "Material type", FILLER_TYPES,
            index=FILLER_TYPES.index(default_filler_type[i]),
            key=f"ftype_{i}",
            help="Active filler (e.g. hydrated lime) is capped by Table 17.3; "
                 "inert filler (e.g. rock dust) and ordinary aggregate are not.",
        )
        filler_types.append(ftype)
        default_max = active_cap_pct if ftype == "Active filler" else 100.0
        c_min, c_max = st.columns(2)
        with c_min:
            mn = st.number_input("Min %", min_value=0.0, max_value=100.0, value=0.0,
                                  step=1.0, key=f"min_{i}")
        with c_max:
            mx = st.number_input("Max %", min_value=0.0, max_value=100.0, value=default_max,
                                  step=0.1 if ftype == "Active filler" else 1.0, key=f"max_{i}")
        min_pcts.append(mn)
        max_pcts.append(mx)
        if ftype == "Active filler" and mx > active_cap_pct + 1e-9:
            st.caption(
                f"⚠ Max % ({mx:g}%) exceeds the {active_cap_pct:g}% active filler cap."
            )

pile_names = _dedupe(pile_names)

st.markdown("**Sieve analysis (% passing by mass) for each stockpile**")

if ("_grad_df" not in st.session_state
        or list(st.session_state["_grad_df"].columns) != pile_names):
    st.session_state["_grad_df"] = pd.DataFrame(
        100.0, index=SIEVE_LABELS, columns=pile_names,
    )

grad_df = st.data_editor(
    st.session_state["_grad_df"],
    column_config={
        name: st.column_config.NumberColumn(name, min_value=0.0, max_value=100.0,
                                             step=0.1, format="%.1f")
        for name in pile_names
    },
    use_container_width=True,
    key="grad_editor",
)
st.session_state["_grad_df"] = grad_df

# Basic sanity check: % passing should not increase as sieve size decreases
warnings = []
for name in pile_names:
    col = grad_df[name].to_numpy(dtype=float)
    if np.any(np.diff(col) > 0.5):  # small tolerance for rounding
        warnings.append(name)
if warnings:
    st.warning(
        "Percent passing increases at a smaller sieve for: "
        + ", ".join(warnings)
        + ". Double-check these gradations — cumulative % passing should "
          "not increase as sieve opening decreases."
    )

# =======================================================================
# 3. Proportioning — three trial blends
# =======================================================================
st.header("3. Proportioning")

run = st.button("Compute proportioning options", type="primary")

if run:
    matrix = grad_df.loc[SIEVE_LABELS, pile_names].to_numpy(dtype=float)
    if np.isnan(matrix).any():
        st.error(
            "One or more sieve entries are blank. Fill in every cell of the "
            "stockpile gradation table (use 100 for sieves the material "
            "fully passes) before computing proportions."
        )
        st.session_state.pop("results", None)
    else:
        try:
            options = optimize_blend_options(matrix, target, min_pct=min_pcts, max_pct=max_pcts)
            st.session_state["results"] = {
                "matrix": matrix, "names": pile_names, "options": options,
            }
        except ValueError as e:
            st.error(str(e))
            st.session_state.pop("results", None)

if "results" in st.session_state:
    matrix = st.session_state["results"]["matrix"]
    names = st.session_state["results"]["names"]
    options = st.session_state["results"]["options"]

    n_fails = [int((~o["result"]["passes"]).sum()) for o in options]
    default_idx = int(np.argmin(n_fails))

    st.subheader("Trial blend comparison")
    st.caption(
        "Three trial blends are generated across the spec band — coarse-leaning, "
        "balanced (mid-band), and fine-leaning — following standard trial-blend "
        "practice. Pick one below to carry forward for the detailed report."
    )

    cols = st.columns(len(options))
    for i, (col, opt) in enumerate(zip(cols, options)):
        with col:
            nf = n_fails[i]
            badge_html = (
                '<span class="blend-badge-pass">✓ Meets spec</span>' if nf == 0
                else f'<span class="blend-badge-fail">⚠ {nf} sieve(s) fail</span>'
            )
            mini_df = pd.DataFrame({
                "Stockpile": names,
                "%": np.round(opt["result"]["weights"] * 100, 1),
            })
            st.markdown(
                f'<div class="blend-card"><b>{opt["label"]}</b><br>'
                f'<span style="color:#6b7280;font-size:0.85rem;">{opt["note"]}</span><br><br>'
                f'{badge_html}</div>',
                unsafe_allow_html=True,
            )
            st.dataframe(mini_df, hide_index=True, use_container_width=True, height=38 * (len(names) + 1))

    st.write("")
    selected_label = st.radio(
        "Use this blend for the detailed report",
        [o["label"] for o in options], index=default_idx, horizontal=True,
    )
    selected = next(o for o in options if o["label"] == selected_label)
    res = selected["result"]
    n_fail = n_fails[[o["label"] for o in options].index(selected_label)]

    if not res["success"]:
        st.warning(
            "The optimizer did not fully converge (" + res["message"] + ") for the "
            f"{selected_label} blend. The proportions below are its best attempt — "
            "review carefully."
        )
    if n_fail == 0:
        st.success(f"{selected_label} blend satisfies the target band at every controlled sieve.")
    else:
        st.warning(
            f"{selected_label} blend is outside the target band at {n_fail} sieve(s) — "
            "see the table below. Try one of the other trial blends above, adjust "
            "min/max limits, or source an additional stockpile (e.g. extra filler or fines)."
        )

    st.subheader(f"Recommended proportions — {selected_label}")

    rounding = st.select_slider(
        "Round proportions to nearest", options=[0.1, 0.5, 1.0], value=0.5,
    )
    raw_pct = res["weights"] * 100
    rounded = np.round(raw_pct / rounding) * rounding
    if rounded.sum() > 0:
        rounded = rounded * (100.0 / rounded.sum())  # renormalize to 100%

    prop_df = pd.DataFrame({
        "Stockpile": names,
        "Material type": filler_types,
        "Optimized %": np.round(raw_pct, 2),
        f"Rounded % (to {rounding})": np.round(rounded, 2),
    })
    st.dataframe(prop_df, hide_index=True, use_container_width=True)

    # -----------------------------------------------------------------
    # Active filler cap check (Table 17.3 mineral filler clause)
    # -----------------------------------------------------------------
    filler_checks = check_active_filler_cap(names, filler_types, rounded, cap_pct=active_cap_pct)
    if filler_checks:
        st.markdown("**Active filler cap check**")
        fc_df = pd.DataFrame([{
            "Stockpile": fc["name"],
            "Blend %": round(fc["pct"], 2),
            "Cap (%)": fc["cap_pct"],
            "Status": "OK" if fc["compliant"] else "OVER CAP",
        } for fc in filler_checks])
        st.dataframe(fc_df, hide_index=True, use_container_width=True)
        n_over_cap = sum(1 for fc in filler_checks if not fc["compliant"])
        if n_over_cap:
            st.error(
                f"{n_over_cap} active filler stockpile(s) exceed the {active_cap_pct:g}% cap "
                "by mass of the total asphalt concrete. Lower its Max % limit in section 2 "
                "and recompute, use it partly as inert filler instead, or confirm a Special "
                "Specification permits a higher limit."
            )
        else:
            st.success(f"All active filler stockpiles are within the {active_cap_pct:g}% cap.")

    c1, c2 = st.columns([1, 1])
    with c1:
        fig1, ax1 = plt.subplots(figsize=(4.5, 3.5))
        ax1.bar(names, raw_pct, color="#4C78A8")
        ax1.set_ylabel("% of blend")
        ax1.set_title("Stockpile proportions")
        ax1.set_xticks(range(len(names)))
        ax1.set_xticklabels(names, rotation=30, ha="right")
        fig1.tight_layout()
        st.pyplot(fig1)

    # Use rounded proportions for the reported blend/gradation curve so what
    # you see matches what you'd actually bin out in the field.
    eval_rounded = evaluate_blend(rounded / 100.0, matrix, target)

    with c2:
        sieves_asc = SIEVES[::-1]
        idx_asc = list(range(len(SIEVES) - 1, -1, -1))
        lower = eval_rounded["lower"][idx_asc]
        upper = eval_rounded["upper"][idx_asc]
        blend = eval_rounded["blend"][idx_asc]

        fig2, ax2 = plt.subplots(figsize=(5, 3.8))
        ax2.set_xscale("log")
        ax2.fill_between(sieves_asc, lower, upper, color="#4C78A8", alpha=0.2,
                          label="Spec band")
        ax2.plot(sieves_asc, blend, marker="o", color="#E45756", label="Blend")
        ax2.set_xticks(sieves_asc)
        ax2.set_xticklabels([str(s) for s in sieves_asc], rotation=45)
        ax2.set_xlabel("Sieve size (mm, log scale)")
        ax2.set_ylabel("% passing")
        ax2.set_ylim(0, 105)
        ax2.set_title(f"{mix_type} – {course} – {designation}")
        ax2.legend()
        fig2.tight_layout()
        st.pyplot(fig2)

    st.subheader("Blended gradation vs. target (using rounded proportions)")

    table_rows = []
    for i, s in enumerate(SIEVES):
        m = eval_rounded["mask"][i]
        table_rows.append({
            "Sieve (mm)": s,
            "Lower spec": f"{eval_rounded['lower'][i]:.0f}" if m else "-",
            "Upper spec": f"{eval_rounded['upper'][i]:.0f}" if m else "-",
            "Blend % passing": round(float(eval_rounded["blend"][i]), 1),
            "Status": ("Pass" if eval_rounded["passes"][i] else "FAIL") if m else "n/a",
        })
    result_df = pd.DataFrame(table_rows)

    def highlight_fail(row):
        color = "background-color: #fddede" if row["Status"] == "FAIL" else ""
        return [color] * len(row)

    st.dataframe(
        result_df.style.apply(highlight_fail, axis=1),
        hide_index=True, use_container_width=True,
    )

    # ---------------------------------------------------------------
    # Export
    # ---------------------------------------------------------------
    st.subheader("Export")
    ec1, ec2 = st.columns(2)

    xbuf = io.BytesIO()
    with pd.ExcelWriter(xbuf, engine="openpyxl") as writer:
        prop_df.to_excel(writer, sheet_name="Proportions", index=False)
        result_df.to_excel(writer, sheet_name="Blended Gradation", index=False)
    with ec1:
        st.download_button(
            "Download Excel workbook",
            data=xbuf.getvalue(),
            file_name=f"asphalt_proportioning_{mix_type.replace(' ', '')}_{course.replace(' ', '')}_{designation.replace('/', '-')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

    blend_options_summary = [
        {"label": o["label"], "note": o["note"], "n_fail": n_fails[i]}
        for i, o in enumerate(options)
    ]
    target_info = {"mix_type": mix_type, "course": course, "designation": designation}
    pdf_bytes = build_pdf_report(
        project_info=project_info,
        target_info=target_info,
        blend_options=blend_options_summary,
        selected_label=selected_label,
        prop_df=prop_df,
        result_df=result_df,
        n_fail=n_fail,
        gradation_fig=fig2,
        proportions_fig=fig1,
        filler_checks=filler_checks,
        active_cap_pct=active_cap_pct,
    )
    with ec2:
        st.download_button(
            "Download PDF report",
            data=pdf_bytes,
            file_name=f"asphalt_proportioning_report_{designation.replace('/', '-')}.pdf",
            mime="application/pdf",
            use_container_width=True,
        )
else:
    st.info("Enter your stockpile gradations above, then click **Compute proportioning options**.")
