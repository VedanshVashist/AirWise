"""Install Airwise's optional, local Windows x64 inference engine."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import hashlib
import os
import platform
import shutil
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parent / ".airwise" / "ai"
MODEL = "qwen2.5-1.5b-instruct-q4_k_m.gguf"


def download(name, url, checksum):
    path = ROOT / name
    if path.exists() and digest(path) == checksum:
        return path
    temporary = path.with_suffix(".partial")
    with urllib.request.urlopen(url, timeout=120) as source, temporary.open("wb") as target:
        shutil.copyfileobj(source, target, 1024 * 1024)
    if digest(temporary) != checksum:
        temporary.unlink()
        raise ValueError(f"Checksum mismatch for {name}")
    temporary.replace(path)
    return path


def digest(path):
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def engine():
    name = "llama-b12723-bin-win-cpu-x64.zip"
    archive = download(name, "https://github.com/ggml-org/llama.cpp/releases/download/b12723/" + name,
                       "414e0f4e85b80a1b58d26904a2174016c9fdcf5d21b22130088e797673d9062f")
    with zipfile.ZipFile(archive) as bundle:
        for member in bundle.infolist():
            filename = Path(member.filename).name
            if filename.endswith(".dll") or filename in ("llama-server.exe", "LICENSE", "LICENSE.md"):
                with bundle.open(member) as source, (ROOT / filename).open("wb") as target:
                    shutil.copyfileobj(source, target)


def model():
    download(MODEL, "https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/"
             "91cad51170dc346986eccefdc2dd33a9da36ead9/" + MODEL,
             "6a1a2eb6d15622bf3c96857206351ba97e1af16c30d7a74ee38970e434e9407e")


if __name__ == "__main__":
    if os.name != "nt" or platform.machine().lower() not in ("amd64", "x86_64"):
        raise SystemExit("This installer supports Windows x64. On other systems set AIRWISE_MODEL_URL and AIRWISE_MODEL.")
    ROOT.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(2) as pool:
        jobs = [pool.submit(task) for task in (engine, model)]
        for job in jobs:
            job.result()
    print("Local AI is ready.")
