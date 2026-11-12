# Voyage Planner - routing engine (Member 2)

Needs Python 3.9+. On macOS/Linux use `python3` (plain `python` often does not exist). On Windows use `py` or `python`.

## Setup (once, from inside this folder)
```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt    # searoute==1.6.0, openpyxl, pytest, streamlit, pandas, folium
```
After activating the venv, `python` also works.

## Run
```bash
python3 scripts/run_benchmarks.py   # 10/10 benchmark table
python3 scripts/demo.py             # guided tour of example calls
python3 -m pytest -q                # 148 tests (117 engine, 24 app, 7 Member 1)
python3 scripts/run_comparisons.py  # T20 comparisons
streamlit run app.py                # the app; VOYAGE_API_URL=local = engine in-process
```

```
voyage_planner/   the package        data/     the 27 Oct workbook + port_review.json
app.py            Streamlit app (exclusion selector, highlighted routes)
scripts/          runnable scripts   tests/    pytest suite
docs/             CODE_WALKTHROUGH.md (start here), T16, T32, HANDOFF_NOTES
results/          benchmark, T20 comparison + T16 evidence
member1_review/   Member 1's reviewed T02/T03/T13 scripts + results (as supplied)
```
Other workbook: set `VOYAGE_PLANNER_DATA=/path/file.xlsx`.
