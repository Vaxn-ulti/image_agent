from pathlib import Path


path = Path("/home/yyf/project/image_agent/apps/api/app/main.py")
text = path.read_text()

if "import mimetypes" not in text:
    text = text.replace("import json\n", "import json\nimport mimetypes\n", 1)

if "check_scientific_report_output" not in text:
    text = text.replace(
        "from app.workflows.result_contract import load_result_summary, result_contract_spec\n",
        "from app.workflows.result_contract import load_result_summary, result_contract_spec\n"
        "from apps.api.scripts.verify_scientific_reports import check_output as check_scientific_report_output\n"
        "from apps.api.scripts.verify_scientific_reports import resolve_task_output_dirs\n",
        1,
    )

if "class ScientificReportVerifyRequest" not in text:
    marker = "class RagQueryRequest(BaseModel):\n    project_id: int | None = None\n    query: str\n\n"
    text = text.replace(
        marker,
        marker
        + "\nclass ScientificReportVerifyRequest(BaseModel):\n"
        + "    task_ids: list[int] = []\n"
        + "    output_dirs: list[str] = []\n"
        + "    projects_root: str | None = None\n"
        + "    require_modalities: list[str] = []\n\n",
        1,
    )

if "def agent_verify_scientific_reports" not in text:
    marker = '@app.get("/runtime/containers")\ndef runtime_containers():\n    return inspect_runtime()\n'
    endpoint = '''@app.post("/agent/tools/verify-scientific-reports")
def agent_verify_scientific_reports(req: ScientificReportVerifyRequest):
    projects_root = Path(req.projects_root) if req.projects_root else PROJECTS_ROOT
    task_output_dirs, resolution_errors = resolve_task_output_dirs(projects_root, req.task_ids)
    explicit_output_dirs = [Path(path) for path in req.output_dirs]
    output_paths = [*explicit_output_dirs, *task_output_dirs]
    results = [check_scientific_report_output(path) for path in output_paths]
    required_modalities = {modality.upper() for modality in req.require_modalities}
    present_modalities = {result.modality for result in results}
    missing_modalities = sorted(required_modalities - present_modalities)
    ok = all(result.ok for result in results) and not resolution_errors and not missing_modalities
    return {
        "ok": ok,
        "read_only": True,
        "projects_root": str(projects_root),
        "task_ids": req.task_ids,
        "resolution_errors": resolution_errors,
        "missing_modalities": missing_modalities,
        "results": [
            {
                "output_dir": str(result.output_dir),
                "modality": result.modality,
                "ok": result.ok,
                "errors": result.errors,
                "warnings": result.warnings,
            }
            for result in results
        ],
    }


'''
    text = text.replace(marker, endpoint + marker, 1)

old_media = '    media_type = "application/gzip" if target.name.endswith(".nii.gz") else None\n    return FileResponse(target, media_type=media_type)\n'
new_media = '''    if target.name.endswith(".nii.gz"):
        media_type = "application/gzip"
    else:
        media_type = mimetypes.guess_type(target.name)[0]
    return FileResponse(target, media_type=media_type)
'''
if old_media in text:
    text = text.replace(old_media, new_media, 1)

path.write_text(text)
