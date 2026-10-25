#!/usr/bin/env python3
"""Minimal read-only TFTP server (RFC 1350) for pushing firmware to the router.

Usage:  python3 tftp_server.py [port] [serve_dir]     (default 1069 /tmp/tftpboot)

Router side:  tftp -g -l /var/file.bin -r file.bin <pc-ip> 1069 &

WARNING: a sandboxed server process never receives LAN UDP — run this
unsandboxed. Port 69 (needed by bootloader rescue modes) requires root.
"""
import socket, os, sys

ROOT = sys.argv[2] if len(sys.argv) > 2 else "/tmp/tftpboot"
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 1069


def serve():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("0.0.0.0", PORT))
    print(f"TFTP server on :{PORT} serving {ROOT}", flush=True)
    while True:
        data, addr = sock.recvfrom(2048)
        if int.from_bytes(data[0:2], "big") != 1:  # RRQ only
            continue
        parts = data[2:].split(b"\x00")
        fname = os.path.basename(parts[0].decode())
        print(f"RRQ {fname} from {addr}", flush=True)
        try:
            blob = open(os.path.join(ROOT, fname), "rb").read()
        except OSError as e:
            sock.sendto(b"\x00\x05\x00\x01" + str(e).encode() + b"\x00", addr)
            continue
        blk = 1
        try:
            for off in range(0, len(blob), 512):
                pkt = b"\x00\x03" + blk.to_bytes(2, "big") + blob[off:off + 512]
                ok = False
                for _ in range(8):
                    sock.sendto(pkt, addr)
                    sock.settimeout(2)
                    try:
                        rdata, _ = sock.recvfrom(1024)
                        if rdata[0:2] == b"\x00\x04" and int.from_bytes(rdata[2:4], "big") == blk:
                            ok = True
                            break
                    except socket.timeout:
                        pass
                if not ok:
                    print(f"no ack for block {blk}, abort", flush=True)
                    break
                blk = (blk + 1) & 0xFFFF or 1
            else:
                print(f"sent {len(blob)} bytes of {fname}", flush=True)
        finally:
            sock.settimeout(None)


if __name__ == "__main__":
    serve()
