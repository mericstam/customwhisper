import sys

from PyQt5.QtCore import Qt, QRectF
from PyQt5.QtGui import QPainter, QBrush, QColor, QFont, QPainterPath, QGuiApplication
from PyQt5.QtWidgets import QApplication, QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout, QMainWindow

# The frameless window is painted with its own background. On Windows it's the
# original semi-transparent white with dark text. On macOS that read as white-on-
# white under dark mode, so use an opaque dark background with light text to match
# the system dark appearance (see apply_macos_theme in main.py).
if sys.platform == 'darwin':
    BACKGROUND_COLOR = QColor(43, 43, 43, 255)
    TITLE_TEXT_COLOR = '#e0e0e0'
    CLOSE_BUTTON_COLOR = '#e0e0e0'
    CLOSE_BUTTON_HOVER = '#ffffff'
else:
    BACKGROUND_COLOR = QColor(255, 255, 255, 220)
    TITLE_TEXT_COLOR = '#404040'
    CLOSE_BUTTON_COLOR = '#404040'
    CLOSE_BUTTON_HOVER = '#000000'


class BaseWindow(QMainWindow):
    def __init__(self, title, width, height):
        """
        Initialize the base window.
        """
        super().__init__()
        self.initUI(title, width, height)
        self.setWindowPosition()
        self.is_dragging = False

    def initUI(self, title, width, height):
        """
        Initialize the user interface.
        """
        self.setWindowTitle(title)
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFixedSize(width, height)

        self.main_widget = QWidget(self)
        self.main_layout = QVBoxLayout(self.main_widget)
        self.main_layout.setContentsMargins(10, 10, 10, 10)

        # Create a widget for the title bar
        title_bar = QWidget()
        title_bar_layout = QHBoxLayout(title_bar)
        title_bar_layout.setContentsMargins(0, 0, 0, 0)

        # Add the title label
        title_label = QLabel('CustomWhisper')
        title_label.setFont(QFont('Segoe UI', 12, QFont.Bold))
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet(f"color: {TITLE_TEXT_COLOR};")

        # Create a widget for the close button
        close_button_widget = QWidget()
        close_button_layout = QHBoxLayout(close_button_widget)
        close_button_layout.setContentsMargins(0, 0, 0, 0)

        close_button = QPushButton('×')
        close_button.setFixedSize(25, 25)
        close_button.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                border: none;
                color: {CLOSE_BUTTON_COLOR};
            }}
            QPushButton:hover {{
                color: {CLOSE_BUTTON_HOVER};
            }}
        """)
        close_button.clicked.connect(self.handleCloseButton)

        close_button_layout.addWidget(close_button, alignment=Qt.AlignRight)

        # Add widgets to the title bar layout
        title_bar_layout.addWidget(QWidget(), 1)  # Left spacer
        title_bar_layout.addWidget(title_label, 3)  # Title (with more width)
        title_bar_layout.addWidget(close_button_widget, 1)  # Close button

        self.main_layout.addWidget(title_bar)
        self.setCentralWidget(self.main_widget)

    def setWindowPosition(self):
        """
        Set the window position to the center of the screen.
        """
        center_point = QGuiApplication.primaryScreen().availableGeometry().center()
        frame_geometry = self.frameGeometry()
        frame_geometry.moveCenter(center_point)
        self.move(frame_geometry.topLeft())

    def handleCloseButton(self):
        """
        Close the window.
        """
        self.close()

    def mousePressEvent(self, event):
        """
        Allow the window to be moved by clicking and dragging anywhere on the window.
        """
        if event.button() == Qt.LeftButton:
            self.is_dragging = True
            self.start_position = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        """
        Move the window when dragging.
        """
        if Qt.LeftButton and self.is_dragging:
            self.move(event.globalPos() - self.start_position)
            event.accept()

    def mouseReleaseEvent(self, event):
        """
        Stop dragging the window.
        """
        self.is_dragging = False

    def paintEvent(self, event):
        """
        Create a rounded rectangle with a semi-transparent white background.
        """
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), 20, 20)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QBrush(BACKGROUND_COLOR))
        painter.setPen(Qt.NoPen)
        painter.drawPath(path)
