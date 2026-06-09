import json
import urllib.request


def get(url: str):
    with urllib.request.urlopen(url, timeout=20) as response:
        return response.status, response.headers, response.read()


payload = json.dumps({"task_ids": [41, 111, 114], "require_modalities": ["T1", "BOLD", "DWI"]}).encode()
request = urllib.request.Request(
    "http://127.0.0.1:8000/agent/tools/verify-scientific-reports",
    data=payload,
    headers={"Content-Type": "application/json"},
    method="POST",
)
with urllib.request.urlopen(request, timeout=20) as response:
    body = json.loads(response.read().decode())
print("VERIFY_TOOL", response.status, body["ok"], body["missing_modalities"], len(body["results"]))

status, headers, body = get("http://127.0.0.1:8000/tasks/114/artifacts/reports/dwi_tensor_metrics.svg")
print("DWI_SVG", status, headers.get("Content-Type"), len(body), body[:4].decode(errors="ignore"))

status, headers, body = get("http://127.0.0.1:8000/tasks/41/artifacts/reports/index.html")
print("T1_HTML", status, headers.get("Content-Type"), len(body), body[:15].decode(errors="ignore"))

status, headers, body = get("http://127.0.0.1:8000/tasks/111/result-summary")
summary = json.loads(body.decode())
print("BOLD_SUMMARY", status, summary.get("modality"), len(summary.get("outputs", {}).get("reports", [])))
