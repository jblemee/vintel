# This is  a windows shortcut helper,
#
# Setup a shortcut using your ananconda installation directory and your vintel source triggered
#   "E:\Program Files\Anaconda2\pythonw.exe" "\FULL\PATH\TO\src\vintel\src\conda2_launcher.py" "E:\Program File\Anaconda2"
#
# It is based on the cwp.py script included with ananconda, but that script is hardcoded to switch
# the current working directory to the user's home directory on launch

import os
import sys
import subprocess
from os.path import join

prefix = sys.argv[1]

env = os.environ.copy()
env['PATH'] = os.path.pathsep.join([
        prefix,
        join(prefix, "Scripts"),
        join(prefix, "Library", "bin"),
        env['PATH'],
])

dir = os.path.abspath(os.path.dirname(__file__))
print("prefix=[%s], dir=[%s]" % (prefix, dir))
os.chdir(os.path.abspath(os.path.dirname(__file__)))
subprocess.call([sys.executable, "vintel.py"], env=env)
