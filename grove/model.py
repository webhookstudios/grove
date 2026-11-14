"""One app in the library: what GitHub says, and what is installed here."""
from . import packages


class Entry:
    def __init__(self, info):
        self.info = info
        self.installed = None      # installed version, or None
        self.has_update = False
        self.busy = ''             # '', 'Downloading', 'Installing', 'Removing'
        self.progress = 0.0
        self.needs_logout = False  # an extension that was just installed
        self._listeners = []

    @property
    def title(self):
        return self.info.title

    @property
    def is_installed(self):
        return self.installed is not None

    @property
    def available(self):
        """False when the app is built for another kind of computer."""
        return self.info.arch == 'all' or self.info.arch == packages.architecture()

    @property
    def summary(self):
        return first_sentence(self.info.description)

    def set_installed(self, version):
        self.installed = version
        self.has_update = bool(version) and packages.is_newer(self.info.version, version)

    def listen(self, callback):
        self._listeners.append(callback)

    def unlisten(self, callback):
        if callback in self._listeners:
            self._listeners.remove(callback)

    def changed(self):
        for callback in self._listeners:
            callback()


def human_size(size):
    for unit in ('B', 'KB', 'MB', 'GB'):
        if size < 1024 or unit == 'GB':
            return f'{size:.0f} {unit}' if unit == 'B' else f'{size:.1f} {unit}'
        size /= 1024


ARCH_NAMES = {'amd64': '64-bit Intel and AMD', 'arm64': '64-bit ARM', 'armhf': '32-bit ARM', 'i386': '32-bit Intel'}


def arch_note(info):
    return f"Made for {ARCH_NAMES.get(info.arch, info.arch)} computers only."


def first_sentence(text):
    text = (text or '').strip()
    for i, ch in enumerate(text):
        if ch == '.' and (i + 1 == len(text) or text[i + 1] == ' '):
            return text[:i + 1]
    return text
