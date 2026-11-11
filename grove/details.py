import threading

from gi.repository import Adw, GLib, Gtk

from . import OWNER
from .card import ActionButtons, load_icon
from .github import fetch_cached
from .model import human_size


class DetailsDialog(Adw.Dialog):
    def __init__(self, entry, window):
        super().__init__(title=entry.title, content_width=560, content_height=680)
        self.entry, self.window = entry, window
        info = entry.info

        view = Adw.ToolbarView()
        view.add_top_bar(Adw.HeaderBar())
        scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, vexpand=True)
        view.set_content(scroll)
        self.set_child(view)

        clamp = Adw.Clamp(maximum_size=520, margin_top=12, margin_bottom=24, margin_start=16, margin_end=16)
        scroll.set_child(clamp)
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        clamp.set_child(page)

        head = Gtk.Box(spacing=16)
        icon = Gtk.Image(pixel_size=80)
        load_icon(icon, entry)
        head.append(icon)
        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, valign=Gtk.Align.CENTER)
        text.append(Gtk.Label(label=entry.title, xalign=0, css_classes=['title-1']))
        text.append(Gtk.Label(label=info.description, xalign=0, wrap=True, css_classes=['dim-label']))
        head.append(text)
        page.append(head)

        page.append(ActionButtons(entry, window, after=self.close, halign=Gtk.Align.FILL))

        self.shots = Adw.Carousel(allow_scroll_wheel=False, visible=False, height_request=300, spacing=12)
        self.dots = Adw.CarouselIndicatorDots(carousel=self.shots, visible=False)
        page.append(self.shots)
        page.append(self.dots)

        group = Adw.PreferencesGroup(title='Details')
        for title, value in (
            ('Latest version', info.version),
            ('Installed version', entry.installed or 'Not installed'),
            ('Released', info.published),
            ('Download size', human_size(info.deb_size)),
            ('Type', 'GNOME Shell extension, with a settings app' if info.is_extension else 'App'),
            ('Package', info.package),
        ):
            row = Adw.ActionRow(title=title, subtitle=GLib.markup_escape_text(value), subtitle_selectable=True)
            row.add_css_class('property')
            group.add(row)
        page.append(group)

        if info.notes:
            notes = Adw.PreferencesGroup(title='What is new')
            notes.add(Gtk.Label(label=info.notes, wrap=True, xalign=0, selectable=True,
                                css_classes=['grove-notes']))
            page.append(notes)

        link = Gtk.LinkButton(uri=info.html_url, label='View on GitHub', halign=Gtk.Align.START)
        page.append(link)

        threading.Thread(target=self._load_shots, daemon=True).start()

    def _load_shots(self):
        try:
            urls = self.window.client.screenshots(self.entry.info.repo)[:6]
        except Exception:
            return
        paths = [p for i, u in enumerate(urls)
                 if (p := fetch_cached(u, f'{self.entry.info.repo}-shot{i}-{u.rsplit("/", 1)[-1]}'))]
        if paths:
            GLib.idle_add(self._show_shots, paths)

    def _show_shots(self, paths):
        for path in paths:
            picture = Gtk.Picture.new_for_filename(path)
            picture.set_can_shrink(True)
            picture.set_content_fit(Gtk.ContentFit.CONTAIN)
            self.shots.append(picture)
        self.shots.set_visible(True)
        self.dots.set_visible(len(paths) > 1)
        self.shots.set_allow_scroll_wheel(len(paths) > 1)
        return False
