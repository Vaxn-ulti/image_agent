from pathlib import Path

path = Path("/app/.pixi/envs/xcp-d/lib/python3.12/site-packages/xcp_d/utils/utils.py")
lines = path.read_text().splitlines()
for idx in range(30, 105):
    print(f"{idx + 1}: {lines[idx]}")
