import sys
from PySide6.QtCore import Qt, QRect, QSize, QRegularExpression
from PySide6.QtGui import QFont, QColor, QTextFormat, QPainter, QAction, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import QApplication, QMainWindow, QTextEdit, QFileDialog


class LineNumberAreaMixin:
    def __init__(self, editor):
        super().__init__()

        self.code_editor = editor
        self.line_number_area_width = 50

    def line_number_area_width_update(self, _):
        self.code_editor.setViewportMargins(self.line_number_area_width, 0, 0, 0)

    def line_number_area_paint_event(self, event):
        painter = QPainter(self.code_editor.line_number_area)
        painter.fillRect(event.rect(), QColor('#E8E8E8'))

        block = self.code_editor.firstVisibleBlock()
        block_number = block.blockNumber()
        top = int(self.code_editor.blockBoundingGeometry(block).translated(self.code_editor.contentOffset()).top())
        bottom = top + int(self.code_editor.blockBoundingRect(block).height())

        # 绘制可见区域内的行号
        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                number = str(block_number + 1)
                painter.setPen(Qt.black)
                painter.drawText(0, top, self.code_editor.line_number_area.width(), self.code_editor.fontMetrics().height(),
                                 Qt.AlignCenter, number)

            block = block.next()
            top = bottom
            bottom = top + int(self.code_editor.blockBoundingRect(block).height())
            block_number += 1


class PythonEditor(QMainWindow):
    def __init__(self):
        super().__init__()

        self.text_edit = QTextEdit(self)
        self.setCentralWidget(self.text_edit)

        # 添加行号区域
        self.line_number_area = LineNumberAreaMixin(self.text_edit)
        self.line_number_area.line_number_area_width_update(None)

        self.init_ui()

        # 连接信号和槽
        self.text_edit.blockCountChanged.connect(self.line_number_area.line_number_area_width_update)
        self.text_edit.updateRequest.connect(self.line_number_area.line_number_area_paint_event)

    def init_ui(self):
        # 创建菜单栏
        menubar = self.menuBar()
        file_menu = menubar.addMenu('File')

        # 创建打开和保存文件的操作
        open_action = QAction('Open', self)
        open_action.triggered.connect(self.open_file)
        file_menu.addAction(open_action)

        save_action = QAction('Save', self)
        save_action.triggered.connect(self.save_file)
        file_menu.addAction(save_action)

        # 设置窗口属性
        self.setWindowTitle('Python Editor')
        self.setGeometry(100, 100, 800, 600)

    def open_file(self):
        file_dialog = QFileDialog(self)
        file_dialog.setNameFilter('Python Files (*.py)')
        file_dialog.setFileMode(QFileDialog.ExistingFile)

        if file_dialog.exec_():
            file_path = file_dialog.selectedFiles()[0]

            with open(file_path, 'r') as file:
                self.text_edit.setPlainText(file.read())

    def save_file(self):
        file_dialog = QFileDialog(self)
        file_dialog.setNameFilter('Python Files (*.py)')
        file_dialog.setAcceptMode(QFileDialog.AcceptSave)

        if file_dialog.exec_():
            file_path = file_dialog.selectedFiles()[0]

            with open(file_path, 'w') as file:
                file.write(self.text_edit.toPlainText())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cr = self.contentsRect()
        self.line_number_area.setGeometry(QRect(cr.left(), cr.top(), self.line_number_area_width, cr.height()))


class CodeHighlightMixin:
    def __init__(self, editor):
        super().__init__()

        self.code_editor = editor

    def highlight_current_line(self):
        extra_selections = []

        if not self.code_editor.isReadOnly():
            selection = QTextEdit.ExtraSelection()

            line_color = QColor(Qt.yellow).lighter(160)

            selection.format.setBackground(line_color)
            selection.format.setProperty(QTextFormat.FullWidthSelection, True)
            selection.cursor = self.code_editor.textCursor()
            selection.cursor.clearSelection()

            extra_selections.append(selection)

        self.code_editor.setExtraSelections(extra_selections)

    def highlight_syntax(self):
        text = self.code_editor.toPlainText()

        # 清除所有格式
        self.code_editor.setPlainText(text)

        keyword_format = QTextCharFormat()
        keyword_format.setForeground(QColor("#0000FF"))
        keyword_format.setFontWeight(QFont.Bold)

        keywords = ["def", "class", "if", "else", "elif", "for", "while", "import", "from", "as", "return", "try", "except", "finally", "raise"]

        # 对关键字进行高亮
        for keyword in keywords:
            expression = "\\b" + keyword + "\\b"
            pattern = QRegularExpression(expression)
            matches = pattern.globalMatch(text)

            while matches.hasNext():
                match = matches.next()
                start = match.capturedStart()
                length = match.capturedLength()

                format_range = QTextCharFormat()
                format_range.setForeground(QColor("#0000FF"))
                format_range.setFontWeight(QFont.Bold)
                cursor = self.code_editor.textCursor()
                cursor.setPosition(start)
                cursor.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor, length)
                cursor.mergeCharFormat(format_range)

        self.highlight_current_line()


class PythonEditorWithHighlight(PythonEditor, CodeHighlightMixin):
    def __init__(self):
        super().__init__()

    def init_ui(self):
        super().init_ui()
        self.highlight_syntax()

    def line_number_area_paint_event(self, event):
        super().line_number_area.line_number_area_paint_event(event)
        self.highlight_current_line()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    editor = PythonEditorWithHighlight()
    editor.show()
    sys.exit(app.exec())
