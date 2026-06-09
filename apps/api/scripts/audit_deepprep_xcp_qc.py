import json
import sqlite3
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup


ROOT = Path("/home/yyf/project/image_agent")
PROJECTS = ROOT / "data/projects"
DERIV = PROJECTS / "13/derivatives"


def print_section(title: str) -> None:
    print(f"\n## {title}")


def read_html_text(path: Path, max_lines: int = 80) -> None:
    print(f"FILE\t{path}\texists={path.exists()}\tsize={path.stat().st_size if path.exists() else 'NA'}")
    if not path.exists():
        return
    text = BeautifulSoup(path.read_text(encoding="utf-8", errors="ignore"), "html.parser").get_text("\n")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for line in lines[:max_lines]:
        print(f"HTML\t{line[:220]}")


def summarize_tsv(path: Path) -> None:
    print(f"FILE\t{path}\texists={path.exists()}\tsize={path.stat().st_size if path.exists() else 'NA'}")
    if not path.exists():
        return
    df = pd.read_csv(path, sep="\t")
    print(f"SHAPE\t{df.shape[0]}\t{df.shape[1]}")
    print("COLUMNS\t" + ",".join(map(str, df.columns[:120])))
    numeric = df.select_dtypes(include="number")
    for col in numeric.columns:
        s = numeric[col].dropna()
        if s.empty:
            continue
        print(f"STAT\t{col}\tn={len(s)}\tmean={s.mean():.6g}\tmedian={s.median():.6g}\tmax={s.max():.6g}\tp95={s.quantile(0.95):.6g}")
    print("HEAD")
    print(df.head(5).to_string(index=False))


print_section("Tasks")
db = ROOT / "data/app.db"
if db.exists():
    conn = sqlite3.connect(db)
    for row in conn.execute("select id, project_id, workflow_type, status, progress, created_at from tasks where project_id=13 order by id"):
        print("\t".join(map(str, row)))

print_section("XCP-D-like files")
patterns = [
    "*desc-linc_qc.tsv",
    "*outliers.tsv",
    "*motion.tsv",
    "*temporal_mask.tsv",
    "*desc-denoised_bold*",
    "*desc-interpolated_bold*",
    "*executive_summary.html",
]
for pattern in patterns:
    matches = sorted(PROJECTS.glob(f"**/{pattern}"))
    print(f"PATTERN\t{pattern}\tcount={len(matches)}")
    for path in matches[:20]:
        print(f"MATCH\t{path}")

print_section("DeepPrep BOLD QC HTML")
for path in [
    DERIV / "64/output/QC/sub-01/sub-01.html",
    DERIV / "64/output/QC/sub-01/figures/sub-01_task-rest_desc-validation_bold.html",
    DERIV / "64/output/QC/sub-01/figures/sub-01_task-rest_desc-summary_bold.html",
    DERIV / "64/output/BOLD/sub-01/figures/sub-01_task-rest_desc-validation_bold.html",
    DERIV / "64/output/BOLD/sub-01/figures/sub-01_task-rest_desc-summary_bold.html",
    DERIV / "41/output/QC/sub-01/sub-01.html",
]:
    read_html_text(path, max_lines=40)

print_section("DeepPrep BOLD Confounds")
summarize_tsv(DERIV / "64/output/BOLD/sub-01/func/sub-01_task-rest_desc-confounds_timeseries.tsv")

print_section("Downstream BOLD summaries")
for path in [
    DERIV / "111/output/sub-01_task-rest_desc-confounds_summary.tsv",
    DERIV / "111/output/summary/bold_result_summary.json",
    DERIV / "111/output/summary/bold_scientific_report_summary.json",
]:
    print(f"FILE\t{path}\texists={path.exists()}\tsize={path.stat().st_size if path.exists() else 'NA'}")
    if path.suffix == ".tsv" and path.exists():
        summarize_tsv(path)
    elif path.suffix == ".json" and path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
        print(json.dumps({k: payload.get(k) for k in ("modality", "workflow_type", "spaces", "feature_groups", "provenance")}, indent=2, ensure_ascii=False)[:3000])
