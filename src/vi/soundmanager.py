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

import os
import sys
import six
import logging

from PyQt5.QtCore import QThread, QUrl, QEventLoop
from PyQt5.QtMultimedia import QSoundEffect
from six.moves.queue import Queue
from vi.resources import resourcePath
from vi.singleton import Singleton

global festivalAvailable

try:
    import festival
    festivalAvailable = True
except:
    festivalAvailable = False

try:
    import pyttsx
    pyttsxAvailable = True
except:
    pyttsxAvailable = False


class SoundManager(six.with_metaclass(Singleton)):

    @staticmethod
    def ALARM(): return "alarm"

    @staticmethod
    def KOS(): return "kos"

    @staticmethod
    def REQUEST(): return "request"

    SOUNDS = {
        ALARM.__func__(): "178032__zimbot__redalert-klaxon-sttos-recreated.wav",
        KOS.__func__():  "178031__zimbot__transporterstartbeep0-sttos-recreated.wav",
        REQUEST.__func__(): "178028__zimbot__bosun-whistle-sttos-recreated.wav"
    }

    DISABLED = False

    soundActive = False
    soundAvailable = False
    useSpokenNotifications = False
    _soundThread = None
    volume = 25      # Must be an integer between 0 and 100

    isDarwin = sys.platform.startswith("darwin")

    def __init__(self):
        self.soundAvailable = self.platformSupportsAudio()
        if not self.soundAvailable:
            return
        self._soundThread = self.SoundThread(self, self.SOUNDS)
        if not self.platformSupportsSpeech():
            self.setUseSpokenNotifications(False)
        if self.soundAvailable:
            self._soundThread.start()

    def platformSupportsAudio(self):
        return not SoundManager.DISABLED

    def platformSupportsSpeech(self):
        return self.isDarwin or festivalAvailable or pyttsxAvailable

    def setUseSpokenNotifications(self, newValue):
        if self.platformSupportsSpeech():
            self.useSpokenNotifications = newValue
        else:
            logging.critical("Cannot enable speech on a platform that does not support it.")

    def enable(self):
        self.soundActive = True

    def disable(self):
        self.soundActive = False

    def setSoundVolume(self, newValue):
        """ Accepts and stores a number between 0 and 100.
        """
        # TODO: Voice and sound effect don't use same dynamic range, maybe use two sliders?
        if newValue > 100:
            newValue = 100
        elif newValue < 0:
            newValue = 0
        self.volume = newValue
        if self._soundThread:
            self._soundThread.updateVolume()

    def getSoundVolume(self):
        return self.volume

    def playSound(self, name="alarm", message="", abbreviatedMessage=""):
        """ Schedules the work, which is picked up by SoundThread.run()
        """
        if self.soundAvailable and self.soundActive:
            logging.debug("Queing sound: \"%s\" \"%s\" \"%s\"" % (name, message, abbreviatedMessage))
            self._soundThread.queue.put((name, message, abbreviatedMessage))
        else:
            logging.error("Sound not %s, ignoring play request: \"%s\" \"%s\" \"%s\""
                % ("active" if self.soundAvailable else "available", name, message, abbreviatedMessage))

    def say(self,  message='This is a test!'):
        """ Schedules the work, which is picked up by SoundThread.run()
        """
        if self.soundAvailable and self.soundActive:
            self._soundThread.queue.put((None, message, None))

    def quit(self):
        if self._soundThread:
            self._soundThread.quit()

    #
    #  Inner class handle audio playback without blocking the UI
    #

    class SoundThread(QThread):
        queue = None
        effects = {}
        parent = None
        pyttxsxEngine = None
        predefined = None
        playingEffect = None

        # On stock windows 10 english, see "Microsoft David Desktop" and female "Microsoft Zira Desktop"
        FEMALE_WIN_VOICE = 'Microsoft Zira'

        def __init__(self, parent, predefined):
            QThread.__init__(self)
            self.parent = parent
            self.predefined = predefined
            if not parent.soundAvailable:
                logging.critical('NO SOUND ENGINE.')
                return
            self.queue = Queue()
            self.active = True

        def run(self):
            # Initialize anything with timers in the "same thread".  __init__() runs in parent's thread
            if pyttsxAvailable and not festivalAvailable:
                self.pyttxsxEngine = pyttsx.init()
                for voice in self.pyttxsxEngine.getProperty('voices'):
                    if voice.gender == 'female':
                        logging.critical('using female voice ' + voice.name)
                        self.pyttxsxEngine.setProperty('voice', voice.id)
                        break
                    elif self.FEMALE_WIN_VOICE in voice.name:
                        logging.critical('using ' + self.FEMALE_WIN_VOICE + ' voice ' + voice.name)
                        self.pyttxsxEngine.setProperty('voice', voice.id)
                        break
                    else:
                        logging.info('available voice ' + voice.name)
            for key in self.predefined:
                self.effects[key] = QSoundEffect()
                self.effects[key].setSource(QUrl.fromLocalFile(resourcePath("vi/ui/res/{0}".format(self.predefined[key]))))
            self.updateVolume()

            while True:
                # Need to process events in this thread's event loop while effects are playing
                if self.playingEffect and self.playingEffect.isPlaying():
                    QEventLoop().processEvents(QEventLoop.AllEvents)
                    continue
                else:
                    self.playingEffect = None
                # Now it's ok to block and wait for an event, we finished playing previous sound
                name, message, abbreviatedMessage = self.queue.get()
                if not self.active:
                    return
                if self.parent.useSpokenNotifications and (message or abbreviatedMessage):
                    if abbreviatedMessage:
                        message = abbreviatedMessage
                    if not self.speak(message):
                        self.play(name)
                        logging.error("SoundThread: sorry, speech not yet implemented on this platform")
                else:
                    self.play(name)


        def updateVolume(self):
            effectsVolume = float(self.parent.getSoundVolume())/100
            for key in self.effects:
                self.effects[key].setVolume(effectsVolume)
            if self.pyttxsxEngine:
                self.pyttxsxEngine.setProperty('volume', effectsVolume)


        def play(self, name):
            if name in self.effects:
                logging.debug("Playing sound: %s" % name)
                self.effects[name].play()
                self.playingEffect = self.effects[name]
            else:
                logging.error("SoundThread: NO SOUND PLAYED, unknown sound \"%s\"" % name)


        def quit(self):
            self.active = False
            self.queue.put((None, None, None))
            QThread.quit(self)


        def speak(self, message):
            logging.critical("speaking: %s" % message)
            if self.parent.isDarwin:
                self.darwinSpeak(message)
            elif festivalAvailable:
                festival.sayText(message)
            elif pyttsxAvailable:
                self.pyttsxSpeak(message)
            else:
                return False
            return True


        #
        #  Audio subsytem access
        #

        def darwinSpeak(self, message):
            logging.debug("Speaking with darwin: %s" % message)
            try:
                os.system("say [[volm {0}]] '{1}'".format(float(self.parent.getSoundVolume()) / 100.0, message))
            except Exception as e:
                logging.error("SoundThread.darwinSpeak exception: %s", e)


        def pyttsxSpeak(self, message):
            logging.debug("Speaking with pyttsx: %s" % message)
            try:
                self.pyttxsxEngine.say(message)
                self.pyttxsxEngine.runAndWait()
            except Exception as e:
                logging.error("SoundThread.darwinSpeak exception: %s", e)
