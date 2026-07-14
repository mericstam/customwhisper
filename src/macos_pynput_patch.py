"""macOS-only workaround for a pynput crash on modern macOS (14+ / 15 / 26).

pynput's global keyboard Listener runs its event loop on a *background* thread
and, to translate each key event to a character, calls
``pynput._util.darwin.keycode_context()``. That helper queries the current
keyboard layout via the HIToolbox Text Input Source APIs
(``TISCopyCurrentKeyboardInputSource`` / ``TISGetInputSourceProperty``), which on
recent macOS may only be called from the **main thread** — calling them off the
main thread aborts the whole process with ``dispatch_assert_queue`` / SIGTRAP
(EXC_BREAKPOINT). The result: the app crashes the moment the hotkey listener
starts.

The layout information pynput actually needs is a plain
``(keyboard_type: int, layout_data: bytes)`` tuple, and the translation itself
(``UCKeyTranslate``) is a pure function over those bytes that is thread-safe. So
we compute that tuple **once, on the main thread**, at startup and replace
``keycode_context`` with a version that yields the cached value. The background
listener thread then never touches the Text Input Source APIs.

Call :func:`install` from the main thread before starting the ``KeyListener``.
It is a no-op off macOS. If the user switches keyboard layout mid-session,
keystroke-to-character translation keeps using the layout captured at startup;
the default activation hotkey (modifiers + space) is unaffected either way.
"""
import contextlib
import sys

_installed = False


def install():
    """Patch pynput to avoid off-main-thread Text Input Source calls on macOS."""
    global _installed
    if _installed or sys.platform != 'darwin':
        return

    try:
        from pynput._util import darwin as _darwin
    except Exception:
        return

    # Compute the (keyboard_type, layout_data) context once, here on the main
    # thread, using pynput's own (unpatched) implementation.
    try:
        with _darwin.keycode_context() as cached_context:
            pass
    except Exception:
        return

    @contextlib.contextmanager
    def _cached_keycode_context():
        yield cached_context

    _darwin.keycode_context = _cached_keycode_context

    # keyboard/_darwin.py did ``from pynput._util.darwin import keycode_context``,
    # so it holds its own reference to the original — patch that name too.
    try:
        from pynput.keyboard import _darwin as _kbd_darwin
        _kbd_darwin.keycode_context = _cached_keycode_context
    except Exception:
        pass

    # pyobjc resolves framework symbols lazily and not thread-safely. pynput's
    # listener thread is the first thing to touch HIServices.AXIsProcessTrusted,
    # and that first lazy resolution from a background thread can raise
    # KeyError('AXIsProcessTrusted'), killing the listener. Resolve (and cache) it
    # here on the main thread so the background thread gets the ready function.
    try:
        import HIServices
        HIServices.AXIsProcessTrusted()
    except Exception:
        pass

    _installed = True
