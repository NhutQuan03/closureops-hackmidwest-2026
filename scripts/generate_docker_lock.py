"""Generate runtime version pins from installed metadata and a Linux pip report."""

import argparse
from importlib.metadata import distributions
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--constraints", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    if args.constraints:
        pins = sorted({f"{item.metadata['Name']}=={item.version}" for item in distributions()}, key=str.lower)
        (ROOT / "backend/requirements-docker.constraints.txt").write_text(
            "# Versions from the working local environment; used only during lock resolution.\n"
            + "\n".join(pins) + "\n", encoding="utf-8",
        )
        print("Wrote package-version constraints; no credentials or package URLs collected.")
    elif args.report:
        report = json.loads(args.report.read_text(encoding="utf-8"))
        pins = sorted({
            f"{item['metadata']['name']}=={item['metadata']['version']} --hash=sha256:{item['download_info']['archive_info']['hashes']['sha256']}"
            for item in report["install"]
        }, key=str.lower)
        (ROOT / "backend/requirements-docker.lock").write_text(
            "# Python 3.12 Linux runtime closure resolved from requirements-docker.in.\n"
            "# Exact direct/transitive versions and wheel hashes for linux/amd64.\n"
            "# Update intentionally with a Linux pip report and rerun tests.\n"
            + "\n".join(pins) + "\n", encoding="utf-8",
        )
        print(f"Wrote {len(pins)} exact runtime dependency pins.")
    else:
        parser.error("Choose --constraints or --report.")


if __name__ == "__main__":
    main()
