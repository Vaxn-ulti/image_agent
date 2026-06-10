import re
from pathlib import Path


def test_backend_requirements_include_neuroimaging_and_agent_dependencies():
    requirements = (Path(__file__).resolve().parents[1] / "requirements.txt").read_text(encoding="utf-8")

    for package in ("numpy", "nibabel", "scipy", "nilearn", "langgraph", "llama-index", "openai", "httpx", "socksio"):
        assert package in requirements


def test_runtime_scripts_do_not_pipe_literal_passwords_to_sudo():
    repo_root = Path(__file__).resolve().parents[3]
    script_roots = [repo_root / "apps" / "api" / "scripts", repo_root / "tools"]
    unsafe_patterns = [
        re.compile(r"echo\s+\S+\s*\|\s*sudo\s+-S"),
        re.compile(r"--password(=|\s+)\S+"),
    ]
    offenders = []

    for root in script_roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.suffix.lower() not in {".sh", ".py", ".bash"} or not path.is_file():
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for pattern in unsafe_patterns:
                if pattern.search(text):
                    offenders.append(path.relative_to(repo_root).as_posix())
                    break

    assert offenders == []
