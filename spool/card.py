import os
import threading

from gi.repository import Gio, GLib, Gtk

from . import OWNER, packages
from .github import fetch_cached, icon_urls
from .model import human_size

SEDGE_ICONS = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sedge', 'apps')


def load_icon(image, entry):
    """Shows the app's own icon: its Sedge icon if Grove carries one, then the
    installed one, otherwise the picture from its repo, downloaded once."""
    bundled = os.path.join(SEDGE_ICONS, f'{entry.title.lower()}.svg')
    if os.path.exists(bundled):
        image.set_from_gicon(Gio.FileIcon.new(Gio.File.new_for_path(bundled)))
        return
    theme = Gtk.IconTheme.get_for_display(image.get_display())
    app_id_name = entry.info.repo[:1].upper() + entry.info.repo[1:]  # app ids keep the repo's name
    for name in (f'io.github.{OWNER}.{app_id_name}', entry.info.repo):
        if theme.has_icon(name):
            image.set_from_icon_name(name)
            return
    image.set_from_icon_name('package-x-generic')

    def fetch():
        path = None
        for remote in icon_urls(entry.info.repo, entry.title):
            path = fetch_cached(remote, f'{entry.info.repo}.svg')
            if path:
                break
        if path:
            GLib.idle_add(lambda: image.set_from_file(path) or False)

    threading.Thread(target=fetch, daemon=True).start()


def badge(text, css=''):
    label = Gtk.Label(label=text, css_classes=['spool-badge', *([css] if css else [])])
    return label


class ActionButtons(Gtk.Box):
    """Install, Update, Open and Uninstall for one app. Used by the card and
    by the detail window."""

    def __init__(self, entry, window, after=None, **kwargs):
        super().__init__(spacing=6, **kwargs)
        self.entry, self.window, self.after = entry, window, after
        self.main = Gtk.Button(valign=Gtk.Align.CENTER, hexpand=True)
        self.main.connect('clicked', self._on_main)
        self.remove_button = Gtk.Button(icon_name='user-trash-symbolic', valign=Gtk.Align.CENTER,
                                        tooltip_text='Uninstall')
        self.remove_button.connect('clicked', self._on_remove)
        self.append(self.main)
        self.append(self.remove_button)
        entry.listen(self.refresh)
        self.refresh()

    def refresh(self):
        e = self.entry
        for cls in ('suggested-action', 'pill'):
            self.main.remove_css_class(cls)
        if e.busy:
            self.main.set_label(e.busy + '…')
            self.main.set_sensitive(False)
            self.remove_button.set_visible(False)
            return
        self.main.set_sensitive(True)
        self.remove_button.set_visible(e.is_installed and e.info.package != 'spool')
        if e.has_update:
            self.main.set_label('Update')
            self.main.add_css_class('suggested-action')
        elif e.is_installed:
            self.main.set_label('Settings' if e.info.is_extension else 'Open')
        else:
            self.main.set_label('Install')
            self.main.add_css_class('suggested-action')

    def _done(self):
        if self.after:
            self.after()

    def _on_main(self, _button):
        e = self.entry
        if e.has_update or not e.is_installed:
            self.window.install([e])
            self._done()
        else:
            self.window.open_app(e)

    def _on_remove(self, _button):
        self.window.confirm_uninstall(self.entry)
        self._done()


class AppCard(Gtk.FlowBoxChild):
    def __init__(self, entry, window):
        super().__init__()
        self.entry, self.window = entry, window
        self._pulse = 0
        self.add_css_class('spool-card-child')

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, css_classes=['card', 'spool-card'])
        self.set_child(box)

        top = Gtk.Box(spacing=14)
        self.icon = Gtk.Image(pixel_size=56, valign=Gtk.Align.START)
        load_icon(self.icon, entry)
        top.append(self.icon)
        names = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, valign=Gtk.Align.CENTER, hexpand=True)
        names.append(Gtk.Label(label=entry.title, xalign=0, css_classes=['spool-name']))
        self.version = Gtk.Label(xalign=0, css_classes=['dim-label', 'caption'])
        names.append(self.version)
        top.append(names)
        box.append(top)

        box.append(Gtk.Label(label=entry.info.description, xalign=0, wrap=True, lines=3, vexpand=True,
                             ellipsize=3, valign=Gtk.Align.START, natural_wrap_mode=0,
                             max_width_chars=26, width_chars=24, css_classes=['dim-label']))

        self.badges = Gtk.Box(spacing=6, height_request=22)
        box.append(self.badges)

        self.bar = Gtk.ProgressBar(visible=False)
        box.append(self.bar)
        self.actions = ActionButtons(entry, window)
        box.append(self.actions)

        click = Gtk.GestureClick()
        click.connect('released', lambda *_: window.show_details(entry))
        top.add_controller(click)

        entry.listen(self.refresh)
        self.refresh()

    def refresh(self):
        e = self.entry
        if e.is_installed:
            text = f'Installed {e.installed}'
            if e.has_update:
                text += f'  ·  {e.info.version} available'
        else:
            text = f'Version {e.info.version}  ·  {human_size(e.info.deb_size)}'
        self.version.set_label(text)

        child = self.badges.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self.badges.remove(child)
            child = nxt
        if e.needs_logout:
            self.badges.append(badge('Log out to turn on', 'logout'))
        elif e.has_update:
            self.badges.append(badge('Update available', 'update'))
        elif e.is_installed:
            self.badges.append(badge('Installed', 'ok'))
        self.badges.append(badge('Shell extension' if e.info.is_extension else 'App'))

        self.bar.set_visible(bool(e.busy))
        if e.busy == 'Downloading':
            self.bar.set_fraction(e.progress)
        elif e.busy and not self._pulse:
            self._pulse = GLib.timeout_add(120, self._tick)

    def _tick(self):
        if not self.entry.busy or self.entry.busy == 'Downloading':
            self._pulse = 0
            return False
        self.bar.pulse()
        return True
