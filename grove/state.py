"""Small things Grove remembers between runs, in ~/.config/grove/state.json."""
import json
import os

PATH = os.path.join(os.environ.get('XDG_CONFIG_HOME') or os.path.expanduser('~/.config'), 'grove', 'state.json')


def _load():
    try:
        with open(PATH) as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def get(key, default=None):
    return _load().get(key, default)


def set(key, value):  # noqa: A001 (mirrors get)
    data = _load()
    data[key] = value
    try:
        os.makedirs(os.path.dirname(PATH), exist_ok=True)
        tmp = PATH + '.tmp'
        with open(tmp, 'w') as handle:
            json.dump(data, handle, indent=2)
        os.replace(tmp, PATH)
    except OSError:
        pass
