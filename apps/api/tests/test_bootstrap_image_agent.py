import importlib.util
import json
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "scripts" / "bootstrap_image_agent.py"
README_PATH = REPO_ROOT / "README.md"


def _load_bootstrap():
    spec = importlib.util.spec_from_file_location("bootstrap_image_agent", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_bootstrap_plan_installs_from_git_checkout_without_remote_server_binding(tmp_path):
    script = _load_bootstrap()

    plan = script.build_bootstrap_plan(
        repo_root=tmp_path,
        env_file=tmp_path / ".env",
        enable_elasticsearch_hybrid=True,
        prepare_workflow_images=True,
        embedding_model="text-embedding-3-small",
        embedding_base_url="https://embedding.example/v1",
        apply_changes=False,
    )

    serialized = json.dumps(plan, sort_keys=True)
    assert plan["plan_id"] == "image_agent_bootstrap_v1"
    assert plan["mode"] == "dry_run"
    assert plan["repo_root"] == str(tmp_path)
    assert "yyf@10.2.32.14" not in serialized
    assert "10.2.32.14" not in serialized
    assert "sk-" not in serialized
    assert [step["id"] for step in plan["steps"]] == [
        "configure_image_agent_root",
        "configure_image_agent_release_root",
        "check_python",
        "create_api_venv",
        "install_api_requirements",
        "install_desktop_dependencies",
        "prepare_fixed_workflow_images",
        "setup_elasticsearch_hybrid_rag",
        "verify_local_runtime_probe",
    ]
    assert "apps/api/scripts/setup_elasticsearch_hybrid_rag.py" in serialized
    assert "--apply" in serialized
    assert "IMAGE_AGENT_RAG_EMBEDDING_API_KEY" in serialized
    assert "IMAGE_AGENT_ROOT" in serialized
    root_step = next(step for step in plan["steps"] if step["id"] == "configure_image_agent_root")
    assert root_step["command"] == ["write_env", str(tmp_path / ".env"), "IMAGE_AGENT_ROOT", str(tmp_path)]
    assert "docker.elastic.co/elasticsearch/elasticsearch:9.4.2" in serialized
    assert "pennlinc/qsiprep:26.0.0" in serialized


def test_bootstrap_apply_executes_ordered_commands_without_secret_in_report(tmp_path, monkeypatch):
    script = _load_bootstrap()
    calls = []
    env_files = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        env_files.append(kwargs.get("env", {}).get("IMAGE_AGENT_ENV_FILE"))

        class Proc:
            returncode = 0
            stdout = "ok"
            stderr = ""

        return Proc()

    monkeypatch.setattr(script.subprocess, "run", fake_run)
    monkeypatch.setenv("IMAGE_AGENT_RAG_EMBEDDING_API_KEY", "test-embedding-token")

    report = script.bootstrap_image_agent(
        repo_root=tmp_path,
        env_file=tmp_path / ".env",
        enable_elasticsearch_hybrid=True,
        prepare_workflow_images=True,
        embedding_model="text-embedding-3-small",
        embedding_base_url="https://embedding.example/v1",
        apply_changes=True,
    )

    assert report["status"] == "completed"
    assert f"IMAGE_AGENT_ROOT={script._env_file_value(str(tmp_path))}" in (tmp_path / ".env").read_text(
        encoding="utf-8"
    )
    assert all(value == str(tmp_path / ".env") for value in env_files)
    assert any("venv" in cmd for cmd in calls)
    assert any(any("pip" in part for part in cmd) and "requirements.txt" in cmd for cmd in calls)
    assert any("npm" in cmd and "install" in cmd for cmd in calls)
    assert any("app.scripts.probe_runtime_environment" in cmd and "--prepare-missing-images" in cmd for cmd in calls)
    assert any(any("setup_elasticsearch_hybrid_rag.py" in part for part in cmd) and "--apply" in cmd for cmd in calls)
    serialized = json.dumps(report, sort_keys=True)
    assert "test-embedding-token" not in serialized


def test_bootstrap_can_write_live_root_separate_from_release_checkout(tmp_path, monkeypatch):
    script = _load_bootstrap()
    release_root = tmp_path / "release-overlay"
    live_root = tmp_path / "live-root"
    env_file = tmp_path / "deploy.env"
    release_root.mkdir()
    live_root.mkdir()
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append({"cmd": cmd, "env_file": kwargs.get("env", {}).get("IMAGE_AGENT_ENV_FILE")})

        class Proc:
            returncode = 0
            stdout = "ok"
            stderr = ""

        return Proc()

    monkeypatch.setattr(script.subprocess, "run", fake_run)

    plan = script.build_bootstrap_plan(
        repo_root=release_root,
        image_agent_root=live_root,
        env_file=env_file,
        enable_elasticsearch_hybrid=False,
        prepare_workflow_images=False,
        embedding_model="",
        embedding_base_url="",
        apply_changes=False,
    )
    root_step = next(step for step in plan["steps"] if step["id"] == "configure_image_agent_root")
    assert root_step["command"] == ["write_env", str(env_file), "IMAGE_AGENT_ROOT", str(live_root)]
    release_step = next(step for step in plan["steps"] if step["id"] == "configure_image_agent_release_root")
    assert release_step["command"] == ["write_env", str(env_file), "IMAGE_AGENT_RELEASE_ROOT", str(release_root)]

    report = script.bootstrap_image_agent(
        repo_root=release_root,
        image_agent_root=live_root,
        env_file=env_file,
        enable_elasticsearch_hybrid=False,
        prepare_workflow_images=False,
        embedding_model="",
        embedding_base_url="",
        apply_changes=True,
    )

    assert report["status"] == "completed"
    assert report["repo_root"] == str(release_root)
    assert report["image_agent_root"] == str(live_root)
    env_text = env_file.read_text(encoding="utf-8")
    assert f"IMAGE_AGENT_ROOT={script._env_file_value(str(live_root))}" in env_text
    assert f"IMAGE_AGENT_RELEASE_ROOT={script._env_file_value(str(release_root))}" in env_text
    assert all(call["env_file"] == str(env_file) for call in calls)


def test_bootstrap_can_write_production_readiness_env(tmp_path, monkeypatch):
    script = _load_bootstrap()
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append({"cmd": cmd, "env_file": kwargs.get("env", {}).get("IMAGE_AGENT_ENV_FILE")})

        class Proc:
            returncode = 0
            stdout = "ok"
            stderr = ""

        return Proc()

    monkeypatch.setattr(script.subprocess, "run", fake_run)
    env_file = tmp_path / "deploy.env"

    plan = script.build_bootstrap_plan(
        repo_root=tmp_path,
        env_file=env_file,
        enable_elasticsearch_hybrid=False,
        prepare_workflow_images=False,
        production=True,
        production_cors_origins="https://console.example.com",
        production_public_base_url="https://api.example.com",
        embedding_model="",
        embedding_base_url="",
        apply_changes=False,
    )

    steps = {step["id"]: step for step in plan["steps"]}
    assert steps["configure_image_agent_env"]["command"] == ["write_env", str(env_file), "IMAGE_AGENT_ENV", "production"]
    assert steps["configure_production_cors_origins"]["command"] == [
        "write_env",
        str(env_file),
        "IMAGE_AGENT_CORS_ORIGINS",
        "https://console.example.com",
    ]
    assert steps["configure_public_base_url"]["command"] == [
        "write_env",
        str(env_file),
        "IMAGE_AGENT_PUBLIC_BASE_URL",
        "https://api.example.com",
    ]

    report = script.bootstrap_image_agent(
        repo_root=tmp_path,
        env_file=env_file,
        enable_elasticsearch_hybrid=False,
        prepare_workflow_images=False,
        production=True,
        production_cors_origins="https://console.example.com",
        production_public_base_url="https://api.example.com",
        embedding_model="",
        embedding_base_url="",
        apply_changes=True,
    )

    env_text = env_file.read_text(encoding="utf-8")
    assert report["status"] == "completed"
    assert "IMAGE_AGENT_ENV=production" in env_text
    assert "IMAGE_AGENT_CORS_ORIGINS=https://console.example.com" in env_text
    assert "IMAGE_AGENT_PUBLIC_BASE_URL=https://api.example.com" in env_text
    assert all(call["env_file"] == str(env_file) for call in calls)


def test_bootstrap_can_write_operator_managed_docker_command(tmp_path):
    script = _load_bootstrap()
    env_file = tmp_path / "deploy.env"

    plan = script.build_bootstrap_plan(
        repo_root=tmp_path,
        env_file=env_file,
        enable_elasticsearch_hybrid=False,
        prepare_workflow_images=False,
        docker_command="sudo -n docker",
        config_only=True,
        embedding_model="",
        embedding_base_url="",
        apply_changes=False,
    )

    steps = {step["id"]: step for step in plan["steps"]}
    assert steps["configure_docker_command"]["command"] == [
        "write_env",
        str(env_file),
        "IMAGE_AGENT_DOCKER_COMMAND",
        "sudo -n docker",
    ]
    assert "IMAGE_AGENT_DOCKER_COMMAND" in plan["runtime_configuration"]
    assert "sudo -n docker" not in plan["secret_handling"]

    report = script.bootstrap_image_agent(
        repo_root=tmp_path,
        env_file=env_file,
        enable_elasticsearch_hybrid=False,
        prepare_workflow_images=False,
        docker_command="sudo -n docker",
        config_only=True,
        embedding_model="",
        embedding_base_url="",
        apply_changes=True,
    )

    assert report["status"] == "completed"
    assert "IMAGE_AGENT_DOCKER_COMMAND='sudo -n docker'" in env_file.read_text(encoding="utf-8")
    assert "sudo -n docker" not in json.dumps(report, sort_keys=True)


def test_bootstrap_writes_shell_safe_env_values(tmp_path):
    script = _load_bootstrap()
    env_file = tmp_path / "deploy.env"
    env_file.write_text(
        "\n".join(
            [
                "IMAGE_AGENT_ENV=staging",
                "IMAGE_AGENT_DOCKER_COMMAND=docker",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    script._write_env_file(
        env_file,
        {
            "IMAGE_AGENT_ENV": "production",
            "IMAGE_AGENT_DOCKER_COMMAND": "sudo -n docker",
        },
    )

    assert env_file.read_text(encoding="utf-8").splitlines() == [
        "IMAGE_AGENT_ENV=production",
        "IMAGE_AGENT_DOCKER_COMMAND='sudo -n docker'",
    ]


def test_bootstrap_can_verify_operator_managed_docker_command(tmp_path):
    script = _load_bootstrap()
    env_file = tmp_path / "deploy.env"

    plan = script.build_bootstrap_plan(
        repo_root=tmp_path,
        env_file=env_file,
        enable_elasticsearch_hybrid=False,
        prepare_workflow_images=False,
        docker_command="sudo -n docker",
        verify_docker_command=True,
        config_only=True,
        embedding_model="",
        embedding_base_url="",
        apply_changes=False,
    )

    steps = {step["id"]: step for step in plan["steps"]}
    assert steps["verify_docker_command"]["command"] == [
        "sudo",
        "-n",
        "docker",
        "version",
        "--format",
        "{{.Server.Version}}",
    ]
    assert steps["verify_docker_command"]["mutates_state"] is False
    assert [step["id"] for step in plan["steps"][:2]] == [
        "verify_docker_command",
        "configure_image_agent_root",
    ]


def test_bootstrap_verifies_docker_command_before_writing_env(tmp_path, monkeypatch):
    script = _load_bootstrap()
    env_file = tmp_path / "deploy.env"
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)

        class Proc:
            returncode = 1
            stdout = ""
            stderr = "sudo password required"

        return Proc()

    monkeypatch.setattr(script.subprocess, "run", fake_run)

    with pytest.raises(SystemExit, match="bootstrap command failed"):
        script.bootstrap_image_agent(
            repo_root=tmp_path,
            env_file=env_file,
            enable_elasticsearch_hybrid=False,
            prepare_workflow_images=False,
            docker_command="sudo -n docker",
            verify_docker_command=True,
            config_only=True,
            embedding_model="",
            embedding_base_url="",
            apply_changes=True,
        )

    assert calls == [["sudo", "-n", "docker", "version", "--format", "{{.Server.Version}}"]]
    assert not env_file.exists()


def test_bootstrap_docker_command_verification_requires_explicit_command(tmp_path):
    script = _load_bootstrap()

    with pytest.raises(SystemExit, match="docker command is required"):
        script.build_bootstrap_plan(
            repo_root=tmp_path,
            env_file=tmp_path / ".env",
            enable_elasticsearch_hybrid=False,
            prepare_workflow_images=False,
            verify_docker_command=True,
            config_only=True,
            embedding_model="",
            embedding_base_url="",
            apply_changes=False,
        )


@pytest.mark.parametrize("docker_command", ["sudo -S docker", "docker compose", "bash -lc docker", ""])
def test_bootstrap_rejects_unsafe_docker_command(tmp_path, docker_command):
    script = _load_bootstrap()

    with pytest.raises(SystemExit, match="docker command"):
        script.build_bootstrap_plan(
            repo_root=tmp_path,
            env_file=tmp_path / ".env",
            enable_elasticsearch_hybrid=False,
            prepare_workflow_images=False,
            docker_command=docker_command,
            embedding_model="",
            embedding_base_url="",
            apply_changes=False,
        )


def test_bootstrap_can_write_verified_strict_acceptance_env(tmp_path, monkeypatch):
    script = _load_bootstrap()
    acceptance_json = tmp_path / "strict-acceptance.json"
    acceptance_json.write_text(
        json.dumps(
            {
                "generated_at_utc": "2026-06-21T01:00:00Z",
                "smoke_gate": {"deployment_id": "codex-release-20260621T010000"},
            }
        ),
        encoding="utf-8",
    )
    calls = []

    class FakeVerifier:
        @staticmethod
        def verify_acceptance_payload(payload, *, max_age_hours=None, now_utc=None):
            assert payload["smoke_gate"]["deployment_id"] == "codex-release-20260621T010000"
            assert max_age_hours == 24
            assert now_utc == "2026-06-22T00:00:00Z"
            return {"status": "passed"}

        @staticmethod
        def fast_launch_env_lines(report, payload):
            assert report == {"status": "passed"}
            return [
                "IMAGE_AGENT_STRICT_REMOTE_ACCEPTANCE_STATUS=passed",
                "IMAGE_AGENT_STRICT_REMOTE_ACCEPTANCE_ID=codex-release-20260621T010000",
            ]

    def fake_run(cmd, **kwargs):
        calls.append(cmd)

        class Proc:
            returncode = 0
            stdout = "ok"
            stderr = ""

        return Proc()

    monkeypatch.setattr(script, "_load_strict_acceptance_verifier", lambda _repo_root: FakeVerifier)
    monkeypatch.setattr(script.subprocess, "run", fake_run)
    env_file = tmp_path / "deploy.env"

    plan = script.build_bootstrap_plan(
        repo_root=tmp_path,
        env_file=env_file,
        enable_elasticsearch_hybrid=False,
        prepare_workflow_images=False,
        strict_acceptance_json=acceptance_json,
        strict_acceptance_max_age_hours=24,
        strict_acceptance_now_utc="2026-06-22T00:00:00Z",
        config_only=True,
        embedding_model="",
        embedding_base_url="",
        apply_changes=False,
    )

    assert [step["id"] for step in plan["steps"]] == [
        "configure_image_agent_root",
        "configure_image_agent_release_root",
        "configure_strict_remote_acceptance_status",
        "configure_strict_remote_acceptance_id",
    ]
    steps = {step["id"]: step for step in plan["steps"]}
    assert steps["configure_strict_remote_acceptance_status"]["command"] == [
        "write_env",
        str(env_file),
        "IMAGE_AGENT_STRICT_REMOTE_ACCEPTANCE_STATUS",
        "passed",
    ]
    assert steps["configure_strict_remote_acceptance_id"]["command"] == [
        "write_env",
        str(env_file),
        "IMAGE_AGENT_STRICT_REMOTE_ACCEPTANCE_ID",
        "codex-release-20260621T010000",
    ]
    assert str(acceptance_json) in plan["strict_acceptance_json"]

    report = script.bootstrap_image_agent(
        repo_root=tmp_path,
        env_file=env_file,
        enable_elasticsearch_hybrid=False,
        prepare_workflow_images=False,
        strict_acceptance_json=acceptance_json,
        strict_acceptance_max_age_hours=24,
        strict_acceptance_now_utc="2026-06-22T00:00:00Z",
        config_only=True,
        embedding_model="",
        embedding_base_url="",
        apply_changes=True,
    )

    env_text = env_file.read_text(encoding="utf-8")
    assert report["status"] == "completed"
    assert "IMAGE_AGENT_STRICT_REMOTE_ACCEPTANCE_STATUS=passed" in env_text
    assert "IMAGE_AGENT_STRICT_REMOTE_ACCEPTANCE_ID=codex-release-20260621T010000" in env_text
    assert "sk-" not in json.dumps(plan, sort_keys=True)
    assert "sk-" not in json.dumps(report, sort_keys=True)
    assert not calls


def test_bootstrap_rejects_unverified_strict_acceptance_env(tmp_path, monkeypatch):
    script = _load_bootstrap()
    acceptance_json = tmp_path / "strict-acceptance.json"
    acceptance_json.write_text(json.dumps({"smoke_gate": {"deployment_id": "bad"}}), encoding="utf-8")

    class FakeVerifier:
        @staticmethod
        def verify_acceptance_payload(payload, *, max_age_hours=None, now_utc=None):
            raise SystemExit("strict acceptance failed")

    monkeypatch.setattr(script, "_load_strict_acceptance_verifier", lambda _repo_root: FakeVerifier)

    with pytest.raises(SystemExit) as exc:
        script.build_bootstrap_plan(
            repo_root=tmp_path,
            env_file=tmp_path / ".env",
            enable_elasticsearch_hybrid=False,
            prepare_workflow_images=False,
            strict_acceptance_json=acceptance_json,
            strict_acceptance_max_age_hours=24,
            embedding_model="",
            embedding_base_url="",
            apply_changes=False,
        )

    assert "strict acceptance failed" in str(exc.value)


def test_bootstrap_can_write_direct_rawchat_model_gateway_env(tmp_path):
    script = _load_bootstrap()
    env_file = tmp_path / "deploy.env"

    plan = script.build_bootstrap_plan(
        repo_root=tmp_path,
        env_file=env_file,
        enable_elasticsearch_hybrid=False,
        prepare_workflow_images=False,
        model_provider="rawchat",
        model_name="gpt-5.5",
        model_review_name="gpt-5.5",
        model_base_url="https://rawchat.cn/codex",
        model_wire_api="responses",
        model_trust_env_proxy=False,
        config_only=True,
        embedding_model="",
        embedding_base_url="",
        apply_changes=False,
    )

    steps = {step["id"]: step for step in plan["steps"]}
    assert steps["configure_model_provider"]["command"] == [
        "write_env",
        str(env_file),
        "IMAGE_AGENT_MODEL_PROVIDER",
        "rawchat",
    ]
    assert steps["configure_model_base_url"]["command"] == [
        "write_env",
        str(env_file),
        "IMAGE_AGENT_MODEL_BASE_URL",
        "https://rawchat.cn/codex",
    ]
    assert steps["configure_model_trust_env_proxy"]["command"] == [
        "write_env",
        str(env_file),
        "IMAGE_AGENT_MODEL_TRUST_ENV_PROXY",
        "0",
    ]
    assert "IMAGE_AGENT_MODEL_API_KEY" in "\n".join(plan["secret_handling"])
    assert "sk-" not in json.dumps(plan, sort_keys=True)

    report = script.bootstrap_image_agent(
        repo_root=tmp_path,
        env_file=env_file,
        enable_elasticsearch_hybrid=False,
        prepare_workflow_images=False,
        model_provider="rawchat",
        model_name="gpt-5.5",
        model_review_name="gpt-5.5",
        model_base_url="https://rawchat.cn/codex",
        model_wire_api="responses",
        model_trust_env_proxy=False,
        config_only=True,
        embedding_model="",
        embedding_base_url="",
        apply_changes=True,
    )

    env_text = env_file.read_text(encoding="utf-8")
    assert report["status"] == "completed"
    assert "IMAGE_AGENT_MODEL_PROVIDER=rawchat" in env_text
    assert "IMAGE_AGENT_MODEL_NAME=gpt-5.5" in env_text
    assert "IMAGE_AGENT_MODEL_REVIEW_NAME=gpt-5.5" in env_text
    assert "IMAGE_AGENT_MODEL_BASE_URL=https://rawchat.cn/codex" in env_text
    assert "IMAGE_AGENT_MODEL_WIRE_API=responses" in env_text
    assert "IMAGE_AGENT_MODEL_TRUST_ENV_PROXY=0" in env_text
    assert "IMAGE_AGENT_MODEL_API_KEY" not in env_text


def test_bootstrap_rejects_rawchat_model_gateway_proxy(tmp_path):
    script = _load_bootstrap()

    with pytest.raises(SystemExit, match="rawchat model gateway must use direct"):
        script.build_bootstrap_plan(
            repo_root=tmp_path,
            env_file=tmp_path / ".env",
            enable_elasticsearch_hybrid=False,
            prepare_workflow_images=False,
            model_provider="rawchat",
            model_name="gpt-5.5",
            model_base_url="https://rawchat.cn/codex",
            model_wire_api="responses",
            model_trust_env_proxy=True,
            config_only=True,
            embedding_model="",
            embedding_base_url="",
            apply_changes=False,
        )


@pytest.mark.parametrize(
    ("public_base_url", "cors_origins", "message"),
    [
        ("", "https://console.example.com", "production public base URL is required"),
        ("http://api.example.com", "https://console.example.com", "production public base URL must be a public HTTPS origin"),
        ("https://localhost:8000", "https://console.example.com", "production public base URL must be a public HTTPS origin"),
        ("https://10.2.32.14", "https://console.example.com", "production public base URL must be a public HTTPS origin"),
        ("https://api", "https://console.example.com", "production public base URL must be a public HTTPS origin"),
        ("https://api.example.com/v1", "https://console.example.com", "production public base URL must be a public HTTPS origin"),
        ("https://api.example.com", "", "production CORS origins are required"),
        ("https://api.example.com", "http://console.example.com", "production CORS origins must be HTTPS public origins"),
        ("https://api.example.com", "https://localhost:5173", "production CORS origins must be HTTPS public origins"),
        ("https://api.example.com", "https://10.2.32.14", "production CORS origins must be HTTPS public origins"),
        ("https://api.example.com", "https://console", "production CORS origins must be HTTPS public origins"),
        ("https://api.example.com", "*", "production CORS origins must be HTTPS public origins"),
    ],
)
def test_bootstrap_production_readiness_env_rejects_unsafe_origins(tmp_path, public_base_url, cors_origins, message):
    script = _load_bootstrap()

    with pytest.raises(SystemExit) as exc:
        script.build_bootstrap_plan(
            repo_root=tmp_path,
            env_file=tmp_path / ".env",
            enable_elasticsearch_hybrid=False,
            prepare_workflow_images=False,
            production=True,
            production_cors_origins=cors_origins,
            production_public_base_url=public_base_url,
            embedding_model="",
            embedding_base_url="",
            apply_changes=False,
        )

    assert message in str(exc.value)


def test_bootstrap_production_readiness_env_accepts_private_network_scope(tmp_path):
    script = _load_bootstrap()

    plan = script.build_bootstrap_plan(
        repo_root=tmp_path,
        env_file=tmp_path / ".env",
        enable_elasticsearch_hybrid=False,
        prepare_workflow_images=False,
        production=True,
        deployment_scope="private_network",
        production_cors_origins="http://127.0.0.1:5173",
        production_public_base_url="http://127.0.0.1:8000",
        embedding_model="",
        embedding_base_url="",
        apply_changes=False,
    )

    commands = [step["command"] for step in plan["steps"]]
    assert ["write_env", str((tmp_path / ".env").resolve()), "IMAGE_AGENT_DEPLOYMENT_SCOPE", "private_network"] in commands
    assert ["write_env", str((tmp_path / ".env").resolve()), "IMAGE_AGENT_CORS_ORIGINS", "http://127.0.0.1:5173"] in commands
    assert ["write_env", str((tmp_path / ".env").resolve()), "IMAGE_AGENT_PUBLIC_BASE_URL", "http://127.0.0.1:8000"] in commands


@pytest.mark.parametrize(
    ("public_base_url", "cors_origins", "message"),
    [
        ("", "http://127.0.0.1:5173", "production public base URL is required"),
        ("http://0.0.0.0:8000", "http://127.0.0.1:5173", "production private network API base URL must be an HTTP(S) origin"),
        ("http://127.0.0.1:8000/v1", "http://127.0.0.1:5173", "production private network API base URL must be an HTTP(S) origin"),
        ("http://127.0.0.1:8000", "", "production CORS origins are required"),
        ("http://127.0.0.1:8000", "*", "production private network CORS origins must be HTTP(S) origins"),
        ("http://127.0.0.1:8000", "http://0.0.0.0:5173", "production private network CORS origins must be HTTP(S) origins"),
        ("http://127.0.0.1:8000", "http://127.0.0.1:5173/app", "production private network CORS origins must be HTTP(S) origins"),
    ],
)
def test_bootstrap_private_network_readiness_env_rejects_unsafe_origins(
    tmp_path,
    public_base_url,
    cors_origins,
    message,
):
    script = _load_bootstrap()

    with pytest.raises(SystemExit) as exc:
        script.build_bootstrap_plan(
            repo_root=tmp_path,
            env_file=tmp_path / ".env",
            enable_elasticsearch_hybrid=False,
            prepare_workflow_images=False,
            production=True,
            deployment_scope="private_network",
            production_cors_origins=cors_origins,
            production_public_base_url=public_base_url,
            embedding_model="",
            embedding_base_url="",
            apply_changes=False,
        )

    assert message in str(exc.value)


def test_bootstrap_cli_accepts_image_agent_root_for_release_overlay(tmp_path):
    script = _load_bootstrap()
    release_root = tmp_path / "release-overlay"
    live_root = tmp_path / "live-root"
    env_file = tmp_path / "deploy.env"
    out = tmp_path / "plan.json"
    release_root.mkdir()
    live_root.mkdir()

    script.main(
        [
            "--repo-root",
            str(release_root),
            "--image-agent-root",
            str(live_root),
            "--env-file",
            str(env_file),
            "--skip-elasticsearch-hybrid",
            "--skip-workflow-images",
            "--output-json",
            str(out),
        ]
    )

    plan = json.loads(out.read_text(encoding="utf-8"))
    first_step = plan["steps"][0]
    assert plan["repo_root"] == str(release_root.resolve())
    assert plan["image_agent_root"] == str(live_root.resolve())
    assert first_step["id"] == "configure_image_agent_root"
    assert first_step["command"] == [
        "write_env",
        str(env_file.resolve()),
        "IMAGE_AGENT_ROOT",
        str(live_root.resolve()),
    ]
    assert "sk-" not in json.dumps(plan)


def test_bootstrap_readme_documents_live_root_for_release_overlay():
    readme = README_PATH.read_text(encoding="utf-8", errors="ignore")

    assert "--image-agent-root" in readme
    assert "IMAGE_AGENT_ROOT" in readme
    assert "release overlay" in readme


def test_bootstrap_readme_documents_elasticsearch_trial_license_setup():
    readme = README_PATH.read_text(encoding="utf-8", errors="ignore")

    assert "_license/start_trial?acknowledge=true" in readme
    assert "--skip-elasticsearch-trial-license" in readme
    assert "--skip-start-trial-license" in readme
    assert "127.0.0.1:9200" in readme


def test_bootstrap_readme_documents_production_readiness_env():
    readme = README_PATH.read_text(encoding="utf-8", errors="ignore")

    assert "--production" in readme
    assert "--production-cors-origins" in readme
    assert "--production-public-base-url" in readme
    assert "--docker-command" in readme
    assert "--verify-docker-command" in readme
    assert "--model-provider rawchat" in readme
    assert "--model-base-url https://rawchat.cn/codex" in readme
    assert "IMAGE_AGENT_MODEL_TRUST_ENV_PROXY=0" in readme
    assert "IMAGE_AGENT_DOCKER_COMMAND" in readme
    assert "sudo -n docker" in readme
    assert "sudo -S" in readme
    assert "--strict-acceptance-json" in readme
    assert "IMAGE_AGENT_ENV=production" in readme
    assert "IMAGE_AGENT_PUBLIC_BASE_URL" in readme
    assert "IMAGE_AGENT_STRICT_REMOTE_ACCEPTANCE_STATUS" in readme
    assert "IMAGE_AGENT_STRICT_REMOTE_ACCEPTANCE_ID" in readme


def test_bootstrap_plan_requires_embedding_config_when_elasticsearch_enabled(tmp_path):
    script = _load_bootstrap()

    with pytest.raises(SystemExit) as exc:
        script.build_bootstrap_plan(
            repo_root=tmp_path,
            env_file=tmp_path / ".env",
            enable_elasticsearch_hybrid=True,
            prepare_workflow_images=True,
            embedding_model="",
            embedding_base_url="",
            apply_changes=False,
        )

    assert "embedding model and embedding base URL are required" in str(exc.value)


def test_bootstrap_plan_can_install_local_embedding_service_before_elasticsearch(tmp_path):
    script = _load_bootstrap()

    plan = script.build_bootstrap_plan(
        repo_root=tmp_path,
        env_file=tmp_path / ".env",
        enable_elasticsearch_hybrid=True,
        prepare_workflow_images=False,
        setup_local_embedding_service=True,
        embedding_model="",
        embedding_base_url="",
        apply_changes=False,
    )

    step_ids = [step["id"] for step in plan["steps"]]
    assert "setup_local_embedding_service" in step_ids
    assert step_ids.index("setup_local_embedding_service") < step_ids.index("setup_elasticsearch_hybrid_rag")
    serialized = json.dumps(plan, sort_keys=True)
    assert "apps/api/scripts/setup_local_embedding_service.py" in serialized
    assert "ghcr.io/huggingface/text-embeddings-inference:cpu-1.9" in serialized
    es_step = next(step for step in plan["steps"] if step["id"] == "setup_elasticsearch_hybrid_rag")
    embedding_step = next(step for step in plan["steps"] if step["id"] == "setup_local_embedding_service")
    assert "image-agent-minilm-l6-v2" in es_step["command"]
    assert "--network-mode" in embedding_step["command"]
    assert "host" in embedding_step["command"]
    assert "sentence-transformers/all-MiniLM-L6-v2" in embedding_step["command"]
    assert "http://127.0.0.1:18081/v1" in es_step["command"]


def test_bootstrap_plan_can_skip_elasticsearch_trial_license_for_managed_cluster(tmp_path):
    script = _load_bootstrap()

    plan = script.build_bootstrap_plan(
        repo_root=tmp_path,
        env_file=tmp_path / ".env",
        enable_elasticsearch_hybrid=True,
        prepare_workflow_images=False,
        embedding_model="text-embedding-3-small",
        embedding_base_url="https://embedding.example/v1",
        skip_elasticsearch_trial_license=True,
        apply_changes=False,
    )

    es_step = next(step for step in plan["steps"] if step["id"] == "setup_elasticsearch_hybrid_rag")
    assert "--skip-start-trial-license" in es_step["command"]
    assert "sk-" not in json.dumps(plan, sort_keys=True)


def test_bootstrap_cli_accepts_skip_elasticsearch_trial_license(tmp_path):
    script = _load_bootstrap()
    out = tmp_path / "plan.json"

    script.main(
        [
            "--repo-root",
            str(tmp_path),
            "--skip-workflow-images",
            "--embedding-model",
            "text-embedding-3-small",
            "--embedding-base-url",
            "https://embedding.example/v1",
            "--skip-elasticsearch-trial-license",
            "--output-json",
            str(out),
        ]
    )

    plan = json.loads(out.read_text(encoding="utf-8"))
    es_step = next(step for step in plan["steps"] if step["id"] == "setup_elasticsearch_hybrid_rag")
    assert "--skip-start-trial-license" in es_step["command"]


def test_bootstrap_cli_accepts_direct_rawchat_model_gateway_config(tmp_path):
    script = _load_bootstrap()
    out = tmp_path / "plan.json"

    script.main(
        [
            "--repo-root",
            str(tmp_path),
            "--skip-elasticsearch-hybrid",
            "--skip-workflow-images",
            "--config-only",
            "--model-provider",
            "rawchat",
            "--model-name",
            "gpt-5.5",
            "--model-review-name",
            "gpt-5.5",
            "--model-base-url",
            "https://rawchat.cn/codex",
            "--model-wire-api",
            "responses",
            "--output-json",
            str(out),
        ]
    )

    plan = json.loads(out.read_text(encoding="utf-8"))
    steps = {step["id"]: step for step in plan["steps"]}
    assert steps["configure_model_trust_env_proxy"]["command"] == [
        "write_env",
        str(tmp_path / ".env"),
        "IMAGE_AGENT_MODEL_TRUST_ENV_PROXY",
        "0",
    ]


def test_bootstrap_plan_can_prewarm_templateflow_cache_for_bold_workflows(tmp_path):
    script = _load_bootstrap()

    plan = script.build_bootstrap_plan(
        repo_root=tmp_path,
        env_file=tmp_path / ".env",
        enable_elasticsearch_hybrid=False,
        prepare_workflow_images=True,
        prewarm_templateflow=True,
        embedding_model="",
        embedding_base_url="",
        apply_changes=False,
    )

    step_ids = [step["id"] for step in plan["steps"]]
    assert "prepare_fixed_workflow_images" in step_ids
    assert "prewarm_templateflow_cache" in step_ids
    assert step_ids.index("prepare_fixed_workflow_images") < step_ids.index("prewarm_templateflow_cache")
    step = next(item for item in plan["steps"] if item["id"] == "prewarm_templateflow_cache")
    serialized = json.dumps(step, sort_keys=True)
    assert "scripts/prewarm_templateflow_cache.py" in serialized
    assert "nipreps/fmriprep:25.2.5" in serialized
    assert "MNI152NLin2009cAsym" in serialized
    assert "MNI152NLin6Asym" in serialized
    assert "OASIS30ANTs" in serialized
    assert "--write-env" in step["command"]
    assert str(tmp_path / ".env") in step["command"]


def test_bootstrap_plan_can_forward_templateflow_runtime_proxy_without_proxy_values(tmp_path):
    script = _load_bootstrap()

    plan = script.build_bootstrap_plan(
        repo_root=tmp_path,
        env_file=tmp_path / ".env",
        enable_elasticsearch_hybrid=False,
        prepare_workflow_images=True,
        prewarm_templateflow=True,
        forward_templateflow_proxy_env=True,
        templateflow_network_mode="host",
        embedding_model="",
        embedding_base_url="",
        apply_changes=False,
    )

    step = next(item for item in plan["steps"] if item["id"] == "prewarm_templateflow_cache")
    serialized = json.dumps(plan, sort_keys=True)
    assert "--forward-proxy-env" in step["command"]
    assert "--network-mode" in step["command"]
    assert "host" in step["command"]
    assert "proxy-subscription-host-marker" not in serialized
    assert "proxy-token-query-marker" not in serialized


def test_bootstrap_plan_can_use_direct_curl_templateflow_prewarm(tmp_path):
    script = _load_bootstrap()

    plan = script.build_bootstrap_plan(
        repo_root=tmp_path,
        env_file=tmp_path / ".env",
        enable_elasticsearch_hybrid=False,
        prepare_workflow_images=True,
        prewarm_templateflow=True,
        templateflow_download_method="curl",
        direct_templateflow_download=True,
        templateflow_attempts=3,
        templateflow_request_timeout=240,
        embedding_model="",
        embedding_base_url="",
        apply_changes=False,
    )

    step = next(item for item in plan["steps"] if item["id"] == "prewarm_templateflow_cache")
    serialized = json.dumps(plan, sort_keys=True)
    assert "--download-method" in step["command"]
    assert "curl" in step["command"]
    assert "--direct-download" in step["command"]
    assert "--attempts" in step["command"]
    assert "3" in step["command"]
    assert "--request-timeout" in step["command"]
    assert "240" in step["command"]
    assert "yyf@10.2.32.14" not in serialized
    assert "10.2.32.14" not in serialized


def test_bootstrap_apply_runs_templateflow_prewarm_without_secret_in_report(tmp_path, monkeypatch):
    script = _load_bootstrap()
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)

        class Proc:
            returncode = 0
            stdout = "ok"
            stderr = ""

        return Proc()

    monkeypatch.setattr(script.subprocess, "run", fake_run)

    report = script.bootstrap_image_agent(
        repo_root=tmp_path,
        env_file=tmp_path / ".env",
        enable_elasticsearch_hybrid=False,
        prepare_workflow_images=True,
        prewarm_templateflow=True,
        embedding_model="",
        embedding_base_url="",
        apply_changes=True,
    )

    assert report["status"] == "completed"
    assert any(any("prewarm_templateflow_cache.py" in part for part in cmd) and "--apply" in cmd for cmd in calls)
    assert "sk-" not in json.dumps(report, sort_keys=True)
