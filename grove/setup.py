"""The setup checklist: tick the apps you want and install them in one go.

Shown the first time Grove opens on a computer with none of the apps yet,
and from the main menu at any time."""
from gi.repository import Adw, GLib, Gtk, Pango

from . import ollama, packages
from .card import load_icon
from .model import arch_note, human_size


def _plural(n, word):
    return f"{n} {word}{'' if n == 1 else 's'}"


def _names(entries, limit=3):
    names = [e.title for e in entries]
    if len(names) <= limit:
        return ', '.join(names[:-1]) + (' and ' if len(names) > 1 else '') + names[-1] if names else ''
    return ', '.join(names[:limit]) + f' and {len(names) - limit} more'


class SetupDialog(Adw.Dialog):
    def __init__(self, window):
        super().__init__(title='Set up your apps', content_width=640, content_height=760)
        self.window = window
        self.checks = {}        # entry -> Gtk.CheckButton
        self.progress_rows = {}  # entry -> (Adw.ActionRow, Gtk.Stack)
        self.chosen = []
        self.updating = set()   # chosen apps that were installed already
        self.set_up = set()     # packages apt has finished setting up
        self.running = False
        self.is_closed = False
        self.ollama_check = None     # shown when Fleece needs Ollama and it is missing
        self.ollama_size = 0
        self.ollama_phase = ''       # '', 'waiting', 'busy', 'done', 'failed'
        self.ollama_row = None
        self.ollama_state = None
        self.connect('closed', self._on_closed)

        view = Adw.ToolbarView()
        view.add_top_bar(Adw.HeaderBar())
        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE, vhomogeneous=False)
        view.set_content(self.stack)
        self.set_child(view)

        self.stack.add_named(self._pick_page(), 'pick')
        self.stack.add_named(self._progress_page(), 'progress')

        bar = Gtk.Box(spacing=12, margin_top=10, margin_bottom=10, margin_start=18, margin_end=18)
        self.total = Gtk.Label(xalign=0, hexpand=True, css_classes=['dim-label'], wrap=True)
        bar.append(self.total)
        self.back_button = Gtk.Button(label='Back', visible=False, valign=Gtk.Align.CENTER, css_classes=['pill'])
        self.back_button.connect('clicked', lambda *_: self._show_pick())
        bar.append(self.back_button)
        self.logout_button = Gtk.Button(label='Log out', visible=False, valign=Gtk.Align.CENTER, css_classes=['pill'])
        self.logout_button.connect('clicked', self._on_logout)
        bar.append(self.logout_button)
        self.go = Gtk.Button(label='Install selected', valign=Gtk.Align.CENTER,
                             css_classes=['pill', 'suggested-action'])
        self.go.connect('clicked', self._on_go)
        bar.append(self.go)
        view.add_bottom_bar(bar)
        self._update_total()
        if self.ollama_check:
            packages.in_thread(ollama.download_size, lambda size, err: self._set_ollama_size(size or 0))

    # ---- choosing ------------------------------------------------------------

    def _pick_page(self):
        entries = [e for e in self.window.entries if e.info.package != 'grove']
        to_get = [e for e in entries if e.available and (not e.is_installed or e.has_update)]
        have = [e for e in entries if e.is_installed and not e.has_update]
        missing = [e for e in entries if not e.available and not e.is_installed]

        fleece = next((e for e in entries if e.info.package == 'fleece'), None)
        offer_ollama = bool(fleece and ollama.supported() and not ollama.installed()
                            and (fleece in to_get or fleece.is_installed))
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
        intro = Gtk.Label(
            label='Tick the apps you want, then press Install selected. Grove downloads them, adds anything '
                  'they need from your system’s software sources, such as Python, and asks for your '
                  'password once.',
            xalign=0, wrap=True)
        if to_get or offer_ollama:
            page.append(intro)

        if to_get:
            line = Gtk.Box(spacing=6)
            self.count = Gtk.Label(xalign=0, hexpand=True, css_classes=['dim-label'])
            line.append(self.count)
            for label, value in (('Select all', True), ('Select none', False)):
                button = Gtk.Button(label=label, css_classes=['flat'])
                button.connect('clicked', self._select_all, value)
                line.append(button)
            page.append(line)
        else:
            self.count = None
            done = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            done.append(Gtk.Label(label='You have every app', xalign=0, css_classes=['title-3']))
            done.append(Gtk.Label(label='Everything here is installed and up to date.', xalign=0,
                                  css_classes=['dim-label']))
            page.append(done)

        apps = [e for e in to_get if not e.info.is_extension]
        extensions = [e for e in to_get if e.info.is_extension]
        if apps:
            page.append(self._group('Apps', None, apps, self._choice_row))
        if offer_ollama:
            page.append(self._ollama_group(fleece))
        if extensions:
            page.append(self._group('Shell extensions', 'These change GNOME itself. They turn on after you '
                                    'log out and back in, once for all of them.', extensions, self._choice_row))
        if have:
            group = self._group('Already installed', None, have, self._have_row)
            if fleece and fleece.is_installed and ollama.installed():
                row = Adw.ActionRow(title='Ollama', subtitle='Runs the AI models Fleece chats with.')
                row.add_prefix(Gtk.Image(icon_name='package-x-generic', pixel_size=40, valign=Gtk.Align.CENTER))
                row.add_suffix(Gtk.Label(label='Installed', css_classes=['grove-badge', 'ok'], valign=Gtk.Align.CENTER))
                group.add(row)
            page.append(group)
        if missing:
            page.append(self._group('Not available on this computer', None, missing, self._missing_row))
        return self._scrolled(page)

    def _scrolled(self, child):
        clamp = Adw.Clamp(maximum_size=560, margin_top=12, margin_bottom=24, margin_start=16, margin_end=16)
        clamp.set_child(child)
        return Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, vexpand=True, child=clamp)

    def _group(self, title, description, entries, make_row):
        group = Adw.PreferencesGroup(title=title, description=description)
        for e in sorted(entries, key=lambda e: e.title.lower()):
            group.add(make_row(e))
        return group

    def _row(self, entry):
        row = Adw.ActionRow(title=entry.title, subtitle=entry.summary, subtitle_lines=2)
        icon = Gtk.Image(pixel_size=40, valign=Gtk.Align.CENTER)
        load_icon(icon, entry)
        row.add_prefix(icon)
        return row

    def _choice_row(self, entry):
        row = self._row(entry)
        check = Gtk.CheckButton(active=True, valign=Gtk.Align.CENTER)
        check.connect('toggled', lambda *_: self._update_total())
        row.add_prefix(check)
        row.set_activatable_widget(check)
        self.checks[entry] = check
        if entry.has_update:
            row.add_suffix(Gtk.Label(label=f'Update to {entry.info.version}', css_classes=['grove-badge', 'update'],
                                     valign=Gtk.Align.CENTER))
        row.add_suffix(Gtk.Label(label=human_size(entry.info.deb_size), css_classes=['dim-label', 'caption'],
                                 valign=Gtk.Align.CENTER))
        return row

    def _ollama_group(self, fleece):
        group = Adw.PreferencesGroup(title='Needed by Fleece', description=(
            'Fleece chats with AI models that run on your own computer, through Ollama. Ollama is not in '
            'your system\u2019s software sources, so Grove runs the official installer from ollama.com.'))
        row = Adw.ActionRow(title='Ollama', subtitle='Runs the AI models Fleece chats with.', subtitle_lines=2)
        self.ollama_check = Gtk.CheckButton(valign=Gtk.Align.CENTER)
        row.add_prefix(self.ollama_check)
        row.add_prefix(Gtk.Image(icon_name='package-x-generic', pixel_size=40, valign=Gtk.Align.CENTER))
        row.set_activatable_widget(self.ollama_check)
        self.ollama_size_label = Gtk.Label(css_classes=['dim-label', 'caption'], valign=Gtk.Align.CENTER)
        row.add_suffix(self.ollama_size_label)
        group.add(row)
        fleece_check = self.checks.get(fleece)
        self.ollama_check.set_active(fleece_check.get_active() if fleece_check else True)
        if fleece_check:
            fleece_check.connect('toggled', lambda c: self.ollama_check.set_active(c.get_active()))
        self.ollama_check.connect('toggled', lambda *_: self._update_total())
        return group

    def _set_ollama_size(self, size):
        self.ollama_size = size
        if self.ollama_check:
            self.ollama_size_label.set_label(human_size(size) if size else '')
            self._update_total()

    def _ollama_chosen(self):
        return bool(self.ollama_check and self.ollama_check.get_active())

    def _have_row(self, entry):
        row = self._row(entry)
        row.add_suffix(Gtk.Label(label='Installed', css_classes=['grove-badge', 'ok'], valign=Gtk.Align.CENTER))
        return row

    def _missing_row(self, entry):
        row = self._row(entry)
        row.set_subtitle(arch_note(entry.info))
        row.set_sensitive(False)
        return row

    def _select_all(self, _button, value):
        for check in self.checks.values():
            check.set_active(value)
        if self.ollama_check:
            self.ollama_check.set_active(value)

    def _selected(self):
        return [e for e, check in self.checks.items() if check.get_active()]

    def _update_total(self):
        chosen = self._selected()
        with_ollama = self._ollama_chosen()
        if self.count is not None:
            extra = 1 if self.ollama_check else 0
            self.count.set_label(f'{len(chosen) + int(with_ollama)} of {len(self.checks) + extra} selected')
        size = sum(e.info.deb_size for e in chosen) + (self.ollama_size if with_ollama else 0)
        what = ' and '.join(filter(None, [_plural(len(chosen), 'app') if chosen else '',
                                          'Ollama' if with_ollama else '']))
        if not self.checks and not self.ollama_check:
            # Nothing left to install: the button just closes.
            self.total.set_label('')
            self.go.set_label('Close')
            self.go.remove_css_class('suggested-action')
            self.go.set_sensitive(True)
            return
        self.total.set_label(f'{what}, {human_size(size)} to download' if what else 'Nothing selected')
        self.go.set_sensitive(bool(what) and not self.running)

    def _show_pick(self):
        self.stack.set_visible_child_name('pick')
        self.back_button.set_visible(False)
        self.logout_button.set_visible(False)
        self.logout_button.remove_css_class('suggested-action')
        self.go.set_label('Install selected')
        self.go.add_css_class('suggested-action')
        self._update_total()

    # ---- installing ----------------------------------------------------------

    def _progress_page(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.heading = Gtk.Label(xalign=0, wrap=True, css_classes=['title-2'])
        page.append(self.heading)
        self.detail = Gtk.Label(xalign=0, wrap=True, css_classes=['dim-label'])
        page.append(self.detail)
        self.bar = Gtk.ProgressBar(margin_top=6)
        page.append(self.bar)
        self.step = Gtk.Label(xalign=0, ellipsize=Pango.EllipsizeMode.END, css_classes=['dim-label', 'caption'])
        page.append(self.step)
        self.list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE, css_classes=['boxed-list'], margin_top=12)
        page.append(self.list)
        return self._scrolled(page)

    @staticmethod
    def _state_stack():
        state = Gtk.Stack(valign=Gtk.Align.CENTER, hhomogeneous=False)
        state.add_named(Adw.Spinner(width_request=20, height_request=20), 'busy')
        state.add_named(Gtk.Image(icon_name='object-select-symbolic', css_classes=['success']), 'done')
        state.add_named(Gtk.Image(icon_name='dialog-warning-symbolic', css_classes=['warning']), 'failed')
        state.add_named(Gtk.Box(), 'waiting')
        return state

    def _on_go(self, _button):
        if self.stack.get_visible_child_name() != 'pick' or (not self.checks and not self.ollama_check):
            self.close()
            return
        self.chosen = sorted(self._selected(), key=lambda e: e.title.lower())
        with_ollama = self._ollama_chosen()
        if not self.chosen and not with_ollama:
            return
        self.running = True
        self.updating = {e for e in self.chosen if e.is_installed}
        self.set_up = set()
        child = self.list.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self.list.remove(child)
            child = nxt
        for e in self.progress_rows:
            e.unlisten(self._refresh)
        self.progress_rows = {}
        for e in self.chosen:
            row = self._row(e)
            row.set_subtitle_lines(1)
            state = self._state_stack()
            row.add_suffix(state)
            self.list.append(row)
            self.progress_rows[e] = (row, state)
            e.listen(self._refresh)
        self.ollama_row = None
        self.ollama_phase = 'waiting' if with_ollama else ''
        if with_ollama:
            row = Adw.ActionRow(title='Ollama', subtitle_lines=1)
            row.add_prefix(Gtk.Image(icon_name='package-x-generic', pixel_size=40, valign=Gtk.Align.CENTER))
            self.ollama_state = self._state_stack()
            row.add_suffix(self.ollama_state)
            self.list.append(row)
            self.ollama_row = row

        what = ' and '.join(filter(None, [_plural(len(self.chosen), 'app') if self.chosen else '',
                                          'Ollama' if with_ollama else '']))
        self.heading.set_label(f'Installing {what}')
        self.detail.set_label('Grove asks for your password once, after the downloads. '
                              'You can close this window; the install keeps going.')
        self.step.set_label('')
        self.stack.set_visible_child_name('progress')
        self.go.set_label('Close')
        self.go.remove_css_class('suggested-action')
        self.go.set_sensitive(True)
        self.total.set_label('')
        self._refresh()
        self.window.install(self.chosen, on_line=self._on_line, on_done=self._on_done, with_ollama=with_ollama)

    def _on_line(self, line):
        if line.startswith('>>> ') and self.ollama_phase:
            self.ollama_phase = 'busy'
            self.step.set_label(line[4:].strip())
            self._refresh()
            return
        words = line.split()
        if len(words) >= 3 and words[0] in ('Unpacking', 'Setting') and (words[0] == 'Unpacking' or words[1] == 'up'):
            name = words[1] if words[0] == 'Unpacking' else words[2]
            name = name.split(':')[0]
            self.step.set_label(('Setting up ' if words[0] == 'Setting' else 'Unpacking ') + name)
            if words[0] == 'Setting':
                self.set_up.add(name)
            self._refresh()

    def _status(self, e):
        if e.info.package in self.set_up:
            return ('Updated' if e in self.updating else 'Installed'), 'done'
        if e.busy == 'Downloading':
            if e.progress <= 0:
                return 'Waiting to download', 'waiting'
            if e.progress >= 1:
                return 'Downloaded', 'waiting'
            return f'Downloading, {int(e.progress * 100)} %', 'busy'
        if e.busy == 'Installing':
            return 'Installing', 'busy'
        if e.is_installed and not e.has_update and not self.running:
            return ('Updated' if e in self.updating else 'Installed'), 'done'
        if not self.running:
            return ('Not updated' if e in self.updating else 'Not installed'), 'failed'
        return 'Waiting', 'waiting'

    def _refresh(self):
        for e, (row, state) in self.progress_rows.items():
            text, kind = self._status(e)
            row.set_subtitle(text)
            state.set_visible_child_name(kind)
        if self.ollama_row:
            phase = self.ollama_phase
            self.ollama_row.set_subtitle({'waiting': 'Waiting', 'busy': 'Installing with the official installer',
                                          'done': 'Installed', 'failed': 'Not installed'}.get(phase, ''))
            self.ollama_state.set_visible_child_name(phase or 'waiting')
        if not self.running:
            return
        if self.ollama_phase == 'busy':
            self.bar.set_fraction(0.9)
            return
        if not self.chosen:
            return
        size = sum(e.info.deb_size for e in self.chosen) or 1
        downloaded = sum(e.info.deb_size * (e.progress if e.busy == 'Downloading' else 1) for e in self.chosen)
        installing = any(e.busy == 'Installing' for e in self.chosen)
        fraction = 0.8 * downloaded / size
        if installing:
            done = sum(1 for e in self.chosen if e.info.package in self.set_up)
            fraction = 0.8 + 0.2 * done / len(self.chosen)
            if not self.step.get_label():
                self.step.set_label('Waiting for your password')
        self.bar.set_fraction(min(fraction, 1.0))

    def _on_done(self, ok, message, turned_on, ollama_ok=None):
        """Shows how the install went. Returns False when the dialog was
        closed meanwhile, so the window tells the person instead."""
        self.running = False
        if self.ollama_phase:
            self.ollama_phase = 'done' if ollama_ok else 'failed'
        self.bar.set_fraction(1.0 if ok else self.bar.get_fraction())
        self.step.set_label('')
        self._refresh()
        if ok:
            self.heading.set_label('All set' if ollama_ok is not False else 'Almost done')
            text = f'{_plural(len(self.chosen), "app")} installed.' if self.chosen else ''
            if ollama_ok:
                text += ' Ollama is installed and running.'
            elif ollama_ok is False:
                text += ' Ollama did not install; you can get it from ollama.com/download.'
            text = text.strip()
            if turned_on:
                text += (f' {_names(turned_on)} turn{"s" if len(turned_on) == 1 else ""} on after you log out '
                         'and back in.')
            self.detail.set_label(text)
            self.logout_button.set_visible(bool(turned_on))
            self.go.set_label('Done')
            (self.logout_button if turned_on else self.go).add_css_class('suggested-action')
        else:
            self.heading.set_label('Nothing was installed' if 'Cancelled' in message else 'The install did not finish')
            self.detail.set_label(message + ' Your choices are kept, so you can try again.')
            self.back_button.set_visible(True)
            self.go.set_label('Close')
        self.go.set_sensitive(True)
        return not self.is_closed

    def _on_logout(self, _button):
        if not packages.log_out():
            self.detail.set_label('Log out from the system menu at the top right, then log back in.')
            return
        self.close()

    def _on_closed(self, *_):
        self.is_closed = True
        for e in self.progress_rows:
            e.unlisten(self._refresh)
