"""Have a short spoken conversation through the Foscam C1 camera.

Run with the Python environment that has requests and faster-whisper installed.
The camera password is read from FOSCAM_PASSWORD or prompted for. Each turn
captures one snapshot and a short microphone clip; --loop repeats until Ctrl+C.
"""

import argparse
import base64
import getpass
import os
import platform
import shutil
import subprocess
import tempfile
import wave
from pathlib import Path
from urllib.parse import quote

import requests

from foscam_talk import play_wav


SYSTEM_PROMPT = (
    "You are speaking to the camera owner through a garage camera. "
    "Reply naturally in one or two short sentences. Use the image when it helps "
    "answer their question. Do not claim to recognize anyone's identity. "
    "If an image detail is unclear, say so. Your reply will be spoken aloud."
)


def camera_snapshot(host, user, password):
    try:
        response = requests.get(
            f"http://{host}:88/cgi-bin/CGIProxy.fcgi",
            params={"cmd": "snapPicture2", "usr": user, "pwd": password},
            timeout=15,
        )
        response.raise_for_status()
    except requests.RequestException as error:
        raise RuntimeError("Camera snapshot failed: " + str(error).replace(password, "[redacted]")) from None
    if not response.headers.get("content-type", "").startswith("image/jpeg"):
        raise RuntimeError("Camera did not return a JPEG snapshot")
    return response.content


def record_mic(host, user, password, seconds, output):
    url = f"rtsp://{quote(user, safe='')}:{quote(password, safe='')}@{host}:554/videoSub"
    command = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-rtsp_transport", "tcp",
        "-i", url, "-map", "0:a:0", "-vn", "-t", str(seconds), "-ac", "1", "-ar", "16000",
        "-c:a", "pcm_s16le", str(output),
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode:
        raise RuntimeError("Microphone recording failed: " + result.stderr.replace(password, "[redacted]"))


def transcribe(mic_model, audio_path, language):
    segments, _ = mic_model.transcribe(str(audio_path), language=language, vad_filter=True, beam_size=1)
    return " ".join(segment.text.strip() for segment in segments).strip()


def ask_model(base_url, model, history, heard, snapshot):
    image_url = "data:image/jpeg;base64," + base64.b64encode(snapshot).decode("ascii")
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, *history,
                {"role": "user", "content": [
                    {"type": "text", "text": heard},
                    {"type": "image_url", "image_url": {"url": image_url}},
                ]}]
    response = requests.post(
        base_url.rstrip("/") + "/v1/chat/completions",
        json={"model": model, "messages": messages, "max_tokens": 250,
              "temperature": 0.2, "chat_template_kwargs": {"enable_thinking": False}},
        timeout=120,
    )
    response.raise_for_status()
    reply = response.json()["choices"][0]["message"]["content"].strip()
    if not reply:
        raise RuntimeError("The model returned no spoken reply")
    return reply


def speak_through_camera(host, user, password, reply, workdir, tts_backend):
    speech_source = workdir / "speech-source"
    camera_wav = workdir / "camera-speech.wav"
    text_file = workdir / "speech.txt"
    text_file.write_text(reply, encoding="utf-8")
    backend = tts_backend
    if backend == "auto":
        backend = {"Windows": "windows", "Darwin": "macos", "Linux": "espeak"}.get(platform.system())
    if backend is None:
        raise RuntimeError(f"No built-in speech synthesis backend for {platform.system()}; use --silent")
    if backend == "windows":
        powershell = shutil.which("powershell")
        if not powershell:
            raise RuntimeError("Windows speech synthesis requires Windows PowerShell; use --silent to skip speech")
        speech_wav = speech_source.with_suffix(".wav")
        script = (
            "[Console]::InputEncoding=[System.Text.Encoding]::UTF8; "
            "Add-Type -AssemblyName System.Speech; "
            "$s=New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            "$s.SetOutputToWaveFile($env:FOSCAM_TTS_WAV); "
            "$s.Speak([Console]::In.ReadToEnd()); $s.Dispose()"
        )
        environment = {**os.environ, "FOSCAM_TTS_WAV": str(speech_wav)}
        speech = subprocess.run([powershell, "-NoProfile", "-Command", script],
                                input=reply, text=True, capture_output=True, env=environment, check=False)
        if speech.returncode:
            raise RuntimeError("Windows speech synthesis failed: " + speech.stderr)
    elif backend == "macos":
        speech_wav = speech_source.with_suffix(".aiff")
        say = shutil.which("say")
        if not say:
            raise RuntimeError("macOS speech synthesis requires the 'say' command; use --silent to skip speech")
        speech = subprocess.run([say, "-f", str(text_file), "-o", str(speech_wav)],
                                capture_output=True, text=True, check=False)
        if speech.returncode:
            raise RuntimeError("macOS speech synthesis failed: " + speech.stderr)
    else:
        speech_wav = speech_source.with_suffix(".wav")
        espeak = shutil.which("espeak-ng") or shutil.which("espeak")
        if not espeak:
            raise RuntimeError("Linux speech synthesis requires espeak-ng or espeak; use --silent to skip speech")
        speech = subprocess.run([espeak, "-f", str(text_file), "-w", str(speech_wav)],
                                capture_output=True, text=True, check=False)
        if speech.returncode:
            raise RuntimeError("eSpeak speech synthesis failed: " + speech.stderr)
    conversion = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(speech_wav),
         "-ac", "1", "-ar", "8000", "-c:a", "pcm_s16le", str(camera_wav)],
        capture_output=True, text=True, check=False,
    )
    if conversion.returncode:
        raise RuntimeError("Speech conversion failed: " + conversion.stderr)
    with wave.open(str(camera_wav), "rb") as wav:
        play_wav(host, user, password, wav)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True)
    parser.add_argument("--user", required=True)
    parser.add_argument("--llm-url", required=True, help="OpenAI-compatible server base URL")
    parser.add_argument("--seconds", type=float, default=8, help="Microphone capture length per turn")
    parser.add_argument("--language", default="en", help="Whisper language code")
    parser.add_argument("--whisper-model", default="base", help="Cached Faster Whisper model or local path")
    parser.add_argument("--allow-model-download", action="store_true", help="Allow Faster Whisper to fetch its model")
    parser.add_argument("--text", help="Use typed text instead of the camera mic for a test turn")
    parser.add_argument("--silent", action="store_true", help="Print the reply without using the camera speaker")
    parser.add_argument("--tts-backend", choices=("auto", "windows", "macos", "espeak"), default="auto",
                        help="Speech synthesis backend (default: auto-detect for this operating system)")
    parser.add_argument("--loop", action="store_true", help="Keep listening for more turns")
    args = parser.parse_args()
    if args.seconds <= 0 or (args.text and args.loop):
        parser.error("--seconds must be positive, and --text cannot be used with --loop")
    if not shutil.which("ffmpeg"):
        parser.error("ffmpeg is required on PATH")

    password = os.getenv("FOSCAM_PASSWORD") or getpass.getpass("Camera password: ")
    server = args.llm_url.rstrip("/")
    response = requests.get(server + "/v1/models", timeout=10)
    response.raise_for_status()
    models = response.json().get("data", [])
    if not models:
        raise RuntimeError("The LLM server has no loaded model")
    model_id = models[0]["id"]
    print(f"Using {model_id} at {server}", flush=True)

    if args.text:
        mic_model = None
    else:
        from faster_whisper import WhisperModel
        mic_model = WhisperModel(args.whisper_model, device="cpu", compute_type="int8",
                                 local_files_only=not args.allow_model_download)
    history = []
    try:
        while True:
            with tempfile.TemporaryDirectory(prefix="foscam-companion-") as temporary:
                workdir = Path(temporary)
                snapshot = camera_snapshot(args.host, args.user, password)
                if args.text:
                    heard = args.text
                else:
                    audio = workdir / "mic.wav"
                    print(f"Listening for {args.seconds:g} seconds...", flush=True)
                    record_mic(args.host, args.user, password, args.seconds, audio)
                    heard = transcribe(mic_model, audio, args.language)
                if not heard:
                    print("No speech recognized; waiting for the next turn." if args.loop else "No speech recognized.")
                else:
                    print(f"Heard: {heard}", flush=True)
                    reply = ask_model(server, model_id, history, heard, snapshot)
                    print(f"Reply: {reply}", flush=True)
                    if not args.silent:
                        speak_through_camera(args.host, args.user, password, reply, workdir, args.tts_backend)
                    history.extend([{"role": "user", "content": heard},
                                    {"role": "assistant", "content": reply}])
                    history = history[-8:]
            if not args.loop:
                break
    except KeyboardInterrupt:
        print("Stopped.")


if __name__ == "__main__":
    main()
