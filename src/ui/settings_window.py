import os
import sys
import time
from dotenv import set_key, load_dotenv
from PyQt5.QtWidgets import (
    QApplication, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QComboBox, QCheckBox,
    QMessageBox, QTabWidget, QWidget, QSizePolicy, QSpacerItem, QToolButton, QStyle, QFileDialog,
    QProgressBar
)
from PyQt5.QtCore import Qt, QCoreApplication, QProcess, pyqtSignal, QTimer

try:
    import numpy as np
    import sounddevice as sd
    _AUDIO_AVAILABLE = True
except Exception:
    _AUDIO_AVAILABLE = False

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from ui.base_window import BaseWindow
from utils import ConfigManager

load_dotenv()

class SettingsWindow(BaseWindow):
    settings_closed = pyqtSignal()
    settings_saved = pyqtSignal()

    SOUND_DEVICE_WIDGET_NAME = 'recording_options_sound_device_input'

    def __init__(self):
        """Initialize the settings window."""
        super().__init__('Settings', 700, 700)
        self.schema = ConfigManager.get_schema()

        # Live microphone test state (see create_sound_device_widget).
        self.sound_device_combo = None
        self.mic_test_button = None
        self.mic_level_bar = None
        self.mic_test_status = None
        self._test_stream = None
        self._test_peak = 0
        self._test_error = None
        self._test_started_at = 0.0
        self._test_timer = QTimer(self)
        self._test_timer.setInterval(50)
        self._test_timer.timeout.connect(self._update_mic_level)

        self.init_settings_ui()

    def init_settings_ui(self):
        """Initialize the settings user interface."""
        self.tabs = QTabWidget()
        self.main_layout.addWidget(self.tabs)

        self.create_tabs()
        self.create_buttons()

        # Connect the use_api checkbox state change
        self.use_api_checkbox = self.findChild(QCheckBox, 'model_options_use_api_input')
        if self.use_api_checkbox:
            self.use_api_checkbox.stateChanged.connect(lambda: self.toggle_api_local_options(self.use_api_checkbox.isChecked()))
            self.toggle_api_local_options(self.use_api_checkbox.isChecked())

    def create_tabs(self):
        """Create tabs for each category in the schema."""
        for category, settings in self.schema.items():
            tab = QWidget()
            tab_layout = QVBoxLayout()
            tab.setLayout(tab_layout)
            self.tabs.addTab(tab, category.replace('_', ' ').capitalize())

            self.create_settings_widgets(tab_layout, category, settings)
            tab_layout.addSpacerItem(QSpacerItem(20, 40, QSizePolicy.Minimum, QSizePolicy.Expanding))

    def create_settings_widgets(self, layout, category, settings):
        """Create widgets for each setting in a category."""
        for sub_category, sub_settings in settings.items():
            if isinstance(sub_settings, dict) and 'value' in sub_settings:
                self.add_setting_widget(layout, sub_category, sub_settings, category)
            else:
                for key, meta in sub_settings.items():
                    self.add_setting_widget(layout, key, meta, category, sub_category)

    def create_buttons(self):
        """Create reset and save buttons."""
        reset_button = QPushButton('Reset to saved settings')
        reset_button.clicked.connect(self.reset_settings)
        self.main_layout.addWidget(reset_button)

        save_button = QPushButton('Save')
        save_button.clicked.connect(self.save_settings)
        self.main_layout.addWidget(save_button)

    def add_setting_widget(self, layout, key, meta, category, sub_category=None):
        """Add a setting widget to the layout."""
        item_layout = QHBoxLayout()
        label = QLabel(f"{key.replace('_', ' ').capitalize()}:")
        label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        widget = self.create_widget_for_type(key, meta, category, sub_category)
        if not widget:
            return

        help_button = self.create_help_button(meta.get('description', ''))

        item_layout.addWidget(label)
        if isinstance(widget, QWidget):
            item_layout.addWidget(widget)
        else:
            item_layout.addLayout(widget)
        item_layout.addWidget(help_button)
        layout.addLayout(item_layout)

        # Set object names for the widget, label, and help button
        widget_name = f"{category}_{sub_category}_{key}_input" if sub_category else f"{category}_{key}_input"
        label_name = f"{category}_{sub_category}_{key}_label" if sub_category else f"{category}_{key}_label"
        help_name = f"{category}_{sub_category}_{key}_help" if sub_category else f"{category}_{key}_help"
        
        label.setObjectName(label_name)
        help_button.setObjectName(help_name)
        
        if isinstance(widget, QWidget):
            widget.setObjectName(widget_name)
        else:
            # If it's a layout (for model_path), set the object name on the QLineEdit
            line_edit = widget.itemAt(0).widget()
            if isinstance(line_edit, QLineEdit):
                line_edit.setObjectName(widget_name)

    def create_widget_for_type(self, key, meta, category, sub_category):
        """Create a widget based on the meta type."""
        meta_type = meta.get('type')
        current_value = self.get_config_value(category, sub_category, key, meta)

        if category == 'recording_options' and key == 'sound_device':
            return self.create_sound_device_widget(current_value)
        if meta_type == 'bool':
            return self.create_checkbox(current_value, key)
        elif meta_type == 'str' and 'options' in meta:
            return self.create_combobox(current_value, meta['options'])
        elif meta_type == 'str':
            return self.create_line_edit(current_value, key)
        elif meta_type in ['int', 'float']:
            return self.create_line_edit(str(current_value))
        return None

    def create_checkbox(self, value, key):
        widget = QCheckBox()
        widget.setChecked(value)
        if key == 'use_api':
            widget.setObjectName('model_options_use_api_input')
        return widget

    def create_combobox(self, value, options):
        widget = QComboBox()
        widget.addItems(options)
        widget.setCurrentText(value)
        return widget

    def create_line_edit(self, value, key=None):
        widget = QLineEdit(value)
        if key == 'api_key':
            widget.setEchoMode(QLineEdit.Password)
            widget.setText(os.getenv('OPENAI_API_KEY') or value)
        elif key == 'model_path':
            layout = QHBoxLayout()
            layout.addWidget(widget)
            browse_button = QPushButton('Browse')
            browse_button.clicked.connect(lambda: self.browse_model_path(widget))
            layout.addWidget(browse_button)
            layout.setContentsMargins(0, 0, 0, 0)
            container = QWidget()
            container.setLayout(layout)
            return container
        return widget

    def create_sound_device_widget(self, current_value):
        """Build the microphone picker + live 'test my mic' panel.

        Returns a container QWidget (its objectName is set to
        SOUND_DEVICE_WIDGET_NAME by the generic wiring), so get/set of the
        configured value is special-cased in the widget value helpers below.
        """
        container = QWidget()
        outer = QVBoxLayout()
        outer.setContentsMargins(0, 0, 0, 0)
        container.setLayout(outer)

        # Row 1: device dropdown + refresh
        picker_row = QHBoxLayout()
        self.sound_device_combo = QComboBox()
        self.sound_device_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._populate_devices(self.sound_device_combo, current_value)
        picker_row.addWidget(self.sound_device_combo)
        refresh_button = QPushButton('Refresh')
        refresh_button.setToolTip('Re-scan for input devices (e.g. after plugging in a mic).')
        refresh_button.clicked.connect(self._refresh_devices)
        picker_row.addWidget(refresh_button)
        outer.addLayout(picker_row)

        # Row 2: test button
        self.mic_test_button = QPushButton('Test microphone')
        self.mic_test_button.setCheckable(True)
        self.mic_test_button.toggled.connect(self._toggle_mic_test)
        if not _AUDIO_AVAILABLE:
            self.mic_test_button.setEnabled(False)
            self.mic_test_button.setToolTip('Audio libraries unavailable.')
        outer.addWidget(self.mic_test_button)

        # Row 3: live level bar
        self.mic_level_bar = QProgressBar()
        self.mic_level_bar.setRange(0, 100)
        self.mic_level_bar.setValue(0)
        self.mic_level_bar.setTextVisible(False)
        outer.addWidget(self.mic_level_bar)

        # Row 4: status text
        self.mic_test_status = QLabel('Idle — press "Test microphone" and speak.')
        self.mic_test_status.setWordWrap(True)
        outer.addWidget(self.mic_test_status)

        return container

    def _input_devices(self):
        """Return a list of (index, label) for usable input devices.

        Only MME devices are surfaced: MME resamples in the driver, so it's the
        one host API that reliably accepts the 16 kHz the app records at. Other
        host APIs (WASAPI/WDM-KS) reject 16 kHz and would only mislead the user.
        """
        devices = []
        if not _AUDIO_AVAILABLE:
            return devices
        try:
            hostapis = sd.query_hostapis()
            for idx, dev in enumerate(sd.query_devices()):
                if dev.get('max_input_channels', 0) <= 0:
                    continue
                hostapi = dev.get('hostapi')
                api_name = hostapis[hostapi]['name'] if hostapi is not None else ''
                if 'MME' not in api_name:
                    continue
                devices.append((idx, f"{idx}: {dev['name']}"))
        except Exception as e:
            ConfigManager.console_print(f'Could not enumerate input devices: {e}')
        return devices

    def _populate_devices(self, combo, selected_value):
        """Fill the combo with 'Default' + all input devices; select selected_value."""
        combo.blockSignals(True)
        combo.clear()
        combo.addItem('Default (system)', None)
        # Normalise a possibly-string index from an older config.
        selected_index = None
        if selected_value is not None:
            try:
                selected_index = int(selected_value)
            except (TypeError, ValueError):
                selected_index = None

        for idx, label in self._input_devices():
            combo.addItem(label, idx)

        target = 0  # default
        if selected_index is not None:
            pos = combo.findData(selected_index)
            if pos >= 0:
                target = pos
            else:
                # Configured device is not currently present; keep it visible.
                combo.addItem(f'{selected_index}: (not connected)', selected_index)
                target = combo.count() - 1
        combo.setCurrentIndex(target)
        combo.blockSignals(False)

    def _refresh_devices(self):
        if self.sound_device_combo is None:
            return
        current = self.sound_device_combo.currentData()
        self._populate_devices(self.sound_device_combo, current)

    def _toggle_mic_test(self, checked):
        if checked:
            self._start_mic_test()
        else:
            self._stop_mic_test()

    def _start_mic_test(self):
        if not _AUDIO_AVAILABLE:
            return
        self._stop_mic_test(update_button=False)  # ensure clean state
        device = self.sound_device_combo.currentData() if self.sound_device_combo else None
        sample_rate = ConfigManager.get_config_value('recording_options', 'sample_rate') or 16000
        self._test_peak = 0
        self._test_error = None
        self._test_started_at = time.time()

        def callback(indata, frames, time_info, status):
            try:
                self._test_peak = int(np.abs(indata).max())
            except Exception:
                self._test_peak = 0

        try:
            self._test_stream = sd.InputStream(
                samplerate=sample_rate, channels=1, dtype='int16',
                blocksize=int(sample_rate * 0.03), device=device, callback=callback
            )
            self._test_stream.start()
        except Exception as e:
            self._test_stream = None
            self._test_error = str(e)

        if self.mic_test_button:
            self.mic_test_button.setText('Stop test')
        self._test_timer.start()
        self._update_mic_level()

    def _stop_mic_test(self, update_button=True):
        self._test_timer.stop()
        if self._test_stream is not None:
            try:
                self._test_stream.stop()
                self._test_stream.close()
            except Exception:
                pass
            self._test_stream = None
        if self.mic_level_bar:
            self.mic_level_bar.setValue(0)
        if update_button:
            if self.mic_test_button:
                self.mic_test_button.blockSignals(True)
                self.mic_test_button.setChecked(False)
                self.mic_test_button.setText('Test microphone')
                self.mic_test_button.blockSignals(False)
            if self.mic_test_status:
                self.mic_test_status.setStyleSheet('')
                self.mic_test_status.setText('Idle — press "Test microphone" and speak.')

    def _update_mic_level(self):
        """Timer tick: reflect the latest captured level and receive-state."""
        if self.mic_test_status is None:
            return

        # Failed to open the device at all (e.g. busy / contended by another instance).
        if self._test_error is not None:
            self.mic_level_bar.setValue(0)
            self.mic_test_status.setStyleSheet('color: #c0392b;')
            self.mic_test_status.setText(
                f'Could not open this microphone: {self._test_error}\n'
                'It may be in use by another app (or a duplicate CustomWhisper instance).'
            )
            return

        # peak is 0..32768; map to 0..100 with a little headroom for visibility.
        peak = self._test_peak
        level = min(100, int(peak / 32768 * 100 * 2.5))
        self.mic_level_bar.setValue(level)

        NOISE_FLOOR = 150  # int16 amplitude below this is effectively digital silence
        if peak > NOISE_FLOOR:
            self.mic_test_status.setStyleSheet('color: #1e8449;')
            self.mic_test_status.setText(f'Receiving audio ✓  (level {level}%)')
        elif time.time() - self._test_started_at > 1.5:
            self.mic_test_status.setStyleSheet('color: #b9770e;')
            self.mic_test_status.setText(
                'Stream open but no audio detected — check the mic is unmuted, '
                'the right device is selected, and Windows mic access is allowed.'
            )
        else:
            self.mic_test_status.setStyleSheet('')
            self.mic_test_status.setText('Listening… speak into the mic.')

    def create_help_button(self, description):
        help_button = QToolButton()
        help_button.setIcon(self.style().standardIcon(QStyle.SP_MessageBoxQuestion))
        help_button.setAutoRaise(True)
        help_button.setToolTip(description)
        help_button.setCursor(Qt.PointingHandCursor)
        help_button.setFocusPolicy(Qt.TabFocus)
        help_button.clicked.connect(lambda: self.show_description(description))
        return help_button

    def get_config_value(self, category, sub_category, key, meta):
        if sub_category:
            return ConfigManager.get_config_value(category, sub_category, key) or meta['value']
        return ConfigManager.get_config_value(category, key) or meta['value']

    def browse_model_path(self, widget):
        file_path, _ = QFileDialog.getOpenFileName(self, "Select Whisper Model File", "", "Model Files (*.bin);;All Files (*)")
        if file_path:
            widget.setText(file_path)

    def show_description(self, description):
        """Show a description dialog."""
        QMessageBox.information(self, 'Description', description)

    def save_settings(self):
        """Save the settings to the config file and .env file."""
        self._stop_mic_test(update_button=False)  # release the mic before the app restarts
        self.iterate_settings(self.save_setting)

        # Save the API key to the .env file
        api_key = ConfigManager.get_config_value('model_options', 'api', 'api_key') or ''
        set_key('.env', 'OPENAI_API_KEY', api_key)
        os.environ['OPENAI_API_KEY'] = api_key

        # Remove the API key from the config
        ConfigManager.set_config_value(None, 'model_options', 'api', 'api_key')

        ConfigManager.save_config()
        QMessageBox.information(self, 'Settings Saved', 'Settings have been saved. The application will now restart.')
        self.settings_saved.emit()
        self.close()

    def save_setting(self, widget, category, sub_category, key, meta):
        value = self.get_widget_value_typed(widget, meta.get('type'))
        if sub_category:
            ConfigManager.set_config_value(value, category, sub_category, key)
        else:
            ConfigManager.set_config_value(value, category, key)

    def reset_settings(self):
        """Reset the settings to the saved values."""
        ConfigManager.reload_config()
        self.update_widgets_from_config()

    def update_widgets_from_config(self):
        """Update all widgets with values from the current configuration."""
        self.iterate_settings(self.update_widget_value)

    def update_widget_value(self, widget, category, sub_category, key, meta):
        """Update a single widget with the value from the configuration."""
        if sub_category:
            config_value = ConfigManager.get_config_value(category, sub_category, key)
        else:
            config_value = ConfigManager.get_config_value(category, key)

        self.set_widget_value(widget, config_value, meta.get('type'))

    def set_widget_value(self, widget, value, value_type):
        """Set the value of the widget."""
        if widget.objectName() == self.SOUND_DEVICE_WIDGET_NAME:
            if self.sound_device_combo is not None:
                self._populate_devices(self.sound_device_combo, value)
            return
        if isinstance(widget, QCheckBox):
            widget.setChecked(value)
        elif isinstance(widget, QComboBox):
            widget.setCurrentText(value)
        elif isinstance(widget, QLineEdit):
            widget.setText(str(value) if value is not None else '')
        elif isinstance(widget, QWidget) and widget.layout():
            # This is for the model_path widget
            line_edit = widget.layout().itemAt(0).widget()
            if isinstance(line_edit, QLineEdit):
                line_edit.setText(str(value) if value is not None else '')

    def get_widget_value_typed(self, widget, value_type):
        """Get the value of the widget with proper typing."""
        if widget.objectName() == self.SOUND_DEVICE_WIDGET_NAME:
            return self.sound_device_combo.currentData() if self.sound_device_combo else None
        if isinstance(widget, QCheckBox):
            return widget.isChecked()
        elif isinstance(widget, QComboBox):
            return widget.currentText() or None
        elif isinstance(widget, QLineEdit):
            text = widget.text()
            if value_type == 'int':
                return int(text) if text else None
            elif value_type == 'float':
                return float(text) if text else None
            else:
                return text or None
        elif isinstance(widget, QWidget) and widget.layout():
            # This is for the model_path widget
            line_edit = widget.layout().itemAt(0).widget()
            if isinstance(line_edit, QLineEdit):
                return line_edit.text() or None
        return None

    def toggle_api_local_options(self, use_api):
        """Toggle visibility of API and local options."""
        self.iterate_settings(lambda w, c, s, k, m: self.toggle_widget_visibility(w, c, s, k, use_api))

    def toggle_widget_visibility(self, widget, category, sub_category, key, use_api):
        if sub_category in ['api', 'local']:
            widget.setVisible(use_api if sub_category == 'api' else not use_api)
            
            # Also toggle visibility of the corresponding label and help button
            label = self.findChild(QLabel, f"{category}_{sub_category}_{key}_label")
            help_button = self.findChild(QToolButton, f"{category}_{sub_category}_{key}_help")
            
            if label:
                label.setVisible(use_api if sub_category == 'api' else not use_api)
            if help_button:
                help_button.setVisible(use_api if sub_category == 'api' else not use_api)


    def iterate_settings(self, func):
        """Iterate over all settings and apply a function to each."""
        for category, settings in self.schema.items():
            for sub_category, sub_settings in settings.items():
                if isinstance(sub_settings, dict) and 'value' in sub_settings:
                    widget = self.findChild(QWidget, f"{category}_{sub_category}_input")
                    if widget:
                        func(widget, category, None, sub_category, sub_settings)
                else:
                    for key, meta in sub_settings.items():
                        widget = self.findChild(QWidget, f"{category}_{sub_category}_{key}_input")
                        if widget:
                            func(widget, category, sub_category, key, meta)

    def closeEvent(self, event):
        """Confirm before closing the settings window without saving."""
        self._stop_mic_test(update_button=False)  # never leave the test stream holding the mic
        reply = QMessageBox.question(
            self,
            'Close without saving?',
            'Are you sure you want to close without saving?',
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            ConfigManager.reload_config()  # Revert to last saved configuration
            self.update_widgets_from_config()
            self.settings_closed.emit()
            super().closeEvent(event)
        else:
            event.ignore()
