"""Run under JMRI's jython: real managers and the real web server, on a scratch folder."""
import time

import java
from jmri import InstanceManager as IM
from jmri.jmrit.roster import RosterConfigManager
from jmri.util import FileUtil
from jmri.web.server import WebServer, WebServerPreferences

FileUtil.setUserFilesPath(None, java.lang.System.getProperty("ops.home") + "/")
IM.setDefault(RosterConfigManager, RosterConfigManager())
IM.getDefault(WebServerPreferences).setPort(int(java.lang.System.getProperty("web.port")))
WebServer.getDefault().start()
while True:
    time.sleep(5)
