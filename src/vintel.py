#!/usr/bin/env python
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

import sys
import os
import logging
import traceback
import argparse

from logging.handlers import RotatingFileHandler
from logging import StreamHandler

from PyQt5 import QtGui, QtWidgets
from PyQt5.QtCore import QT_VERSION_STR
from PyQt5.Qt import PYQT_VERSION_STR
from PyQt5.QtWidgets import QApplication, QMessageBox
from vi import version, PanningWebView
from vi.ui import viui, systemtray
from vi.cache import cache
from vi.resources import resourcePath
from vi.cache.cache import Cache


def exceptHook(exceptionType, exceptionValue, tracebackObject):
    """
        Global function to catch unhandled exceptions.
    """
    try:
        logging.critical("-- Unhandled Exception --")
        logging.critical(''.join(traceback.format_tb(tracebackObject)))
        logging.critical('{0}: {1}'.format(exceptionType, exceptionValue))
        logging.critical("-- ------------------- --")
    except Exception:
        pass

sys.excepthook = exceptHook
backGroundColor = "#c6d9ec"


class Application(QApplication):

    def __init__(self, args):
        super(Application, self).__init__(args)

        self.setWindowIcon(QtGui.QIcon('icon.ico'))
        # windows silliness to set taskbar icon
        if sys.platform.startswith("win32"):
            import ctypes
            myappid = u'eve.vintel.' + version.VERSION
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)

        logLevel = None
        oneTimeOptions = {}

        # Set up paths
        chatLogDirectory = ""
        for p, v in enumerate(sys.argv):
            if 0 == p:
                continue
            if '--debug' == v:
                logLevel = logging.DEBUG
            elif '--info' == v:
                logLevel = logging.INFO
            elif '--warn' == v:
                logLevel = logging.WARN
            elif '--nosound' == v:
                oneTimeOptions['NO_SOUND'] = True
            elif '--noreplay' == v:
                oneTimeOptions['NO_REPLAY'] = True
            elif '--clear' == v:
                oneTimeOptions['CLEAR_CACHE'] = True
            elif '--nosplash' == v:
                oneTimeOptions['NO_SPLASH'] = True
            else:
                chatLogDirectory = v

        if not chatLogDirectory or not os.path.exists(chatLogDirectory):
            if sys.platform.startswith("darwin") or sys.platform.startswith("cygwin"):
                chatLogDirectory = os.path.join(os.path.expanduser("~"), "Documents", "EVE", "logs", "Chatlogs")
                if not os.path.exists(chatLogDirectory):
                    chatLogDirectory = os.path.join(os.path.expanduser("~"), "Library", "Application Support", "Eve Online",
                                          "p_drive", "User", "My Documents", "EVE", "logs", "Chatlogs")
            elif sys.platform.startswith("linux"):
                chatLogDirectory = os.path.join(os.path.expanduser("~"), "EVE", "logs", "Chatlogs")
                if not os.path.exists(chatLogDirectory):
                    # Default path created by EveLauncher:  https://forums.eveonline.com/default.aspx?g=posts&t=482663
                    chatLogDirectory = os.path.join(os.path.expanduser("~"), "Documents","EVE", "logs", "Chatlogs")
            elif sys.platform.startswith("win32"):
                import ctypes.wintypes
                from win32com.shell import shellcon
                buf = ctypes.create_unicode_buffer(ctypes.wintypes.MAX_PATH)
                hResult = ctypes.windll.shell32.SHGetFolderPathW(0, shellcon.CSIDL_PERSONAL, 0, 0, buf)
                if hResult == 0:
                    documentsPath = buf.value
                    chatLogDirectory = os.path.join(documentsPath, "EVE", "logs", "Chatlogs")
        if not chatLogDirectory:
            QMessageBox.critical(None, "No path to Logs", "Unable to determine chat directory, please specify one on the command line.", "Quit")
            sys.exit(1)
        if not os.path.exists(chatLogDirectory):
            # None of the paths for logs exist, bailing out
            QMessageBox.critical(None, "No path to Logs", "No logs found at: " + chatLogDirectory, "Quit")
            sys.exit(1)

        # Setting local directory for cache and logging
        vintelDirectory = os.path.join(os.path.dirname(os.path.dirname(chatLogDirectory)), "vintel")
        if not os.path.exists(vintelDirectory):
            os.mkdir(vintelDirectory)
        cache.Cache.PATH_TO_CACHE = os.path.join(vintelDirectory, "cache-2.sqlite3")

        vintelLogDirectory = os.path.join(vintelDirectory, "logs")
        if not os.path.exists(vintelLogDirectory):
            os.mkdir(vintelLogDirectory)

        splash = QtWidgets.QSplashScreen(QtGui.QPixmap(resourcePath("vi/ui/res/logo.png")))

        vintelCache = Cache()
        if 'CLEAR_CACHE' in oneTimeOptions and oneTimeOptions['CLEAR_CACHE']:
            vintelCache.clear()
        if not logLevel:
            logLevel = vintelCache.getConfigValue("logging_level")
        if not logLevel:
            logLevel = logging.WARN
        backGroundColor = vintelCache.getConfigValue("background_color")
        if backGroundColor:
            self.setStyleSheet("QWidget { background-color: %s; }" % backGroundColor)

        if not 'NO_SPLASH' in oneTimeOptions:
            splash.show()
        self.processEvents()

        # Setup logging for console and rotated log files
        formatter = logging.Formatter('%(asctime)s| %(message)s', datefmt='%m/%d %I:%M:%S')
        rootLogger = logging.getLogger()
        rootLogger.setLevel(level=logLevel)

        logFilename = vintelLogDirectory + "/output.log"
        fileHandler = RotatingFileHandler(maxBytes=(1048576*5), backupCount=7, filename=logFilename, mode='a')
        fileHandler.setFormatter(formatter)
        rootLogger.addHandler(fileHandler)

        consoleHandler = StreamHandler()
        consoleHandler.setFormatter(formatter)
        rootLogger.addHandler(consoleHandler)

        logging.critical("Logging set to %s." % logging.getLevelName(logLevel))

        logging.critical("------------------- Vintel %s starting up -------------------", version.VERSION)
        logging.critical("QT version %s | PyQT Version %s", QT_VERSION_STR, PYQT_VERSION_STR)
        logging.critical("Python version %s", sys.version)
        logging.debug("Looking for chat logs at: %s", chatLogDirectory)
        logging.debug("Cache maintained here: %s", cache.Cache.PATH_TO_CACHE)
        logging.debug("Writing logs to: %s", vintelLogDirectory)

        self.setOrganizationName("Vintel Development Team")
        self.setOrganizationDomain("https://github.com/Xanthos-Eve/vintel")
        self.setApplicationName("Vintel")

        trayIcon = systemtray.TrayIcon(self)
        trayIcon.show()
        self.mainWindow = viui.MainWindow(chatLogDirectory, trayIcon, backGroundColor, oneTimeOptions)
        self.mainWindow.show()
        splash.finish(self.mainWindow)


# The main application
if __name__ == "__main__":

    app = Application(sys.argv)
    sys.exit(app.exec_())
