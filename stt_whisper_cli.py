# /// script
# requires-python = ">=3.12"
# dependencies = ["sounddevice", "soundfile", "numpy"]
# ///
"""
Real-time Speech Transcription using OpenAI Whisper

Requires:
- macOS (uses pbcopy for clipboard)
- Whisper CLI installed (e.g. `brew install openai-whisper`)

Usage:
    uv run stt_whisper_cli.py                      # Basic usage with default settings
    uv run stt_whisper_cli.py -m small -l ja       # Specify model and language
    uv run stt_whisper_cli.py -a                   # Append mode (append to clipboard)
    uv run stt_whisper_cli.py -o ./transcripts.txt # Save transcription to file
    uv run stt_whisper_cli.py -a -o out.txt        # Append mode + save transcription
"""

import argparse
import subprocess
import sys
import tempfile
import threading
from datetime import datetime
from pathlib import Path
from time import sleep, time
from typing import Any

import numpy as np
import sounddevice as sd
import soundfile as sf


class Recorder:
    def __init__(self):
        self.samplerate = int(sd.query_devices(kind="input")["default_samplerate"])
        self.recording = False
        self.audio_data: list[np.ndarray] = []
        self._start_time: float = 0

    def start(self) -> None:
        self.audio_data = []
        self.recording = True
        self._start_time = time()
        self.stream = sd.InputStream(
            samplerate=self.samplerate,
            channels=1,
            dtype="float32",
            callback=self._callback,
        )
        self.stream.start()

    def _callback(
        self, indata: np.ndarray, frames: int, time: Any, status: Any
    ) -> None:
        if self.recording:
            self.audio_data.append(indata.copy())

    def elapsed(self) -> float:
        """Return elapsed recording time in seconds."""
        if self._start_time:
            return time() - self._start_time
        return 0.0

    def stop(self) -> np.ndarray:
        self.recording = False
        self.stream.stop()
        self.stream.close()
        if self.audio_data:
            return np.concatenate(self.audio_data, axis=0)
        return np.array([])


def transcribe(audio_path: Path, model: str = "base", lang: str = "en") -> str:
    result = subprocess.run(
        [
            "whisper",
            str(audio_path),
            "--model",
            model,
            "--language",
            lang,
            "--output_format",
            "txt",
            "--output_dir",
            str(audio_path.parent),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"Whisper error: {result.stderr}", file=sys.stderr)
        return ""

    # Read the generated .txt file
    txt_path = audio_path.with_suffix(".txt")
    if txt_path.exists():
        text = txt_path.read_text().strip()
        txt_path.unlink()
        return text
    return ""


def copy_to_clipboard(text: str) -> None:
    """Copy text to clipboard (macOS)."""
    subprocess.run(["pbcopy"], input=text.encode(), check=True)


def save_transcription(text: str, output_fp: Path) -> None:
    """Append transcription to output file with timestamp."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    parent_dir = output_fp.parent
    if not parent_dir.exists():
        parent_dir.mkdir(parents=True, exist_ok=True)
    with open(output_fp, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}]\n{text}\n\n")


def display_timer(recorder: Recorder, stop_event: threading.Event) -> None:
    """Display recording duration in real-time."""
    while not stop_event.is_set():
        elapsed = recorder.elapsed()
        mins, secs = divmod(int(elapsed), 60)
        # \r moves cursor to start of line, end="" prevents newline
        print(
            f"\r[REC] {mins:02d}:{secs:02d} (Press Enter to stop)", end="", flush=True
        )
        sleep(0.1)
    print()  # Newline after timer stops


def main() -> None:
    parser = argparse.ArgumentParser(description="Real-time Speech Transcription")
    parser.add_argument(
        "-m",
        "--model",
        default="base",
        help="Whisper model (tiny/base/small/medium/large/turbo)",
    )
    parser.add_argument(
        "-l", "--lang", default="en", help="Language code (e.g. en, ja, zh, etc.)"
    )
    parser.add_argument(
        "-a",
        "--append",
        action="store_true",
        help="Append to clipboard instead of replacing",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        metavar="FILE",
        help="Save transcription to specified file",
    )
    args = parser.parse_args()

    recorder = Recorder()
    print("Real-time Speech Transcription")
    print(f"  Model: {args.model}")
    print(f"  Language: {args.lang}")
    print(f"  Sample rate: {recorder.samplerate} Hz")
    print(f"  Append mode: {'on' if args.append else 'off'}")
    if args.output:
        print(f"  Output file: {args.output}")
    print("-" * 40)
    print("Press Enter to start recording, Enter again to stop and transcribe")
    print("Press Ctrl+C to exit")
    print()

    # Store all transcriptions in this session for append mode
    session_transcripts: list[str] = []

    try:
        while True:
            input("Press Enter to start recording...")

            # Start recording and timer display
            recorder.start()
            stop_event = threading.Event()
            timer_thread = threading.Thread(
                target=display_timer, args=(recorder, stop_event), daemon=True
            )
            timer_thread.start()

            input()
            stop_event.set()
            timer_thread.join()
            audio = recorder.stop()

            if len(audio) == 0:
                print("No audio detected!")
                continue

            duration = len(audio) / recorder.samplerate
            print(f"Duration: {duration:.1f}s")

            # Save temporary file
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                temp_path = Path(f.name)
                sf.write(temp_path, audio, recorder.samplerate)

            start = time()
            print("Transcribing...")
            text = transcribe(temp_path, model=args.model, lang=args.lang)
            temp_path.unlink()

            if text:
                elapsed = time() - start

                # Handle clipboard
                if args.append:
                    session_transcripts.append(text)
                    clipboard_text = "\n".join(session_transcripts)
                else:
                    clipboard_text = text
                copy_to_clipboard(clipboard_text)

                # Save transcription to output file if specified
                if args.output:
                    save_transcription(text, args.output)

                mode_info = " (appended)" if args.append else ""
                print(f"Completed in {elapsed:.1f}s (copied to clipboard{mode_info})")
                print(f"  > {text}")
            else:
                print("Transcription failed or no content!")

            print()

    except KeyboardInterrupt:
        print("\nGoodbye!")


if __name__ == "__main__":
    main()
