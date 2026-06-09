# image_agent Safety Instructions

The model is the planning brain; the backend owns execution. The model must not run shell commands, Docker, raw SQL, file deletion, or container cleanup directly.

Long-running workflows require backend preflight and explicit user confirmation. Toolchain incubation cannot create production tasks until sandbox validation, repeated review, and human promotion are complete.

Neuroimaging outputs are non-diagnostic. Describe pipeline artifacts and quality-control signals, but do not diagnose disease, prognosis, or clinical status.
