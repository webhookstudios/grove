"""Finds the apps on GitHub: every public repo of the owner whose latest
release carries a .deb package."""
import json
import os
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from . import OWNER, __version__

API = 'https://api.github.com'
RAW = 'https://raw.githubusercontent.com'
CACHE_DIR = os.path.join(os.environ.get('XDG_CACHE_HOME') or os.path.expanduser('~/.cache'), 'grove')


class GitHubError(Exception):
    pass


class RateLimited(GitHubError):
    pass


@dataclass
class AppInfo:
    repo: str
    title: str
    description: str
    tag: str
    version: str
    package: str
    deb_name: str
    deb_url: str
    deb_size: int
    deb_digest: str
    is_extension: bool
    extension_uuid: str
    arch: str
    html_url: str
    notes: str
    published: str
    pushed: str


def _headers(etag=None, accept='application/vnd.github+json'):
    headers = {'User-Agent': f'grove/{__version__}', 'Accept': accept,
               'X-GitHub-Api-Version': '2022-11-28'}
    if etag:
        headers['If-None-Match'] = etag
    return headers


def _open(url, etag=None):
    request = urllib.request.Request(url, headers=_headers(etag))
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return response.status, response.read(), response.headers.get('ETag')
    except urllib.error.HTTPError as error:
        if error.code == 304:
            return 304, b'', etag
        if error.code == 404:
            return 404, b'', None
        if error.code in (403, 429):
            reset = error.headers.get('X-RateLimit-Reset')
            when = ''
            if reset and reset.isdigit():
                when = ' Try again at ' + time.strftime('%H:%M', time.localtime(int(reset))) + '.'
            raise RateLimited('GitHub is limiting requests from this computer.' + when)
        raise GitHubError(f'GitHub answered with error {error.code}.')
    except (urllib.error.URLError, TimeoutError, OSError):
        raise GitHubError('Could not reach GitHub. Check your internet connection.')


class Client:
    """Small GitHub client. Answers are cached on disk with their ETag, so
    an unchanged answer costs no rate limit, and the last answers still work
    with no connection."""

    def __init__(self):
        self._path = os.path.join(CACHE_DIR, 'api.json')
        self._lock = threading.Lock()
        self.stale = False
        try:
            with open(self._path) as handle:
                self._cache = json.load(handle)
        except (OSError, ValueError):
            self._cache = {}

    def _save(self):
        try:
            os.makedirs(CACHE_DIR, exist_ok=True)
            with self._lock, open(self._path, 'w') as handle:
                json.dump(self._cache, handle)
        except OSError:
            pass

    def get(self, url):
        with self._lock:
            cached = self._cache.get(url)
        try:
            status, body, etag = _open(url, cached['etag'] if cached else None)
        except GitHubError:
            if cached is None:
                raise
            self.stale = True
            return cached['data']
        if status == 304 and cached:
            return cached['data']
        if status == 404:
            return None
        data = json.loads(body)
        with self._lock:
            self._cache[url] = {'etag': etag, 'data': data}
        return data

    def catalog(self):
        repos = self.get(f'{API}/users/{OWNER}/repos?per_page=100&type=owner') or []
        repos = [r for r in repos if not r.get('fork') and not r.get('archived')]

        def one(repo):
            release = self.get(f"{API}/repos/{OWNER}/{repo['name']}/releases/latest")
            return self._info(repo, release)

        with ThreadPoolExecutor(max_workers=6) as pool:
            found = [i for i in pool.map(one, repos) if i]
        self._save()
        return sorted(found, key=lambda i: i.title.lower())

    @staticmethod
    def _info(repo, release):
        if not release:
            return None
        assets = release.get('assets', [])
        deb = next((a for a in assets if a['name'].endswith('.deb')), None)
        if deb is None:
            return None
        tag = release.get('tag_name', '')
        zipped = next((a['name'] for a in assets if a['name'].endswith('.shell-extension.zip')), '')
        return AppInfo(
            repo=repo['name'],
            title=repo['name'][:1].upper() + repo['name'][1:],
            description=repo.get('description') or '',
            tag=tag,
            version=tag.lstrip('vV'),
            package=deb['name'].split('_')[0],
            deb_name=deb['name'],
            deb_url=deb['browser_download_url'],
            deb_size=deb.get('size', 0),
            deb_digest=deb.get('digest') or '',
            is_extension=bool(zipped),
            extension_uuid=zipped[:-len('.shell-extension.zip')] if zipped else '',
            arch=deb['name'][:-len('.deb')].rsplit('_', 1)[-1] if deb['name'].count('_') >= 2 else 'all',
            html_url=repo['html_url'],
            notes=(release.get('body') or '').strip(),
            published=(release.get('published_at') or '')[:10],
            pushed=repo.get('pushed_at') or '',
        )

    def screenshots(self, repo):
        listing = self.get(f'{API}/repos/{OWNER}/{repo}/contents/docs/screenshots')
        if not isinstance(listing, list):
            return []
        self._save()
        return [f['download_url'] for f in listing
                if f.get('download_url') and f['name'].lower().endswith(('.png', '.jpg', '.jpeg', '.webp'))]


def download(url, destination, progress=None, digest=''):
    """Saves a file, reporting a 0 to 1 fraction, and checks its SHA-256."""
    import hashlib
    request = urllib.request.Request(url, headers=_headers(accept='application/octet-stream'))
    sha = hashlib.sha256()
    try:
        with urllib.request.urlopen(request, timeout=30) as response, open(destination, 'wb') as out:
            total = int(response.headers.get('Content-Length') or 0)
            done = 0
            while True:
                chunk = response.read(64 * 1024)
                if not chunk:
                    break
                out.write(chunk)
                sha.update(chunk)
                done += len(chunk)
                if progress and total:
                    progress(done / total)
    except (urllib.error.URLError, TimeoutError, OSError):
        raise GitHubError('The download failed. Check your internet connection.')
    if digest.startswith('sha256:') and sha.hexdigest() != digest[7:]:
        raise GitHubError('The downloaded file did not match its checksum, so it was not installed.')


def fetch_cached(url, name):
    """Downloads a small image once and keeps it. Returns the path or None."""
    folder = os.path.join(CACHE_DIR, 'images')
    path = os.path.join(folder, name)
    if os.path.exists(path):
        return path
    try:
        os.makedirs(folder, exist_ok=True)
        status, body, _ = _open(url)
        if status != 200:
            return None
        with open(path, 'wb') as handle:
            handle.write(body)
        return path
    except (GitHubError, OSError):
        return None


def icon_urls(repo, title):
    """Where a repo keeps its icon: the app-id name first, then the repo name."""
    base = f'{RAW}/{OWNER}/{repo}/HEAD/data'
    return [f'{base}/io.github.{OWNER}.{title}.svg', f'{base}/{repo}.svg']
