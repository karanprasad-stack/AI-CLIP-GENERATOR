"""Speech-to-text transcription engine using faster-whisper on CUDA."""

import os
import sys
import site
import ctypes
from pathlib import Path
from typing import Dict, Any, Union, Optional
import ctranslate2
from faster_whisper import WhisperModel


class TranscriberError(Exception):
    """Raised when audio transcription or model initialization fails."""
    pass


def _preload_cuda_dlls() -> None:
    """
    On Windows, CTranslate2 dynamically loads cublas64_12.dll.
    When installed via pip (nvidia-cublas-cu12), Windows needs the DLL directory
    registered and the libraries pre-loaded into the process address space.
    """
    if sys.platform != "win32":
        return

    site_packages = site.getsitepackages()
    user_site = site.getusersitepackages() if hasattr(site, "getusersitepackages") else None
    search_dirs = list(site_packages)
    if user_site and user_site not in search_dirs:
        search_dirs.append(user_site)

    for sp in search_dirs:
        nvidia_base = Path(sp) / "nvidia"
        if nvidia_base.is_dir():
            for bin_dir in nvidia_base.glob("*/bin"):
                if bin_dir.is_dir():
                    try:
                        os.add_dll_directory(str(bin_dir))
                    except (AttributeError, OSError):
                        pass
                    if str(bin_dir) not in os.environ.get("PATH", ""):
                        os.environ["PATH"] = f"{bin_dir};{os.environ.get('PATH', '')}"

                    for dll_target in ["cublasLt64_12.dll", "cublas64_12.dll"]:
                        dll_file = bin_dir / dll_target
                        if dll_file.is_file():
                            try:
                                ctypes.CDLL(str(dll_file))
                            except Exception:
                                pass


_preload_cuda_dlls()


# Domain vocabulary prompt priming for Faster-Whisper: enhances recognition
# of gaming terminology, abbreviations, weapons, and colloquial Hinglish.
DEFAULT_GAMING_INITIAL_PROMPT = (
    "Valorant, CS2, Counter-Strike, AWP, AK-47, clutch, ace, one tap, headshot, "
    "peek, rush, plant, defuse, spike, vandal, phantom, low HP, GG, brother, "
    "bhai, arre, kya, kaise, chal, dekho, mast, accha, sahi, maar, zone, knock"
)


class AudioTranscriber:
    """Handles speech transcription using faster-whisper with CUDA acceleration."""

    def __init__(
        self,
        model_size: str = "base.en",
        device: str = "cuda",
        compute_type: str = "float16",
        beam_size: int = 1,
        initial_prompt: Optional[str] = DEFAULT_GAMING_INITIAL_PROMPT,
    ):
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self.beam_size = beam_size
        self.initial_prompt = initial_prompt
        self.model: Optional[WhisperModel] = None

    def _ensure_cuda_ready(self) -> None:
        """Validate that CUDA is operational before attempting to load GPU model."""
        if self.device == "cuda":
            _preload_cuda_dlls()
            cuda_count = ctranslate2.get_cuda_device_count()
            if cuda_count < 1:
                raise TranscriberError(
                    "CUDA device requested but no CUDA-compatible GPU detected by CTranslate2. "
                    "Verify NVIDIA driver and CUDA installation."
                )

    def load_model(self) -> WhisperModel:
        """Load the model once and cache the instance."""
        if self.model is not None:
            return self.model

        self._ensure_cuda_ready()

        try:
            self.model = WhisperModel(
                model_size_or_path=self.model_size,
                device=self.device,
                compute_type=self.compute_type,
            )
            return self.model
        except Exception as e:
            raise TranscriberError(
                f"Failed to initialize faster-whisper model '{self.model_size}' "
                f"on {self.device} ({self.compute_type}): {str(e)}"
            ) from e

    def unload_model(self) -> None:
        """Explicitly unloads Faster-Whisper model from GPU/host memory."""
        if self.model is not None:
            del self.model
            self.model = None
            import gc
            gc.collect()

    def __enter__(self):
        self.load_model()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.unload_model()

    def transcribe(self, audio_path: Union[str, Path]) -> Dict[str, Any]:
        """
        Transcribe the audio file on disk, generating word-level timestamped segments.
        Streams audio directly from disk without duplicating the entire file in RAM.
        """
        audio_file = Path(audio_path)
        if not audio_file.exists():
            raise TranscriberError(f"Audio file does not exist: {audio_file}")

        if audio_file.stat().st_size == 0:
            raise TranscriberError(f"Audio file is empty: {audio_file}")

        model = self.load_model()

        try:
            transcribe_kwargs = {
                "beam_size": self.beam_size,
                "word_timestamps": True,
                "vad_filter": True,
                "vad_parameters": dict(min_silence_duration_ms=500),
            }
            if self.initial_prompt:
                transcribe_kwargs["initial_prompt"] = self.initial_prompt

            segments_gen, info = model.transcribe(
                str(audio_file),
                **transcribe_kwargs,
            )

            structured_segments = []
            for seg in segments_gen:
                words_list = []
                if seg.words:
                    for w in seg.words:
                        clean_word = w.word.strip()
                        if clean_word:
                            words_list.append({
                                "start": round(w.start, 2),
                                "end": round(w.end, 2),
                                "word": clean_word,
                            })

                structured_segments.append({
                    "start": round(seg.start, 2),
                    "end": round(seg.end, 2),
                    "text": seg.text.strip(),
                    "words": words_list,
                })

            return {
                "language": info.language,
                "language_probability": round(info.language_probability, 3),
                "duration": round(info.duration, 2),
                "segments": structured_segments,
            }

        except Exception as e:
            raise TranscriberError(f"Transcription failed for {audio_file}: {str(e)}") from e
