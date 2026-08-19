"""Verify a saved capture without opening hardware."""

import json
import sys
from pathlib import Path

TARGET = 36.938876


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(f"usage: {Path(sys.argv[0]).name} CAPTURE.json")
    payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    runs = payload.get("runs", [])
    passed = (
        len(runs) == 5
        and all(not item.get("errors") for item in runs)
        and all(len(item.get("streams", [])) == 2 for item in runs)
        and all(
            stream.get("oracle_match") == "24/24"
            for item in runs
            for stream in item["streams"]
        )
        and all(item["result"].get("oracle_match") == "48/48" for item in runs)
        and all(float(item["result"].get("aggregate_tok_s", 0)) >= TARGET for item in runs)
    )
    print(json.dumps({"runs": len(runs), "target_tok_s": TARGET, "passed": passed}))
    raise SystemExit(0 if passed else 1)


if __name__ == "__main__":
    main()
