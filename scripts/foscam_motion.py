"""Read or watch the Foscam C1's built-in motion alarm over its local CGI API.

Usage: python foscam_motion.py status
       python foscam_motion.py watch --interval 1
       python foscam_motion.py watch --snapshot-dir motion-events
       python foscam_motion.py enable
       python foscam_motion.py disable

The camera password comes from FOSCAM_PASSWORD or an interactive prompt.
Enable/disable preserves the other reported settings and saves a backup in the
working directory (or --backup-dir).
"""

import argparse
import getpass
import json
import os
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

import requests


MOTION_STATES = {0: "disabled", 1: "idle", 2: "motion"}


def cgi(host, user, password, command, extra=None):
    try:
        response = requests.get(
            f"http://{host}:88/cgi-bin/CGIProxy.fcgi",
            params={"cmd": command, "usr": user, "pwd": password, **(extra or {})},
            timeout=10,
        )
        response.raise_for_status()
    except requests.RequestException as error:
        raise RuntimeError(str(error).replace(password, "[redacted]")) from None
    try:
        root = ET.fromstring(response.content)
        values = {item.tag: item.text for item in root}
    except ET.ParseError:
        raise RuntimeError(f"Camera returned invalid XML for {command}") from None
    if values.get("result") != "0":
        raise RuntimeError(f"Camera rejected {command}: result={values.get('result')}")
    return values


def motion_status(host, user, password):
    values = cgi(host, user, password, "getDevState")
    raw = int(values["motionDetectAlarm"])
    return {"time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "state": MOTION_STATES.get(raw, "unknown"), "raw": raw}


def snapshot(host, user, password):
    try:
        response = requests.get(
            f"http://{host}:88/cgi-bin/CGIProxy.fcgi",
            params={"cmd": "snapPicture2", "usr": user, "pwd": password},
            timeout=15,
        )
        response.raise_for_status()
    except requests.RequestException as error:
        raise RuntimeError(str(error).replace(password, "[redacted]")) from None
    if not response.headers.get("content-type", "").startswith("image/jpeg"):
        raise RuntimeError("Camera did not return a JPEG snapshot")
    return response.content


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("status", "watch", "enable", "disable"))
    parser.add_argument("--host", required=True)
    parser.add_argument("--user", required=True)
    parser.add_argument("--interval", type=float, default=1.0, help="Seconds between polls in watch mode")
    parser.add_argument("--snapshot-dir", type=Path, help="Save a JPEG when motion begins (watch mode)")
    parser.add_argument("--backup-dir", type=Path, default=Path.cwd(),
                        help="Directory for a configuration backup before enable/disable")
    args = parser.parse_args()
    if args.interval <= 0:
        parser.error("--interval must be positive")
    if args.snapshot_dir and args.mode != "watch":
        parser.error("--snapshot-dir can only be used with watch")
    password = os.getenv("FOSCAM_PASSWORD") or getpass.getpass("Camera password: ")

    if args.mode == "status":
        config = cgi(args.host, args.user, password, "getMotionDetectConfig")
        status = motion_status(args.host, args.user, password)
        status["enabled"] = config.get("isEnable") == "1"
        status["sensitivity"] = int(config["sensitivity"]) if "sensitivity" in config else None
        status["trigger_interval"] = int(config["triggerInterval"]) if "triggerInterval" in config else None
        print(json.dumps(status))
        return

    if args.mode in ("enable", "disable"):
        desired = "1" if args.mode == "enable" else "0"
        config = cgi(args.host, args.user, password, "getMotionDetectConfig")
        if config.get("isEnable") == desired:
            print(json.dumps({"enabled": desired == "1", "changed": False,
                              "status": motion_status(args.host, args.user, password)}))
            return
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        args.backup_dir.mkdir(parents=True, exist_ok=True)
        backup = args.backup_dir / f"motion-config-before-{args.mode}-{timestamp}.json"
        backup.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
        settings = {key: value for key, value in config.items() if key != "result"}
        settings["isEnable"] = desired
        cgi(args.host, args.user, password, "setMotionDetectConfig", settings)
        after = cgi(args.host, args.user, password, "getMotionDetectConfig")
        differences = {key: {"before": value, "after": after.get(key)}
                       for key, value in config.items() if key != "isEnable" and after.get(key) != value}
        print(json.dumps({"enabled": after.get("isEnable") == "1", "backup": str(backup),
                          "other_changes": differences,
                          "status": motion_status(args.host, args.user, password)}))
        if after.get("isEnable") != desired or differences:
            raise RuntimeError("Motion configuration verification did not match the requested change")
        return

    previous = None
    try:
        while True:
            status = motion_status(args.host, args.user, password)
            if status["raw"] != previous:
                if status["raw"] == 2 and args.snapshot_dir:
                    args.snapshot_dir.mkdir(parents=True, exist_ok=True)
                    filename = datetime.now(timezone.utc).strftime("motion-%Y%m%dT%H%M%S-%fZ.jpg")
                    path = args.snapshot_dir / filename
                    path.write_bytes(snapshot(args.host, args.user, password))
                    status["snapshot"] = str(path.resolve())
                print(json.dumps(status), flush=True)
                previous = status["raw"]
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("Stopped.", file=sys.stderr)


if __name__ == "__main__":
    main()
