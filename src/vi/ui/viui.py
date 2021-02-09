###########################################################################
#  Vintel - Visual Intel Chat Analyzer									  #
#  Copyright (C) 2014-15 Sebastian Meyer (sparrow.242.de+eve@gmail.com )  #
#																		  #
#  This program is free software: you can redistribute it and/or modify	  #
#  it under the terms of the GNU General Public License as published by	  #
#  the Free Software Foundation, either version 3 of the License, or	  #
#  (at your option) any later version.									  #
#																		  #
#  This program is distributed in the hope that it will be useful,		  #
#  but WITHOUT ANY WARRANTY; without even the implied warranty of		  #
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.	 See the		  #
#  GNU General Public License for more details.							  #
#																		  #
#																		  #
#  You should have received a copy of the GNU General Public License	  #
#  along with this program.	 If not, see <http://www.gnu.org/licenses/>.  #
###########################################################################

import datetime
import functools
import os
import sys
import time
import six
import json
import traceback
import requests
import webbrowser
import logging
import vi

from PyQt5 import QtWidgets, QtGui, uic, QtCore
from PyQt5.QtCore import pyqtSignal, pyqtSlot, QSettings, QPoint, QByteArray
from PyQt5.QtWidgets import QMessageBox, QAction, QActionGroup, QStyleOption, QStyle, QSystemTrayIcon, QDialog, QWidget
from PyQt5.QtGui import QImage, QPixmap, QPainter
from vi import amazon_s3, evegate, dotlan, filewatcher, states, systems, version
from vi.cache.cache import Cache
from vi.resources import resourcePath
from vi.soundmanager import SoundManager
from vi.threads import AvatarFindThread, KOSCheckerThread, MapStatisticsThread
from vi.ui.systemtray import TrayContextMenu
from vi.regions import REGIONS
from vi.chatparser.chatparser import ChatParser, Message

OLD_STYLE_WEBKIT = "OLD_STYLE_WEBKIT" in os.environ
try:
    from PyQt5.QtWebEngineWidgets import QWebEnginePage
except ImportError:
    logging.warning('Using old style QT webkit.  PyQt5.QtWebEngineWidgets.QWebEnginePage is not available')
    OLD_STYLE_WEBKIT = True

if OLD_STYLE_WEBKIT:
    logging.warning('Using old style QT webkit.')
    from PyQt5.QtWebEngineWidgets import QWebEnginePage

# Timer intervals
MESSAGE_EXPIRY_SECS = 60 * 60 * 1
MAP_UPDATE_INTERVAL_MSECS = 4 * 1000
CLIPBOARD_CHECK_INTERVAL_MSECS = 4 * 1000


class MainWindow(QtWidgets.QMainWindow):

    chatMessageAdded = pyqtSignal(object)
    avatarLoaded = pyqtSignal(str, object)
    replayLogsRequested = pyqtSignal()
    oldStyleWebKit = OLD_STYLE_WEBKIT

    def __init__(self, pathToLogs, trayIcon, backGroundColor, oneTimeOptions):

        QtWidgets.QMainWindow.__init__(self)
        self.cache = Cache()

        self.cache.dumpConfig()

        if backGroundColor:
            self.setStyleSheet("QWidget { background-color: %s; }" % backGroundColor)
        uic.loadUi(resourcePath('vi/ui/MainWindow.ui'), self)
        self.setWindowTitle("Vintel " + vi.version.VERSION + "{dev}".format(dev="-SNAPSHOT" if vi.version.SNAPSHOT else ""))
        self.taskbarIconQuiescent = QtGui.QIcon(resourcePath("vi/ui/res/logo_small.png"))
        self.taskbarIconWorking = QtGui.QIcon(resourcePath("vi/ui/res/logo_small_green.png"))
        self.setWindowIcon(self.taskbarIconQuiescent)
        self.setFocusPolicy(QtCore.Qt.StrongFocus)

        self.pathToLogs = pathToLogs
        self.mapTimer = QtCore.QTimer(self)
        self.mapTimer.timeout.connect(self.scheduledUpdateMapView)
        self.clipboardTimer = QtCore.QTimer(self)
        self.oldClipboardContent = ""
        self.trayIcon = trayIcon
        self.trayIcon.activated.connect(self.systemTrayActivated)
        self.clipboard = QtWidgets.QApplication.clipboard()
        self.clipboard.clear(mode=self.clipboard.Clipboard)
        self.alarmDistance = 0
        self.lastStatisticsUpdate = 0
        self.chatEntries = []
        self.frameButton.setVisible(False)
        self.scanIntelForKosRequestsEnabled = True
        self.initialMapPosition = None
        self.mapPositionsDict = {}
        self.chatparser = None
        self.systemsWithRegions = systems.buildUpperKeyedAliases()
        self.locations = {}

        self.chatbox.setTitle("All Intel (past {0} minues)".format(str(MESSAGE_EXPIRY_SECS/60)))

        # Load user's toon names
        self.knownPlayerNames = self.cache.getFromCache("known_player_names")
        if self.knownPlayerNames:
            self.knownPlayerNames = set(self.knownPlayerNames.split(","))
        else:
            self.knownPlayerNames = set()
            # Use non-modal, it gets stuck under the splash screen sometimes
            msgBox = QMessageBox(self)
            msgBox.setText("Known Characters not Found")
            msgBox.setInformativeText("Vintel scans EVE system logs and remembers your characters as they change systems.\n\nSome features (clipboard KOS checking, alarms, etc.) may not work until your character(s) have been registered. Change systems, with each character you want to monitor, while Vintel is running to remedy this.")
            msgBox.show()

        # Set up user's intel rooms
        roomnames = self.cache.getConfigValue("channel_names")
        if roomnames:
            roomnames = roomnames.split(",")
        else:
            roomnames = (u"TheCitadel", u"North Provi Intel", u"North Catch Intel", "North Querious Intel")
            self.cache.saveConfigValue("channel_names", u",".join(roomnames))
        self.roomnames = roomnames

        # Disable the sound UI if sound is not available
        if 'NO_SOUND' in oneTimeOptions and oneTimeOptions['NO_SOUND']:
            SoundManager.DISABLED = True
            self.changeSound(disable=True)
        elif not SoundManager().soundAvailable:
            self.changeSound(disable=True)
        else:
            self.changeSound()

        # Set up Transparency menu - fill in opacity values and make connections
        self.opacityGroup = QActionGroup(self.menu)
        for i in (100, 80, 60, 40, 20):
            action = QAction("Opacity {0}%".format(i), None, checkable=True)
            if i == 100:
                action.setChecked(True)
            action.opacity = i / 100.0
            self.opacityGroup.triggered.connect(self.changeOpacity)
            self.opacityGroup.addAction(action)
            self.menuTransparency.addAction(action)

        #
        # Platform specific UI resizing - we size items in the resource files to look correct on the mac,
        # then resize other platforms as needed
        #
        if sys.platform.startswith("win32") or sys.platform.startswith("cygwin"):
            font = self.statisticsButton.font()
            font.setPointSize(8)
            self.statisticsButton.setFont(font)
            self.jumpbridgesButton.setFont(font)
        elif sys.platform.startswith("linux"):
            pass

        self.wireUpUIConnections()
        self.readAndApplySettings()
        self.setupThreads()
        self.updateRegionMenu()
        self.updateOtherRegionMenu()
        self.setupMap(True)
        self.replayLogsRequested.connect(self.replayLogs)
        if 'NO_REPLAY' in oneTimeOptions and oneTimeOptions['NO_REPLAY']:
            logging.critical('Skipping log replay.')
        else:
            # Keep a handle to the thread or it will be cleaned up early
            self.replayThread = self.ReplayLogsThread(self)
            self.replayThread.start()

    class ReplayLogsThread(QtCore.QThread):
        def __init__(self, parent):
            QtCore.QThread.__init__(self)
            self.parent = parent
        def run(self):
            self.parent.replayLogsRequested.emit()
            return

    def paintEvent(self, event):
        opt = QStyleOption()
        opt.initFrom(self)
        painter = QPainter(self)
        self.style().drawPrimitive(QStyle.PE_Widget, opt,  painter, self)

    def wheelEvent(self,event):
        if event.modifiers() & QtCore.Qt.ControlModifier:
            steps = event.angleDelta().y() // 120
            vector = steps and steps // abs(steps) # 0, 1, or -1
            for step in range(1, abs(steps) + 1):
                self.mapView.setZoomFactor(self.mapView.zoomFactor() + vector * 0.1)

    def keyPressEvent(self, event):
        key = event.key()
        if key == QtCore.Qt.Key_0:
            if event.modifiers() & QtCore.Qt.ControlModifier:
                self.mapView.setZoomFactor(1.0)
        elif key == QtCore.Qt.Key_Plus or key == QtCore.Qt.Key_Equal:
            if event.modifiers() & QtCore.Qt.ControlModifier:
                self.mapView.setZoomFactor(self.mapView.zoomFactor() + 0.1)
        elif key == QtCore.Qt.Key_Minus or key == QtCore.Qt.Key_Underscore:
            if event.modifiers() & QtCore.Qt.ControlModifier:
                self.mapView.setZoomFactor(self.mapView.zoomFactor() - 0.1)
        elif key == QtCore.Qt.Key_J:
            self.changeJumpbridgesVisibility()


    def updateOtherRegionMenu(self):
        for region in REGIONS:
            menuItem = self.otherRegionSubmenu.addAction(region)
            menuItem.triggered.connect(functools.partial(self.onRegionSelect, region))
            self.otherRegionSubmenu.addAction(menuItem)


    def updateRegionMenu(self):
        quick_regions = self.cache.getConfigValue("quick_regions")
        if quick_regions:
            j = json.loads(quick_regions)
            for old_item in self.menuRegion.actions():
                if "Other Region..." == old_item.text():
                    orm = self.menuRegion.insertSeparator(old_item)
                    break
                self.menuRegion.removeAction(old_item)
            for r in j:
                if not 'label' in r:
                    self.trayIcon.showMessage("Quick regions error", "No label field in :\n {0}".format(str(r)), 1)
                label = r['label']
                if label.startswith('-'):
                    menuItem = self.menuRegion.insertSeparator(orm)
                    continue
                if 'region' in r:
                    region = r['region']
                else:
                    region = label
                menuItem = self.menuRegion.addAction(label)
                menuItem.triggered.connect(functools.partial(self.onRegionSelect, region))
                self.menuRegion.insertAction(orm, menuItem)


    @pyqtSlot(str)
    def onRegionSelect(self, region):
        logging.critical("NEW REGION: [%s]", region)
        Cache().saveConfigValue("region_name", region)
        self.handleRegionChosen()


    def wireUpUIConnections(self):
        # Wire up general UI connections
        self.clipboard.dataChanged.connect(self.clipboardChanged)
        self.autoScanIntelAction.triggered.connect(self.changeAutoScanIntel)
        self.kosClipboardActiveAction.triggered.connect(self.changeKosCheckClipboard)
        self.zoomInButton.clicked.connect(self.zoomMapIn)
        self.zoomOutButton.clicked.connect(self.zoomMapOut)
        self.statisticsButton.clicked.connect(self.changeStatisticsVisibility)
        self.jumpbridgesButton.clicked.connect(self.changeJumpbridgesVisibility)
        self.chatLargeButton.clicked.connect(self.chatLarger)
        self.chatSmallButton.clicked.connect(self.chatSmaller)
        self.infoAction.triggered.connect(self.showInfo)
        self.showChatAvatarsAction.triggered.connect(self.changeShowAvatars)
        self.alwaysOnTopAction.triggered.connect(self.changeAlwaysOnTop)
        self.chooseRegionAction.triggered.connect(self.showRegionChooser)
        self.showChatAction.triggered.connect(self.changeChatVisibility)
        self.soundSetupAction.triggered.connect(self.showSoundSetup)
        self.activateSoundAction.triggered.connect(self.changeSound)
        self.useSpokenNotificationsAction.triggered.connect(self.changeUseSpokenNotifications)
        self.trayIcon.alarmDistanceChange.connect(self.changeAlarmDistance)
        self.framelessWindowAction.triggered.connect(self.changeFrameless)
        self.trayIcon.changeFramelessSignal.connect(self.changeFrameless)
        self.frameButton.clicked.connect(self.changeFrameless)
        self.quitAction.triggered.connect(self.close)
        self.trayIcon.quitSignal.connect(self.close)
        self.settingsAction.triggered.connect(self.showSettings)
        self.flushCacheAction.triggered.connect(self.flushCache)
        if OLD_STYLE_WEBKIT:
            self.mapView.page().scrollRequested.connect(self.mapPositionChanged)
        else:
            self.mapView.page().scrollPositionChanged.connect(self.mapPositionChangedToPoint)
            self.mapView.mapLinkClicked.connect(self.mapLinkClicked)
            self.mapView.page().loadFinished.connect(self.handleLoadFinished)


    def setupThreads(self):
        # Set up threads and their connections
        self.versionCheckThread = amazon_s3.NotifyNewVersionThread()
        self.versionCheckThread.newVersion.connect(self.notifyNewerVersion)
        self.versionCheckThread.start()

        self.avatarFindThread = AvatarFindThread()
        self.avatarFindThread.avatarUpdate.connect(self.updateAvatarOnChatEntry)
        self.avatarFindThread.start()

        # statisticsThread is blocked until first call of requestStatistics
        self.statisticsThread = MapStatisticsThread()
        self.statisticsThread.updateMap.connect(self.updateStatisticsOnMap)
        self.statisticsThread.start()

        self.kosRequestThread = KOSCheckerThread()
        self.kosRequestThread.showKos.connect(self.showKosResult)
        self.kosRequestThread.start()

        self.filewatcherThread = filewatcher.FileWatcher(self.pathToLogs)
        self.filewatcherThread.fileChanged.connect(self.logFileChanged)
        self.filewatcherThread.start()


    def setupMap(self, initialize=False):
        self.mapTimer.stop()
        self.filewatcherThread.paused = True

        logging.info("Finding map file")
        regionName = self.cache.getConfigValue("region_name")
        if not regionName:
            regionName = "Providence"
        svg = None
        try:
            with open(resourcePath("vi/ui/res/mapdata/{0}.svg".format(regionName))) as svgFile:
                svg = svgFile.read()
        except Exception as e:
            pass

        try:
            self.dotlan = dotlan.Map(regionName, svg)
        except dotlan.DotlanException as e:
            logging.error(e)
            QMessageBox.critical(None, "Error getting map", six.text_type(e), QMessageBox.Close)
            sys.exit(1)
        except Exception as e:
            self.cache.deleteFromCache("region_name")
            logging.error(e)
            QMessageBox.critical(None, "Error setting up map", six.text_type(e), QMessageBox.Close)
            sys.exit(1)

        if self.dotlan.outdatedCacheError:
            e = self.dotlan.outdatedCacheError
            diagText = "Something went wrong getting map data. Proceeding with older cached data. " \
                       "Check for a newer version and inform the maintainer.\n\nError: {0} {1}".format(type(e), six.text_type(e))
            logging.warning(diagText)
            QMessageBox.warning(None, "Using map from cache", diagText, QMessageBox.Ok)

        # Load the jumpbridges
        logging.critical("Load jump bridges")
        self.setJumpbridges(self.cache.getConfigValue("jumpbridge_url"))

        self.systems = self.dotlan.systems

        for char in self.locations:
            if self.locations[char] in self.systems:
                self.systems[self.locations[char]].addLocatedCharacter(char)

        logging.critical("Creating chat parser")
        oldParser = self.chatparser
        self.chatparser = ChatParser(self.pathToLogs, self.roomnames, self.systemsWithRegions, MESSAGE_EXPIRY_SECS)
        if oldParser:
            scrollPosition = self.chatListWidget.verticalScrollBar().value()
            self.chatListWidget.clear()
            self.processLogMessages(oldParser.knownMessages)
            self.chatListWidget.verticalScrollBar().setSliderPosition(scrollPosition)
            self.chatparser.knownMessages = oldParser.knownMessages

        # Menus - only once
        if initialize:
            logging.critical("Initializing contextual menus")

            # Add a contextual menu to the mapView
            def mapContextMenuEvent(event):
                #if QApplication.activeWindow() or QApplication.focusWidget():
                self.mapView.contextMenu.exec_(self.mapToGlobal(QPoint(event.x(), event.y())))

            self.mapView.contextMenu = self.trayIcon.contextMenu()
            self.mapView.contextMenuEvent = mapContextMenuEvent

            if MainWindow.oldStyleWebKit:
                self.mapView.linkClicked.connect(self.mapLinkClicked)
                self.mapView.page().setLinkDelegationPolicy(QWebEnginePage.DelegateAllLinks)

        self.jumpbridgesButton.setChecked(False)
        self.statisticsButton.setChecked(False)

        # Update the new map view, then clear old statistics from the map and request new
        logging.critical("Updating the map")
        self.updateMapView()
        self.setInitialMapPositionForRegion(regionName)
        self.mapTimer.start(MAP_UPDATE_INTERVAL_MSECS)

        # Allow the file watcher to run now that all else is set up
        self.filewatcherThread.paused = False
        logging.critical("Map setup complete")


    def readAndApplySettings(self):
        # Widget settings
        qsettings = QSettings()

        qsettings.beginGroup("mainWindow")
        self.restoreGeometry(qsettings.value("geometry", self.saveGeometry()))
        self.restoreState(qsettings.value("saveState", self.saveState()))
        self.move(qsettings.value("pos", self.pos()))
        self.resize(qsettings.value("size", self.size()))
        if qsettings.value("maximized", self.isMaximized()) == "true":
            self.showMaximized()
        qsettings.endGroup()

        qsettings.beginGroup("splitter")
        self.splitter.restoreGeometry(qsettings.value("geometry", self.splitter.saveGeometry()))
        self.splitter.restoreState(qsettings.value("saveState", self.splitter.saveState()))
        self.splitter.move(qsettings.value("pos", self.splitter.pos()))
        self.splitter.resize(qsettings.value("size", self.splitter.size()))
        qsettings.endGroup()

        qsettings.beginGroup("mapView")
        self.mapView.setZoomFactor(float(qsettings.value("zoomFactor", self.mapView.zoomFactor())))
        qsettings.endGroup()

        # Cached settings
        try:
            settings = self.cache.getConfigValue("settings-2")
            if settings:
                try:
                    settings = eval(settings)
                    for setting in settings:
                        obj = self if not setting[0] else getattr(self, setting[0])
                        logging.debug("{0} | {1} | {2}".format(str(obj), setting[1], setting[2]))
                        try:
                            getattr(obj, setting[1])(setting[2])
                        except Exception as e:
                            logging.error(e)
                except Exception as e:
                    logging.error(e)
        except Exception as e:
            logging.error(e)
            # todo: add a button to delete the cache / DB
            self.trayIcon.showMessage("Settings error", "Something went wrong loading saved state:\n {0}".format(str(e)), 1)


    def writeSettings(self):
        # Widget settings
        qsettings = QSettings()

        qsettings.beginGroup("mainWindow")
        qsettings.setValue("geometry", self.saveGeometry())
        qsettings.setValue("saveState", self.saveState())
        qsettings.setValue("maximized", self.isMaximized())
        if not self.isMaximized() == True:
            qsettings.setValue("pos", self.pos())
            qsettings.setValue("size", self.size())
        qsettings.endGroup()

        qsettings.beginGroup("splitter")
        qsettings.setValue("geometry", self.splitter.saveGeometry())
        qsettings.setValue("saveState", self.splitter.saveState())
        qsettings.endGroup()

        qsettings.beginGroup("mapView")
        qsettings.setValue("zoomFactor", self.mapView.zoomFactor())
        qsettings.endGroup()

        # Cached non Widget program state
        thirtyDaysInSeconds = 60 * 60 * 24 * 30

        # Known playernames
        if self.knownPlayerNames:
            value = ",".join(self.knownPlayerNames)
            self.cache.putIntoCache("known_player_names", value, thirtyDaysInSeconds)

        settings = ((None, "changeChatFontSize", ChatEntryWidget.TEXT_SIZE),
                    (None, "changeOpacity", self.opacityGroup.checkedAction().opacity),
                    (None, "changeAlwaysOnTop", self.alwaysOnTopAction.isChecked()),
                    (None, "changeShowAvatars", self.showChatAvatarsAction.isChecked()),
                    (None, "changeAlarmDistance", self.alarmDistance),
                    (None, "changeSound", self.activateSoundAction.isChecked()),
                    (None, "changeChatVisibility", self.showChatAction.isChecked()),
                    (None, "loadInitialMapPositions", self.mapPositionsDict),
                    (None, "setSoundVolume", SoundManager().getSoundVolume()),
                    (None, "changeFrameless", self.framelessWindowAction.isChecked()),
                    (None, "changeUseSpokenNotifications", self.useSpokenNotificationsAction.isChecked()),
                    (None, "changeKosCheckClipboard", self.kosClipboardActiveAction.isChecked()),
                    (None, "changeAutoScanIntel", self.scanIntelForKosRequestsEnabled))

        self.cache.saveConfigValue("settings-2", str(settings))


    def startClipboardTimer(self):
        """
            Start a timer to check the keyboard for changes and kos check them,
            first initializing the content so we dont kos check from random content
        """
        self.oldClipboardContent = tuple(six.text_type(self.clipboard.text()))
        self.clipboardTimer.timeout.connect(self.clipboardChanged)
        self.clipboardTimer.start(CLIPBOARD_CHECK_INTERVAL_MSECS)


    def stopClipboardTimer(self):
        if self.clipboardTimer:
            try:
                # When settings are loaded, this will be called before it is connected.
                self.clipboardTimer.timeout.disconnect(self.clipboardChanged)
            except:
                pass
            self.clipboardTimer.stop()


    def closeEvent(self, event):
        self.writeSettings()

        # Stop the threads
        try:
            # Shutdown file watcher first since it uses the others
            self.filewatcherThread.quit()
            self.filewatcherThread.wait()
            SoundManager().quit()
            self.avatarFindThread.quit()
            self.avatarFindThread.wait()
            self.kosRequestThread.quit()
            self.kosRequestThread.wait()
            self.versionCheckThread.quit()
            self.versionCheckThread.wait()
            self.statisticsThread.quit()
            self.statisticsThread.wait()
        except Exception:
            pass
        self.trayIcon.hide()
        event.accept()


    def notifyNewerVersion(self, newestVersion):
        self.trayIcon.showMessage("Newer Version", ("An update is available for Vintel.\nhttps://github.com/Xanthos-Eve/vintel"), 1)

    def changeChatVisibility(self, newValue=None):
        if newValue is None:
            newValue = self.showChatAction.isChecked()
        self.showChatAction.setChecked(newValue)
        self.chatbox.setVisible(newValue)

    def changeKosCheckClipboard(self, newValue=None):
        if newValue is None:
            newValue = self.kosClipboardActiveAction.isChecked()
        self.kosClipboardActiveAction.setChecked(newValue)
        if newValue:
            self.startClipboardTimer()
        else:
            self.stopClipboardTimer()

    def changeAutoScanIntel(self, newValue=None):
        if newValue is None:
            newValue = self.autoScanIntelAction.isChecked()
        self.autoScanIntelAction.setChecked(newValue)
        self.scanIntelForKosRequestsEnabled = newValue

    def changeUseSpokenNotifications(self, newValue=None):
        if SoundManager().platformSupportsSpeech():
            if newValue is None:
                newValue = self.useSpokenNotificationsAction.isChecked()
            self.useSpokenNotificationsAction.setChecked(newValue)
            SoundManager().setUseSpokenNotifications(newValue)
        else:
            self.useSpokenNotificationsAction.setChecked(False)
            self.useSpokenNotificationsAction.setEnabled(False)

    def changeOpacity(self, newValue=None):
        if newValue is not None:
            for action in self.opacityGroup.actions():
                if action.opacity == newValue:
                    action.setChecked(True)
        action = self.opacityGroup.checkedAction()
        self.setWindowOpacity(action.opacity)

    def changeSound(self, newValue=None, disable=False):
        if disable:
            self.activateSoundAction.setChecked(False)
            self.activateSoundAction.setEnabled(False)
            self.soundSetupAction.setEnabled(False)
            #self.soundButton.setEnabled(False)
            QMessageBox.warning(None, "Sound disabled", "Please check the log files. This warning will not be shown again.", QMessageBox.Ok)
        else:
            if newValue is None:
                newValue = self.activateSoundAction.isChecked()
            self.activateSoundAction.setChecked(newValue)
            if newValue:
                SoundManager().enable()
            else:
                SoundManager().disable()

    def changeAlwaysOnTop(self, newValue=None):
        if newValue is None:
            newValue = self.alwaysOnTopAction.isChecked()
        self.hide()
        self.alwaysOnTopAction.setChecked(newValue)
        if newValue:
            self.setWindowFlags(self.windowFlags() | QtCore.Qt.WindowStaysOnTopHint)
        else:
            self.setWindowFlags(self.windowFlags() & (~QtCore.Qt.WindowStaysOnTopHint))
        self.show()

    def changeFrameless(self, newValue=None):
        if newValue is None:
            newValue = not self.frameButton.isVisible()
        self.hide()
        if newValue:
            self.setWindowFlags(QtCore.Qt.FramelessWindowHint)
            self.changeAlwaysOnTop(True)
        else:
            self.setWindowFlags(self.windowFlags() & (~QtCore.Qt.FramelessWindowHint))
        self.menubar.setVisible(not newValue)
        self.frameButton.setVisible(newValue)
        self.framelessWindowAction.setChecked(newValue)

        for cm in TrayContextMenu.instances:
            cm.framelessCheck.setChecked(newValue)
        self.show()

    def changeShowAvatars(self, newValue=None):
        if newValue is None:
            newValue = self.showChatAvatarsAction.isChecked()
        self.showChatAvatarsAction.setChecked(newValue)
        ChatEntryWidget.SHOW_AVATAR = newValue
        for entry in self.chatEntries:
            entry.avatarLabel.setVisible(newValue)

    def changeChatFontSize(self, newSize):
        if newSize:
            for entry in self.chatEntries:
                entry.changeFontSize(newSize)
            ChatEntryWidget.TEXT_SIZE = newSize


    def chatSmaller(self):
        newSize = ChatEntryWidget.TEXT_SIZE - 1
        self.changeChatFontSize(newSize)


    def chatLarger(self):
        newSize = ChatEntryWidget.TEXT_SIZE + 1
        self.changeChatFontSize(newSize)


    def changeAlarmDistance(self, distance):
        self.alarmDistance = distance
        for cm in TrayContextMenu.instances:
            for action in cm.distanceGroup.actions():
                if action.alarmDistance == distance:
                    action.setChecked(True)
        self.trayIcon.alarmDistance = distance


    def changeJumpbridgesVisibility(self):
        newValue = self.dotlan.changeJumpbridgesVisibility()
        self.jumpbridgesButton.setChecked(newValue)
        self.updateMapView()


    def changeStatisticsVisibility(self):
        newValue = self.dotlan.changeStatisticsVisibility()
        self.statisticsButton.setChecked(newValue)
        self.updateMapView()
        if newValue:
            self.statisticsThread.requestStatistics()


    def clipboardChanged(self, mode=0):
        if not (mode == 0 and self.kosClipboardActiveAction.isChecked() and self.clipboard.mimeData().hasText()):
            return
        content = six.text_type(self.clipboard.text())
        contentTuple = tuple(content)
        # Limit redundant kos checks
        if contentTuple != self.oldClipboardContent:
            parts = tuple(content.split("\n"))
            knownPlayers = self.knownPlayerNames
            for part in parts:
                # Make sure user is in the content (this is a check of the local system in Eve).
                # also, special case for when you have no knonwnPlayers (initial use)
                if not knownPlayers or part in knownPlayers:
                    self.trayIcon.setIcon(self.taskbarIconWorking)
                    self.kosRequestThread.addRequest(parts, "clipboard", True)
                    break
            self.oldClipboardContent = contentTuple


    def mapLinkClicked(self, url):
        systemName = six.text_type(url.path().split("/")[-1]).upper()
        system = self.systems[str(systemName)]
        sc = SystemChat(self, SystemChat.SYSTEM, system, self.chatEntries, self.knownPlayerNames)
        self.chatMessageAdded.connect(sc.addChatEntry)
        self.avatarLoaded.connect(sc.newAvatarAvailable)
        sc.setLocationSignal.connect(self.setLocation)
        sc.show()


    def markSystemOnMap(self, systemname):
        n = six.text_type(systemname)
        if n in self.systems:
            self.systems[n].mark()
            self.updateMapView()
        elif n.upper() in self.systemsWithRegions:
            logging.warn('System [%s] is in another region [%s]',
                self.systemsWithRegions[n]['name'], self.systemsWithRegions[n]['region'])
            ans = QMessageBox.question(self,
                u"System not on current map",
                u"{0} is in {1}.  Would you like to view the {1} map?".format(
                    six.text_type(self.systemsWithRegions[n]['name']),
                    six.text_type(self.systemsWithRegions[n]['region'])),
                QMessageBox.Ok, QMessageBox.Cancel)
            if QMessageBox.Ok == ans:
                self.onRegionSelect(self.systemsWithRegions[n]['region'])
                self.markSystemOnMap(systemname)
        else:
            logging.warn('System [%s] is unknown.', n)


    def setLocation(self, char, newSystem, isReplay=False):
        for system in self.systems.values():
            system.removeLocatedCharacter(char)
        if not newSystem == "?":
            if newSystem in self.systems:
                self.systems[newSystem].addLocatedCharacter(char)
                if not isReplay:
                    self.updateMapView()
            self.locations[char] = newSystem

    def getMapScrollPosition(self):
        if OLD_STYLE_WEBKIT:
            return self.mapView.page().mainFrame().scrollPosition()
        else:
            return self.mapView.page().scrollPosition()


    def setMapScrollPosition(self, position):
        if OLD_STYLE_WEBKIT:
            self.mapView.page().mainFrame().setScrollPosition(position)
        else:
            if self.loaded:
                self.mapView.page().runJavaScript('window.scrollTo({}, {});'.format(position.x(), position.y()))
            else:
                self.deferedScrollPosition = position


    def setMapContent(self, content):
        self.loaded = False
        if self.initialMapPosition is None:
            scrollPosition = self.getMapScrollPosition()
        else:
            scrollPosition = self.initialMapPosition

        if MainWindow.oldStyleWebKit:
            self.mapView.setContent(content)
        else:
            self.mapView.page().setContent(str.encode(content), mimeType=str('image/svg+xml'))
        self.setMapScrollPosition(scrollPosition)

        # Make sure we have positioned the window before we nil the initial position;
        # even though we set it, it may not take effect until the map is fully loaded
        scrollPosition = self.getMapScrollPosition()
        if scrollPosition and (scrollPosition.x() or scrollPosition.y()):
            self.initialMapPosition = None


    def loadInitialMapPositions(self, newDictionary):
        self.mapPositionsDict = newDictionary


    def setInitialMapPositionForRegion(self, regionName):
        try:
            if not regionName:
                regionName = self.cache.getConfigValue("region_name")
            if regionName:
                xy = self.mapPositionsDict[regionName]
                self.initialMapPosition = QPoint(xy[0], xy[1])
        except Exception:
            pass


    def mapPositionChanged(self, dx, dy, rectToScroll):
        regionName = self.cache.getConfigValue("region_name")
        if regionName:
            scrollPosition = self.getMapScrollPosition()
            self.mapPositionsDict[regionName] = (scrollPosition.x(), scrollPosition.y())


    def showSettings(self):
        chooser = Settings(self)
        chooser.roomsChanged.connect(self.changedRoomnames)
        chooser.setJumpbridgeUrl.connect(self.setJumpbridges)
        chooser.show()


    def mapPositionChangedToPoint(self, point):
        regionName = self.cache.getFromCache("region_name")
        if regionName:
            self.mapPositionsDict[regionName] = (point.x(), point.y())


    def handleLoadFinished(self):
        self.loaded = True
        if self.deferedScrollPosition:
            self.mapView.page().runJavaScript('window.scrollTo({}, {});'.format(self.deferedScrollPosition.x(), self.deferedScrollPosition.y()))
            self.deferedScrollPosition = None


    def flushCache(self):
        self.cache.flush()


    def setSoundVolume(self, value):
        SoundManager().setSoundVolume(value)


    def setJumpbridges(self, url):

        # TODO: better handle blank, it is valid and doesn't need to go to s3
        if not url:
            cacheKey = "jb_" + self.dotlan.region.lower()
            url = amazon_s3.getJumpbridgeUrl(self.dotlan.region.lower())
        else:
            # embed url in key so we update cache when url changes
            cacheKey = "jb_" + url

        try:
            cache = Cache()
            data = cache.getFromCache(cacheKey)
            if data:
                data = json.loads(data)
            else:
                data = []
                resp = requests.get(url)
                if resp.status_code == requests.codes.ok:
                    for line in resp.iter_lines(decode_unicode=True):
                        parts = line.strip().split()
                        if len(parts) == 3:
                            data.append(parts)
                cache.putIntoCache(cacheKey, json.dumps(data), 60 * 60 * 12)
            self.dotlan.setJumpbridges(data)
            self.cache.saveConfigValue("jumpbridge_url", url)
        except Exception as e:
            QMessageBox.warning(None, "Loading jumpbridges failed!", "Error: {0}".format(six.text_type(e)), QMessageBox.Ok)


    def handleRegionMenuItemSelected(self, menuAction=None):
        if menuAction:
            regionName = six.text_type(str(menuAction.property("regionName")))
            regionName = dotlan.convertRegionName(regionName)
            Cache().saveConfigValue("region_name", regionName)
            self.setupMap()

    def handleRegionChosen(self):
        self.setupMap()

    def showRegionChooser(self):
        chooser = RegionChooser(self)
        chooser.newRegionChosen.connect(self.handleRegionChosen)
        chooser.show()

    def replayLogs(self):
        """On startup, replay info from logfiles"""
        logging.critical("LOG REPLAY: starting")
        try:
            self.filewatcherThread.paused = True
            self.mapTimer.stop()
            messages = []
            for path in self.chatparser.rewind():
                messages.extend(self.chatparser.fileModified(path))
            messages.sort(key=lambda x: x.timestamp)
            logging.debug("LOG REPLAY: read logs.")
            # we use these parsed messages to replay events on region switch, reset them to a time ordered list
            self.chatparser.knownMessages = messages
            self.processLogMessages(messages, True)
        finally:
            self.filewatcherThread.paused = False
            self.mapTimer.start(MAP_UPDATE_INTERVAL_MSECS)
        logging.critical("LOG REPLAY: complete")

    def addMessageToIntelChat(self, message):
        scrollToBottom = False
        if (self.chatListWidget.verticalScrollBar().value() == self.chatListWidget.verticalScrollBar().maximum()):
            scrollToBottom = True
        chatEntryWidget = ChatEntryWidget(message)
        listWidgetItem = QtWidgets.QListWidgetItem(self.chatListWidget)
        listWidgetItem.setSizeHint(chatEntryWidget.sizeHint())
        self.chatListWidget.addItem(listWidgetItem)
        self.chatListWidget.setItemWidget(listWidgetItem, chatEntryWidget)
        self.avatarFindThread.addChatEntry(chatEntryWidget)
        self.chatEntries.append(chatEntryWidget)
        chatEntryWidget.markSystem.connect(self.markSystemOnMap)
        self.chatMessageAdded.emit(chatEntryWidget)
        self.pruneMessages()
        if scrollToBottom:
            self.chatListWidget.scrollToBottom()


    def pruneMessages(self):
        self.chatparser.expire()
        try:
            now = time.mktime(evegate.currentEveTime().timetuple())
            for row in range(self.chatListWidget.count()):
                chatListWidgetItem = self.chatListWidget.item(0)
                chatEntryWidget = self.chatListWidget.itemWidget(chatListWidgetItem)
                message = chatEntryWidget.message
                if now - time.mktime(message.timestamp.timetuple()) > MESSAGE_EXPIRY_SECS:
                    self.chatEntries.remove(chatEntryWidget)
                    self.chatListWidget.takeItem(0)

                    for widgetInMessage in message.widgets:
                        widgetInMessage.removeItemWidget(chatListWidgetItem)
                else:
                    break
        except Exception as e:
            logging.error(e)


    def showKosResult(self, state, text, requestType, hasKos):
        if not self.scanIntelForKosRequestsEnabled:
            return
        try:
            if hasKos:
                SoundManager().playSound(SoundManager.KOS(), text)
            if state == "ok":
                if requestType == "xxx":  # An xxx request out of the chat
                    self.trayIcon.showMessage("Player KOS-Check", text, 1)
                elif requestType == "clipboard":  # request from clipboard-change
                    if len(text) <= 0:
                        text = "None KOS"
                    self.trayIcon.showMessage("Your KOS-Check", text, 1)
                text = text.replace("\n\n", "<br>")
                message = Message("Vintel KOS-Check", text, evegate.currentEveTime(), "VINTEL", [], states.NOT_CHANGE, text.upper(), text)
                self.addMessageToIntelChat(message)
            elif state == "error":
                self.trayIcon.showMessage("KOS Failure", text, 3)
        except Exception:
            pass
        self.trayIcon.setIcon(self.taskbarIconQuiescent)


    def changedRoomnames(self, newRoomnames):
        self.cache.saveConfigValue("channel_names", u",".join(newRoomnames))
        self.chatparser.rooms = newRoomnames


    def showInfo(self):
        infoDialog = QDialog(self, QtCore.Qt.WindowTitleHint | QtCore.Qt.WindowCloseButtonHint)
        uic.loadUi(resourcePath("vi/ui/Info.ui"), infoDialog)
        infoDialog.versionLabel.setText(u"Version: {0}".format(vi.version.VERSION))
        infoDialog.logoLabel.setPixmap(QtGui.QPixmap(resourcePath("vi/ui/res/logo.png")))
        infoDialog.closeButton.clicked.connect(infoDialog.accept)
        infoDialog.show()


    def showSoundSetup(self):
        dialog = QDialog(self, QtCore.Qt.WindowTitleHint | QtCore.Qt.WindowCloseButtonHint)
        uic.loadUi(resourcePath("vi/ui/SoundSetup.ui"), dialog)
        dialog.volumeSlider.setValue(SoundManager().getSoundVolume())
        dialog.volumeSlider.valueChanged.connect(SoundManager().setSoundVolume)
        dialog.testSoundButton.clicked.connect(lambda: SoundManager().playSound())
        dialog.testVoiceButton.clicked.connect(lambda: SoundManager().say('Test... 1, 2, 3.'))
        dialog.closeButton.clicked.connect(dialog.accept)
        dialog.show()


    def systemTrayActivated(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            if self.isMinimized():
                self.showNormal()
                self.activateWindow()
            elif not self.isActiveWindow():
                self.activateWindow()
            else:
                self.showMinimized()


    def updateAvatarOnChatEntry(self, chatEntry, avatarData):
        updated = chatEntry.updateAvatar(avatarData)
        if not updated:
            self.avatarFindThread.addChatEntry(chatEntry) # , clearCache=True)
        else:
            self.avatarLoaded.emit(chatEntry.message.user, avatarData)


    def updateStatisticsOnMap(self, data):
        if not self.statisticsButton.isChecked():
            return
        if data["result"] == "ok":
            self.dotlan.addSystemStatistics(data["statistics"])
        elif data["result"] == "error":
            text = data["text"]
            self.trayIcon.showMessage("Loading statstics failed", text, 3)
            logging.error("updateStatisticsOnMap, error: %s" % text)


    def scheduledUpdateMapView(self):
        logging.debug("Updating map due to timer event.")
        self.updateMapView()


    def updateMapView(self):
        logging.debug("Updating map: start")
        self.setMapContent(self.dotlan.svg)
        logging.debug("Updating map: complete")


    def zoomMapIn(self):
        self.mapView.setZoomFactor(self.mapView.zoomFactor() + 0.1)


    def zoomMapOut(self):
        self.mapView.setZoomFactor(self.mapView.zoomFactor() - 0.1)


    def logFileChanged(self, path):
        messages = self.chatparser.fileModified(path)
        if messages:
            self.processLogMessages(messages)

    def processLogMessages(self, messages, isReplay=False):
        for message in messages:

            # This function is a resource pig, give others a chance to run while we process messages
            time.sleep(0)

            # If players location has changed
            if message.status == states.LOCATION:
                self.knownPlayerNames.add(message.user)
                self.setLocation(message.user, message.systems[0], isReplay)
            elif message.status == states.KOS_STATUS_REQUEST:
                # Do not accept KOS requests from any but monitored intel channels
                # as we don't want to encourage the use of xxx in those channels.
                if not message.room in self.roomnames:
                    text = message.message[4:]
                    text = text.replace("  ", ",")
                    parts = (name.strip() for name in text.split(","))
                    self.trayIcon.setIcon(self.taskbarIconWorking)
                    self.kosRequestThread.addRequest(parts, "xxx", False)
            # Otherwise consider it a 'normal' chat message
            elif message.user not in ("EVE-System", "EVE System") and message.status != states.IGNORE:
                self.addMessageToIntelChat(message)
                # For each system that was mentioned in the message, check for alarm distance to the current system
                # and alarm if within alarm distance.
                if message.systems:
                    for systemname in message.systems:
                        if not systemname in self.systems:
                            logging.debug("No dotlan match for system [%s], maybe it's not shown right now:", systemname)
                            continue
                        system = self.systems[systemname]
                        system.setStatus(message.status, message.timestamp)
                        if (evegate.currentEveTime() - message.timestamp).total_seconds() < system.ALARM_COLORS[0][0]:
                            if message.status in (states.REQUEST, states.ALARM) and message.user not in self.knownPlayerNames:
                                alarmDistance = self.alarmDistance if message.status == states.ALARM else 0
                                for nSystem, data in system.getNeighbours(alarmDistance).items():
                                    distance = data["distance"]
                                    chars = nSystem.getLocatedCharacters()
                                    if len(chars) > 0 and message.user not in chars:
                                        self.trayIcon.showNotification(message, system.name, ", ".join(chars), distance)
                        system.messages.append(message)

        # call once after all messages are processed
        self.updateMapView()

class RegionChooser(QDialog):

    newRegionChosen = pyqtSignal()

    def __init__(self, parent):
        QDialog.__init__(self, parent)
        uic.loadUi(resourcePath("vi/ui/RegionChooser.ui"), self)
        self.setWindowFlags(self.windowFlags() & ~(QtCore.Qt.WindowContextHelpButtonHint|QtCore.Qt.WindowSystemMenuHint))
        self.cancelButton.clicked.connect(self.accept)
        self.saveButton.clicked.connect(self.saveClicked)
        cache = Cache()
        regionName = cache.getConfigValue("region_name")
        if not regionName:
            regionName = u"Providence"
        self.regionNameField.setPlainText(regionName)


    def saveClicked(self):
        text = six.text_type(self.regionNameField.toPlainText())
        text = dotlan.convertRegionName(text)
        self.regionNameField.setPlainText(text)
        correct = False
        try:
            url = dotlan.dotlan_url(text)
            content = requests.get(url).text
            if u"not found" in content:
                correct = False
                # Fallback -> ships vintel with this map?
                try:
                    with open(resourcePath("vi/ui/res/mapdata/{0}.svg".format(text))) as _:
                        correct = True
                except Exception as e:
                    logging.error(e)
                    correct = False
                if not correct:
                    QMessageBox.warning(self, u"No such region!", u"I can't find a region called '{0}'".format(text))
            else:
                correct = True
        except Exception as e:
            QMessageBox.critical(self, u"Something went wrong!", u"Error while testing existing '{0}'".format(str(e)))
            logging.error(e)
            correct = False
        if correct:
            Cache().saveConfigValue("region_name", text)
            self.accept()
            self.newRegionChosen.emit()


class SystemChat(QDialog):

    setLocationSignal = pyqtSignal(str, str)
    SYSTEM = 0

    def __init__(self, parent, chatType, selector, chatEntries, knownPlayerNames):
        QDialog.__init__(self, parent)
        uic.loadUi(resourcePath("vi/ui/SystemChat.ui"), self)
        self.setWindowFlags(self.windowFlags() & ~(QtCore.Qt.WindowContextHelpButtonHint|QtCore.Qt.WindowSystemMenuHint))
        self.parent = parent
        self.chatType = 0
        self.selector = selector
        titleName = ""
        self.chatEntries = []
        if self.chatType == SystemChat.SYSTEM:
            self.system = selector
            systemDisplayName = self.system.name
            if systemDisplayName in parent.systemsWithRegions:
                systemDisplayName = parent.systemsWithRegions[systemDisplayName]['name']
            titleName = "%s [%s]" % (systemDisplayName, self.selector.secondaryInfo)
            for entry in chatEntries:
                self.addChatEntry(entry)
        for name in knownPlayerNames:
            self.playerNamesBox.addItem(name)
        self.setWindowTitle("Chat for {0}".format(titleName))
        self.closeButton.clicked.connect(self.closeDialog)
        self.alarmButton.clicked.connect(self.setSystemAlarm)
        self.clearButton.clicked.connect(self.setSystemClear)
        self.locationButton.clicked.connect(self.locationSet)


    def _addMessageToChat(self, message, avatarPixmap):
        scrollToBottom = False
        if (self.chat.verticalScrollBar().value() == self.chat.verticalScrollBar().maximum()):
            scrollToBottom = True
        entry = ChatEntryWidget(message)
        entry.avatarLabel.setPixmap(avatarPixmap)
        listWidgetItem = QtWidgets.QListWidgetItem(self.chat)
        listWidgetItem.setSizeHint(entry.sizeHint())
        self.chat.addItem(listWidgetItem)
        self.chat.setItemWidget(listWidgetItem, entry)
        self.chatEntries.append(entry)
        entry.markSystem.connect(self.parent.markSystemOnMap)
        if scrollToBottom:
            self.chat.scrollToBottom()


    def addChatEntry(self, entry):
        if self.chatType == SystemChat.SYSTEM:
            message = entry.message
            try:
                avatarPixmap = entry.avatarLabel.pixmap()
                if self.system.name in message.systems:
                    self._addMessageToChat(message, avatarPixmap)
            except:
                pass

    def locationSet(self):
        char = six.text_type(self.playerNamesBox.currentText())
        self.setLocationSignal.emit(char, self.system.name)


    def newAvatarAvailable(self, charname, avatarData):
        for entry in self.chatEntries:
            if entry.message.user == charname:
                entry.updateAvatar(avatarData)


    def setSystemAlarm(self):
        self.system.setStatus(states.ALARM)
        self.parent.updateMapView()


    def setSystemClear(self):
        self.system.setStatus(states.CLEAR)
        self.parent.updateMapView()


    def closeDialog(self):
        self.accept()


class ChatEntryWidget(QWidget):

    markSystem = pyqtSignal(object)
    TEXT_SIZE = 11
    SHOW_AVATAR = True
    questionMarkPixmap = None

    def __init__(self, message):
        QWidget.__init__(self)
        if not self.questionMarkPixmap:
            self.questionMarkPixmap = QtGui.QPixmap(resourcePath("vi/ui/res/qmark.png")).scaledToHeight(32)
        uic.loadUi(resourcePath("vi/ui/ChatEntry.ui"), self)
        self.avatarLabel.setPixmap(self.questionMarkPixmap)
        self.message = message
        self.updateText()
        self.textLabel.linkActivated.connect(self.linkClicked)
        if sys.platform.startswith("win32") or sys.platform.startswith("cygwin"):
            ChatEntryWidget.TEXT_SIZE = 8
        self.changeFontSize(self.TEXT_SIZE)
        if not ChatEntryWidget.SHOW_AVATAR:
            self.avatarLabel.setVisible(False)


    def linkClicked(self, link):
        link = six.text_type(link)
        function, parameter = link.split("/", 1)
        if function == "mark_system":
            self.markSystem.emit(parameter)
        elif function == "link":
            webbrowser.open(parameter)


    def updateText(self):
        time = datetime.datetime.strftime(self.message.timestamp, "%H:%M:%S")
        text = u"<small>{time} - <b>{user}</b> - <i>{room}</i></small><br>{text}".format(user=self.message.user,
                                                                                         room=self.message.room,
                                                                                         time=time,
                                                                                         text=self.message.message)
        self.textLabel.setText(text)


    def updateAvatar(self, avatarData):
        image = QImage.fromData(avatarData)
        pixmap = QPixmap.fromImage(image)
        if pixmap.isNull():
            return False
        scaledAvatar = pixmap.scaled(32, 32)
        try:
            self.avatarLabel.setPixmap(scaledAvatar)
        except:
            pass
        return True


    def changeFontSize(self, newSize):
        try:
            font = self.textLabel.font()
            font.setPointSize(newSize)
            self.textLabel.setFont(font)
        except:
            pass


class Settings(QDialog):

    setJumpbridgeUrl = pyqtSignal(str)
    roomsChanged = pyqtSignal(object)

    def __init__(self, parent):
        QDialog.__init__(self, parent)
        uic.loadUi(resourcePath("vi/ui/SettingsTabs.ui"), self)
        self.setWindowFlags(self.windowFlags() & ~(QtCore.Qt.WindowContextHelpButtonHint|QtCore.Qt.WindowSystemMenuHint))
        self.cache = Cache()
        self.parent = parent
        self.tabs.setCurrentIndex(0)    # load displaying first tab, regardless of which page was last open in designer

        # Chatrooms
        self.chatDefaultButton.clicked.connect(self.setChatToDefaults)
        self.chatCancelButton.clicked.connect(self.resetChatSettings)
        self.chatSaveButton.clicked.connect(self.saveChatSettings)
        self.resetChatSettings()

        # JBS
        self.jbSaveButton.clicked.connect(self.saveJbs)
        self.jbCancelButton.clicked.connect(self.resetJbs)
        self.resetJbs()

        # loading format explanation from textfile
        # with open(resourcePath("docs/jumpbridgeformat.txt")) as f:
        #     self.formatInfoField.setPlainText(f.read())

        # Quick Setup
        self.quickSettingsSaveButton.clicked.connect(self.saveQuickSettings)
        self.quickSettingsCancelButton.clicked.connect(self.resetQuickSettings)
        self.resetQuickSettings()

    def resetJbs(self):
        self.jbUrlField.setText(self.cache.getConfigValue("jumpbridge_url"))
        self.jbIdField.setText(self.cache.getConfigValue("dotlan_jb_id"))

    def saveJbs(self):
        try:
            url = six.text_type(self.jbUrlField.text())
            if url != "":
                requests.get(url).text
            self.cache.saveConfigValue("dotlan_jb_id", six.text_type(self.jbIdField.text()))
            self.setJumpbridgeUrl.emit(url)
        except Exception as e:
            QMessageBox.critical(None, "Finding Jumpbridgedata failed", "Error: {0}".format(six.text_type(e)), "OK")

    def resetChatSettings(self):
        roomnames = self.cache.getConfigValue("channel_names")
        if not roomnames:
            self.setChatToDefaults()
        else:
            self.roomnamesField.setPlainText(roomnames)

    def saveChatSettings(self):
        text = six.text_type(self.roomnamesField.toPlainText())
        rooms = [six.text_type(name.strip()) for name in text.split(",")]
        self.roomsChanged.emit(rooms)

    def setChatToDefaults(self):
        roomnames = self.cache.getConfigValue("default_room_names")
        if not roomnames:
            self.roomnamesField.setPlainText(u"TheCitadel,North Provi Intel,North Catch Intel,North Querious Intel")
        else:
            self.roomnamesField.setPlainText(roomnames)

    def resetQuickSettings(self):
        self.quickSettingsField.setPlainText("")

    def saveQuickSettings(self):
        try:
            d = json.loads(six.text_type(self.quickSettingsField.toPlainText()))
            if not dict:
                QMessageBox.critical(None, "Could not parse input field", "Error: {0}".format(six.text_type(d)), "OK")
                return

            if 'channels' in d:
                self.cache.saveConfigValue('default_room_names', ",".join(d['channels']))
                self.roomsChanged.emit(d['channels'])

            if 'dotlan_jb_id' in d:
                self.cache.saveConfigValue("dotlan_jb_id", d['dotlan_jb_id'])

            if 'jumpbridge_url' in d:
                self.setJumpbridgeUrl.emit(d['jumpbridge_url'])

            if 'kos_url' in d:
                self.cache.saveConfigValue("kos_url", d['kos_url'])

            if 'region_name' in d:
                self.cache.saveConfigValue("region_name", d['region_name'])
                self.parent.handleRegionChosen()

            if 'quick_regions' in d:
                self.cache.saveConfigValue("quick_regions", json.dumps(d['quick_regions']))
                self.parent.updateRegionMenu()

            self.resetChatSettings()
            self.resetJbs()

        except Exception as e:
            traceback.print_exc()
            QMessageBox.critical(None, "Saving quick settings failed", "Error: {0}".format(six.text_type(e)), "OK")
