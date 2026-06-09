import json
import re
from pathlib import Path

import pandas as pd


root = Path("/home/yyf/project/image_agent/data/projects/13/derivatives")

for qc in [
    root / "64/output/QC/sub-01/sub-01.html",
    root / "41/output/QC/sub-01/sub-01.html",
]:
    print("REPORT", qc, "exists", qc.exists(), "size", qc.stat().st_size if qc.exists() else None)
    html = qc.read_text(encoding="utf-8", errors="ignore") if qc.exists() else ""
    print("problem_loading_count", html.lower().count("problem loading"), "error_word_count", len(re.findall("error", html, re.I)))
    refs = sorted(set(re.findall(r"figures/[^\"'<> ]+", html)))
    missing = [ref for ref in refs if not (qc.parent / ref).exists()]
    print("figure_refs", len(refs), "missing", len(missing))
    for ref in missing[:20]:
        print("MISSING", ref)

conf = root / "64/output/BOLD/sub-01/func/sub-01_task-rest_desc-confounds_timeseries.tsv"
df = pd.read_csv(conf, sep="\t")
fd = df["framewise_displacement"].dropna()
std = df["std_dvars"].dropna()
print(
    "MOTION_SUMMARY",
    json.dumps(
        {
            "n_volumes": int(df.shape[0]),
            "fd_n": int(fd.shape[0]),
            "fd_mean": float(fd.mean()),
            "fd_median": float(fd.median()),
            "fd_p95": float(fd.quantile(0.95)),
            "fd_max": float(fd.max()),
            "fd_gt_0p2": int((fd > 0.2).sum()),
            "fd_gt_0p5": int((fd > 0.5).sum()),
            "fd_gt_0p2_pct": float((fd > 0.2).mean()),
            "fd_gt_0p5_pct": float((fd > 0.5).mean()),
            "std_dvars_mean": float(std.mean()),
            "std_dvars_p95": float(std.quantile(0.95)),
            "std_dvars_max": float(std.max()),
        },
        ensure_ascii=False,
        indent=2,
    ),
)

for path in [
    root / "64/output/BOLD/sub-01/func/sub-01_task-rest_space-MNI152NLin6Asym_res-02_desc-preproc_bold.nii.gz",
    root / "64/output/BOLD/sub-01/func/sub-01_task-rest_space-T1w_desc-preproc_bold.nii.gz",
    root / "64/output/BOLD/sub-01/func/sub-01_task-rest_desc-confounds_timeseries.tsv",
    root / "111/output/sub-01_task-rest_desc-bold_metrics_summary.json",
    root / "111/output/sub-01_task-rest_desc-confounds_summary.tsv",
]:
    print("KEYFILE", path, "exists", path.exists(), "size", path.stat().st_size if path.exists() else None)
