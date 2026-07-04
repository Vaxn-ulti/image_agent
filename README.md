# Image Agent

Image Agent is a ready-to-use first release for guided neuroimaging workflow
execution. It provides a FastAPI control plane, React console, LangGraph-based
agent orchestration, upload inspection, workflow confirmation, task observation,
and result review for medical imaging research workflows.

The system is designed for local or intranet deployment where the application
can inspect the host Docker runtime, prepare required workflow images, run fixed
pipelines, and expose downloadable result bundles. It is research software and
does not provide clinical diagnosis.

## What It Does

- Upload and organize medical imaging inputs, including DICOM archives, NIfTI
  files, and sidecar files.
- Explain detected files and eligible workflows before asking for approval.
- Launch fixed workflows only through registry, preflight, human confirmation,
  fingerprinting, task creation, and the pipeline runner.
- Keep unsupported or unknown workflow requests in the incubation/proposal path
  instead of creating production tasks.
- Observe tasks, summarize results, show reports and QC artifacts, and export a
  complete result bundle.
- Use Elasticsearch hybrid search for the RAG layer when configured through the
  Git-managed setup scripts.

## Repository Layout

- `apps/api`: FastAPI backend, LangGraph agent runtime, workflow registry,
  upload handling, task services, artifact manifests, and result APIs.
- `apps/console`: React/Vite web console for projects, uploads, agent workflow
  approval, tasks, reports, and results.
- `apps/desktop`: Desktop-oriented React shell kept for local packaging work.
- `scripts`: Git-managed bootstrap, hygiene, Docker access, and frontend
  contract utilities.
- `docs`: Public architecture, workflow, RAG, deployment, and skill references.

## Quick Start

Install backend dependencies:

```bash
cd apps/api
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Install and run the console:

```bash
cd apps/console
npm install
npm run dev -- --host 0.0.0.0 --port 5180
```

By default the development console can talk to an API on the same host. For a
different API origin, configure the console environment or browser local storage
according to the deployment target.

## Git-Based Installation

After cloning the repository on a deployment machine, use the bootstrap script
as the install and configuration entrypoint. Start with a dry run:

```bash
python3 scripts/bootstrap_image_agent.py
```

Review the emitted plan, then add `--apply` when ready. The bootstrap path can:

- install API and frontend dependencies;
- probe the local Docker runtime;
- prepare pinned workflow Docker images when enabled;
- set non-secret deployment values in the selected env file;
- configure a local embedding service;
- configure Elasticsearch hybrid RAG;
- keep secrets out of Git-managed files.

The installer supports a release overlay layout where the checked-out release
and the live Image Agent working root are separate. Use `--image-agent-root` to
write `IMAGE_AGENT_ROOT` into the selected env file so runtime data, indexes,
and generated outputs live outside the immutable release overlay.

For production-like intranet deployment, make the deployment origins explicit:

```bash
python3 scripts/bootstrap_image_agent.py \
  --production \
  --production-cors-origins https://console.example.org \
  --production-public-base-url https://api.example.org \
  --docker-command "sudo -n docker" \
  --verify-docker-command
```

The production setup writes non-secret readiness values such as
`IMAGE_AGENT_ENV=production`, `IMAGE_AGENT_PUBLIC_BASE_URL`,
`IMAGE_AGENT_STRICT_REMOTE_ACCEPTANCE_STATUS`, and
`IMAGE_AGENT_STRICT_REMOTE_ACCEPTANCE_ID` when the matching operator-approved
inputs are supplied, including `--strict-acceptance-json`. If a deployment uses
a narrow sudo Docker wrapper, prefer `sudo -n docker`; interactive `sudo -S`
password handling should stay outside Git-managed scripts and logs. The
effective runtime command is exposed to the app through
`IMAGE_AGENT_DOCKER_COMMAND`.

For a local Elasticsearch hybrid RAG setup:

```bash
python3 scripts/bootstrap_image_agent.py \
  --setup-local-embedding-service
```

The Elasticsearch setup uses the repository scripts and a pinned Elasticsearch
image. If the official Elastic trial license is appropriate for the deployment,
the setup path can call Elastic's trial endpoint:
`POST /_license/start_trial?acknowledge=true`.
The local acceptance/development endpoint is normally bound to
`127.0.0.1:9200`. Use `--skip-elasticsearch-trial-license` or
`--skip-start-trial-license` when the operator does not want the installer to
request the official Elastic trial license.

## Model Gateway Configuration

Image Agent expects an OpenAI-compatible model endpoint for the agent layer.
Configure the provider through environment variables or the deployment secret
manager, for example:

```bash
IMAGE_AGENT_MODEL_PROVIDER=openai
IMAGE_AGENT_MODEL_BASE_URL=https://api.openai.com/v1
IMAGE_AGENT_MODEL_NAME=<model-name>
IMAGE_AGENT_MODEL_API_KEY=<secret-from-env-or-secret-manager>
IMAGE_AGENT_MODEL_WIRE_API=responses
```

For a rawchat-compatible deployment profile, pass non-secret routing settings
such as `--model-provider rawchat` and
`--model-base-url https://rawchat.cn/codex`, keep the API key in the operator's
secret environment, and set `IMAGE_AGENT_MODEL_TRUST_ENV_PROXY=0` when model
traffic should ignore host proxy variables.

Do not commit API keys, proxy URLs, generated `.env` files, patient data,
runtime logs, or acceptance transcripts.

## Docker Runtime

The fixed workflow images are pinned in the backend configuration and can be
prepared by the Git-managed bootstrap/runtime probe path. If the API service
user cannot access Docker directly, configure host policy such as group
membership or a narrow `sudo -n docker` rule outside the repository, then point
Image Agent at that command through non-secret environment configuration.

## Safety Boundaries

- Image Agent is intended for research workflow automation and QC review, not
  clinical diagnosis.
- Fixed workflows must use the registry and confirmation path before production
  tasks are created.
- Unknown workflow ideas are recorded as proposals only.
- Observe/repair behavior is read-only by default and should not automatically
  rerun production tasks.
- Real imaging data, credentials, local server addresses, generated archives,
  and logs should remain outside Git.

## License

This project is released as open source under the MIT License.
