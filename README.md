# Grove

*Formerly Spool. Part of the Sedge family of webhookstudios apps.*

One library for every [webhookstudios](https://github.com/webhookstudios) app on Ubuntu. Browse them as cards, install, update or remove any of them with a click, and see new versions as soon as you open it.

![The Grove library](docs/screenshots/library.png)

## What it does

- **Finds the apps by itself.** It reads webhookstudios' public repos on GitHub and lists every one whose latest release has a `.deb`. A new app shows up the day it is released, with no update to Grove.
- **Checks for updates every time it opens**, and shows a banner with an **Update all** button.
- **Installs, updates and removes** through apt, so dependencies are handled and everything appears in the normal package list. You are asked for your password once, by the standard system prompt.
- **Shows each app's details:** description, versions, size, release notes and its screenshots.
- **Works offline** with the last list it saw, and tells you it may be out of date.
- Downloads are checked against the checksum GitHub publishes before anything is installed.

![An app's details, with its screenshots](docs/screenshots/details.png)

## Requirements

- Ubuntu 26.04 (any recent Debian-based system with GTK 4 and libadwaita 1.5 or later should work)
- An internet connection to see new apps and versions

## Install

### With the deb package (recommended)

Download `spool_1.1.0_all.deb` from the [latest release](https://github.com/webhookstudios/spool/releases/latest), then install it:

```bash
sudo apt install ./spool_1.1.0_all.deb
```

Open **Grove** from the apps menu. After that, Grove can update itself like any other app in the list.

To remove it:

```bash
sudo apt remove spool
```

### From source

```bash
git clone https://github.com/webhookstudios/spool.git
```

```bash
./spool/install.sh
```

## Using it

| To do this | Do this |
|---|---|
| Install an app | Click **Install** on its card |
| Update one app | Click **Update** on its card |
| Update everything | Click **Update all** in the banner |
| Open an app | Click **Open** (for a shell extension it opens its settings) |
| Remove an app | Click the trash icon, then confirm |
| See details and screenshots | Click an app's icon or name |
| Check again | Click the refresh button at the top left |

The **Installed** and **Updates** tabs filter the list, and the search box matches names and descriptions.

Shell extensions, such as Sprig and Sheaf, only turn on after you log out and back in. Grove reminds you when you install one.

## How it works

Grove asks the GitHub API for the owner's repos and each one's latest release. Answers are cached in `~/.cache/spool` with their ETag, so an unchanged answer costs nothing against GitHub's limit of 60 requests an hour for anonymous use. Installed versions come from `dpkg-query`. Installing downloads the `.deb` files to a temporary folder and runs `apt-get install` through `pkexec`; removing runs `apt-get remove`.

| File | Purpose |
|---|---|
| `spool/github.py` | Finds apps and releases, downloads and checks files |
| `spool/packages.py` | Installed versions, install and remove through polkit |
| `spool/window.py` | The main window, filters, install and update flows |
| `spool/card.py`, `spool/details.py` | The app cards and the details window |

## Limitations

- Only apps with a `.deb` in their latest GitHub release are listed.
- GitHub allows 60 anonymous requests an hour. Opening Grove uses about ten, and unchanged answers are free, so this is only a problem if you reopen it dozens of times in an hour.
- Removing an app keeps its settings, the way `apt remove` does.

## Development

```bash
python3 bin/spool
```

Build the deb package into `dist/` with `./build-deb.sh` (needs only `dpkg-deb`).

## License

GPL-2.0-or-later. See [LICENSE](LICENSE).
