#!/usr/bin/env bash
set -eu

ROOT=/home/yyf/project/image_agent/data/projects/13/derivatives
SOURCE=$ROOT/64/output/BOLD
IN=$ROOT/115/input_deepprep_fmriprep_compat
OUT=$ROOT/115/output
WORK=$ROOT/115/work
LOG=$ROOT/115/xcpd_deepprep_test.log
TEMPLATEFLOW=/home/yyf/project/image_agent/data/templateflow

mkdir -p "$OUT" "$WORK" "$ROOT/115"
rm -rf "$IN"
mkdir -p "$IN"
cp -a "$SOURCE/." "$IN/"

COMPAT_MASK="$IN/sub-01/anat/sub-01_space-MNI152NLin6Asym_desc-brain_mask.nii.gz"
if [ ! -f "$COMPAT_MASK" ]; then
  PYTHONPATH=/home/yyf/project/image_agent/apps/api /home/yyf/project/image_agent/apps/api/.venv/bin/python - <<'PY'
from pathlib import Path
import nibabel as nib
import numpy as np

root = Path("/home/yyf/project/image_agent/data/projects/13/derivatives/115/input_deepprep_fmriprep_compat")
source = root / "sub-01/anat/sub-01_space-MNI152NLin6Asym_res-02_desc-noskull_T1w.nii.gz"
target = root / "sub-01/anat/sub-01_space-MNI152NLin6Asym_desc-brain_mask.nii.gz"
img = nib.load(str(source))
data = img.get_fdata()
mask = (data > 0).astype("uint8")
nib.save(nib.Nifti1Image(mask, img.affine, img.header), str(target))
print(f"created {target}")
PY
fi

COMPAT_XFM="$IN/sub-01/anat/sub-01_from-T1w_to-MNI152NLin6Asym_mode-image_xfm.nii.gz"
if [ ! -e "$COMPAT_XFM" ]; then
  ln -s "sub-01_from-T1w_to-MNI152NLin6Asym_desc-joint_trans.nii.gz" "$COMPAT_XFM"
fi

COMPAT_INV_XFM="$IN/sub-01/anat/sub-01_from-MNI152NLin6Asym_to-T1w_mode-image_xfm.nii.gz"
if [ ! -e "$COMPAT_INV_XFM" ]; then
  ln -s "sub-01_from-T1w_to-MNI152NLin6Asym_desc-joint_trans.nii.gz" "$COMPAT_INV_XFM"
fi

COMPAT_BOLD_MASK="$IN/sub-01/func/sub-01_task-rest_space-MNI152NLin6Asym_res-02_desc-brain_mask.nii.gz"
if [ ! -f "$COMPAT_BOLD_MASK" ]; then
  PYTHONPATH=/home/yyf/project/image_agent/apps/api /home/yyf/project/image_agent/apps/api/.venv/bin/python - <<'PY'
from pathlib import Path
import nibabel as nib
import numpy as np

root = Path("/home/yyf/project/image_agent/data/projects/13/derivatives/115/input_deepprep_fmriprep_compat")
source = root / "sub-01/func/sub-01_task-rest_space-MNI152NLin6Asym_res-02_desc-preproc_bold.nii.gz"
target = root / "sub-01/func/sub-01_task-rest_space-MNI152NLin6Asym_res-02_desc-brain_mask.nii.gz"
img = nib.load(str(source))
data = np.asanyarray(img.dataobj)
finite = np.isfinite(data)
nonzero = data != 0
mask = np.any(finite & nonzero, axis=3).astype("uint8")
header = img.header.copy()
header.set_data_dtype("uint8")
nib.save(nib.Nifti1Image(mask, img.affine, header), str(target))
print(f"created {target}")
PY
fi

echo "START $(date -Is)" | tee "$LOG"
if [ -z "${IMAGE_AGENT_SUDO_PASSWORD:-}" ]; then
  echo "IMAGE_AGENT_SUDO_PASSWORD is required for sudo docker run" >&2
  exit 1
fi

printf '%s\n' "$IMAGE_AGENT_SUDO_PASSWORD" | sudo -S docker run --rm \
  --network host \
  -v "$IN":/fmri:ro \
  -v "$OUT":/out \
  -v "$WORK":/work \
  -v "$TEMPLATEFLOW":/templateflow \
  -e TEMPLATEFLOW_HOME=/templateflow \
  pennlinc/xcp_d:26.0.2 \
  /fmri /out participant \
  --mode linc \
  --input-type fmriprep \
  --file-format nifti \
  --participant-label 01 \
  --task-id rest \
  --nprocs 4 \
  --omp-nthreads 2 \
  --mem-mb 16000 \
  --skip parcellation connectivity \
  --linc-qc y \
  --abcc-qc y \
  --notrack \
  -w /work 2>&1 | tee -a "$LOG"
echo "END $(date -Is)" | tee -a "$LOG"
