---
name: foscam
description: Integrate Foscam C1 and compatible HD IP cameras with local snapshots, microphone audio, speaker talk, and motion detection. Use for Foscam camera API discovery, testing, or agent workflows; verify each interface on other models.
---

# Foscam camera integration

Use the bundled scripts for repeatable local camera operations. Ask for or discover the camera host and use credentials the user has supplied; do not put credentials in this skill or generated source. The speaker protocol and capability findings were verified on a C1 V3 and may differ on another model. Read [tested interfaces](references/c1-v3-interfaces.md) when selecting an API or adapting the protocol.

| Task | Script | Interface |
|---|---|---|
| Listen to or record the mic | `scripts/foscam_mic.py` | RTSP `videoSub` or `videoMain`; requires ffmpeg, and ffplay for listening |
| Play a PCM WAV through the speaker | `scripts/foscam_talk.py` | C1 V3 native FOSC protocol on port 88 |
| Read, watch, or change motion detection | `scripts/foscam_motion.py` | Local CGI `getDevState` and motion configuration |
| Run a turn-based visual voice companion | `scripts/camera_companion.py` | Snapshot + RTSP mic + Faster Whisper + OpenAI-compatible vision model + Windows System.Speech + camera speaker |

Pass `--host` and `--user` to every script. They read `FOSCAM_PASSWORD` or prompt for the password. Run `--help` for mode-specific options. Examples:

```text
python scripts/foscam_motion.py status --host CAMERA_IP --user CAMERA_USER
python scripts/foscam_motion.py watch --host CAMERA_IP --user CAMERA_USER --snapshot-dir motion-events
python scripts/foscam_mic.py --host CAMERA_IP --user CAMERA_USER --record mic.wav --seconds 10
python scripts/foscam_talk.py --host CAMERA_IP --user CAMERA_USER speech-8k-mono.wav
python scripts/camera_companion.py --host CAMERA_IP --user CAMERA_USER --llm-url http://127.0.0.1:8080
```

Use 8 kHz, mono, signed 16-bit PCM WAV for speaker input; `ffmpeg -i input.wav -ar 8000 -ac 1 -c:a pcm_s16le output.wav` converts other audio. The companion additionally needs `requests` and `faster-whisper`, a locally cached Whisper model unless `--allow-model-download` is set, and Windows PowerShell with `System.Speech` for spoken replies. `--silent` runs its vision/transcription path without TTS on other systems. Its `--loop` mode continues until interrupted; start it only when the user wants ongoing listening.

For motion, first read `status`. `watch` emits timestamped JSON on state changes, and `--snapshot-dir` saves a JPEG on a motion state. `enable` and `disable` change camera configuration: use them only when requested, inspect the existing alert linkage, preserve the other settings, and verify the readback. The script writes a pre-change backup to the current directory or `--backup-dir`.

Keep camera credentials and media on a trusted network. CGI and native talk send credentials in camera requests; RTSP credentials also appear in ffmpeg process arguments while recording or listening. Put camera access in a backend for browser-facing projects. On the tested C1 V3, ONVIF exposes video and microphone profiles but did not expose a speaker backchannel or PullPoint motion events; use the tested native speaker and CGI motion paths when those capabilities are absent.
