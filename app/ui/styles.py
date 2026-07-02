from __future__ import annotations

from typing import Final

from PySide6 import QtWidgets


APP_STYLESHEET: Final[str] = """
QWidget {
    background-color: #1e1e1e;
    color: #d4d4d4;
    font-size: 12px;
    selection-background-color: #0078d4;
    selection-color: #ffffff;
}

QMainWindow {
    background-color: #1e1e1e;
}

QGroupBox {
    background-color: #252526;
    border: 1px solid #3c3c3c;
    border-radius: 6px;
    margin-top: 14px;
    padding: 8px;
}

QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    color: #ffffff;
    padding: 0 6px;
}

QTabWidget::pane {
    background-color: #1e1e1e;
    border: 1px solid #3c3c3c;
    border-radius: 6px;
    top: -1px;
}

QTabBar::tab {
    background-color: #252526;
    border: 1px solid #3c3c3c;
    border-bottom-color: #3c3c3c;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    color: #bdbdbd;
    min-width: 84px;
    padding: 8px 12px;
}

QTabBar::tab:selected {
    background-color: #1e1e1e;
    border-bottom-color: #1e1e1e;
    color: #ffffff;
}

QTabBar::tab:hover:!selected {
    background-color: #2d2d30;
    color: #ffffff;
}

QPushButton {
    background-color: #2d2d30;
    border: 1px solid #3c3c3c;
    border-radius: 6px;
    color: #ffffff;
    padding: 8px 12px;
}

QPushButton:hover {
    background-color: #333337;
    border-color: #0078d4;
}

QPushButton:pressed {
    background-color: #0078d4;
    border-color: #0078d4;
}

QPushButton:disabled {
    background-color: #252526;
    border-color: #333333;
    color: #6a6a6a;
}

QComboBox,
QSpinBox,
QDoubleSpinBox,
QLineEdit,
QPlainTextEdit {
    background-color: #252526;
    border: 1px solid #3c3c3c;
    border-radius: 6px;
    color: #d4d4d4;
    padding: 6px 8px;
}

QComboBox:hover,
QSpinBox:hover,
QDoubleSpinBox:hover,
QLineEdit:hover,
QPlainTextEdit:hover {
    border-color: #505050;
}

QComboBox:focus,
QSpinBox:focus,
QDoubleSpinBox:focus,
QLineEdit:focus,
QPlainTextEdit:focus {
    border-color: #0078d4;
}

QComboBox:disabled,
QSpinBox:disabled,
QDoubleSpinBox:disabled,
QLineEdit:disabled,
QPlainTextEdit:disabled {
    background-color: #202020;
    border-color: #333333;
    color: #6a6a6a;
}

/* SpinBox buttons - clear visual separation with direction indicators */
QSpinBox::up-button,
QSpinBox::down-button,
QDoubleSpinBox::up-button,
QDoubleSpinBox::down-button {
    background-color: #2d2d30;
    border: none;
    border-left: 1px solid #3c3c3c;
    width: 22px;
    subcontrol-origin: border;
}

QSpinBox::up-button,
QDoubleSpinBox::up-button {
    subcontrol-position: top right;
    border-top-right-radius: 5px;
    /* Up arrow using border triangle */
    background-image: none;
}

QSpinBox::down-button,
QDoubleSpinBox::down-button {
    subcontrol-position: bottom right;
    border-bottom-right-radius: 5px;
}

/* Style the buttons to show direction via background gradient */
QSpinBox::up-button,
QDoubleSpinBox::up-button {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #3a3a3f, stop:1 #2d2d30);
}

QSpinBox::down-button,
QDoubleSpinBox::down-button {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #2d2d30, stop:1 #3a3a3f);
}

/* Hover states */
QSpinBox::up-button:hover,
QSpinBox::down-button:hover,
QDoubleSpinBox::up-button:hover,
QDoubleSpinBox::down-button:hover {
    background-color: #0078d4;
    border-left-color: #0078d4;
}

/* Pressed states */
QSpinBox::up-button:pressed,
QSpinBox::down-button:pressed,
QDoubleSpinBox::up-button:pressed,
QDoubleSpinBox::down-button:pressed {
    background-color: #005a9e;
}

/* Disabled state */
QSpinBox:disabled::up-button,
QSpinBox:disabled::down-button,
QDoubleSpinBox:disabled::up-button,
QDoubleSpinBox:disabled::down-button {
    background-color: #202020;
    border-left-color: #333333;
}

QComboBox QAbstractItemView {
    background-color: #252526;
    border: 1px solid #3c3c3c;
    color: #d4d4d4;
    outline: 0;
    selection-background-color: #0078d4;
    selection-color: #ffffff;
}

QCheckBox {
    background-color: transparent;
    spacing: 8px;
}

QCheckBox::indicator {
    background-color: #252526;
    border: 1px solid #3c3c3c;
    border-radius: 4px;
    height: 14px;
    width: 14px;
}

QCheckBox::indicator:hover {
    border-color: #0078d4;
}

QCheckBox::indicator:checked {
    background-color: #0078d4;
    border-color: #0078d4;
}

QLabel {
    background-color: transparent;
    color: #d4d4d4;
}

QScrollArea {
    background-color: #1e1e1e;
    border: 1px solid #3c3c3c;
    border-radius: 6px;
}

QScrollArea > QWidget > QWidget {
    background-color: #1e1e1e;
}

QScrollBar:vertical,
QScrollBar:horizontal {
    background-color: #1e1e1e;
    border: none;
    margin: 0;
}

QScrollBar:vertical {
    width: 12px;
}

QScrollBar:horizontal {
    height: 12px;
}

QScrollBar::handle:vertical,
QScrollBar::handle:horizontal {
    background-color: #3c3c3c;
    border-radius: 6px;
    min-height: 24px;
    min-width: 24px;
}

QScrollBar::handle:vertical:hover,
QScrollBar::handle:horizontal:hover {
    background-color: #505050;
}

QScrollBar::add-line,
QScrollBar::sub-line,
QScrollBar::add-page,
QScrollBar::sub-page {
    background: none;
    border: none;
}
"""


def apply_style(app: QtWidgets.QApplication) -> None:
    app.setStyleSheet(APP_STYLESHEET)
