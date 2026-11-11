import os
import shutil
import tempfile

from gi.repository import Adw, Gio, GLib, Gtk

from . import OWNER, __version__, packages
from .card import AppCard
from .details import DetailsDialog
from .github import Client, GitHubError, download
from .model import Entry


class GroveWindow(Adw.ApplicationWindow):
    def __init__(self, **kwargs):
        super().__init__(title='Grove', default_width=1000, default_height=720, **kwargs)
        self.client = Client()
        self.entries = []
        self.cards = {}
        self.mode = 'all'

        self.toasts = Adw.ToastOverlay()
        self.set_content(self.toasts)
        view = Adw.ToolbarView()
        self.toasts.set_child(view)

        header = Adw.HeaderBar()
        self.filters = Gtk.Box(css_classes=['linked'])
        first = None
        self.filter_buttons = {}
        for key, label in (('all', 'All'), ('installed', 'Installed'), ('updates', 'Updates')):
            button = Gtk.ToggleButton(label=label, group=first, active=key == 'all')
            first = first or button
            button.connect('toggled', self._on_filter, key)
            self.filters.append(button)
            self.filter_buttons[key] = button
        header.set_title_widget(self.filters)

        self.refresh_button = Gtk.Button(icon_name='view-refresh-symbolic', tooltip_text='Check for updates')
        self.refresh_button.connect('clicked', lambda *_: self.reload())
        header.pack_start(self.refresh_button)

        about = Gtk.Button(icon_name='help-about-symbolic', tooltip_text='About Grove')
        about.connect('clicked', self._on_about)
        header.pack_end(about)
        self.search = Gtk.SearchEntry(placeholder_text='Search apps', width_chars=22)
        self.search.connect('search-changed', lambda *_: self.flow.invalidate_filter())
        header.pack_end(self.search)
        view.add_top_bar(header)

        self.banner = Adw.Banner(revealed=False, button_label='Update all')
        self.banner.connect('button-clicked', lambda *_: self.install([e for e in self.entries if e.has_update]))
        view.add_top_bar(self.banner)

        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        view.set_content(self.stack)

        self.stack.add_named(Adw.StatusPage(title='Checking GitHub…', child=Adw.Spinner(width_request=48, height_request=48)),
                             'loading')
        self.error_page = Adw.StatusPage(icon_name='network-offline-symbolic', title='Could not load the library')
        retry = Gtk.Button(label='Try again', halign=Gtk.Align.CENTER, css_classes=['pill', 'suggested-action'])
        retry.connect('clicked', lambda *_: self.reload())
        self.error_page.set_child(retry)
        self.stack.add_named(self.error_page, 'error')

        self.flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, homogeneous=True, min_children_per_line=1,
                                max_children_per_line=4, column_spacing=14, row_spacing=14, margin_top=18,
                                margin_bottom=18, margin_start=18, margin_end=18, valign=Gtk.Align.START)
        self.flow.set_filter_func(self._filter)
        self.flow.set_sort_func(self._sort)
        scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
        clamp = Adw.Clamp(maximum_size=1100, tightening_threshold=900)
        clamp.set_child(self.flow)
        scroll.set_child(clamp)
        self.stack.add_named(scroll, 'apps')

        self.nothing = Adw.StatusPage(icon_name='system-search-symbolic', title='Nothing here')
        self.stack.add_named(self.nothing, 'nothing')

        self.reload()

    # ---- loading ---------------------------------------------------------

    def reload(self):
        self.refresh_button.set_sensitive(False)
        if not self.entries:
            self.stack.set_visible_child_name('loading')

        def work():
            infos = self.client.catalog()
            installed = packages.installed_versions([i.package for i in infos] + ['grove'])
            return infos, installed

        packages.in_thread(work, self._loaded)

    def _loaded(self, result, error):
        self.refresh_button.set_sensitive(True)
        if error:
            if self.entries:
                self.toasts.add_toast(Adw.Toast(title=str(error)))
            else:
                self.error_page.set_description(str(error))
                self.stack.set_visible_child_name('error')
            return
        infos, installed = result
        old = {e.info.repo: e for e in self.entries}
        self.entries = []
        for info in infos:
            entry = old.get(info.repo) or Entry(info)
            entry.info = info
            entry.set_installed(installed.get(info.package))
            if entry.installed is None:
                entry.needs_logout = False
            self.entries.append(entry)
            if info.repo not in self.cards:
                card = AppCard(entry, self)
                self.cards[info.repo] = card
                self.flow.append(card)
            entry.changed()
        self._after_change()
        if self.client.stale:
            self.toasts.add_toast(Adw.Toast(title='You are offline, so this list may be out of date.'))
        self.stack.set_visible_child_name('apps')
        self.flow.invalidate_filter()
        self.flow.invalidate_sort()

    def _after_change(self):
        updates = [e for e in self.entries if e.has_update]
        self.banner.set_revealed(bool(updates))
        if updates:
            names = ', '.join(e.title for e in updates[:3]) + (' and more' if len(updates) > 3 else '')
            self.banner.set_title(f"{len(updates)} update{'s' if len(updates) != 1 else ''} available: {names}")
        label = 'Updates' if not updates else f'Updates ({len(updates)})'
        self.filter_buttons['updates'].set_label(label)
        self.flow.invalidate_filter()

    # ---- filtering -------------------------------------------------------

    def _on_filter(self, button, key):
        if button.get_active():
            self.mode = key
            self.flow.invalidate_filter()

    def _filter(self, child):
        e = child.entry
        if self.mode == 'installed' and not e.is_installed:
            return False
        if self.mode == 'updates' and not e.has_update:
            return False
        q = self.search.get_text().strip().lower()
        shown = not q or q in e.title.lower() or q in e.info.description.lower()
        GLib.idle_add(self._check_empty)
        return shown

    def _check_empty(self):
        if self.stack.get_visible_child_name() not in ('apps', 'nothing'):
            return False
        any_shown = any(c.get_child_visible() for c in self.cards.values())
        if not any_shown:
            self.nothing.set_description({'installed': 'None of these apps are installed yet.',
                                          'updates': 'Everything is up to date.'}.get(self.mode, 'No app matches your search.'))
        self.stack.set_visible_child_name('apps' if any_shown else 'nothing')
        return False

    def _sort(self, a, b):
        ea, eb = a.entry, b.entry
        ka = (not ea.has_update, ea.title.lower())
        kb = (not eb.has_update, eb.title.lower())
        return (ka > kb) - (ka < kb)

    # ---- actions ---------------------------------------------------------

    def show_details(self, entry):
        DetailsDialog(entry, self).present(self)

    def open_app(self, entry):
        path = packages.desktop_file(entry.info.package)
        app = Gio.DesktopAppInfo.new_from_filename(path) if path else None
        if app is None:
            self.toasts.add_toast(Adw.Toast(title=f'{entry.title} has no window to open.'))
            return
        if entry.needs_logout:
            self.toasts.add_toast(Adw.Toast(title='Log out and back in first, so it can turn on.'))
        app.launch([], None)

    def install(self, entries):
        entries = [e for e in entries if not e.busy]
        if not entries:
            return
        for e in entries:
            e.busy, e.progress = 'Downloading', 0.0
            e.changed()

        def work():
            folder = tempfile.mkdtemp(prefix='grove-')
            try:
                paths = []
                for e in entries:
                    path = os.path.join(folder, e.info.deb_name)
                    download(e.info.deb_url, path,
                             lambda f, e=e: GLib.idle_add(self._progress, e, f), e.info.deb_digest)
                    os.chmod(path, 0o644)
                    paths.append(path)
                GLib.idle_add(self._set_busy, entries, 'Installing')
                return packages.run_root(['apt-get', 'install', '-y', *paths])
            finally:
                shutil.rmtree(folder, ignore_errors=True)

        packages.in_thread(work, lambda r, err: self._install_done(entries, r, err))

    def _progress(self, entry, fraction):
        entry.progress = fraction
        entry.changed()
        return False

    def _set_busy(self, entries, text):
        for e in entries:
            e.busy = text
            e.changed()
        return False

    def _install_done(self, entries, result, error):
        names = ', '.join(e.title for e in entries)
        if error:
            return self._fail(entries, str(error))
        code, output = result
        if code in (126, 127):
            return self._fail(entries, 'Cancelled. Nothing was installed.')
        if code != 0:
            return self._fail(entries, 'The install did not finish.', output)
        fresh = [e for e in entries if e.info.is_extension and not e.is_installed]
        self._settle(entries)
        for e in fresh:
            e.needs_logout = e.is_installed
            e.changed()
        extension = any(e.info.is_extension for e in entries)
        toast = Adw.Toast(title=f'{names} installed.' + (' Log out and back in to turn on new extensions.' if extension else ''))
        toast.set_timeout(8)
        self.toasts.add_toast(toast)

    def confirm_uninstall(self, entry):
        dialog = Adw.AlertDialog(heading=f'Uninstall {entry.title}?',
                                 body='The app is removed. Your settings are kept in case you install it again.')
        dialog.add_response('cancel', 'Cancel')
        dialog.add_response('remove', 'Uninstall')
        dialog.set_response_appearance('remove', Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response('cancel')
        dialog.set_close_response('cancel')
        dialog.connect('response', lambda d, r: self._uninstall(entry) if r == 'remove' else None)
        dialog.present(self)

    def _uninstall(self, entry):
        self._set_busy([entry], 'Removing')
        packages.in_thread(
            lambda: packages.run_root(['apt-get', 'remove', '-y', entry.info.package]),
            lambda r, err: self._uninstall_done(entry, r, err))

    def _uninstall_done(self, entry, result, error):
        if error:
            return self._fail([entry], str(error))
        code, output = result
        if code in (126, 127):
            return self._fail([entry], 'Cancelled. Nothing was removed.')
        if code != 0:
            return self._fail([entry], 'The removal did not finish.', output)
        entry.needs_logout = False
        self._settle([entry])
        self.toasts.add_toast(Adw.Toast(title=f'{entry.title} uninstalled.'))

    def _settle(self, entries):
        for e in entries:
            e.busy = ''
        installed = packages.installed_versions([e.info.package for e in entries])
        for e in entries:
            e.set_installed(installed.get(e.info.package))
            e.changed()
        self._after_change()

    def _fail(self, entries, message, output=''):
        for e in entries:
            e.busy = ''
            e.changed()
        if output:
            dialog = Adw.AlertDialog(heading='Something went wrong', body=message)
            tail = '\n'.join(output.strip().splitlines()[-12:])
            dialog.set_extra_child(Gtk.Label(label=tail, wrap=True, selectable=True, xalign=0,
                                             css_classes=['monospace', 'caption']))
            dialog.add_response('ok', 'Close')
            dialog.present(self)
        else:
            self.toasts.add_toast(Adw.Toast(title=message))

    def _on_about(self, _button):
        about = Adw.AboutDialog(
            application_name='Grove', application_icon=f'io.github.{OWNER}.Grove', version=__version__,
            developer_name='webhookstudios', website=f'https://github.com/{OWNER}/grove',
            comments='One library to install, update and remove every webhookstudios app.\n\nPart of the Sedge family of apps.',
            license_type=Gtk.License.GPL_2_0)
        about.present(self)
