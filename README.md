# Foscam Camera Skill

An Agent Skill with Python command-line tools for working with Foscam C1 and compatible HD IP cameras. The tools can check motion status, save snapshots, listen to or record the camera microphone, play audio through the speaker, and run a turn-based voice companion.

The bundled camera interfaces were verified on a Foscam C1 V3. Other models and firmware have not been verified; confirm their CGI commands, RTSP paths, ports, and audio behavior before relying on these scripts.

## Requirements

Use Python 3.8 or later. Additional dependencies depend on the feature: `requests` for camera CGI and companion requests, `ffmpeg` for audio capture and conversion, `ffplay` for live listening, and `faster-whisper` for companion microphone transcription. Spoken replies use the native speech synthesizer when available; `--silent` skips speech. The voice companion also needs an OpenAI-compatible chat completions server.

Install only the dependencies needed for the features you plan to use. The companion can use `--text` instead of camera microphone transcription.

## Credentials

Each script accepts the camera host and username on the command line. The camera password is read from `FOSCAM_PASSWORD`; if it is unset, the script prompts for it. Set or clear the environment variable using the method supported by your shell. Avoid putting passwords directly in commands or source files.

Use these tools on a trusted local network. The camera CGI and speaker protocols send credentials to the camera, and the RTSP password can be visible in local `ffmpeg` process arguments while streaming.

## Usage

Run commands from the repository root. Replace `CAMERA_IP` and `CAMERA_USER` with your camera details.

### Motion detection

Read current motion status and configuration:

```
python scripts/foscam_motion.py status --host CAMERA_IP --user CAMERA_USER
```

Watch for state changes, optionally saving a JPEG when motion begins:

```
python scripts/foscam_motion.py watch --host CAMERA_IP --user CAMERA_USER --interval 1 --snapshot-dir motion-events
```

Enable or disable motion detection:

```
python scripts/foscam_motion.py enable --host CAMERA_IP --user CAMERA_USER
python scripts/foscam_motion.py disable --host CAMERA_IP --user CAMERA_USER
```

Before changing the setting, the script saves the existing camera configuration as a JSON backup. It then checks that the requested change took effect and that the other reported settings were preserved. Check your camera's alert linkage before enabling motion detection, since linked actions may become active.

The CGI motion commands and snapshot response were verified on a C1 V3. Confirm that another model supports the same commands and response format before use.

### Microphone

Record 10 seconds of microphone audio to a WAV file:

```
python scripts/foscam_mic.py --host CAMERA_IP --user CAMERA_USER --record mic.wav --seconds 10
```

Listen live instead:

```
python scripts/foscam_mic.py --host CAMERA_IP --user CAMERA_USER
```

The stream can be selected with `--stream videoSub` or `--stream videoMain`; it defaults to `videoSub`.

The `videoSub` and `videoMain` RTSP paths and microphone audio format were verified on a C1 V3. Other models may expose different paths or audio formats.

### Speaker

Provide an uncompressed, mono, 16-bit PCM WAV file sampled at 8 kHz:

```
python scripts/foscam_talk.py --host CAMERA_IP --user CAMERA_USER speech.wav
```

Convert another audio file to the required format with `ffmpeg`:

```
ffmpeg -i input.wav -ar 8000 -ac 1 -c:a pcm_s16le speech.wav
```

Speaker output and the native speaker protocol were verified on a C1 V3. The protocol may not work on other models or firmware.

### Voice companion

The companion takes a snapshot, gets typed input or records a short microphone clip, sends the text and image to an OpenAI-compatible model server, and can speak the response through the camera.

For a typed test turn:

```
python scripts/camera_companion.py --host CAMERA_IP --user CAMERA_USER --llm-url http://127.0.0.1:8080 --text "What can you see?" --silent
```

For a microphone turn:

```
python scripts/camera_companion.py --host CAMERA_IP --user CAMERA_USER --llm-url http://127.0.0.1:8080
```

Add `--loop` to continue taking turns until interrupted. The default Whisper model must already be cached locally; use `--allow-model-download` to permit downloading it. The companion calls the server's `/v1/models` and `/v1/chat/completions` endpoints and uses the first listed model.

Speech synthesis is selected automatically for the current operating system. Use `--tts-backend` to override the selection. Spoken output also requires `ffmpeg` to convert the result to the camera's audio format; use `--silent` to skip speech output.

## Using this as an Agent Skill

The skill instructions are in [`SKILL.md`](SKILL.md), with C1 V3 interface findings in [`references/c1-v3-interfaces.md`](references/c1-v3-interfaces.md). Place the skill directory in the skills location supported by your agent. Agents that support the open Agent Skills format can use the `SKILL.md` instructions and the bundled `scripts/` and `references/` files.

The optional [`agents/openai.yaml`](agents/openai.yaml) file provides display metadata for compatible OpenAI/Codex clients. Other agents can ignore it; the skill instructions do not depend on it.
