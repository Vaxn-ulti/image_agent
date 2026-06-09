from pathlib import Path


root = Path("/home/yyf/project/image_agent")
scripts_dir = root / "apps/api/app/scripts"
scripts_dir.mkdir(parents=True, exist_ok=True)
(scripts_dir / "__init__.py").touch()
(scripts_dir / "verify_scientific_reports.py").write_text(
    (root / "apps/api/scripts/verify_scientific_reports.py").read_text(),
    encoding="utf-8",
)

main_path = root / "apps/api/app/main.py"
text = main_path.read_text()
text = text.replace(
    "from apps.api.scripts.verify_scientific_reports import check_output as check_scientific_report_output\n"
    "from apps.api.scripts.verify_scientific_reports import resolve_task_output_dirs\n",
    "from app.scripts.verify_scientific_reports import check_output as check_scientific_report_output\n"
    "from app.scripts.verify_scientific_reports import resolve_task_output_dirs\n",
)
main_path.write_text(text)
