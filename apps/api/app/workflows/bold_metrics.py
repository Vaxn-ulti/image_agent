import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--metric", choices=["ALFF", "fALFF"], required=True)
    parser.add_argument("--bids", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    csv_path = out / f"sub-01_{args.metric.lower()}_summary.csv"
    json_path = out / f"sub-01_{args.metric.lower()}_metadata.json"
    csv_path.write_text(f"subject,metric,status\n01,{args.metric},computed_placeholder\n", encoding="utf-8")
    json_path.write_text(json.dumps({"metric": args.metric, "method": "phase3 placeholder runner", "bids_dir": args.bids}, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
