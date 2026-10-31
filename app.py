"""Native SHD Media desktop shell. All network work stays off the Qt UI thread."""
import json
import logging
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot, QUrl, QLockFile, QTimer, Qt
from PySide6.QtGui import QColor, QIcon
from PySide6.QtWidgets import QApplication, QMainWindow, QFileDialog, QMessageBox, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSizeGrip
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView

from core import Service, ROOT


class Bridge(QObject):
    result = Signal(str, str)

    def __init__(self, service, parent):
        super().__init__(parent)
        self.service = service
        self.pool = ThreadPoolExecutor(max_workers=6)
        self.pending = 0
        self.allowed = {'bootstrap', 'search', 'library', 'settings', 'test_proxy', 'launch_thunder',
                        'subscribe', 'unsubscribe', 'check_subscriptions', 'calendar', 'calendar_covers', 'calendar_titles', 'subscription_covers'}

    @Slot(str, str, str)
    def request(self, request_id, method, payload):
        try:
            data = json.loads(payload)
            if method == 'browse':
                selected, _ = QFileDialog.getOpenFileName(self.parent(), '选择迅雷', '', '迅雷 (Thunder.exe)')
                self.result.emit(request_id, json.dumps({'ok': True, 'data': selected}))
                return
            if method not in self.allowed:
                raise ValueError('未知操作')
            future = self.pool.submit(getattr(self.service, method), data)
            future.add_done_callback(lambda f: self.done(request_id, f))
        except Exception as e:
            self.result.emit(request_id, json.dumps({'ok': False, 'error': str(e)}, ensure_ascii=False))

    def done(self, request_id, future):
        try:
            message = {'ok': True, 'data': future.result()}
        except Exception as e:
            logging.exception('Operation failed')
            message = {'ok': False, 'error': str(e)}
        self.result.emit(request_id, json.dumps(message, ensure_ascii=False))


class LocalPage(QWebEnginePage):
    def acceptNavigationRequest(self, url, kind, is_main):
        return url.isLocalFile() or url.scheme() in ('qrc', 'about', 'data')


class TitleBar(QWidget):
    def __init__(self, window):
        super().__init__(window)
        self.owner = window
        self.setFixedHeight(32)
        self.setStyleSheet('background:#151719;color:#d8dcdf;')
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 0, 0, 0)
        layout.setSpacing(0)
        mark = QLabel('●')
        mark.setStyleSheet('color:#ff8500;padding-right:8px;')
        layout.addWidget(mark)
        layout.addWidget(QLabel('SHD  /  影音终端'))
        layout.addStretch()
        for label, tip, action in [('—', '最小化', window.showMinimized), ('□', '最大化 / 还原', self.toggle), ('×', '关闭', window.close)]:
            button = QPushButton(label)
            button.setToolTip(tip)
            button.setFixedSize(46, 32)
            hover = '#b43b35' if label == '×' else '#30363a'
            button.setStyleSheet('QPushButton{border:0;font-size:17px;background:transparent;}QPushButton:hover{background:'+hover+';}')
            button.clicked.connect(action)
            layout.addWidget(button)

    def toggle(self):
        self.owner.showNormal() if self.owner.isMaximized() else self.owner.showMaximized()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.owner.windowHandle().startSystemMove()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.toggle()


class Window(QMainWindow):
    def __init__(self, service):
        super().__init__()
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.service = service
        self.setWindowTitle('SHD 影音终端')
        self.setWindowIcon(QIcon(str(ROOT / 'ui/assets/shd-minimal.ico')))
        self.resize(1280, 850)
        self.setMinimumSize(900, 650)
        self.view = QWebEngineView(self)
        self.page = LocalPage(self.view)
        self.page.setBackgroundColor(QColor('#151719'))
        self.view.setPage(self.page)
        self.view.settings().setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, False)
        self.channel = QWebChannel(self.page)
        self.bridge = Bridge(service, self)
        self.channel.registerObject('backend', self.bridge)
        self.page.setWebChannel(self.channel)
        shell = QWidget()
        shell.setStyleSheet('background:#151719;')
        layout = QVBoxLayout(shell)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.titlebar = TitleBar(self)
        layout.addWidget(self.titlebar)
        layout.addWidget(self.view)
        self.setCentralWidget(shell)
        self.resize_grip = QSizeGrip(self)
        self.resize_grip.setFixedSize(16, 16)
        self.view.load(QUrl.fromLocalFile(str(ROOT / 'ui' / 'index.html')))
        self.timer = QTimer(self)
        self.timer.setInterval(30 * 60 * 1000)
        self.timer.timeout.connect(lambda: self.bridge.pool.submit(service.check_subscriptions, {}))
        self.timer.start()

    def showEvent(self, event):
        super().showEvent(event)
        self.style_titlebar()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'resize_grip'):
            self.resize_grip.move(self.width()-16, self.height()-16)
            self.resize_grip.setVisible(not self.isMaximized())
            self.resize_grip.raise_()

    def style_titlebar(self):
        """Keep native window controls with the terminal's understated palette."""
        if sys.platform != 'win32':
            return
        import ctypes
        from ctypes import wintypes
        setter = ctypes.windll.dwmapi.DwmSetWindowAttribute
        setter.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
        setter.restype = ctypes.c_long
        # COLORREF uses 0x00BBGGRR. Unsupported attributes leave native defaults.
        for attribute, color in ((20, 1), (35, 0x191715), (36, 0xE6E4E1), (34, 0x39332E)):
            value = wintypes.DWORD(color)
            setter(int(self.winId()), attribute, ctypes.byref(value), ctypes.sizeof(value))

    def closeEvent(self, event):
        self.timer.stop()
        self.bridge.pool.shutdown(wait=False, cancel_futures=True)
        event.accept()


def main():
    if sys.platform == 'win32':
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('SHD.Media.Terminal')
    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon(str(ROOT / 'ui/assets/shd-minimal.ico')))
    app.setApplicationName('SHD Media')
    app.setStyle('Fusion')
    (ROOT / 'data').mkdir(exist_ok=True)
    logging.basicConfig(filename=str(ROOT / 'data' / 'app.log'), level=logging.INFO,
                        format='%(asctime)s %(levelname)s %(message)s', encoding='utf-8')
    lock = QLockFile(str(ROOT / 'data' / 'app.lock'))
    if not lock.tryLock(100):
        QMessageBox.information(None, 'SHD 影音终端', '程序已在运行，请切换到现有窗口。')
        return 0
    service = Service()
    window = Window(service)
    window.show()
    try:
        return app.exec()
    finally:
        lock.unlock()


if __name__ == '__main__':
    sys.exit(main())
