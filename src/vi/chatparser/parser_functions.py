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

""" 12.02.2015
	I know this is a little bit dirty, but I prefer to have all the functions
	to parse the chat in this file together.
	Wer are now work directly with the html-formatted text, which we use to
	display it. We are using a HTML/XML-Parser to have the benefit, that we
	can only work and analyze those text, that is still not on tags, because
	all the text in tags was allready identified.
	f.e. the ship_parser:
		we call it from the chatparser and give them the rtext (richtext).
		if the parser hits a shipname, it will modifiy the tree by creating
		a new tag and replace the old text with it (calls tet_replace),
		than it returns True.
		The chatparser will call the function again until it return False
		(None is False) otherwise.
		We have to call the parser again after a hit, because a hit will change
		the tree and so the original generator is not longer stable.
"""

import six
import logging
import re

import vi.evegate as evegate
from bs4 import BeautifulSoup
from bs4.element import NavigableString
from vi import states
from vi.systems import SYSTEMS

# Do not ignore <>/" which keep html from word matching on replacement
# Do not ignore ? which triggers status change to request
CHARS_TO_IGNORE_REGEX = '[*,!.()]'

REPLACE_WORD_REGEX = r'(^|(?<=[^0-9a-zA-Z])){0}((?=[^0-9a-zA-Z_])|$)'


def textReplace(element, newText):
    newText = "<t>" + newText + "</t>"
    newElements = []
    for newPart in BeautifulSoup(newText, 'html.parser').select("t")[0].contents:
        newElements.append(newPart)
    for newElement in newElements:
        element.insert_before(newElement)
    element.replace_with(six.text_type(""))


def parseStatus(rtext):
    texts = [t for t in rtext.contents if isinstance(t, NavigableString)]
    for text in texts:
        upperText = re.sub(CHARS_TO_IGNORE_REGEX, ' ', text.strip().upper()) # KEEP QUESTION MARK?
        upperText = text.strip().upper()
        upperWords = upperText.split()
        if ("?" in upperText):
            return states.REQUEST
        elif ("CLEAR" in upperWords or "CLR" in upperWords):
            return states.CLEAR
        elif ("STAT" in upperWords or "STATUS" in upperWords):
            return states.REQUEST
        elif (text.strip().upper() in ("BLUE", "BLUES ONLY", "ONLY BLUE" "STILL BLUE", "ALL BLUES")):
            return states.CLEAR


def parseShips(rtext):
    def formatShipName(text, word):
        newText = u"""<span style="color:#d95911;font-weight:bold">{0}</span>"""
        # Only do replacements at word boundaries
        text = re.sub(REPLACE_WORD_REGEX.format(word), newText.format(word), text)
        return text

    texts = [t for t in rtext.contents if isinstance(t, NavigableString)]
    for text in texts:
        upperText = re.sub(CHARS_TO_IGNORE_REGEX, ' ', text.upper())
        upperText = text.upper()
        for shipName in evegate.SHIPNAMES:
            if shipName in upperText:
                hit = True
                start = upperText.find(shipName)
                end = start + len(shipName)
                if ( (start > 0 and re.match('[A-Z0-9]', upperText[start - 1]))
                        or (end < len(upperText) and re.match('[A-RT-Z0-9]', upperText[end])) ):
                    hit = False
                if hit:
                    if (end < len(upperText) and 'S' == upperText[end]):
                        end += 1
                    shipInText = text[start:end]
                    formatted = formatShipName(text, shipInText)
                    textReplace(text, formatted)
                    return True

    return False


def parseSystems(systems, rtext, foundSystems):

    systemNames = systems.keys()

    # words to ignore on the system parser. use UPPER CASE
    WORDS_TO_IGNORE = ("IN", "IS", "AS", "OR", "NV", "TO", "ME", "HE", "SHE", "YOU", "ARE",
        "ON", "HAS", "OF", "IT", "GET", "IF", "THE", "HOT", "OH", "OK", "GJ", "AND", "MY",
        "SAY", "ANY", "NO", "FOR", "OUT", "WH", "MAN", "PART", "AT", "AN" )

    def formatSystem(text, word, system):
        newText = u"""<a style="color:#CC8800;font-weight:bold" href="mark_system/{0}">{1}</a>"""
        # Only do replacements at word boundaries: "no cyno onboard"  would replace both "no"s in the first pass and then find a "cy"
        text = re.sub(REPLACE_WORD_REGEX.format(word), newText.format(system, word), text)
        return text

    texts = [t for t in rtext.contents if isinstance(t, NavigableString) and len(t)]
    for text in texts:
        worktext = re.sub(CHARS_TO_IGNORE_REGEX, ' ', text)

        # Drop redundant whitespace so as to not throw off word index
        worktext = ' '.join(worktext.split())
        words = worktext.split(" ")

        for idx, word in enumerate(words):

            matchKey = None

            # Is this about another a system's gate?
            if len(words) > idx + 1:
                if words[idx+1].upper() == 'GATE':
                    bailout = True
                    if len(words) > idx + 2:
                        if words[idx+2].upper() == 'TO':
                            # Could be '___ GATE TO somewhere' so check this one.
                            bailout = False
                    if bailout:
                        # '_____ GATE' mentioned in message, which is not what we're
                        # interested in, so go to checking next word.
                        continue

            upperWord = word.upper()
            if upperWord != word and upperWord in WORDS_TO_IGNORE: continue
            if upperWord in systemNames:  # - direct hit on name
                matchKey = systems[upperWord]['name']
            elif 1 < len(upperWord) < 5:  # - upperWord 2-4 chars.
                for system in systemNames:  # system begins with?
                    if system.startswith(upperWord):
                        matchKey = systems[system]['name']
                        break
            if matchKey:
                foundSystems.add(matchKey)
                formattedText = formatSystem(text, word, matchKey)
                textReplace(text, formattedText)
                return True

    return False


def parseUrls(rtext):
    def findUrls(s):
        # yes, this is faster than regex and less complex to read
        urls = []
        prefixes = ("http://", "https://")
        for prefix in prefixes:
            start = 0
            while start >= 0:
                start = s.find(prefix, start)
                if start >= 0:
                    stop = s.find(" ", start)
                    if stop < 0:
                        stop = len(s)
                    urls.append(s[start:stop])
                    start += 1
        return urls

    def formatUrl(text, url):
        newText = u"""<a style="color:#28a5ed;font-weight:bold" href="link/{0}">{0}</a>"""
        text = text.replace(url, newText.format(url))
        return text

    texts = [t for t in rtext.contents if isinstance(t, NavigableString)]
    for text in texts:
        urls = findUrls(text)
        for url in urls:
            textReplace(text, formatUrl(text, url))
            return True

    return False
