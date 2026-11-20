"""Execute every Streamlit page against the synthetic demo database using lightweight stubs.

Runs in a subprocess with TRACKER_DATA_MODE=demo so it never touches live data files.
"""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

DRIVER = r'''
import os, runpy, sys, random
sys.path[:0] = [r"{stubs}", r"{root}"]
os.chdir(r"{root}")
import streamlit as st
from tracker import config, build
if not config.PRICES_FILE.exists():
    from tracker import demo; demo.generate()
build.ensure_database()
from tracker.seed import load_taxonomy, load_universe
tax = load_taxonomy(); uni = load_universe()
random.seed(1)
runs = []
pages = ["app.py"] + sorted(str(p) for p in __import__("pathlib").Path("pages").glob("*.py"))
for p in pages:
    runs.append((p, {{}}))
for sid in tax.sectors["sector_id"]:
    runs.append(("pages/1_Sector_Explorer.py", {{"sector_id": sid}}))
for sid in random.sample(list(tax.subsectors["subsector_id"]), 60) + ["CG_XFANC", "PH_VACC", "RE_H2"]:
    runs.append(("pages/2_Subsector_Deep_Dive.py", {{"subsector_id": sid}}))
syms = list(uni.companies["nse_symbol"])
for s in random.sample(syms, 40) + syms[:4]:
    runs.append(("pages/3_Company_Explorer.py", {{"symbol": s}}))
runs.append(("pages/4_Sector_Rotation.py", {{"_stub_radio": {{"Level": "subsector"}}}}))
for p in pages:  # drill-down paths: selectboxes with index=None now pick the first option
    runs.append((p, {{"_stub_no_drill": False}}))
fails = 0
for page, state in runs:
    st.session_state.clear(); st.session_state.update(state)
    try:
        runpy.run_path(page, run_name="__main__")
    except (st.StopRun, st.SwitchPage):
        pass
    except Exception as e:
        fails += 1
        import traceback; print("FAIL", page, state, repr(e)); traceback.print_exc()
print("RUNS", len(runs), "FAILS", fails)
sys.exit(1 if fails else 0)
'''


def test_all_pages_execute():
    env = {**os.environ, "TRACKER_DATA_MODE": "demo"}
    code = DRIVER.format(stubs=ROOT / "tests" / "stubs", root=ROOT)
    res = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=900)
    print(res.stdout[-4000:], res.stderr[-4000:])
    assert res.returncode == 0, res.stdout[-4000:] + res.stderr[-4000:]
