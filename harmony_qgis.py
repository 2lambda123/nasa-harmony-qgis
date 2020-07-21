# -*- coding: utf-8 -*-
"""
/***************************************************************************
 HarmonyQGIS
                                 A QGIS plugin
 Access the Harmony service broker to process and download Earth science data
 Generated by Plugin Builder: http://g-sherman.github.io/Qgis-Plugin-Builder/
                              -------------------
        begin                : 2020-04-05
        git sha              : $Format:%H$
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""
from qgis.PyQt.QtCore import QSettings, QTranslator, QCoreApplication
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction, QTableWidgetItem, QInputDialog, QLineEdit
from qgis.core import QgsProject, QgsSettings, QgsVectorLayer, QgsVectorFileWriter, QgsCoordinateTransformContext, QgsRasterLayer, QgsMessageLog
# from qgis.utils import iface
from zipfile import ZipFile
import tempfile
import requests
import copy
import json
import math
import platform

# Initialize Qt resources from file resources.py
from .resources import *
# Import the code for the dialog
from .harmony_qgis_dialog import HarmonyQGISDialog
from .harmony_qgis_sessions import newSessionTag, switchSession, manageSessions, populateSessionsCombo, saveSession, startDeleteSession
from .HarmonyEventFilter import HarmonyEventFilter
import os.path
from .harmony_response import handleHarmonyResponse
from .harmony_qgis_sessions_dialog import HarmonyQGISSessionsDialog
from .rewind import rewind

class HarmonyQGIS:
    """QGIS Plugin Implementation."""

    def __init__(self, iface):
        """Constructor.

        :param iface: An interface instance that will be passed to this class
            which provides the hook by which you can manipulate the QGIS
            application at run time.
        :type iface: QgsInterface
        """
        # Save reference to the QGIS interface
        self.iface = iface
        # initialize plugin directory
        self.plugin_dir = os.path.dirname(__file__)
        # initialize locale
        locale = QSettings().value('locale/userLocale')[0:2]
        locale_path = os.path.join(
            self.plugin_dir,
            'i18n',
            'HarmonyQGIS_{}.qm'.format(locale))

        if os.path.exists(locale_path):
            self.translator = QTranslator()
            self.translator.load(locale_path)
            QCoreApplication.installTranslator(self.translator)

        # Declare instance attributes
        self.actions = []
        self.menu = self.tr(u'&Harmony')

        # Check if plugin was started the first time in current QGIS session
        # Must be set in initGui() to survive plugin reloads
        self.first_start = None

    # noinspection PyMethodMayBeStatic
    def tr(self, message):
        """Get the translation for a string using Qt translation API.

        We implement this ourselves since we do not inherit QObject.

        :param message: String for translation.
        :type message: str, QString

        :returns: Translated version of message.
        :rtype: QString
        """
        # noinspection PyTypeChecker,PyArgumentList,PyCallByClass
        return QCoreApplication.translate('HarmonyQGIS', message)


    def add_action(
        self,
        icon_path,
        text,
        callback,
        enabled_flag=True,
        add_to_menu=True,
        add_to_toolbar=True,
        status_tip=None,
        whats_this=None,
        parent=None):
        """Add a toolbar icon to the toolbar.

        :param icon_path: Path to the icon for this action. Can be a resource
            path (e.g. ':/plugins/foo/bar.png') or a normal file system path.
        :type icon_path: str

        :param text: Text that should be shown in menu items for this action.
        :type text: str

        :param callback: Function to be called when the action is triggered.
        :type callback: function

        :param enabled_flag: A flag indicating if the action should be enabled
            by default. Defaults to True.
        :type enabled_flag: bool

        :param add_to_menu: Flag indicating whether the action should also
            be added to the menu. Defaults to True.
        :type add_to_menu: bool

        :param add_to_toolbar: Flag indicating whether the action should also
            be added to the toolbar. Defaults to True.
        :type add_to_toolbar: bool

        :param status_tip: Optional text to show in a popup when mouse pointer
            hovers over the action.
        :type status_tip: str

        :param parent: Parent widget for the new action. Defaults None.
        :type parent: QWidget

        :param whats_this: Optional text to show in the status bar when the
            mouse pointer hovers over the action.

        :returns: The action that was created. Note that the action is also
            added to self.actions list.
        :rtype: QAction
        """

        icon = QIcon(icon_path)
        action = QAction(icon, text, parent)
        action.triggered.connect(callback)
        action.setEnabled(enabled_flag)

        if status_tip is not None:
            action.setStatusTip(status_tip)

        if whats_this is not None:
            action.setWhatsThis(whats_this)

        if add_to_toolbar:
            # Adds plugin icon to Plugins toolbar
            self.iface.addToolBarIcon(action)

        if add_to_menu:
            self.iface.addPluginToMenu(
                self.menu,
                action)

        self.actions.append(action)

        return action

    def initGui(self):
        """Create the menu entries and toolbar icons inside the QGIS GUI."""

        icon_path = ':/plugins/harmony_qgis/icon.png'
        self.add_action(
            icon_path,
            text=self.tr(u'Harmony'),
            callback=self.run,
            parent=self.iface.mainWindow())

        # will be set False in run()
        self.first_start = True


    def unload(self):
        """Removes the plugin menu item and icon from QGIS GUI."""
        for action in self.actions:
            self.iface.removePluginMenu(
                self.tr(u'&Harmony'),
                action)
            self.iface.removeToolBarIcon(action)

    def addSearchParameter(self):
        """Add a search parameter to the parameter table"""
        rowPosition = self.dlg.tableWidget.rowCount()
        self.dlg.tableWidget.insertRow(rowPosition)
        self.dlg.tableWidget.setItem(rowPosition, 0, QTableWidgetItem(""))
        self.dlg.tableWidget.setItem(rowPosition, 1, QTableWidgetItem(""))

    def deleteSearchParameter(self):
        """Remove a search parameter from the table"""
        self.dlg.tableWidget.removeRow(self.dlg.tableWidget.currentRow())

    def setupGui(self):
        self.sessionsDlg.deletebutton.clicked.connect(lambda:startDeleteSession(self.dlg, self.sessionsDlg))
        self.dlg.sessionsButton.clicked.connect(lambda:manageSessions(self))
        self.dlg.sessionCombo.currentIndexChanged.connect(lambda:switchSession(self.dlg))
        # add/remove additional query parameters
        self.dlg.addButton.clicked.connect(self.addSearchParameter)
        self.dlg.removeRowButton.clicked.connect(self.deleteSearchParameter)

    def run(self):
        """Run method that performs all the real work"""

        # Create the dialog with elements (after translation) and keep reference
        # Only create GUI ONCE in callback, so that it will only load when the plugin is started
        if self.first_start == True:
            self.first_start = False
            self.dlg = HarmonyQGISDialog()
            self.sessionsDlg = HarmonyQGISSessionsDialog()
            self.setupGui()
        
        self.eventFilter = HarmonyEventFilter(self)
        self.dlg.installEventFilter(self.eventFilter)

        # get stored settings
        settings = QgsSettings()

        # Handle sessions
        # self.dlg.sessionAddButton.clicked.connect(lambda:addSession(self.dlg))
        
        populateSessionsCombo(self.dlg)
        
        # Fetch the currently loaded layers
        layers = QgsProject.instance().layerTreeRoot().children()
        layerNames = [layer.name() for layer in layers]
        layerNames.insert(0, "<None>")

        # Clear the contents of the comboBox from previous runs
        self.dlg.comboBox.clear()
        # Populate the comboBox with names of all the loaded layers
        self.dlg.comboBox.addItems(layerNames)

        # use the active layer as the default
        layer = self.iface.activeLayer()
        if layer:
            self.dlg.comboBox.setCurrentIndex(layerNames.index(layer.name()))

        # set the download directory to the saved value or the system temporary directory
        tempDir = "/tmp"
        if platform.system() == 'Windows':
            tempDir = tempfile.gettempdir()
        downloadDir = settings.value("harmony_qgis/download_dir") or tempDir
        self.dlg.harmonyDownloadDirEdit.setText(downloadDir)

        # fill the harmnoy url input with the saved setting if available
        # harmonyUrl = settings.value("harmony_qgis/harmony_url")
        # if harmonyUrl:
        self.dlg.harmonyUrlLineEdit.clear()

        # collectionId = settings.value("harmony_qgis/collection_id")
        # if collectionId:
        self.dlg.collectionField.clear()

        # version = settings.value("harmony_qgis/version") or "1.0.0"
        self.dlg.versionField.clear()

        # variable = settings.value("harmony_qgis/variable")
        # if variable:
        self.dlg.variableField.clear()

        # clear the table
        self.dlg.tableWidget.setRowCount(0)

        # set the table header
        self.dlg.tableWidget.setHorizontalHeaderLabels('Parameter;Value'.split(';'))

        # DEBUG
        # settings.setValue("saved_sessions", [])

        # show the dialog
        self.dlg.show()
        # Run the dialog event loop
        result = self.dlg.exec_()
        # See if OK was pressed
        if result:
            # ask to save settings
            sessionName = str(self.dlg.sessionCombo.currentText())
            if sessionName == newSessionTag:
                newName, ok = QInputDialog(self.dlg).getText(self.dlg, "Save session?", "Session name:", QLineEdit.Normal)
                if ok and newName:
                    saveSession(self.dlg, newName)
            else:
                saveSession(self.dlg, sessionName)

            # save the dowload diretory in the UI to settings
            settings.setValue("harmony_qgis/download_dir", self.dlg.harmonyDownloadDirEdit.text())

            collectionId = str(self.dlg.collectionField.text())
            version = str(self.dlg.versionField.text())
            variable = str(self.dlg.variableField.text())

            harmonyUrl = self.dlg.harmonyUrlLineEdit.text()
            path = collectionId + "/" + "ogc-api-coverages/" + version + "/collections/" + variable + "/coverage/rangeset"
            url = harmonyUrl + "/" + path

            layerName = str(self.dlg.comboBox.currentText())
            QgsMessageLog.logMessage(layerName)
            if layerName == "<None>":
                # use a GET request
                rowCount = self.dlg.tableWidget.rowCount()
                for row in range(rowCount):
                    separator = "&"
                    if row == 0:
                        separator = "?"
                    parameter = self.dlg.tableWidget.item(row, 0).text()
                    value = self.dlg.tableWidget.item(row, 1).text()
                    url = url + separator + parameter + "=" + value
                resp = requests.get(url)
            else:
                layer = QgsProject.instance().mapLayersByName(layerName)[0]
                opts = QgsVectorFileWriter.SaveVectorOptions()
                opts.driverName = 'GeoJson'
                tempFile = tempfile.gettempdir() + os.path.sep + 'qgis.json'
                QgsVectorFileWriter.writeAsVectorFormatV2(layer, tempFile, QgsCoordinateTransformContext(), opts)
             
                QgsMessageLog.logMessage("URL:" + url, "Harmony Plugin")

                tempFileHandle = open(tempFile, 'r')
                contents = tempFileHandle.read()
                tempFileHandle.close()
                geoJson = rewind(contents)
                tempFileHandle = open(tempFile, 'w')
                tempFileHandle.write(geoJson)
                tempFileHandle.close()
                tempFileHandle = open(tempFile, 'rb')

                multipart_form_data = {
                    'shapefile': (layerName + '.geojson', tempFileHandle, 'application/geo+json')
                }

                rowCount = self.dlg.tableWidget.rowCount()
                for row in range(rowCount):
                    parameter = self.dlg.tableWidget.item(row, 0).text()
                    value = self.dlg.tableWidget.item(row, 1).text()
                    multipart_form_data[parameter] = (None, value)

                resp = requests.post(url, files=multipart_form_data, stream=True)
                tempFileHandle.close()

            handleHarmonyResponse(self.iface, resp, layerName, variable)