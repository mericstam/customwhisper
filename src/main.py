import os
import sys
import time
from audioplayer import AudioPlayer
from pynput.keyboard import Controller
from PyQt5.QtCore import QObject, QProcess
from PyQt5.QtGui import QIcon, QPalette, QColor
from PyQt5.QtWidgets import QApplication, QSystemTrayIcon, QMenu, QAction, QMessageBox


def request_macos_permissions():
    """Proactively surface the macOS permission prompts for CustomWhisper.

    As a proper .app bundle, CustomWhisper has its own TCC identity, so it needs
    Accessibility (to type the transcription into other apps) and Input Monitoring
    (to detect the global hotkey) granted to *itself*. Triggering the system
    prompts here adds "CustomWhisper" to those lists so the user can just flip the
    toggle, instead of hunting through System Settings. Microphone is prompted
    automatically on the first recording. No-op off macOS; safe to call every
    launch (already-granted permissions don't re-prompt).
    """
    if sys.platform != 'darwin':
        return
    # Accessibility — required to synthesize keystrokes into the focused app.
    try:
        from ApplicationServices import (
            AXIsProcessTrustedWithOptions, kAXTrustedCheckOptionPrompt)
        AXIsProcessTrustedWithOptions({kAXTrustedCheckOptionPrompt: True})
    except Exception as e:
        print(f'Accessibility permission prompt failed: {e}')
    # Input Monitoring — required to observe the global activation hotkey.
    try:
        import ctypes
        iokit = ctypes.CDLL('/System/Library/Frameworks/IOKit.framework/IOKit')
        iokit.IOHIDCheckAccess.restype = ctypes.c_int
        iokit.IOHIDCheckAccess.argtypes = [ctypes.c_uint32]
        iokit.IOHIDRequestAccess.restype = ctypes.c_bool
        iokit.IOHIDRequestAccess.argtypes = [ctypes.c_uint32]
        K_LISTEN_EVENT = 1  # kIOHIDRequestTypeListenEvent
        if iokit.IOHIDCheckAccess(K_LISTEN_EVENT) != 0:  # 0 == granted
            iokit.IOHIDRequestAccess(K_LISTEN_EVENT)
    except Exception as e:
        print(f'Input Monitoring permission prompt failed: {e}')


def apply_macos_theme(app):
    """Apply a readable dark theme on macOS.

    The frameless windows paint a dark background (see base_window.py). Under
    macOS the native Qt style ignores palette overrides and, in dark mode, hands
    widgets light default text on our dark background inconsistently. Switching to
    the Fusion style with an explicit dark palette gives consistent, readable
    dark-mode styling. Windows/Linux keep their native look.
    """
    if sys.platform != 'darwin':
        return
    app.setStyle('Fusion')
    text = QColor(224, 224, 224)
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(43, 43, 43))
    palette.setColor(QPalette.WindowText, text)
    palette.setColor(QPalette.Base, QColor(30, 30, 30))
    palette.setColor(QPalette.AlternateBase, QColor(50, 50, 50))
    palette.setColor(QPalette.Text, text)
    palette.setColor(QPalette.Button, QColor(60, 60, 60))
    palette.setColor(QPalette.ButtonText, text)
    palette.setColor(QPalette.ToolTipBase, QColor(43, 43, 43))
    palette.setColor(QPalette.ToolTipText, text)
    palette.setColor(QPalette.PlaceholderText, QColor(130, 130, 130))
    palette.setColor(QPalette.Highlight, QColor(52, 120, 246))
    palette.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
    palette.setColor(QPalette.Disabled, QPalette.Text, QColor(120, 120, 120))
    palette.setColor(QPalette.Disabled, QPalette.WindowText, QColor(120, 120, 120))
    palette.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(120, 120, 120))
    app.setPalette(palette)

from key_listener import KeyListener
from result_thread import ResultThread
from ui.main_window import MainWindow
from ui.settings_window import SettingsWindow
from ui.status_window import StatusWindow
from transcription import create_local_model
from input_simulation import InputSimulator
from utils import ConfigManager


class WhisperWriterApp(QObject):
    def __init__(self):
        """
        Initialize the application, opening settings window if no configuration file is found.
        """
        super().__init__()
        self.app = QApplication(sys.argv)
        self.app.setWindowIcon(QIcon(os.path.join('assets', 'ww-logo-custom.png')))
        # Tray-resident app: don't quit when the last window closes (e.g. the
        # status overlay closing after a dictation would otherwise end the app).
        self.app.setQuitOnLastWindowClosed(False)
        apply_macos_theme(self.app)

        # macOS: make pynput safe to run its key listener off the main thread
        # (must run here, on the main thread, before any listener starts).
        from macos_pynput_patch import install as install_macos_pynput_patch
        install_macos_pynput_patch()

        # macOS: pop the Accessibility / Input Monitoring permission prompts so
        # the user can grant CustomWhisper directly (needed for typing + hotkey).
        request_macos_permissions()

        ConfigManager.initialize()

        self.settings_window = SettingsWindow()
        self.settings_window.settings_closed.connect(self.on_settings_closed)
        self.settings_window.settings_saved.connect(self.restart_app)

        if ConfigManager.config_file_exists():
            self.initialize_components()
        else:
            print('No valid configuration file found. Opening settings window...')
            self.settings_window.show()

    def initialize_components(self):
        """
        Initialize the components of the application.
        """
        self.input_simulator = InputSimulator()

        self.key_listener = KeyListener()
        self.key_listener.add_callback("on_activate", self.on_activation)
        self.key_listener.add_callback("on_deactivate", self.on_deactivation)

        model_options = ConfigManager.get_config_section('model_options')
        model_path = model_options.get('local', {}).get('model_path')
        self.local_model = create_local_model() if not model_options.get('use_api') else None

        # Optional in-dictation voice command recognizer (Vosk)
        self.command_recognizer = None
        if ConfigManager.get_config_value('voice_commands', 'enabled'):
            try:
                from command_recognizer import CommandRecognizer
                self.command_recognizer = CommandRecognizer(
                    sample_rate=ConfigManager.get_config_value('recording_options', 'sample_rate') or 16000
                )
                print('Voice commands enabled (Vosk): say "Jarvis hold / continue / end session".')
            except Exception as e:
                print(f'Voice commands disabled (failed to initialize): {e}')

        self.result_thread = None

        self.main_window = MainWindow()
        self.main_window.openSettings.connect(self.settings_window.show)
        self.main_window.startListening.connect(self.on_start_listening)
        self.main_window.closeApp.connect(self.exit_app)

        if not ConfigManager.get_config_value('misc', 'hide_status_window'):
            self.status_window = StatusWindow()

        self.create_tray_icon()
        self.main_window.show()

    def on_start_listening(self):
        """Activate the hotkey listener and the wake-word listener.

        Wired to the main window's 'Start' button, so listening begins only when
        the user chooses to start it (not automatically at launch).
        """
        self.key_listener.start()
        self.start_wake_listener()

    def start_wake_listener(self):
        """Spawn the wake-word listener (wake_listener.py) as a child process.

        macOS only: running it as our child makes it share the app's TCC identity,
        so it inherits the Microphone and Accessibility grants. On Windows/Linux
        the separate 'Start Hands-Free' launcher runs it as its own process, so we
        don't spawn it here to avoid a duplicate. Gated by wake_word.enabled.
        """
        if sys.platform != 'darwin':
            return
        existing = getattr(self, 'wake_process', None)
        if existing is not None and existing.poll() is None:
            return  # already running (Start pressed again)
        self.wake_process = None
        try:
            enabled = ConfigManager.get_config_value('wake_word', 'enabled')
        except Exception:
            enabled = None
        if enabled is False:
            return
        try:
            import subprocess
            # Sweep any wake listeners orphaned by a previous unclean exit before
            # spawning ours — otherwise each one fires the activation hotkey on the
            # wake word, toggling recording on and immediately back off.
            try:
                from process_cleanup import kill_wake_listeners
                stale = kill_wake_listeners()
                if stale:
                    print(f'Cleared {len(stale)} lingering wake listener(s) before start.')
            except Exception as e:
                print(f'Wake-listener cleanup skipped: {e}')
            repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            log = open(os.path.join(repo_root, 'wake_out.txt'), 'a',
                       buffering=1, encoding='utf-8', errors='replace')
            # --exit-with-parent: the listener self-terminates if we die uncleanly
            # (crash/force-quit), so it can never linger as an orphan holding the mic.
            self.wake_process = subprocess.Popen(
                [sys.executable, os.path.join(repo_root, 'wake_listener.py'),
                 '--exit-with-parent'],
                cwd=repo_root, stdout=log, stderr=subprocess.STDOUT,
            )
            print('Wake-word listener started (say "Hey Jarvis"). Logs: wake_out.txt')
        except Exception as e:
            print(f'Wake-word listener failed to start: {e}')

    def create_tray_icon(self):
        """
        Create the system tray icon and its context menu.
        """
        self.tray_icon = QSystemTrayIcon(QIcon(os.path.join('assets', 'ww-logo-custom.png')), self.app)

        tray_menu = QMenu()

        show_action = QAction('CustomWhisper Main Menu', self.app)
        show_action.triggered.connect(self.main_window.show)
        tray_menu.addAction(show_action)

        settings_action = QAction('Open Settings', self.app)
        settings_action.triggered.connect(self.settings_window.show)
        tray_menu.addAction(settings_action)

        exit_action = QAction('Exit', self.app)
        exit_action.triggered.connect(self.exit_app)
        tray_menu.addAction(exit_action)

        # On macOS, Qt's text heuristic (e.g. "Settings" -> PreferencesRole) can
        # relocate/hide items from a tray menu; NoRole keeps them all in place.
        for action in (show_action, settings_action, exit_action):
            action.setMenuRole(QAction.NoRole)

        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.show()

    def cleanup(self):
        # These components only exist once initialize_components() has run. On
        # first launch the Settings window can be saved (triggering a restart)
        # before that happens, so guard against the attributes being absent.
        key_listener = getattr(self, 'key_listener', None)
        if key_listener:
            key_listener.stop()
        input_simulator = getattr(self, 'input_simulator', None)
        if input_simulator:
            input_simulator.cleanup()
        wake_process = getattr(self, 'wake_process', None)
        if wake_process:
            try:
                wake_process.terminate()
            except Exception:
                pass

    def exit_app(self):
        """
        Exit the application, shutting down every related CustomWhisper process.

        Quitting Qt only ends this process; the wake-word listener and any stray
        duplicate instances are separate processes, so kill them too before we go.
        """
        self.cleanup()
        try:
            from process_cleanup import kill_related_processes
            killed = kill_related_processes()
            if killed:
                print(f'Exit: terminated related CustomWhisper processes {killed}.')
        except Exception as e:
            print(f'Exit: process cleanup failed: {e}')
        QApplication.quit()

    def restart_app(self):
        """Restart the application to apply the new settings."""
        self.cleanup()
        QApplication.quit()
        QProcess.startDetached(sys.executable, sys.argv)

    def on_settings_closed(self):
        """
        If settings is closed without saving on first run, initialize the components with default values.
        """
        if not os.path.exists(os.path.join('src', 'config.yaml')):
            QMessageBox.information(
                self.settings_window,
                'Using Default Values',
                'Settings closed without saving. Default values are being used.'
            )
            self.initialize_components()

    def on_activation(self):
        """
        Called when the activation key combination is pressed.
        """
        if self.result_thread and self.result_thread.isRunning():
            recording_mode = ConfigManager.get_config_value('recording_options', 'recording_mode')
            if recording_mode == 'continuous':
                self.stop_result_thread()
            else:
                # press_to_toggle / voice_activity_detection: pressing the hotkey
                # again finalizes the recording (a manual stop before the silence
                # timeout).
                self.result_thread.stop_recording()
            return

        self.start_result_thread()

    def on_deactivation(self):
        """
        Called when the activation key combination is released.
        """
        if ConfigManager.get_config_value('recording_options', 'recording_mode') == 'hold_to_record':
            if self.result_thread and self.result_thread.isRunning():
                self.result_thread.stop_recording()

    def start_result_thread(self):
        """
        Start the result thread to record audio and transcribe it.
        """
        if self.result_thread and self.result_thread.isRunning():
            return

        self.result_thread = ResultThread(self.local_model, self.command_recognizer)
        if not ConfigManager.get_config_value('misc', 'hide_status_window'):
            self.result_thread.statusSignal.connect(self.status_window.updateStatus)
            self.status_window.closeSignal.connect(self.stop_result_thread)
        self.result_thread.resultSignal.connect(self.on_transcription_complete)
        self.result_thread.start()

    def stop_result_thread(self):
        """
        Stop the result thread.
        """
        if self.result_thread and self.result_thread.isRunning():
            self.result_thread.stop()

    def on_transcription_complete(self, result):
        """
        When the transcription is complete, run a matching custom command (e.g.
        "open word") or type the result, then start listening again.
        """
        # Skip silent/empty captures so they don't type a stray space + Enter.
        if result and result.strip():
            # Catch output failures (e.g. macOS denying keystrokes) so we still
            # re-arm below instead of getting stuck after one dictation.
            try:
                from custom_commands import handle_transcription
                handled = handle_transcription(result)

                if not handled:
                    self.input_simulator.typewrite(result)

                    if ConfigManager.get_config_value('post_processing', 'press_enter_after'):
                        self.input_simulator.press_enter()

                if ConfigManager.get_config_value('misc', 'noise_on_completion'):
                    AudioPlayer(os.path.join('assets', 'beep.wav')).play(block=True)
            except Exception as e:
                print(f'Output step failed (transcription was: {result!r}): {e}')

        if ConfigManager.get_config_value('recording_options', 'recording_mode') == 'continuous':
            self.start_result_thread()
        else:
            self.key_listener.start()

    def run(self):
        """
        Start the application.
        """
        sys.exit(self.app.exec_())


if __name__ == '__main__':
    app = WhisperWriterApp()
    app.run()
