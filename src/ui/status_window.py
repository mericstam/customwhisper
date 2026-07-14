import sys
import os
from ctypes import c_void_p
from PyQt5.QtCore import Qt, pyqtSignal, pyqtSlot, QTimer
from PyQt5.QtGui import QFont, QPixmap, QIcon
from PyQt5.QtWidgets import QApplication, QLabel, QHBoxLayout

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from ui.base_window import BaseWindow

class StatusWindow(BaseWindow):
    statusSignal = pyqtSignal(str)
    closeSignal = pyqtSignal()

    def __init__(self):
        """
        Initialize the status window.
        """
        super().__init__('CustomWhisper Status', 320, 120)
        self.initStatusUI()
        self.statusSignal.connect(self.updateStatus)

    def initStatusUI(self):
        """
        Initialize the status user interface.
        """
        # On macOS a Qt.Tool window is automatically hidden whenever the app is
        # not the active app — so the moment you click into the app you're
        # dictating into, the status overlay disappears. Use flags that keep it
        # visible without stealing focus instead. Windows/Linux keep Qt.Tool.
        if sys.platform == 'darwin':
            self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint |
                                Qt.WindowDoesNotAcceptFocus)
            self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        else:
            self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)

        status_layout = QHBoxLayout()
        status_layout.setContentsMargins(0, 0, 0, 0)

        self.icon_label = QLabel()
        self.icon_label.setFixedSize(32, 32)
        microphone_path = os.path.join('assets', 'microphone.png')
        pencil_path = os.path.join('assets', 'pencil.png')
        self.microphone_pixmap = QPixmap(microphone_path).scaled(32, 32, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.pencil_pixmap = QPixmap(pencil_path).scaled(32, 32, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.icon_label.setPixmap(self.microphone_pixmap)
        self.icon_label.setAlignment(Qt.AlignCenter)

        self.status_label = QLabel('Recording...')
        self.status_label.setFont(QFont('Segoe UI', 12))

        status_layout.addStretch(1)
        status_layout.addWidget(self.icon_label)
        status_layout.addWidget(self.status_label)
        status_layout.addStretch(1)

        self.main_layout.addLayout(status_layout)
        
    def show(self):
        """
        Position the window in the bottom center of the screen and show it.
        """
        screen = QApplication.primaryScreen()
        screen_geometry = screen.geometry()
        screen_width = screen_geometry.width()
        screen_height = screen_geometry.height()
        window_width = self.width()
        window_height = self.height()

        x = (screen_width - window_width) // 2
        y = screen_height - window_height - 120

        self.move(x, y)
        super().show()
        self._apply_macos_overlay_behavior()

    def _apply_macos_overlay_behavior(self):
        """Make the overlay float above other apps and appear on every Space.

        With Qt.Tool removed (so the window survives app deactivation on macOS),
        raise the native NSWindow to a high level and let it join all Spaces, so
        the recording/transcribing status stays visible over whatever app you're
        dictating into. Best-effort; a no-op if AppKit isn't available.
        """
        if sys.platform != 'darwin':
            return
        try:
            import objc
            from AppKit import (
                NSStatusWindowLevel,
                NSWindowCollectionBehaviorCanJoinAllSpaces,
                NSWindowCollectionBehaviorStationary,
                NSWindowCollectionBehaviorFullScreenAuxiliary,
            )
            nswindow = objc.objc_object(c_void_p=int(self.winId())).window()
            nswindow.setLevel_(NSStatusWindowLevel)
            nswindow.setCollectionBehavior_(
                NSWindowCollectionBehaviorCanJoinAllSpaces
                | NSWindowCollectionBehaviorStationary
                | NSWindowCollectionBehaviorFullScreenAuxiliary
            )
        except Exception:
            pass

    def closeEvent(self, event):
        """
        Emit the close signal when the window is closed.
        """
        self.closeSignal.emit()
        super().closeEvent(event)

    @pyqtSlot(str)
    def updateStatus(self, status):
        """
        Update the status window based on the given status.
        """
        if status == 'recording':
            self.icon_label.setPixmap(self.microphone_pixmap)
            self.status_label.setText('Recording...')
            self.show()
        elif status == 'transcribing':
            self.icon_label.setPixmap(self.pencil_pixmap)
            self.status_label.setText('Transcribing...')

        if status in ('idle', 'error', 'cancel'):
            self.close()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    
    status_window = StatusWindow()
    status_window.show()

    # Simulate status updates
    QTimer.singleShot(3000, lambda: status_window.statusSignal.emit('transcribing'))
    QTimer.singleShot(6000, lambda: status_window.statusSignal.emit('idle'))
    
    sys.exit(app.exec_())
