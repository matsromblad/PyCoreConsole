from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QListWidget, QDialogButtonBox, QLabel, QPushButton, QHBoxLayout
)
from typing import List
from core.models import Workflow, ScriptItem

class TemplatesDialog(QDialog):
    def __init__(self, templates: List[Workflow], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Templates")
        self.templates = templates
        self.selected_items: List[ScriptItem] = []

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Choose a template:"))
        self.listw = QListWidget()
        for tpl in templates:
            self.listw.addItem(tpl.name)
        layout.addWidget(self.listw)

        self.preview = QLabel("Preview: select a template to see items.")
        self.preview.setStyleSheet("QLabel { font-family: Consolas, monospace; }")
        self.preview.setWordWrap(True)
        layout.addWidget(self.preview)

        self.listw.currentRowChanged.connect(self._on_row)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _on_row(self, row: int):
        if row < 0: 
            self.preview.setText("")
            return
        tpl = self.templates[row]
        lines = []
        for it in tpl.items:
            lines.append(f"- {it.type.value.upper()}: {it.path}   {('invoke='+it.invoke) if it.invoke else ''}")
        self.preview.setText("\n".join(lines))

    def _accept(self):
        idx = self.listw.currentRow()
        if idx >= 0:
            self.selected_items = self.templates[idx].items
        self.accept()