"""
Voice pipeline — wake word → STT → TTS.
Components:
  - openWakeWord: always-on wake word detection
  - faster-whisper: speech-to-text (base model, CPU-optimized)
  - piper-tts: text-to-speech (local, offline)
"""

import os
import io
import queue
import struct
import threading
import numpy as np
from typing import Optional, Callable

# ============================================================
# Config
# ============================================================
SAMPLE_RATE = 16000
CHANNELS = 1
CHUNK_SIZE = 1280  # 80ms at 16kHz
WAKE_WORD = "hey jarvis"
WHISPER_MODEL = os.environ.get("AGENTOS_WHISPER_MODEL", "base")
PIPER_MODEL = os.environ.get("AGENTOS_PIPER_MODEL", "en_US-lessac-medium")
PIPER_SPEED = float(os.environ.get("AGENTOS_PIPER_SPEED", "1.0"))


class VoicePipeline:
    """
    Unified voice pipeline:
      wake_word_detector → stt → callback → tts → speaker
    """

    def __init__(
        self,
        on_wakeword: Optional[Callable] = None,
        on_stt: Optional[Callable[[str], None]] = None,
        on_tts_start: Optional[Callable] = None,
        on_tts_end: Optional[Callable] = None,
    ):
        self.on_wakeword = on_wakeword
        self.on_stt = on_stt
        self.on_tts_start = on_tts_start
        self.on_tts_end = on_tts_end

        self._running = False
        self._listening_for_speech = False
        self._audio_queue: queue.Queue = queue.Queue()
        self._wake_model = None
        self._stt_model = None
        self._tts_model = None
        self._thread: Optional[threading.Thread] = None

    def start(self):
        """Start voice pipeline in background thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        """Stop voice pipeline."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None

    def speak(self, text: str):
        """Synthesize and play TTS audio (blocking)."""
        try:
            import piper
            if self._tts_model is None:
                self._tts_model = piper.PiperVoice.load(PIPER_MODEL)
            wav = self._tts_model.synthesize(text, length_scale=1.0 / PIPER_SPEED)
            self._play_audio(wav)
        except ImportError:
            # Fallback: print text if piper not available
            print(f"[TTS] {text}")

    def transcribe(self, audio_data: np.ndarray) -> Optional[str]:
        """Transcribe audio numpy array to text."""
        try:
            from faster_whisper import WhisperModel
            if self._stt_model is None:
                self._stt_model = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")
            segments, _ = self._stt_model.transcribe(audio_data, language="en")
            return " ".join(seg.text for seg in segments).strip()
        except ImportError:
            return None

    def detect_wake_word(self, audio_chunk: np.ndarray) -> bool:
        """Run wake word detection on audio chunk."""
        try:
            import openwakeword
            if self._wake_model is None:
                self._wake_model = openwakeword.Model(wakeword_models=["hey_jarvis"])
            prediction = self._wake_model.predict(audio_chunk)
            for key, score in prediction.items():
                if key == "hey_jarvis" and score > 0.5:
                    return True
            return False
        except ImportError:
            return False

    def _run(self):
        """Main pipeline loop."""
        try:
            import pyaudio
            pa = pyaudio.PyAudio()
            stream = pa.open(
                format=pyaudio.paInt16,
                channels=CHANNELS,
                rate=SAMPLE_RATE,
                input=True,
                frames_per_buffer=CHUNK_SIZE,
            )
        except (ImportError, OSError):
            return

        speech_buffer = []
        silence_chunks = 0
        max_silence = 25  # 2 seconds of silence = end of speech

        try:
            while self._running:
                data = stream.read(CHUNK_SIZE, exception_on_overflow=False)
                audio_chunk = np.frombuffer(data, dtype=np.int16)

                # Always run wake word detection
                if not self._listening_for_speech:
                    if self.detect_wake_word(audio_chunk):
                        self._listening_for_speech = True
                        speech_buffer = []
                        silence_chunks = 0
                        if self.on_wakeword:
                            self.on_wakeword()
                else:
                    # Listening for speech after wake word
                    speech_buffer.append(audio_chunk)
                    rms = np.sqrt(np.mean(audio_chunk.astype(np.float32) ** 2))
                    if rms < 300:  # silence threshold
                        silence_chunks += 1
                    else:
                        silence_chunks = 0

                    # End of speech detected
                    if silence_chunks >= max_silence:
                        self._listening_for_speech = False
                        if speech_buffer:
                            audio_data = np.concatenate(speech_buffer)
                            text = self.transcribe(audio_data)
                            if text and self.on_stt:
                                self.on_stt(text)
                        speech_buffer = []
                        silence_chunks = 0
        finally:
            stream.stop_stream()
            stream.close()
            pa.terminate()

    def _play_audio(self, wav_data):
        """Play WAV audio bytes through speaker."""
        try:
            import pyaudio
            pa = pyaudio.PyAudio()
            stream = pa.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=22050,
                output=True,
            )
            if self.on_tts_start:
                self.on_tts_start()
            stream.write(wav_data)
            if self.on_tts_end:
                self.on_tts_end()
            stream.stop_stream()
            stream.close()
            pa.terminate()
        except Exception:
            pass


# ============================================================
# Standalone test
# ============================================================
if __name__ == "__main__":
    def on_wake():
        print("[Wake word detected]")

    def on_text(text):
        print(f"[User said] {text}")
        pipeline.speak(f"You said: {text}")

    pipeline = VoicePipeline(on_wakeword=on_wake, on_stt=on_text)
    print("Voice pipeline started. Say 'hey jarvis' to activate.")
    pipeline.start()

    import time
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pipeline.stop()
        print("Stopped.")
