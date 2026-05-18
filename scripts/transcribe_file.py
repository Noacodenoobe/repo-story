#!/usr/bin/env python3
"""
Transcribe a 16 kHz mono WAV file with faster-whisper (audio-core venv).

Usage:
    python transcribe_file.py /path/to/audio.wav

Prints JSON to stdout: {"text": "...", "language": "pl", "model": "medium"}
On failure: {"error": "..."} and exit code 1.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def _is_cuda_runtime_error(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return any(
        token in msg
        for token in ("cublas", "cuda", "cudnn", "out of memory", "oom")
    )


def _transcribe_with_device(
    wav_path: Path,
    model_size: str,
    device: str,
    compute_type: str,
) -> dict:
    """Run faster-whisper on a single file with explicit device."""
    from faster_whisper import WhisperModel

    models_dir = os.getenv(
        "HF_HOME",
        os.getenv("WHISPER_MODELS_DIR", "/mnt/ollama/whisper_models"),
    )
    language = os.getenv("STT_LANGUAGE", "pl")

    model = WhisperModel(
        model_size,
        device=device,
        compute_type=compute_type,
        download_root=models_dir,
    )
    segments, info = model.transcribe(
        str(wav_path),
        language=language,
        beam_size=5,
        vad_filter=True,
        vad_parameters={
            "min_silence_duration_ms": int(os.getenv("STT_VAD_MIN_SILENCE_MS", "400")),
        },
        no_speech_threshold=float(os.getenv("STT_NO_SPEECH_THRESHOLD", "0.65")),
        log_prob_threshold=float(os.getenv("STT_LOG_PROB_THRESHOLD", "-0.8")),
        compression_ratio_threshold=float(os.getenv("STT_COMPRESSION_RATIO", "2.2")),
    )
    seg_list = list(segments)
    text = " ".join(s.text.strip() for s in seg_list if s.text.strip())
    avg_logprob: float | None = None
    probs = [s.avg_logprob for s in seg_list if getattr(s, "avg_logprob", None) is not None]
    if probs:
        avg_logprob = round(sum(probs) / len(probs), 3)
    return {
        "text": text,
        "language": info.language or language,
        "duration_s": round(float(info.duration or 0), 2),
        "model": model_size,
        "device": device,
        "avg_logprob": avg_logprob,
    }


def _transcribe(wav_path: Path, model_size: str) -> dict:
    """Run faster-whisper; fall back to CPU if CUDA libraries are missing."""
    device = os.getenv("STT_DEVICE", "cuda")
    compute_type = os.getenv("STT_COMPUTE_TYPE", "float16")

    try:
        return _transcribe_with_device(wav_path, model_size, device, compute_type)
    except Exception as exc:  # noqa: BLE001
        if device == "cpu" or not _is_cuda_runtime_error(exc):
            raise
        return _transcribe_with_device(wav_path, model_size, "cpu", "int8")


def main() -> None:
    """CLI entry: argv[1] = WAV path."""
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Brak ścieżki do pliku WAV."}, ensure_ascii=False))
        sys.exit(1)

    wav_path = Path(sys.argv[1])
    if not wav_path.is_file():
        print(
            json.dumps({"error": f"Plik nie istnieje: {wav_path}"}, ensure_ascii=False),
        )
        sys.exit(1)

    primary = os.getenv("STT_MODEL", "medium")
    fallback = os.getenv("STT_FALLBACK_MODEL", "base")

    try:
        result = _transcribe(wav_path, primary)
    except Exception as exc:  # noqa: BLE001
        if primary == fallback:
            print(json.dumps({"error": str(exc)}, ensure_ascii=False))
            sys.exit(1)
        try:
            result = _transcribe(wav_path, fallback)
            result["model"] = fallback
            result["fallback"] = True
        except Exception as exc2:  # noqa: BLE001
            print(json.dumps({"error": str(exc2)}, ensure_ascii=False))
            sys.exit(1)

    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
