"""Fetch the fixed pretrained model during image preparation, never at runtime."""
import argparse
import hashlib
import os
from pathlib import Path
import tempfile
import urllib.request

URL = "https://github.com/ultralytics/assets/releases/download/v8.4.0/yolo26n.pt"
SHA256 = "9b09cc8bf347f0fc8a5f7657480587f25db09b34bf33b0652110fb03a8ad4fef"


def download(path):
    path = Path(path)
    if path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == SHA256:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, suffix=".download")
    try:
        digest = hashlib.sha256()
        with os.fdopen(fd, "wb") as output, urllib.request.urlopen(URL, timeout=60) as response:
            while chunk := response.read(1024*1024):
                digest.update(chunk)
                output.write(chunk)
        if digest.hexdigest() != SHA256:
            raise ValueError("Empreinte du modèle YOLO incorrecte : téléchargement refusé.")
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="/opt/models/yolo26n.pt")
    download(parser.parse_args().output)
