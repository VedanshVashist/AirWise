"""Lifecycle of the optional local inference process and hosted model selection."""
import atexit
import os
import socket
import subprocess
import threading
import time
from pathlib import Path

from http_client import remote

model_lock = threading.Lock()
model_process = None
model_url = None


def inference_url():
    global model_process, model_url
    configured = os.getenv("AIRWISE_MODEL_URL")
    if configured:
        return configured.rstrip("/")
    folder = Path(__file__).resolve().parent / ".airwise" / "ai"
    binary = folder / "llama-server.exe"
    model = next(folder.glob("*.gguf"), None)
    if not binary.exists() or model is None:
        raise RuntimeError("Local AI has not been installed.")
    with model_lock:
        if model_process is not None and model_process.poll() is None:
            return model_url
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        model_url = f"http://127.0.0.1:{port}/v1"
        model_process = subprocess.Popen([str(binary), "-m", str(model), "--host", "127.0.0.1", "--port", str(port),
                                          "-c", "4096", "-np", "1", "-t", str(min(8, os.cpu_count() or 4))],
                                         cwd=folder, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        for _ in range(120):
            if model_process.poll() is not None:
                break
            try:
                remote(f"http://127.0.0.1:{port}/health", timeout=1)
                return model_url
            except OSError:
                time.sleep(.5)
        if model_process.poll() is None:
            model_process.terminate()
        raise RuntimeError("Local AI could not start.")


@atexit.register
def stop_model():
    if model_process and model_process.poll() is None:
        model_process.terminate()
