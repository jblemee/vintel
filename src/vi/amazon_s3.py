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

import requests
import logging

from PyQt5.QtCore import pyqtSignal, QThread
from distutils.version import StrictVersion
from vi import version


def getJumpbridgeUrl(region):
    return "https://s3.amazonaws.com/vintel-resources/{region}_jb.txt".format(region=region)


def getNewestVersion():
    try:
        url = "https://s3.amazonaws.com/vintel-resources/current-version.txt"
        newestVersion = requests.get(url).text
        return newestVersion
    except Exception as e:
        logging.error("Failed version-request: %s", e)
        return "0.0"


class NotifyNewVersionThread(QThread):

    newVersion = pyqtSignal(str)

    def __init__(self):
        QThread.__init__(self)
        self.alerted = False

    def run(self):
        if not self.alerted:
            try:
                # Is there a newer version available?
                newestVersion = getNewestVersion()
                if newestVersion and StrictVersion(newestVersion) > StrictVersion(version.VERSION):
                    self.newVersion.emit(newestVersion)
                    self.alerted = True
            except Exception as e:
                logging.error("Failed NotifyNewVersionThread: %s", e)
