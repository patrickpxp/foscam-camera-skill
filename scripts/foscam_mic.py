"""Listen to or record the microphone on a Foscam C1 RTSP stream.

Requires ffplay for listening and ffmpeg for recording. The camera password is
read from FOSCAM_PASSWORD or prompted for. The RTSP URL appears in the local
ffmpeg process arguments while the command runs.
"""

import argparse
import getpass
import os
import shutil
import subprocess
from urllib.parse import quote


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True)
    parser.add_argument("--user", required=True)
    parser.add_argument("--stream", choices=("videoSub", "videoMain"), default="videoSub")
    parser.add_argument("--record", metavar="WAV", help="Save microphone audio as a WAV file")
    parser.add_argument("--seconds", type=float, help="Stop after this many seconds")
    args = parser.parse_args()

    if args.seconds is not None and args.seconds <= 0:
        parser.error("--seconds must be positive")
    password = os.getenv("FOSCAM_PASSWORD") or getpass.getpass("Camera password: ")
    url = f"rtsp://{quote(args.user, safe='')}:{quote(password, safe='')}@{args.host}:554/{args.stream}"

    ffmpeg = shutil.which("ffmpeg")
    ffplay = shutil.which("ffplay") if not args.record else None
    if not ffmpeg or (not args.record and not ffplay):
        parser.error("ffmpeg is required for recording; ffmpeg and ffplay are required for listening")

    if args.record:
        command = [ffmpeg, "-hide_banner", "-loglevel", "error", "-n", "-rtsp_transport", "tcp", "-i", url,
                   "-map", "0:a:0", "-vn", "-ac", "1", "-ar", "8000", "-c:a", "pcm_s16le"]
        if args.seconds is not None:
            command.extend(("-t", str(args.seconds)))
        command.append(args.record)
        print(f"Recording camera microphone to {args.record}...", flush=True)
    else:
        command = [ffmpeg, "-hide_banner", "-loglevel", "error", "-rtsp_transport", "tcp", "-i", url,
                   "-map", "0:a:0", "-vn", "-ac", "1", "-ar", "8000", "-c:a", "pcm_s16le", "-f", "wav"]
        if args.seconds is not None:
            command.extend(("-t", str(args.seconds)))
        command.append("pipe:1")
        print("Listening to camera microphone. Press Ctrl+C to stop.", flush=True)

    try:
        if args.record:
            result = subprocess.run(command, capture_output=True, text=True, check=False)
            returncode, details = result.returncode, result.stderr
        else:
            producer = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            consumer = subprocess.Popen([ffplay, "-hide_banner", "-loglevel", "error", "-nodisp", "-autoexit",
                                         "-i", "pipe:0"],
                                        stdin=producer.stdout, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            producer.stdout.close()
            _, player_errors = consumer.communicate()
            producer.wait()
            details = producer.stderr.read().decode(errors="replace") + player_errors.decode(errors="replace")
            returncode = producer.returncode or consumer.returncode
    except KeyboardInterrupt:
        if not args.record:
            producer.terminate()
            consumer.terminate()
        print("Stopped.")
        return
    if returncode:
        details = (details or "No error details returned").replace(password, "[redacted]")
        raise SystemExit(f"Audio failed (exit {returncode}): {details.strip()}")
    if args.record:
        print(f"Saved {args.record}")


if __name__ == "__main__":
    main()
