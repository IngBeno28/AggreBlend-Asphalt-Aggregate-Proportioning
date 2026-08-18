# Asphalt Coarse Aggregate Proportioning Calculator

Part of Automation_hub's materials & geotechnical engineering toolset.

Given the sieve analysis of 2-6 aggregate stockpiles, this tool proposes
three trial blends (coarse-leaning, balanced, and fine-leaning — all
summing to 100%) that best satisfy a target asphalt concrete gradation
band, reports the resulting blended gradation against the spec sieve by
sieve, and exports a branded PDF or Excel report.

## Spec source

`gradation_core.py` embeds Table 17.3 - Grading Requirements for Asphalt
Concrete from the Ghana Highway Authority Standard Specification for Road
and Bridge Works: Type I (Wearing Course 0/14, 0/10, 0/6; Binder Course
0/20, 0/14, 0/10) and Type II (Wearing Course 0/14, 0/10). The engineer
selects the mix type, course, and grading designation in the app; nothing
is hard-coded to one combination.

To point the tool at a different specification (another country/agency, or
a project-specific job-mix formula band), edit the `SPEC` dictionary in
`gradation_core.py` — the app UI adapts automatically to whatever types,
courses, and designations you define there.

## How the proportioning works

`optimize_blend()` in `gradation_core.py` uses `scipy.optimize.minimize`
(SLSQP, with analytic gradients and a multi-start restart to avoid stalling
on the non-smooth objective) to find stockpile weights that:

1. Primarily minimize how far the blended gradation falls outside the
   spec's lower/upper control points at each sieve (zero penalty once
   inside the band).
2. Secondarily pull the blend toward a target line within the band
   (`target_frac`), so that when more than one feasible blend exists, the
   result sits near that line rather than hugging an edge.

`optimize_blend_options()` runs that solve three times with different
`target_frac` values (0.3 / 0.5 / 0.7 — see `BLEND_PRESETS`), producing a
coarse-leaning, balanced, and fine-leaning trial blend in one call, mirroring
how mix designers compare a few trial blends before picking a job-mix
formula. The app shows all three side by side; you pick one to carry into
the detailed report. If the stockpiles only support one feasible region,
some presets may converge to the same answer — that's expected, not a bug.

Optional per-stockpile min/max % constraints (e.g. capping mineral filler
at 5-8%) are enforced as bounds during the solve.

If no combination of the entered stockpiles can satisfy every sieve, the
optimizer returns its closest attempt and the app flags exactly which
sieves fail — that's a signal to adjust the stockpile mix (e.g. source
finer material) rather than a bug.

## PDF / Excel export

`pdf_report.py` builds a branded report matching Automation_hub's other
tools (USCS Classifier, Proctor Compaction Calculator, etc.): a cover page
with logo and project info table, a trial-blend comparison + detailed
results page, full-page gradation and proportions charts, and a
certification page — with a running footer (company info, page numbers) on
every page. It has no Streamlit dependency, so `build_pdf_report(...)` can
be called and unit tested on its own.

Drop a real logo at `assets/logo.png` (24mm square works well) to replace
the generated "AH" placeholder badge. Company name, phone, website, and the
app name/tagline are single constants at the top of `pdf_report.py` — edit
those in one place to rebrand.

## Running locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Deploying on Streamlit Community Cloud (or similar)

1. Push this folder (`app.py`, `gradation_core.py`, `pdf_report.py`,
   `requirements.txt`, and optionally `assets/logo.png`) to a GitHub repo.
2. On share.streamlit.io (or your platform of choice), point a new app at
   `app.py` in that repo.
3. No secrets or external services are required — everything runs
   in-process on numpy/scipy/pandas/matplotlib/reportlab.

## Files

- `app.py` — Streamlit UI: Project Information sidebar, mix/course/
  designation selection, stockpile gradation entry, the three-trial-blend
  comparison, results tables/charts, and the Excel/PDF export buttons.
- `gradation_core.py` — UI-independent spec data and optimization engine.
  Kept separate so the math can be unit tested or reused (e.g. in a batch
  script or another tool) without Streamlit installed.
- `pdf_report.py` — UI-independent PDF report builder (reportlab). Also
  reusable outside Streamlit.
- `requirements.txt` — pinned minimum versions for deployment.
- `assets/logo.png` (optional, not included) — drop your real logo here.

## Extending

- Add another agency's spec table by adding a new top-level key to `SPEC`
  in `gradation_core.py` (same nested `{course: {designation: {sieve:
  (lower, upper) or None}}}` shape).
- The gradation chart currently uses a standard semi-log axis; swap in a
  Superpave 0.45-power chart by transforming the sieve x-values to
  `sieve ** 0.45` before plotting, if you extend this into a Superpave mix
  design tool.
