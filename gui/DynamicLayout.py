
from PySide6 import QtCore, QtGui, QtWidgets



class Dialog(QtWidgets.QDialog):
    def __init__(self):
        super(Dialog, self).__init__()

        self.rotableWidgets = []

        self.createRotableGroupBox()
        self.createOptionsGroupBox()
        self.createButtonBox()

        mainLayout = QtWidgets.QGridLayout()
        mainLayout.addWidget(self.rotableGroupBox, 0, 0)
        mainLayout.addWidget(self.optionsGroupBox, 1, 0)
        mainLayout.addWidget(self.buttonBox, 2, 0)
        mainLayout.setSizeConstraint(QtWidgets.QLayout.SetMinimumSize)

        self.mainLayout = mainLayout
        self.setLayout(self.mainLayout)

        self.setWindowTitle("Dynamic Layouts")

    def rotateWidgets(self):
        count = len(self.rotableWidgets)
        if count % 2 == 1:
            raise AssertionError("Number of widgets must be even")

        for widget in self.rotableWidgets:
            self.rotableLayout.removeWidget(widget)

        self.rotableWidgets.append(self.rotableWidgets.pop(0))

        for i in range(count // 2):
            self.rotableLayout.addWidget(self.rotableWidgets[count - i - 1], 0, i)
            self.rotableLayout.addWidget(self.rotableWidgets[i], 1, i)

    def buttonsOrientationChanged(self, index):
        self.mainLayout.setSizeConstraint(QtWidgets.QLayout.SetNoConstraint);
        self.setMinimumSize(0, 0);

        orientation = Qt.Orientation(int(self.buttonsOrientationComboBox.itemData(index)))

        if orientation == self.buttonBox.orientation():
            return

        self.mainLayout.removeWidget(self.buttonBox);

        spacing = self.mainLayout.spacing()

        oldSizeHint = self.buttonBox.sizeHint() + QtWidgets.QSize(spacing, spacing);
        self.buttonBox.setOrientation(orientation)
        newSizeHint = self.buttonBox.sizeHint() + QtWidgets.QSize(spacing, spacing)

        if orientation == QtWidgets.Horizontal:
            self.mainLayout.addWidget(self.buttonBox, 2, 0);
            self.resize(self.size() + QtWidgets.QSize(-oldSizeHint.width(), newSizeHint.height()))
        else:
            self.mainLayout.addWidget(self.buttonBox, 0, 3, 2, 1);
            self.resize(self.size() + QtWidgets.QSize(newSizeHint.width(), -oldSizeHint.height()))

        self.mainLayout.setSizeConstraint(QtWidgets.QLayout.SetDefaultConstraint)

    def show_help(self):
        QtWidgets.QMessageBox.information(self, "Dynamic Layouts Help",
                                "This example shows how to change layouts "
                                "dynamically.")

    def createRotableGroupBox(self):
        self.rotableGroupBox = QtWidgets.QGroupBox("Rotable Widgets")

        self.rotableWidgets.append(QtWidgets.QSpinBox())
        self.rotableWidgets.append(QtWidgets.QSlider())
        self.rotableWidgets.append(QtWidgets.QDial())
        self.rotableWidgets.append(QtWidgets.QProgressBar())
        count = len(self.rotableWidgets)
        for i in range(count):
            self.rotableWidgets[i].valueChanged[int]. \
                connect(self.rotableWidgets[(i + 1) % count].setValue)

        self.rotableLayout = QtWidgets.QGridLayout()
        self.rotableGroupBox.setLayout(self.rotableLayout)

        self.rotateWidgets()

    def createOptionsGroupBox(self):
        self.optionsGroupBox = QtWidgets.QGroupBox("Options")

        buttonsOrientationLabel = QtWidgets.QLabel("Orientation of buttons:")

        buttonsOrientationComboBox = QtWidgets.QComboBox()
        buttonsOrientationComboBox.addItem("Horizontal", QtWidgets.Horizontal)
        buttonsOrientationComboBox.addItem("Vertical", QtWidgets.Vertical)
        buttonsOrientationComboBox.currentIndexChanged[int].connect(self.buttonsOrientationChanged)

        self.buttonsOrientationComboBox = buttonsOrientationComboBox

        optionsLayout = QtWidgets.QGridLayout()
        optionsLayout.addWidget(buttonsOrientationLabel, 0, 0)
        optionsLayout.addWidget(self.buttonsOrientationComboBox, 0, 1)
        optionsLayout.setColumnStretch(2, 1)
        self.optionsGroupBox.setLayout(optionsLayout)

    def createButtonBox(self):
        self.buttonBox = QtWidgets.QDialogButtonBox()

        closeButton = self.buttonBox.addButton(QtWidgets.QDialogButtonBox.Close)
        helpButton = self.buttonBox.addButton(QtWidgets.QDialogButtonBox.Help)
        rotateWidgetsButton = self.buttonBox.addButton("Rotate &Widgets", QtWidgets.QDialogButtonBox.ActionRole)

        rotateWidgetsButton.clicked.connect(self.rotateWidgets)
        closeButton.clicked.connect(self.close)
        helpButton.clicked.connect(self.show_help)