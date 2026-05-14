# Brain Image Agent 工作总结

写日志时间：2026-05-13 13:32:50 CST  
项目目录：`/home/yyf/project/image_agent`  
当前阶段：第一轮可运行 MVP 已完成，第二阶段和第三阶段的调用框架已接入，正在向真实影像处理闭环推进。

## 1. 项目目标

本项目目标是实现一个脑影像 Agent 软件。用户通过 GUI 页面上传脑部影像文件后，系统自动识别影像类型并提供对应处理任务，同时支持和用户进行基础对话，查询影像、任务、日志和输出结果。

目标输入类型包括：

- DICOM 影像，当前约定为上传 `.zip` 压缩包。
- NIfTI 影像，支持 `.nii` 和 `.nii.gz`。
- DWI 数据集，要求上传 DWI NIfTI、`.bval`、`.bvec` 三件套。

目标处理能力包括：

- T1：调用 DeepPrep 做 T1 结构像处理，后续要导出分割结果和可视化图表。
- DWI：调用 QSIPrep 和 QSIRecon，后续要完成 DTI 指标重建、纤维重建、连接矩阵或纤维文件导出。
- BOLD：调用 fMRIPrep/DeepPrep 类预处理，后续要完成 ALFF、fALFF 等指标真实计算和可视化。
- DICOM：调用 dcm2niix 转换为 NIfTI，并在后续自动注册转换后的新 series。
- Chat：能够在 GUI 内正常对话，解释当前项目影像、任务状态、日志和工作流。

## 2. 当前架构

当前采用“桌面/网页 GUI + 远程计算后端”的方案。

主要目录：

- `apps/api`：FastAPI 后端。
- `apps/desktop`：Vite + React 前端。
- `data`：运行数据，包含 SQLite 数据库、上传文件、任务输出等。
- `docs`：阶段性架构、API、工作流和交接文档。
- `logs`：API 和前端开发服务器日志。

当前后端技术：

- FastAPI 提供 HTTP API。
- SQLite 保存用户、项目、文件、影像 series、任务、输出、聊天记录。
- 后台线程启动任务 runner。
- Docker 容器用于 DeepPrep、QSIPrep、QSIRecon、fMRIPrep 等长任务。
- 本机命令 `dcm2niix` 用于 DICOM 转换。

当前前端技术：

- React 单页应用。
- 左侧项目列表和创建项目入口。
- 主工作区包含上传区、影像 series 列表、任务列表、日志/输出查看、聊天区。
- 当前仍是开发服务器形式运行，不是最终桌面打包版本。

## 3. 已实现功能

### 3.1 项目和登录

已实现基础登录接口：

- `POST /auth/login`

当前登录是 MVP token，不做真实权限校验。首次输入用户名会自动创建用户。

已实现项目接口：

- `GET /projects`
- `POST /projects`

创建项目后会在 `data/projects/{project_id}` 下建立：

- `raw`
- `logs`
- `derivatives`

### 3.2 文件上传和识别

已实现单文件 NIfTI 上传：

- `POST /projects/{project_id}/upload`

后端会调用 `app.imaging.detect.detect_series` 识别：

- T1
- BOLD
- DWI
- unknown

识别依据目前主要包括：

- 文件后缀是否为 `.nii` 或 `.nii.gz`
- NIfTI header 中的维度和 shape
- 文件名 token，例如 `t1`、`t1w`、`mprage`、`bold`、`fmri`、`func`、`dwi`
- DWI sidecar 是否存在
- 4D 且 timepoints 较多时倾向识别为 BOLD
- 3D 时倾向识别为 T1

已实现 DWI 三件套上传：

- `POST /projects/{project_id}/upload-dwi`

上传字段：

- `nifti`
- `bval`
- `bvec`

后端固定创建一个 DWI series，并把 `bval_file_id`、`bvec_file_id` 写入 series metadata。

已实现 DICOM zip 上传：

- `POST /projects/{project_id}/upload-dicom`

行为：

- 保存原始 zip 到项目 raw 目录。
- 解压到 `data/projects/{project_id}/raw/dicom_{file_id}`。
- 有 zip-slip 路径安全检查。
- 创建一个 `modality=DICOM`、`format=DICOM_ZIP` 的 imaging_series。
- metadata 中记录：
  - `archive_file_id`
  - `dicom_dir`
  - `dicom_file_count`

### 3.3 Series、任务和输出查询

已实现：

- `GET /projects/{project_id}/series`
- `GET /projects/{project_id}/tasks`
- `GET /series/{series_id}`
- `POST /series/{series_id}/run`
- `GET /tasks/{task_id}`
- `GET /tasks/{task_id}/logs`
- `GET /tasks/{task_id}/outputs`

任务创建后写入 `tasks` 表，并启动后台线程执行。

任务状态字段包括：

- `queued`
- `running`
- `completed`
- `failed`

任务进度字段为 0-100，目前是粗粒度进度。

输出写入 `outputs` 表，当前扫描类型包括：

- `html_report`
- `nifti`
- `tsv`
- `json`
- `tractography`
- `connectome`
- `command`
- `csv`

## 4. 当前工作流清单

后端 `WORKFLOWS` 当前包含：

### T1

- `t1_deepprep_validate`
- `t1_deepprep`
- `t1_deepprep_mock`

说明：

- validate 模式只检查 Docker image 和生成命令，不启动长任务。
- real 模式会尝试启动 DeepPrep Docker 容器。
- mock 模式用于早期测试，可以快速完成并产生模拟输出。

### DWI

- `dwi_qsiprep_validate`
- `dwi_qsiprep`
- `dwi_qsirecon_validate`
- `dwi_qsirecon`
- `dwi_qsi_full_validate`
- `dwi_qsi_full`

说明：

- QSIPrep 要求 series 是 DWI，且 metadata 中有 bval/bvec。
- QSIRecon 要求提供 `qsiprep_task_id`。
- QSIRecon real 模式要求引用的 QSIPrep 或 full task 已完成。
- QSIRecon validate 模式允许引用 validate 任务，用于快速验证命令链路。

### DICOM

- `dicom_convert_validate`
- `dicom_convert`

说明：

- validate 模式生成 `dcm2niix` 命令。
- real 模式调用本机 `dcm2niix -z y -o output/nifti {dicom_dir}`。
- 当前 real 模式会扫描输出并登记 NIfTI 等结果。
- 目前还没有把转换后的 NIfTI 自动注册为新的 imaging_series，这是下一轮重点。

### BOLD

- `bold_fmriprep_validate`
- `bold_fmriprep`
- `bold_alff_validate`
- `bold_alff`
- `bold_falff_validate`
- `bold_falff`

说明：

- BOLD fMRIPrep 使用 `nipreps/fmriprep:latest`。
- ALFF/fALFF 当前是可调用占位 runner，不是真正指标计算。
- ALFF/fALFF validate 和 real 都加入了前置任务校验：
  - validate 需要项目中已有 `bold_fmriprep_validate`、`bold_fmriprep`、`t1_deepprep_validate` 或 `t1_deepprep`。
  - real 需要项目中已有 completed 的 `bold_fmriprep` 或 `t1_deepprep`。
- 前端也已同步禁用不满足前置条件的按钮。

## 5. 当前容器和外部工具调用

当前工作流 runner 文件：

- `apps/api/app/workflows/pipeline.py`

已配置 Docker image：

- T1 DeepPrep：`pbfslab/deepprep:25.1.0`
- DWI QSIPrep：`pennlinc/qsiprep:latest`
- DWI QSIRecon：`pennlinc/qsirecon:latest`
- BOLD fMRIPrep：`nipreps/fmriprep:latest`

已配置本机工具：

- DICOM 转换：`dcm2niix`

FreeSurfer license 路径：

- `/home/yyf/codex/license.txt`

Docker 工作流启动方式：

- 代码通过 `sudo -S docker ...` 启动。
- sudo 密码不写入代码。
- API 进程运行时需要通过环境变量 `IMAGE_AGENT_SUDO_PASSWORD` 注入。

当前 validate 模式的语义：

- 对 Docker 工作流：检查 Docker image 是否存在，并把将要执行的命令写入 outputs。
- 对 DICOM 转换：写入本机 `dcm2niix` 命令。
- 对 ALFF/fALFF：写入 Python 指标命令，目前是占位 runner。

重要边界：

- validate 通过不代表真实医学处理已经跑完，只代表调度链路、任务状态、命令生成和镜像检查链路可用。
- real 模式会启动长时间容器任务，可能运行数小时，需要真实数据和资源计划。

## 6. 前端当前能力

前端文件：

- `apps/desktop/src/main.jsx`
- `apps/desktop/src/lib/api.js`
- `apps/desktop/src/styles.css`

当前 GUI 能力：

- 登录。
- 创建项目。
- 选择项目。
- 上传 T1/BOLD NIfTI。
- 上传 DWI 三件套。
- 上传 DICOM zip。
- 查看 series。
- 根据 series modality 展示不同 workflow 按钮。
- 创建任务。
- 自动轮询任务状态。
- 查看任务日志。
- 查看任务 outputs。
- 基础聊天。

前端按钮策略：

- T1 series 展示 DeepPrep validate、real、mock。
- DWI series 展示 QSIPrep、QSIRecon、full pipeline。
- DICOM series 展示 convert validate 和 convert。
- BOLD series 展示 fMRIPrep、ALFF、fALFF。
- QSIRecon 按钮根据是否已有 QSIPrep/full 任务决定是否禁用。
- ALFF/fALFF 按钮根据是否已有 BOLD/T1 预处理任务决定是否禁用。

API base 当前逻辑：

- `apps/desktop/src/lib/api.js` 中默认按当前页面 host 自动推断 API：
  - 如果前端打开在 `http://127.0.0.1:5173`，API 默认是 `http://127.0.0.1:8000`。
  - 用户也可以通过 localStorage 的 `apiBase` 覆盖。

## 7. 当前测试和验收情况

### 7.1 已跑过的自动测试

API 测试：

```bash
cd /home/yyf/project/image_agent/apps/api
. .venv/bin/activate
pytest -q
```

最近结果：

- `2 passed`
- 有 FastAPI `on_event` deprecation warning，不影响当前功能。

前端构建：

```bash
cd /home/yyf/project/image_agent/apps/desktop
npm run build
```

最近结果：

- Vite build 成功。

### 7.2 已跑过的烟测

已使用合成 NIfTI/DWI/DICOM 数据做过 validate 烟测。

第二阶段 smoke：

- `t1_deepprep_validate` completed
- `dwi_qsiprep_validate` completed
- `dwi_qsi_full_validate` completed
- `dwi_qsirecon_validate` completed

第三阶段 smoke：

- `bold_fmriprep_validate` completed
- `bold_alff_validate` completed
- `bold_falff_validate` completed
- `dicom_convert_validate` completed

Review/Test Agent 发现并修复的问题：

- 问题：`bold_alff*` / `bold_falff*` 原本缺少前置预处理任务校验，可以在没有 fMRIPrep/DeepPrep 任务的情况下运行。
- 修复：
  - 后端 `validate_run_request` 加了前置校验。
  - API 测试新增 `test_bold_alff_validate_requires_preprocessing_task`。
  - 前端同步禁用不满足前置条件的 ALFF/fALFF 按钮。

### 7.3 尚未完成的真实验收

尚未完成真实长任务跑完验收：

- DeepPrep 真实 T1 全流程。
- QSIPrep 真实 DWI 全流程。
- QSIRecon 真实重建全流程。
- fMRIPrep 真实 BOLD 全流程。
- dcm2niix 对真实 DICOM 批次转换并自动注册 series。
- ALFF/fALFF 真实指标计算。
- 分割结果、纤维重建、图表导出和可视化。

因此当前版本应表述为：

> GUI、API、任务系统、影像识别、workflow 调度和 validate 调用链路已经跑通；真实医学处理产物还需要继续做长任务验收和结果解析。

## 8. 当前运行方式

API 启动示例：

```bash
cd /home/yyf/project/image_agent/apps/api
IMAGE_AGENT_SUDO_PASSWORD=<runtime-only> .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
```

前端启动示例：

```bash
cd /home/yyf/project/image_agent/apps/desktop
npm run dev -- --host 0.0.0.0 --port 5173
```

如果远程端口不能从本机浏览器直连，可使用 SSH 隧道：

```bash
ssh -N \
  -L 127.0.0.1:5173:127.0.0.1:5173 \
  -L 127.0.0.1:8000:127.0.0.1:8000 \
  my-remote
```

然后打开：

- 前端：`http://127.0.0.1:5173`
- 后端健康检查：`http://127.0.0.1:8000/health`

## 9. 数据库现状

当前 SQLite schema 包含：

- `users`
- `projects`
- `files`
- `imaging_series`
- `tasks`
- `outputs`
- `chat_messages`

重要字段：

- `files.storage_path` 保存上传文件路径。
- `imaging_series.metadata_json` 保存 NIfTI shape、DWI sidecar、DICOM 解压目录等信息。
- `tasks.workflow_type` 保存工作流类型。
- `tasks.qsiprep_task_id` 用于 QSIRecon 引用上游 QSIPrep 任务。
- `outputs.metadata_json` 用于保存 validate 命令、image 检查结果等。

数据库迁移：

- `apps/api/app/db/database.py` 当前在 `init_db()` 中尝试 `ALTER TABLE tasks ADD COLUMN qsiprep_task_id INTEGER`，失败则忽略。
- 当前迁移机制仍很简陋，后续应引入可追踪 migrations。

## 10. 已知风险和技术债

### 10.1 validate 与 real 的差异

validate 模式只证明命令构造和任务调度可用，不证明容器长任务能够成功完成。

real 模式还需要针对真实样本逐个验证：

- 输入 BIDS 是否被目标工具接受。
- 输出目录结构是否符合预期。
- 是否能完整注册 outputs。
- 长任务失败时日志是否足够可诊断。

### 10.2 BIDS 构建仍是最小实现

当前 `_build_bids` 只构造最小 BIDS：

- T1：`sub-01/anat/sub-01_T1w.nii.gz`
- DWI：`sub-01/dwi/sub-01_dwi.nii.gz`、`.bval`、`.bvec`
- BOLD：`sub-01/func/sub-01_task-rest_bold.nii.gz`

缺少：

- JSON sidecar。
- 多 subject 支持。
- session 支持。
- task/run/acq 解析。
- DICOM metadata 到 BIDS metadata 的转写。
- BIDS validator 通过性验证。

### 10.3 DICOM 转换未闭环

DICOM real 转换目前可以调用 dcm2niix 并扫描输出，但还没有：

- 把转换后的 NIfTI 自动登记成新的 file 和 imaging_series。
- 根据转换结果自动识别 T1/DWI/BOLD。
- 自动关联 DWI sidecar。
- 对转换失败提供更细的错误提示。

### 10.4 ALFF/fALFF 是占位实现

当前 `apps/api/app/workflows/bold_metrics.py` 和 `_write_bold_metric` 只写出占位 CSV/JSON。

后续需要替换为真实指标计算：

- 读取预处理后的 BOLD。
- 做频段滤波和功率谱计算。
- 输出 ALFF/fALFF NIfTI map。
- 输出 QC 图表和 summary。
- 明确依赖库，例如 nilearn、nibabel、numpy、scipy。

### 10.5 前端仍是 MVP

当前前端可用但仍粗糙：

- 没有任务详情页。
- 没有文件预览。
- 没有图表可视化。
- 没有输出下载按钮。
- 没有任务取消/重试。
- 没有长任务资源配置。
- 没有用户级权限。
- 没有桌面 App 打包。

### 10.6 任务系统仍是后台线程

当前任务在 FastAPI 进程内用 `Thread` 启动。

风险：

- API 进程重启会丢失运行中的线程。
- 长任务状态无法可靠恢复。
- 没有并发队列和资源调度。
- 没有任务取消。

后续建议：

- 引入持久化 worker。
- 使用 Celery/RQ/Arq/自定义 supervisor。
- 或至少实现独立 runner 进程和 heartbeat。

## 11. 下一轮建议任务

建议下一轮按优先级推进：

### 11.1 DICOM 转换闭环

目标：

- 用户上传 DICOM zip。
- 运行 `dicom_convert`。
- 系统自动把 dcm2niix 输出的 NIfTI 登记成新 file。
- 自动识别成 T1/DWI/BOLD。
- GUI 里出现新的 series，并可继续点 DeepPrep/QSIPrep/fMRIPrep。

验收：

- 使用合成或真实 DICOM zip。
- `dicom_convert` completed。
- 生成新的 imaging_series。
- 新 series 能继续触发相应 validate workflow。

### 11.2 真实 ALFF/fALFF

目标：

- 替换占位 CSV/JSON。
- 输出 ALFF/fALFF NIfTI map。
- 输出 summary CSV。
- 输出基础 QC PNG 或 HTML。

建议依赖：

- `nibabel`
- `nilearn`
- `numpy`
- `scipy`
- `matplotlib`

验收：

- 使用合成 4D BOLD 数据跑通。
- 输出 `.nii.gz`、`.csv`、`.png` 或 `.html`。
- 前端 outputs 可见。

### 11.3 输出下载和可视化

目标：

- 后端增加静态文件或下载接口。
- 前端 outputs 增加下载按钮。
- HTML report 可直接打开。
- CSV summary 可表格展示。
- PNG 可预览。

验收：

- 任务完成后前端可直接下载或查看 outputs。

### 11.4 真实容器长任务小样本验收

建议先做 validate，再做小数据 real：

- T1 DeepPrep real：用一个小 T1 样本验证到输出 HTML/NIfTI。
- DWI QSIPrep real：用一个小 DWI 样本验证到 QSIPrep output。
- QSIRecon real：接 QSIPrep output 验证到 tractography/connectome 输出。
- BOLD fMRIPrep real：用一个小 BOLD 样本验证到 fMRIPrep output。

验收时必须记录：

- 输入路径。
- 启动命令。
- Docker image digest 或 tag。
- 开始/结束时间。
- 资源占用。
- 输出文件清单。
- 失败日志。

### 11.5 任务系统升级

目标：

- 不再依赖 API 进程内 Thread。
- 引入可恢复任务 runner。
- 增加任务取消、重试、运行中日志流。

## 12. 接手线程快速入口

快速查看 API：

```bash
cd /home/yyf/project/image_agent/apps/api
. .venv/bin/activate
pytest -q
```

快速查看前端：

```bash
cd /home/yyf/project/image_agent/apps/desktop
npm run build
```

快速查 workflow：

```bash
cd /home/yyf/project/image_agent
grep -R "WORKFLOWS" -n apps/api/app/main.py
sed -n '1,320p' apps/api/app/workflows/pipeline.py
```

快速查服务：

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/workflows
```

快速查当前任务：

```bash
sqlite3 /home/yyf/project/image_agent/data/app.db \
  "SELECT id, project_id, series_id, workflow_type, status, progress, error_message FROM tasks ORDER BY id DESC LIMIT 20;"
```

## 13. 当前结论

当前软件已经完成了“可用 MVP 调度框架”：

- GUI 可以上传多类脑影像输入。
- 后端可以识别基本 modality。
- 任务系统可以创建、运行、记录日志、登记输出。
- T1、DWI、DICOM、BOLD 的 workflow 入口已经存在。
- validate 模式已对主要 workflow 跑通过。
- Codex Review/Test 已修复 BOLD 指标前置任务校验问题。

但当前还不是“医学处理结果完全可用”的最终版。下一阶段应集中在真实数据闭环、真实指标计算、输出导出可视化和任务系统可靠性。
