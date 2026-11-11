"""Asks dpkg about installed apps, and installs or removes them with apt."""
import os
import subprocess
import threading


def installed_versions(packages):
    """{package: version} for the ones that are installed."""
    if not packages:
        return {}
    result = subprocess.run(
        ['dpkg-query', '-W', '-f', '${Package}\t${db:Status-Abbrev}\t${Version}\n', *packages],
        capture_output=True, text=True)
    found = {}
    for line in result.stdout.splitlines():
        parts = line.split('\t')
        if len(parts) == 3 and parts[1].startswith('ii'):
            found[parts[0]] = parts[2]
    return found


def is_newer(candidate, installed):
    return subprocess.run(['dpkg', '--compare-versions', candidate, 'gt', installed]).returncode == 0


def package_files(package):
    result = subprocess.run(['dpkg', '-L', package], capture_output=True, text=True)
    return result.stdout.splitlines() if result.returncode == 0 else []


def desktop_file(package):
    for path in package_files(package):
        if path.startswith('/usr/share/applications/') and path.endswith('.desktop'):
            return path
    return None


def run_root(argv, on_output=None):
    """Runs a command as root through polkit. Returns (exit code, output).
    pkexec exits with 126 when the password prompt is dismissed and 127 when
    the user is not allowed."""
    env = dict(os.environ, DEBIAN_FRONTEND='noninteractive', LC_ALL='C.UTF-8')
    process = subprocess.Popen(['pkexec', 'env', 'DEBIAN_FRONTEND=noninteractive', *argv],
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env)
    lines = []
    for line in process.stdout:
        lines.append(line)
        if on_output:
            on_output(line.rstrip())
    process.wait()
    return process.returncode, ''.join(lines)


def in_thread(work, done):
    """Runs work() off the main loop, then done(result, error) on it."""
    from gi.repository import GLib

    def run():
        try:
            result, error = work(), None
        except Exception as exc:  # reported to the user, not swallowed
            result, error = None, exc
        GLib.idle_add(lambda: done(result, error) or False)

    threading.Thread(target=run, daemon=True).start()
