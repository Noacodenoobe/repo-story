#!/usr/bin/env python3
"""Collect system profile as JSON (stdout). No secrets."""
from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path


def _run(cmd: list[str], timeout: int = 10) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
        return (r.stdout or r.stderr or "").strip()
    except Exception:
        return ""


def _tool_version(name: str) -> str:
    path = shutil.which(name)
    if not path:
        return "not_found"
    out = _run([path, "--version"]) or _run([path, "-V"])
    return (out.split("\n")[0] if out else path)[:120]


def main() -> None:
    host = {
        "hostname": platform.node(),
        "kernel": platform.release(),
        "os": platform.platform(),
    }
    if Path("/etc/os-release").is_file():
        for line in Path("/etc/os-release").read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("PRETTY_NAME="):
                host["os"] = line.split("=", 1)[1].strip().strip('"')
                break

    gpu: list[dict] = []
    if shutil.which("nvidia-smi"):
        raw = _run([
            "nvidia-smi", "--query-gpu=name,driver_version,memory.total",
            "--format=csv,noheader",
        ])
        for line in raw.splitlines():
            parts = [p.strip() for p in line.split(",")]
            if parts:
                gpu.append({
                    "name": parts[0],
                    "driver": parts[1] if len(parts) > 1 else "",
                    "memory": parts[2] if len(parts) > 2 else "",
                })

    tools = {n: _tool_version(n) for n in (
        "python3", "node", "npm", "go", "docker", "git", "ollama",
        "make", "gcc", "pipewire", "pactl", "pw-cli",
    )}

    ollama_models: list[str] = []
    if shutil.which("ollama"):
        raw = _run(["ollama", "list"])
        for line in raw.splitlines()[1:]:
            parts = line.split()
            if parts:
                ollama_models.append(parts[0])

    audio = "unknown"
    if shutil.which("pw-cli"):
        audio = "PipeWire"
    elif shutil.which("pactl"):
        audio = "PulseAudio"

    config_paths = []
    home = Path.home()
    for p in (
        home / ".config" / "ollama",
        home / ".ollama",
        home / ".config" / "Cursor",
        home / ".cursor",
        home / ".bashrc",
    ):
        if p.exists():
            config_paths.append(str(p))

    env_safe = {
        k: os.environ[k][:200]
        for k in sorted(os.environ)
        if k.startswith(("CUDA_", "OLLAMA_", "PATH", "HOME", "USER"))
    }

    mem_kb = 0
    mem_path = Path("/proc/meminfo")
    if mem_path.is_file():
        for line in mem_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("MemTotal:"):
                mem_kb = int(line.split()[1])
                break
    mem_gb = round(mem_kb / 1024 / 1024, 1) if mem_kb else 0

    disk_root = {}
    try:
        st = os.statvfs("/")
        disk_root = {
            "free_gb": round((st.f_bavail * st.f_frsize) / (1024**3), 1),
            "total_gb": round((st.f_blocks * st.f_frsize) / (1024**3), 1),
        }
    except OSError:
        pass

    whisper_info = {
        "openai_whisper_cli": shutil.which("whisper") or "not_found",
        "faster_whisper_models_dir": "/mnt/ollama/whisper_models",
        "faster_whisper_models": [],
        "audio_core_venv": "/mnt/ollama/ai-envs/audio-core/.venv",
    }
    models_dir = Path("/mnt/ollama/whisper_models")
    if models_dir.is_dir():
        whisper_info["faster_whisper_models"] = [
            p.name.replace("models--Systran--", "")
            for p in models_dir.iterdir()
            if p.is_dir() and p.name.startswith("models--")
        ]
    try:
        import importlib.util
        venv_py = Path("/mnt/ollama/ai-envs/audio-core/.venv/bin/python")
        if venv_py.is_file():
            whisper_info["faster_whisper_installed"] = True
        else:
            whisper_info["faster_whisper_installed"] = False
    except Exception:
        whisper_info["faster_whisper_installed"] = False

    profile = {
        "host": host,
        "cpu": {"model": platform.processor() or "unknown", "cores": os.cpu_count() or 1},
        "memory": {"total_kb": mem_kb, "total_gb": mem_gb},
        "disk_root": disk_root,
        "whisper": whisper_info,
        "gpu": gpu,
        "tools": tools,
        "ollama_models": ollama_models,
        "audio": {"server": audio},
        "path": os.environ.get("PATH", ""),
        "config_paths": config_paths,
        "environment": env_safe,
    }
    print(json.dumps(profile, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
