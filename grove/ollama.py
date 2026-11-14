"""Ollama, which Fleece needs to run its models. It isn't in Ubuntu's software
sources, so the setup checklist installs it with the official installer from
ollama.com, in the same password prompt as the apps."""
import os
import shutil
import urllib.request

from . import __version__, packages

INSTALLER = 'https://ollama.com/install.sh'
NEEDS = ['curl', 'zstd']          # what the installer itself needs, from apt
ARCHES = ('amd64', 'arm64')       # what the installer supports

# Runs as root: the apps first, then the installer. 10 means apt failed,
# 20 means the apps are in but Ollama is not.
ROOT_SCRIPT = 'apt-get install -y "$@" || exit 10\nsh "$GROVE_OLLAMA" || exit 20\n'


def installed():
    return bool(shutil.which('ollama')) or any(
        os.path.exists(p) for p in ('/usr/local/bin/ollama', '/usr/bin/ollama'))


def supported():
    return packages.architecture() in ARCHES


def download_size():
    """How big the installer's download is, in bytes, or 0 if unknown."""
    url = f'https://ollama.com/download/ollama-linux-{packages.architecture()}.tar.zst'
    request = urllib.request.Request(url, method='HEAD', headers={'User-Agent': f'grove/{__version__}'})
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return int(response.headers.get('Content-Length') or 0)
    except (OSError, ValueError):
        return 0
