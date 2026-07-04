import importlib.util
import json
import re
import subprocess
import tarfile
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "apps" / "api" / "scripts" / "build_release_overlay_sync_plan.py"


def _load_builder():
    spec = importlib.util.spec_from_file_location("build_release_overlay_sync_plan", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _step(plan: dict, step_id: str) -> dict:
    matches = [step for step in plan["steps"] if step["id"] == step_id]
    assert len(matches) == 1
    return matches[0]


def test_build_release_overlay_sync_plan_is_safe_and_ordered():
    builder = _load_builder()

    plan = builder.build_release_overlay_sync_plan(
        release_id="codex-current-20260619T210000Z",
        archive_path="/tmp/image_agent_release_codex-current-20260619T210000Z.tar.gz",
    )

    assert plan["plan_id"] == "remote_release_overlay_sync_plan_v1"
    assert plan["status"] == "operator_review_required"
    assert plan["remote_host"] == "yyf@10.2.32.14"
    assert plan["remote_project_root"] == "/home/yyf/project/image_agent"
    assert plan["release_overlay"] == "/home/yyf/project/image_agent_releases/codex-current-20260619T210000Z"
    assert plan["incoming_release_overlay"] == "/home/yyf/project/image_agent_releases/codex-current-20260619T210000Z.incoming"
    assert [step["id"] for step in plan["steps"]] == [
        "local_preflight",
        "build_current_worktree_archive",
        "upload_archive_to_remote_tmp",
        "extract_archive_to_incoming_overlay",
        "verify_incoming_overlay_contents",
        "promote_incoming_overlay",
        "verify_promoted_overlay_contents",
    ]
    assert plan["privacy_and_safety_invariants"] == [
        "do_not_copy_dotenv_or_secret_files",
        "do_not_copy_git_or_dependency_caches",
        "do_not_copy_raw_patient_data",
        "do_not_modify_remote_live_tree",
        "do_not_overwrite_existing_release_overlay",
    ]
    serialized = json.dumps(plan, sort_keys=True)
    assert "--delete" not in serialized
    assert "rm -rf" not in serialized
    assert ".env" not in serialized
    assert "/home/yyf/project/image_agent " not in _step(plan, "extract_archive_to_incoming_overlay")["command"]
    assert "git diff --check" in _step(plan, "local_preflight")["command"]
    assert "python scripts/run_frontend_contract_tests.py --console-dir apps/console" in _step(plan, "local_preflight")["command"]
    assert "src/lib/api.test.ts" in _step(plan, "local_preflight")["command"]
    assert "src/lib/workflows.test.ts" in _step(plan, "local_preflight")["command"]
    assert "src/routes/AgentPage.test.tsx" in _step(plan, "local_preflight")["command"]
    assert "src/routes/WorkflowsPage.test.tsx" in _step(plan, "local_preflight")["command"]
    assert "src/routes/ResultDetailPage.test.tsx" in _step(plan, "local_preflight")["command"]
    assert "scripts/check_repository_hygiene.py" in _step(plan, "local_preflight")["command"]
    assert "verify_release_gate_command_plan.py" in _step(plan, "local_preflight")["command"]
    assert "--write-archive" in _step(plan, "build_current_worktree_archive")["command"]
    assert "scp " in _step(plan, "upload_archive_to_remote_tmp")["command"]
    assert "test ! -e /home/yyf/project/image_agent_releases/codex-current-20260619T210000Z.incoming" in serialized
    assert "test ! -e /home/yyf/project/image_agent_releases/codex-current-20260619T210000Z" in serialized
    assert "mv /home/yyf/project/image_agent_releases/codex-current-20260619T210000Z.incoming /home/yyf/project/image_agent_releases/codex-current-20260619T210000Z" in serialized
    assert "test -f apps/api/scripts/build_stale_task_apply_request.py" in serialized
    assert "test -f apps/api/scripts/verify_stale_task_apply_request.py" in serialized
    assert "test -f apps/api/scripts/build_elasticsearch_hybrid_config_plan.py" in serialized
    assert "test -f apps/api/scripts/verify_elasticsearch_hybrid_config_plan.py" in serialized
    assert "test -f apps/api/scripts/setup_elasticsearch_hybrid_rag.py" in serialized
    assert "test -f apps/api/scripts/setup_local_embedding_service.py" in serialized
    assert "test -f apps/api/scripts/verify_elasticsearch_hybrid_prerequisites.py" in serialized
    assert "test -f apps/api/app/scripts/probe_runtime_environment.py" in serialized
    assert "test -f scripts/check_repository_hygiene.py" in serialized
    assert "test -f scripts/configure_docker_access.py" in serialized
    assert "test -f scripts/run_frontend_contract_tests.py" in serialized
    assert "test -f scripts/verify_rawchat_direct_connectivity.py" in serialized
    assert "test -f docs/deployment/remote-elasticsearch-hybrid-config-plan.json" in serialized
    assert "test -f docs/rag/contracts/elasticsearch-hybrid-search.md" in serialized
    assert "test -f apps/console/package.json" in serialized
    assert "test -f apps/console/package-lock.json" in serialized
    assert "test -f apps/console/src/lib/api.test.ts" in serialized
    assert "test -f apps/console/src/lib/workflows.test.ts" in serialized
    assert "test -f apps/console/src/routes/AgentPage.test.tsx" in serialized
    assert "test -f apps/console/src/routes/WorkflowsPage.test.tsx" in serialized
    assert "test -f apps/console/src/routes/ResultDetailPage.test.tsx" in serialized
    assert "printf '%s" not in _step(plan, "verify_incoming_overlay_contents")["command"]
    assert "printf '%s" not in _step(plan, "verify_promoted_overlay_contents")["command"]
    assert "repository_hygiene_status=passed" in _step(plan, "local_preflight")["expected_success"]
    assert "frontend_api_contract_tests=passed" in _step(plan, "local_preflight")["expected_success"]


def test_build_release_overlay_sync_plan_rejects_unsafe_release_id():
    builder = _load_builder()

    with pytest.raises(SystemExit) as exc:
        builder.build_release_overlay_sync_plan(
            release_id="/home/yyf/project/image_agent_releases/current",
            archive_path="/tmp/image_agent_release_current.tar.gz",
        )

    assert "release_id must be a privacy-safe release symbol" in str(exc.value)


def test_build_release_overlay_sync_plan_cli_writes_json(tmp_path, capsys):
    builder = _load_builder()
    output_json = tmp_path / "overlay-plan.json"

    builder.main(
        [
            "--release-id",
            "codex-current-20260619T210000Z",
            "--archive-path",
            "/tmp/image_agent_release_codex-current-20260619T210000Z.tar.gz",
            "--output-json",
            str(output_json),
        ]
    )

    stdout_plan = json.loads(capsys.readouterr().out)
    saved_plan = json.loads(output_json.read_text(encoding="utf-8"))
    assert stdout_plan == saved_plan
    assert saved_plan["steps"][0]["id"] == "local_preflight"


def test_write_current_worktree_archive_excludes_secret_runtime_and_dependency_paths(tmp_path):
    builder = _load_builder()
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    (repo / ".gitignore").write_text("ignored.log\n", encoding="utf-8")
    (repo / "apps" / "api" / "scripts").mkdir(parents=True)
    for script_name in (
        "build_stale_task_apply_request.py",
        "verify_stale_task_apply_request.py",
        "build_elasticsearch_hybrid_config_plan.py",
        "verify_elasticsearch_hybrid_config_plan.py",
        "setup_elasticsearch_hybrid_rag.py",
        "setup_local_embedding_service.py",
        "verify_elasticsearch_hybrid_prerequisites.py",
        "smoke_remote_agent.py",
        "verify_remote_smoke_acceptance.py",
        "verify_release_gate_command_plan.py",
    ):
        (repo / "apps" / "api" / "scripts" / script_name).write_text("print('ok')\n", encoding="utf-8")
    (repo / "apps" / "api" / "app" / "scripts").mkdir(parents=True)
    (repo / "apps" / "api" / "app" / "scripts" / "probe_runtime_environment.py").write_text(
        "print('probe')\n",
        encoding="utf-8",
    )
    (repo / "docs" / "rag" / "contracts").mkdir(parents=True)
    (repo / "docs" / "rag" / "contracts" / "elasticsearch-hybrid-search.md").write_text(
        "# ES hybrid\n",
        encoding="utf-8",
    )
    (repo / "docs" / "deployment").mkdir(parents=True)
    (repo / "docs" / "deployment" / "remote-elasticsearch-hybrid-config-plan.json").write_text(
        "{}\n",
        encoding="utf-8",
    )
    (repo / "tools").mkdir()
    (repo / "tools" / "restart_remote_image_agent_api.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    (repo / "apps" / "console" / "src" / "lib").mkdir(parents=True)
    (repo / "apps" / "console" / "src" / "routes").mkdir(parents=True)
    (repo / "apps" / "console" / "package.json").write_text("{}\n", encoding="utf-8")
    (repo / "apps" / "console" / "package-lock.json").write_text("{}\n", encoding="utf-8")
    for test_path in (
        "apps/console/src/lib/api.test.ts",
        "apps/console/src/lib/workflows.test.ts",
        "apps/console/src/routes/AgentPage.test.tsx",
        "apps/console/src/routes/WorkflowsPage.test.tsx",
        "apps/console/src/routes/ResultDetailPage.test.tsx",
    ):
        (repo / test_path).write_text("test('ok', () => undefined)\n", encoding="utf-8")
    (repo / "scripts").mkdir()
    (repo / "scripts" / "check_repository_hygiene.py").write_text("print('hygiene')\n", encoding="utf-8")
    (repo / "scripts" / "configure_docker_access.py").write_text("print('docker access')\n", encoding="utf-8")
    (repo / "scripts" / "run_frontend_contract_tests.py").write_text("print('frontend')\n", encoding="utf-8")
    (repo / "scripts" / "verify_rawchat_direct_connectivity.py").write_text(
        "print('rawchat direct')\n",
        encoding="utf-8",
    )
    (repo / "notes").mkdir()
    (repo / "notes" / "operator-handoff.md").write_text("safe untracked note\n", encoding="utf-8")
    (repo / ".env").write_text("OPENAI_API_KEY=sk-secret-token\n", encoding="utf-8")
    (repo / "data" / "projects").mkdir(parents=True)
    (repo / "data" / "projects" / "patient.nii.gz").write_text("raw patient data\n", encoding="utf-8")
    (repo / "node_modules" / "pkg").mkdir(parents=True)
    (repo / "node_modules" / "pkg" / "index.js").write_text("module\n", encoding="utf-8")
    (repo / ".rag_index").mkdir()
    (repo / ".rag_index" / "manifest.json").write_text("{}\n", encoding="utf-8")
    (repo / "ignored.log").write_text("ignored\n", encoding="utf-8")
    subprocess.run(
        [
            "git",
            "add",
            ".gitignore",
            "apps/api/scripts/build_elasticsearch_hybrid_config_plan.py",
            "apps/api/scripts/setup_elasticsearch_hybrid_rag.py",
            "apps/api/scripts/setup_local_embedding_service.py",
            "apps/api/scripts/build_stale_task_apply_request.py",
            "apps/api/scripts/verify_stale_task_apply_request.py",
            "apps/api/scripts/verify_elasticsearch_hybrid_config_plan.py",
            "apps/api/scripts/verify_elasticsearch_hybrid_prerequisites.py",
            "apps/api/scripts/smoke_remote_agent.py",
            "apps/api/scripts/verify_remote_smoke_acceptance.py",
            "apps/api/scripts/verify_release_gate_command_plan.py",
            "apps/api/app/scripts/probe_runtime_environment.py",
            "docs/deployment/remote-elasticsearch-hybrid-config-plan.json",
            "docs/rag/contracts/elasticsearch-hybrid-search.md",
            "apps/console/package.json",
            "apps/console/package-lock.json",
            "apps/console/src/lib/api.test.ts",
            "apps/console/src/lib/workflows.test.ts",
            "apps/console/src/routes/AgentPage.test.tsx",
            "apps/console/src/routes/WorkflowsPage.test.tsx",
            "apps/console/src/routes/ResultDetailPage.test.tsx",
            "scripts/check_repository_hygiene.py",
            "scripts/configure_docker_access.py",
            "scripts/run_frontend_contract_tests.py",
            "scripts/verify_rawchat_direct_connectivity.py",
            "tools/restart_remote_image_agent_api.sh",
            ".env",
        ],
        cwd=repo,
        check=True,
        capture_output=True,
    )

    archive_path = tmp_path / "image_agent_release_test.tar.gz"
    report = builder.write_current_worktree_archive(repo_root=repo, archive_path=archive_path)

    assert report["status"] == "passed"
    assert report["excluded_secret_and_runtime_paths"] is True
    assert report["required_gate_files_present"] is True
    assert re.fullmatch(r"[0-9a-f]{64}", report["archive_sha256"])
    with tarfile.open(archive_path, "r:gz") as archive:
        names = set(archive.getnames())
    assert "apps/api/scripts/build_elasticsearch_hybrid_config_plan.py" in names
    assert "apps/api/scripts/setup_elasticsearch_hybrid_rag.py" in names
    assert "apps/api/scripts/setup_local_embedding_service.py" in names
    assert "apps/api/scripts/build_stale_task_apply_request.py" in names
    assert "apps/api/scripts/verify_stale_task_apply_request.py" in names
    assert "apps/api/scripts/verify_elasticsearch_hybrid_config_plan.py" in names
    assert "apps/api/scripts/verify_elasticsearch_hybrid_prerequisites.py" in names
    assert "apps/api/app/scripts/probe_runtime_environment.py" in names
    assert "scripts/check_repository_hygiene.py" in names
    assert "scripts/configure_docker_access.py" in names
    assert "scripts/run_frontend_contract_tests.py" in names
    assert "scripts/verify_rawchat_direct_connectivity.py" in names
    assert "docs/deployment/remote-elasticsearch-hybrid-config-plan.json" in names
    assert "docs/rag/contracts/elasticsearch-hybrid-search.md" in names
    assert "apps/console/package.json" in names
    assert "apps/console/package-lock.json" in names
    assert "apps/console/src/lib/api.test.ts" in names
    assert "apps/console/src/lib/workflows.test.ts" in names
    assert "apps/console/src/routes/AgentPage.test.tsx" in names
    assert "apps/console/src/routes/WorkflowsPage.test.tsx" in names
    assert "apps/console/src/routes/ResultDetailPage.test.tsx" in names
    assert "notes/operator-handoff.md" in names
    assert ".env" not in names
    assert "data/projects/patient.nii.gz" not in names
    assert "node_modules/pkg/index.js" not in names
    assert ".rag_index/manifest.json" not in names
    assert "ignored.log" not in names
