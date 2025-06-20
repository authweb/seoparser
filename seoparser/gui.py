import asyncio
from dataclasses import asdict
from functools import partial

from PyQt5.QtCore import Qt, QAbstractTableModel, QModelIndex, QSortFilterProxyModel
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton,
    QProgressBar, QPlainTextEdit, QTableView, QFileDialog, QLabel
)

from .crawler import SEOCrawler, PageResult


class ResultTableModel(QAbstractTableModel):
    headers = ["URL", "Title", "Description", "H1", "Canonical", "Meta Robots", "Status"]

    def __init__(self, data):
        super().__init__()
        self._data = data

    def rowCount(self, parent=QModelIndex()):
        return len(self._data)

    def columnCount(self, parent=QModelIndex()):
        return len(self.headers)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        row = index.row()
        col = index.column()
        page = self._data[row]
        if role == Qt.DisplayRole:
            return asdict(page)[self.headers[col].replace(' ', '_').lower()]
        if role == Qt.BackgroundRole and page.status != 200:
            from PyQt5.QtGui import QBrush, QColor
            return QBrush(QColor('#ffcccc'))
        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self.headers[section]
        return super().headerData(section, orientation, role)

    def update(self):
        self.layoutChanged.emit()


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SEO Parser")
        self.crawler = None
        self.loop = asyncio.get_event_loop()
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        url_layout = QHBoxLayout()
        self.url_edit = QLineEdit()
        self.start_btn = QPushButton("Start")
        self.start_btn.clicked.connect(self.start_crawl)
        url_layout.addWidget(QLabel("URL:"))
        url_layout.addWidget(self.url_edit)
        url_layout.addWidget(self.start_btn)
        layout.addLayout(url_layout)

        self.progress = QProgressBar()
        layout.addWidget(self.progress)

        self.table_model = ResultTableModel([])
        self.proxy_model = QSortFilterProxyModel()
        self.proxy_model.setSourceModel(self.table_model)
        self.proxy_model.setFilterCaseSensitivity(Qt.CaseInsensitive)

        self.table = QTableView()
        self.table.setModel(self.proxy_model)
        self.table.setSortingEnabled(True)
        layout.addWidget(self.table)

        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("Filter:"))
        self.filter_edit = QLineEdit()
        self.filter_edit.textChanged.connect(self.proxy_model.setFilterFixedString)
        filter_layout.addWidget(self.filter_edit)
        layout.addLayout(filter_layout)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        layout.addWidget(self.log)

        export_btn = QPushButton("Export")
        export_btn.clicked.connect(self.export_results)
        layout.addWidget(export_btn)

    def log_message(self, msg: str):
        self.log.appendPlainText(msg)

    def on_progress(self, current: int, total: int):
        percent = int(current / total * 100) if total else 0
        self.progress.setValue(percent)

    def export_results(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save", "results.csv", "CSV (*.csv)")
        if not path:
            return
        self.crawler.export(path.rsplit('.', 1)[0])
        self.log_message(f"Exported to {path}")

    def start_crawl(self):
        url = self.url_edit.text().strip()
        if not url:
            return
        self.crawler = SEOCrawler(url, progress_callback=self.on_progress)
        self.table_model._data = self.crawler.results
        self.table_model.update()
        self.progress.setValue(0)
        self.log_message("Starting crawl...")
        asyncio.ensure_future(self.run_crawl())

    async def run_crawl(self):
        await self.crawler.crawl()
        self.table_model.update()
        self.log_message("Crawl finished")
        self.progress.setValue(100)


def run_app():
    app = QApplication([])
    window = MainWindow()
    window.resize(800, 600)
    window.show()
    asyncio.get_event_loop().run_until_complete(app.exec_())


if __name__ == "__main__":
    run_app()
