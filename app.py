"""
Asphalt Coarse Aggregate Proportioning Calculator
--------------------------------------------------
Automation_hub | Materials & Geotechnical Engineering Tools

Given the percent-passing gradation of 2-6 aggregate stockpiles, this tool
solves for the blend proportions that best satisfy a target job-mix
gradation band, then reports the blended gradation against the spec and
lets you fine-tune by hand.

Spec source (default): Ghana Highway Authority, Standard Specification for
Road and Bridge Works, Table 17.3 - Grading Requirements for Asphalt
Concrete (Type I / Type II, Wearing / Binder Course).

Run locally with:  streamlit run app.py
"""

import io

import numpy as np
import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt

from gradation_core import (
    SIEVES, SIEVE_LABELS, NMAS_MM, SPEC, available_courses,
    available_designations, get_target, optimize_blend, evaluate_blend,
)


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

st.set_page_config(page_title="Asphalt Aggregate Proportioning", layout="wide")

# =======================================================================
# Header
# =======================================================================
st.title("Asphalt Coarse Aggregate Proportioning Calculator")
st.caption(
    "Automation_hub — Materials & Geotechnical Engineering Tools. "
    "Target gradation bands from the Ghana Highway Authority Standard "
    "Specification, Table 17.3."
)

# =======================================================================
# 1. Mix type / course / designation selection
#    (the engineer picks Type I or Type II, and the applicable course)
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

pile_names = []
min_pcts = []
max_pcts = []

name_cols = st.columns(n_piles)
for i in range(n_piles):
    with name_cols[i]:
        nm = st.text_input(f"Stockpile {i + 1} name", value=default_names[i], key=f"name_{i}")
        pile_names.append(nm if nm.strip() else f"Stockpile {i + 1}")
        c_min, c_max = st.columns(2)
        with c_min:
            mn = st.number_input("Min %", min_value=0.0, max_value=100.0, value=0.0,
                                  step=1.0, key=f"min_{i}")
        with c_max:
            mx = st.number_input("Max %", min_value=0.0, max_value=100.0, value=100.0,
                                  step=1.0, key=f"max_{i}")
        min_pcts.append(mn)
        max_pcts.append(mx)

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
# 3. Run optimization
# =======================================================================
st.header("3. Proportioning")

run = st.button("Compute best-fit proportions", type="primary")

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
            res = optimize_blend(matrix, target, min_pct=min_pcts, max_pct=max_pcts)
            st.session_state["results"] = {
                "matrix": matrix, "names": pile_names, "res": res,
            }
        except ValueError as e:
            st.error(str(e))
            st.session_state.pop("results", None)

if "results" in st.session_state:
    matrix = st.session_state["results"]["matrix"]
    names = st.session_state["results"]["names"]
    res = st.session_state["results"]["res"]

    if not res["success"]:
        st.warning(
            "The optimizer did not fully converge (" + res["message"] + "). "
            "The proportions below are its best attempt — review carefully."
        )

    n_fail = int((~res["passes"]).sum())
    if n_fail == 0:
        st.success("Best-fit blend satisfies the target band at every controlled sieve.")
    else:
        st.warning(
            f"Best-fit blend is outside the target band at {n_fail} sieve(s) — "
            "see the table below. This can mean the available stockpiles cannot "
            "fully satisfy this gradation; consider adjusting min/max limits or "
            "sourcing an additional stockpile (e.g. extra filler or fines)."
        )

    st.subheader("Recommended proportions")

    rounding = st.select_slider(
        "Round proportions to nearest", options=[0.1, 0.5, 1.0], value=0.5,
    )
    raw_pct = res["weights"] * 100
    rounded = np.round(raw_pct / rounding) * rounding
    if rounded.sum() > 0:
        rounded = rounded * (100.0 / rounded.sum())  # renormalize to 100%

    prop_df = pd.DataFrame({
        "Stockpile": names,
        "Optimized %": np.round(raw_pct, 2),
        f"Rounded % (to {rounding})": np.round(rounded, 2),
    })
    st.dataframe(prop_df, hide_index=True, use_container_width=True)

    c1, c2 = st.columns([1, 1])
    with c1:
        fig1, ax1 = plt.subplots(figsize=(4.5, 3.5))
        ax1.bar(names, raw_pct, color="#4C78A8")
        ax1.set_ylabel("% of blend")
        ax1.set_title("Stockpile proportions")
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
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        prop_df.to_excel(writer, sheet_name="Proportions", index=False)
        result_df.to_excel(writer, sheet_name="Blended Gradation", index=False)
    st.download_button(
        "Download report (Excel)",
        data=buf.getvalue(),
        file_name=f"asphalt_proportioning_{mix_type.replace(' ', '')}_{course.replace(' ', '')}_{designation.replace('/', '-')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
else:
    st.info("Enter your stockpile gradations above, then click **Compute best-fit proportions**.")
