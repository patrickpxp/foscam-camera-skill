"""Play 8 kHz, mono, 16-bit PCM WAV audio through a Foscam C1 V3 speaker.

Usage: python foscam_talk.py --host CAMERA_IP --user CAMERA_USER tone.wav
Set FOSCAM_PASSWORD for unattended use; otherwise the script prompts for it.
"""

import argparse
import getpass
import os
import socket
import struct
import time
import wave


def packet(command, payload):
    return struct.pack("<I4sI", command, b"FOSC", len(payload)) + payload


class CameraConnection:
    def __init__(self, sock):
        self.sock = sock
        self.buffer = b""
        self.header_seen = False

    def read_packet(self):
        while True:
            if not self.header_seen:
                if len(self.buffer) >= 8 and self.buffer[4:8] == b"FOSC":
                    self.header_seen = True
                elif b"\r\n\r\n" in self.buffer:
                    header, self.buffer = self.buffer.split(b"\r\n\r\n", 1)
                    if not header.startswith(b"HTTP/1.1 200"):
                        raise RuntimeError(f"SERVERPUSH rejected: {header.splitlines()[0]!r}")
                    self.header_seen = True
            if self.header_seen and len(self.buffer) >= 12:
                command, magic, size = struct.unpack("<I4sI", self.buffer[:12])
                if magic != b"FOSC" or size > 1_000_000:
                    raise RuntimeError("Invalid camera packet")
                if len(self.buffer) >= 12 + size:
                    body = self.buffer[12:12 + size]
                    self.buffer = self.buffer[12 + size:]
                    return command, body
            data = self.sock.recv(16384)
            if not data:
                raise ConnectionError("Camera closed the connection")
            self.buffer += data

    def expect(self, command):
        for _ in range(20):
            received, body = self.read_packet()
            if received == command:
                return body
        raise RuntimeError(f"No response for camera command {command}")


def play_wav(host, user, password, wav, port=88):
    credentials = user.encode().ljust(64, b"\0") + password.encode().ljust(64, b"\0")
    if len(credentials) != 128:
        raise ValueError("Username and password must each fit in 64 bytes")
    session_id = int(time.time()) & 0xFFFFFFFF
    with socket.create_connection((host, port), timeout=10) as sock:
        sock.settimeout(10)
        connection = CameraConnection(sock)
        sock.sendall(f"SERVERPUSH / HTTP/1.1\r\nHost: {host}:{port}\r\nAccept:*/*\r\nConnection: Close\r\n\r\n".encode())
        sock.sendall(packet(12, credentials + struct.pack("<I", session_id) + b"\0" * 32))
        connection.expect(100)
        sock.sendall(packet(15, struct.pack("<I", session_id)))
        login = connection.expect(29)
        if len(login) < 4 or struct.unpack("<I", login[:4])[0] != 0:
            raise RuntimeError("Camera login failed")
        opened = False
        try:
            # This payload is exactly 160 bytes. A leading zero makes talk-open fail.
            sock.sendall(packet(4, credentials + struct.pack("<I", session_id) + b"\0" * 28))
            result = connection.expect(20)
            if len(result) < 4 or struct.unpack("<I", result[:4])[0] != 0:
                raise RuntimeError("Camera rejected talk-open")
            opened = True
            deadline = time.monotonic()
            while audio := wav.readframes(480):
                audio = audio.ljust(960, b"\0")
                sock.sendall(packet(6, struct.pack("<I", len(audio)) + audio))
                deadline += 0.06
                time.sleep(max(0, deadline - time.monotonic()))
        finally:
            if opened:
                sock.sendall(packet(5, credentials + b"\0" * 32))
            sock.sendall(packet(1, b"\0" + credentials))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wav", help="8 kHz mono 16-bit PCM WAV file")
    parser.add_argument("--host", required=True)
    parser.add_argument("--user", required=True)
    parser.add_argument("--port", type=int, default=88)
    args = parser.parse_args()
    password = os.getenv("FOSCAM_PASSWORD") or getpass.getpass("Camera password: ")
    with wave.open(args.wav, "rb") as wav:
        if (wav.getnchannels(), wav.getsampwidth(), wav.getframerate(), wav.getcomptype()) != (1, 2, 8000, "NONE"):
            raise ValueError("WAV must be uncompressed, mono, 16-bit PCM at 8000 Hz")
        play_wav(args.host, args.user, password, wav, args.port)
    print("Audio sent and talk session closed.")


if __name__ == "__main__":
    main()
