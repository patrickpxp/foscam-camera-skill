# Tested Foscam C1 V3 interfaces

These are observations from one C1 V3 and the decompiled Foscam Android app. Probe another camera before assuming the same commands, payloads, or ports.

## Local CGI and motion

The camera accepted `http://HOST:88/cgi-bin/CGIProxy.fcgi` with `cmd`, `usr`, and `pwd` query parameters. `snapPicture2` returned JPEG. `getMotionDetectConfig` returned `isEnable`, sensitivity, trigger interval, schedule rows, area rows, and action `linkage`. `getDevState` returned `motionDetectAlarm`: 0 disabled, 1 idle, 2 active motion. Polling once per second captured real idle/motion transitions. `setMotionDetectConfig` accepted the read configuration with only `isEnable` changed; readback confirmed all other reported fields were preserved. The bundled motion script backs up configuration before changing it.

In the documented linkage mask, bit 1 sends email, bit 2 takes a snapshot, bit 3 records, and bit 7 sends a phone push. Inspect the actual mask before enabling detection, since saved actions become active. The Android APK's IPC `FosSdkJNI.GetMotionDetectConfig` sends native command 24033, and `SetMotionDetectConfig` sends 24031; its `DevState` includes `motionDetectAlarm`. `FosSdkJNI.GetEvent` wraps a proprietary event queue, but the CGI status path is the route verified for this skill.

## Microphone and speaker

RTSP port 554 paths `videoSub` and `videoMain` carried H.264 video and PCMU/G.711 mu-law audio at 8 kHz, mono. ffmpeg decoded the mic into PCM WAV. The app's IPC SDK wraps native `OpenAudio`, `GetAudioData`, and `CloseAudio` calls; a project can use RTSP instead of reimplementing that receive path.

The C1 V3 speaker played 8 kHz mono signed 16-bit PCM in 960-byte frames paced every 60 ms. `scripts/foscam_talk.py` performs the authenticated native TCP `SERVERPUSH` exchange on port 88 and sends FOSC packets. The header is little-endian `uint32 command`, `FOSC`, `uint32 payload_length`. Speaker-open is command 4 with an **exactly 160-byte** payload: 64-byte username, 64-byte password, 4-byte session ID, and 28 zero bytes. A leading zero causes the open request to fail. Command 6 carries a 4-byte length plus one PCM frame; command 5 closes talk. The user physically confirmed speaker output. The Android APK uses native `OpenTalk`, `SendTalkData`, and `CloseTalk` with 960-byte PCM buffers.

## ONVIF limits on this unit

ONVIF advertised profiles with microphone encoders, but no audio output or decoder configurations. RTSP DESCRIBE with the ONVIF backchannel `Require` header returned no send-only audio track. ONVIF capabilities reported `WSPullPointSupport=false`, so CGI polling was used for motion. Check the actual device responses rather than assuming all Foscam cameras share these limits.

Primary references: [Foscam IPCamera CGI User Guide](https://www.iltucci.com/blog/wp-content/uploads/2018/12/Foscam-IPCamera-CGI-User-Guide-V1.0.4.pdf), [ONVIF Streaming Specification](https://www.onvif.org/specs/stream/ONVIF-Streaming-Spec.pdf).
