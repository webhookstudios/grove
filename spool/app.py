import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Adw, Gdk, Gtk  # noqa: E402

from . import APP_ID  # noqa: E402
from .window import SpoolWindow  # noqa: E402


class SpoolApplication(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID)

    def do_startup(self):
        Adw.Application.do_startup(self)
        import os
        from . import sedge
        sedge.apply()
        css = Gtk.CssProvider()
        css.load_from_path(os.path.join(os.path.dirname(__file__), 'style.css'))
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def do_activate(self):
        window = self.props.active_window or SpoolWindow(application=self)
        window.present()
