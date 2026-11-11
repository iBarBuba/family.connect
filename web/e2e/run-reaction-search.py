#!/usr/bin/env python3
"""Real-server reaction e2e through Playwright CLI, with screenshots and optional video.

python3 web/e2e/run-reaction-search.py --url http://127.0.0.1:58081 --video
Requires a running local server/Web, Node/npm and installed Google Chrome.
"""
import argparse
import json
from pathlib import Path
import subprocess
from urllib.parse import urlparse


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:58081")
    parser.add_argument("--output", type=Path, default=Path("output/playwright/reaction-search"))
    parser.add_argument("--video", action="store_true")
    args = parser.parse_args()
    if urlparse(args.url).hostname not in {"127.0.0.1", "localhost", "::1"}:
        parser.error("This creates disposable test accounts: --url must be a local server")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    source = Path(__file__).resolve().parent
    base = ["npx", "--yes", "--package", "@playwright/cli@0.1.24", "playwright-cli", "--session", "reaction-search-e2e"]
    sequence = 0

    def cli(*arguments, required=True):
        nonlocal sequence
        sequence += 1
        result = subprocess.run(base + list(arguments), cwd=output, text=True, capture_output=True, timeout=180)
        (output / f"cli-{sequence:02d}.log").write_text(result.stdout + result.stderr)
        if required and result.returncode:
            raise RuntimeError(f"Playwright {arguments[0]} failed; see {output / f'cli-{sequence:02d}.log'}")
        return result

    recording = False
    try:
        cli("open", args.url, "--config", str(source / "browser.json"))
        permissions = cli("eval", "async () => Object.fromEntries(await Promise.all(['camera','microphone'].map(async name => [name, (await navigator.permissions.query({name})).state])))")
        (output / "permissions.log").write_text(permissions.stdout)
        if args.video:
            recording = cli("video-start", str(output / "reaction-search.webm"), required=False).returncode == 0
        scenario = (source / "reaction-search.js").read_text(encoding="utf-8")
        settings = json.dumps({"baseURL": args.url, "outputDir": str(output)})
        result = cli("run-code", f"async (page) => await ({scenario})(page, {settings})")
        text = result.stdout.split("### Result\n", 1)[1].split("\n### ", 1)[0]
        summary = json.loads(text)
        if summary.get("status") != "passed":
            raise RuntimeError("Scenario did not report a passing result")
        summary["video_requested"] = args.video
        summary["video_started"] = recording
        (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    except Exception:
        cli("snapshot", required=False)
        cli("screenshot", "--filename", str(output / "failure.png"), required=False)
        raise
    finally:
        if recording:
            cli("video-stop", required=False)
        cli("close", required=False)


if __name__ == "__main__":
    main()
