import os
import shutil
import tempfile

from gi.repository import Adw, Gio, GLib, Gtk

from . import OWNER, __version__, ollama, packages, state
from .card import AppCard
from .details import DetailsDialog
from .github import Client, GitHubError, download
from .model import Entry
from .setup import SetupDialog


class GroveWindow(Adw.ApplicationWindow):
    def __init__(self, **kwargs):
        super().__init__(title='Grove', default_width=1000, default_height=720, **kwargs)
        self.client = Client()
        self.entries = []
        self.cards = {}
        self.mode = 'all'
        self.setup_checked = False

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

        menu = Gio.Menu()
        menu.append('Set up apps…', 'win.setup')
        menu.append('About Grove', 'win.about')
        header.pack_end(Gtk.MenuButton(icon_name='open-menu-symbolic', tooltip_text='Main menu',
                                       menu_model=menu, primary=True))
        for name, callback in (('setup', self.show_setup), ('about', self._on_about)):
            action = Gio.SimpleAction.new(name, None)
            action.connect('activate', lambda *_, callback=callback: callback())
            self.add_action(action)
        self.lookup_action('setup').set_enabled(False)
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
        self.lookup_action('setup').set_enabled(bool(self.entries))
        if not self.setup_checked:
            self.setup_checked = True
            # A new computer: nothing from the library is installed except Grove.
            if not state.get('setup_shown') and not any(
                    e.is_installed for e in self.entries if e.info.package != 'grove'):
                GLib.idle_add(lambda: self.show_setup() or False)

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

    def show_setup(self):
        state.set('setup_shown', True)
        SetupDialog(self).present(self)

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

    def install(self, entries, on_line=None, on_done=None, with_ollama=False):
        """Downloads and installs apps with one apt run, so one password prompt.
        with_ollama also runs Ollama's official installer in that same prompt.
        on_line gets each line the install prints; on_done(ok, message,
        turned_on, ollama_ok) is called at the end, and when it returns True
        the window adds no toast."""
        entries = [e for e in entries if not e.busy and e.available]
        if not entries and not with_ollama:
            if on_done:
                on_done(False, 'Nothing could be installed.', [], None)
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
                line = (lambda text: GLib.idle_add(lambda: on_line(text) or False)) if on_line else None
                if not with_ollama:
                    return packages.run_root(['apt-get', 'install', '-y', *paths], line)
                script = os.path.join(folder, 'ollama-install.sh')
                download(ollama.INSTALLER, script)
                os.chmod(script, 0o644)
                return packages.run_root([f'GROVE_OLLAMA={script}', 'sh', '-c', ollama.ROOT_SCRIPT, 'grove',
                                          *paths, *ollama.NEEDS], line)
            finally:
                shutil.rmtree(folder, ignore_errors=True)

        packages.in_thread(work, lambda r, err: self._install_done(entries, r, err, on_done, with_ollama))

    def _progress(self, entry, fraction):
        entry.progress = fraction
        entry.changed()
        return False

    def _set_busy(self, entries, text):
        for e in entries:
            e.busy = text
            e.changed()
        return False

    def _install_done(self, entries, result, error, on_done=None, with_ollama=False):
        def failed(message, output=''):
            for e in entries:
                e.busy = ''
                e.changed()
            shown = on_done(False, message, [], False if with_ollama else None) if on_done else False
            if output or not shown:
                self._report(message, output)

        names = ', '.join([e.title for e in entries] + (['Ollama'] if with_ollama else []))
        if error:
            return failed(str(error))
        code, output = result
        if code in (126, 127):
            return failed('Cancelled. Nothing was installed.')
        ollama_ok = None
        if with_ollama:
            ollama_ok = code == 0
            if code == 20 and not entries:
                return failed('Ollama did not install.', output)
            if code == 20:  # the apps are in; only Ollama's installer failed
                code = 0
                names = ', '.join(e.title for e in entries)
                self._report('Ollama did not install. Fleece needs it to run models; you can get it from '
                             'ollama.com/download.', output)
        if code != 0:
            return failed('The install did not finish.', output)
        fresh = [e for e in entries if e.info.is_extension and not e.is_installed]
        self._settle(entries)
        fresh = [e for e in fresh if e.is_installed]
        # New extensions are set to turn on, so they start at the next login.
        packages.enable_extensions([e.info.extension_uuid for e in fresh])
        for e in fresh:
            e.needs_logout = True
            e.changed()
        if on_done and on_done(True, f'{names} installed.', fresh, ollama_ok):
            return
        toast = Adw.Toast(title=f'{names} installed.' + (' Log out and back in to turn on new extensions.' if fresh else ''))
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
        self._report(message, output)

    def _report(self, message, output=''):
        if output:
            dialog = Adw.AlertDialog(heading='Something went wrong', body=message)
            tail = '\n'.join(output.strip().splitlines()[-12:])
            dialog.set_extra_child(Gtk.Label(label=tail, wrap=True, selectable=True, xalign=0,
                                             css_classes=['monospace', 'caption']))
            dialog.add_response('ok', 'Close')
            dialog.present(self)
        else:
            self.toasts.add_toast(Adw.Toast(title=message))

    def _on_about(self, *_):
        about = Adw.AboutDialog(
            application_name='Grove', application_icon=f'io.github.{OWNER}.Grove', version=__version__,
            developer_name='webhookstudios', website=f'https://github.com/{OWNER}/grove',
            comments='One library to install, update and remove every webhookstudios app.\n\nPart of the Sedge family of apps.',
            license_type=Gtk.License.GPL_2_0)
        about.present(self)
