# Non-Diagnostic Evidence

## Safe Language

Use:

- "The pipeline produced..."
- "The registered outputs show..."
- "This artifact appears complete/incomplete because..."
- "These research-derived metrics require qualified interpretation."

Avoid:

- "This indicates disease."
- "The scan is normal/abnormal."
- "The patient has..."
- "Treatment should..."
- "Clinically significant" unless quoting a qualified source and clearly separating it from Image Agent output.

## Evidence Standard

Every finding should cite at least one concrete item:

- task id;
- workflow type;
- result-summary field;
- artifact relative path;
- report manifest entry;
- provenance key;
- log line or validation message.

If a claim lacks evidence, label it as unverified and name the check needed.

## Conflict Handling

If the report page, result-summary, and logs disagree:

1. Prefer result-summary and registered outputs for frontend contract.
2. Use logs to explain how the state occurred.
3. Mark report text stale if it disagrees with current registered artifacts.
4. Recommend regenerating the summary/report from real files rather than editing wording by hand.
