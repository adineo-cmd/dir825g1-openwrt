#!/usr/bin/env python3
"""Build a flashable factory image for the DIR-825 G1 from an OpenWrt sysupgrade.bin.

Reverse-engineered TBS 'old_img_hdr' format (see docs/REVERSE-ENGINEERING.md):

    [144-byte header][payload][4-byte custom CRC-32]

Header fields the stock upgrader validates:
  u32  @ +20   : erase size (payload rounded up to 64K)
  str  @ +24   : "imgs"
  str  @ +32   : product string, must equal llconfig 'model' (RTL8197DN_AC1200)
  str  @ +48   : product string (checked again)
  str  @ +80   : hardware version (1.0.6.2)
  str  @ +112  : board id (DIR825G1)
  str  @ +132  : region (IN)

CRC: custom MSB-first accumulator over the reflected zlib table, init 0,
final complement. The table (256 BE u32 @ file offset 0x5080) is taken from
the router's own /usr/bin/upgrader dump — pass that dump as UPGRADER_BIN.

CRITICAL: the kernel's LZMA stream must use props byte 0x5d (lc=3 lp=0 pb=2).
OpenWrt's default is 0x6d and the bootloader will silently fail to decompress
it → boot loop. --fix-lzma repacks it (REQUIRED unless you verified the props
yourself: first byte of sysupgrade.bin must be 0x5d).
"""
import argparse, lzma, struct

PRODUCT = b"RTL8197DN_AC1200"
BOARD = b"DIR825G1"
HWVER = b"1.0.6.2"
REGION = b"IN"
KERNEL_PART = 1715456  # 0x1A2D00 — kernel partition size; rootfs starts here


def load_crc_table(upgrader_bin):
    raw = open(upgrader_bin, "rb").read()
    return [struct.unpack(">I", raw[0x5080 + i * 4:0x5084 + i * 4]) for i in range(256)]


def tbs_crc(data, table):
    crc = 0
    for b in data:
        crc = ((crc << 8) & 0xFFFFFFFF) ^ table[((crc >> 24) ^ b) & 0xFF]
    return (~crc) & 0xFFFFFFFF


def repack_lzma_5d(kernel_part):
    """Decompress the OpenWrt kernel stream and recompress with stock params."""
    dec = lzma.LZMADecompressor(format=lzma.FORMAT_ALONE)
    raw = dec.decompress(kernel_part)
    filters = [{"id": lzma.FILTER_LZMA1, "preset": 9,
                "dict_size": 8 * 1024 * 1024, "lc": 3, "lp": 0, "pb": 2}]
    comp = lzma.LZMACompressor(format=lzma.FORMAT_ALONE, filters=filters)
    stream = bytearray(comp.compress(raw) + comp.flush())
    assert stream[0] == 0x5d, "props byte is not 0x5d"
    stream[5:13] = struct.pack("<Q", len(raw))  # python writes 'unknown' size
    stream = bytes(stream)
    assert lzma.LZMADecompressor(format=lzma.FORMAT_ALONE).decompress(stream) == raw
    return stream + b"\x00" * (KERNEL_PART - len(stream))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("sysupgrade")
    ap.add_argument("upgrader_bin",
                    help="dumped /usr/bin/upgrader from stock fw (CRC table source)")
    ap.add_argument("-o", "--output", default="openwrt-dir825g1-factory.img")
    ap.add_argument("--fix-lzma", action="store_true",
                    help="repack kernel LZMA with props 0x5d (REQUIRED to boot)")
    args = ap.parse_args()

    img = open(args.sysupgrade, "rb").read()
    if args.fix_lzma:
        img = repack_lzma_5d(img[:KERNEL_PART]) + img[KERNEL_PART:]
    table = load_crc_table(args.upgrader_bin)

    erase = (len(img) + 65535) // 65536 * 65536
    hdr = bytearray(144)
    struct.pack_into(">I", hdr, 20, erase)
    hdr[24:29] = b"imgs\x00"
    hdr[32:32 + len(PRODUCT) + 1] = PRODUCT + b"\x00"
    hdr[48:48 + len(PRODUCT) + 1] = PRODUCT + b"\x00"
    hdr[80:80 + len(HWVER) + 1] = HWVER + b"\x00"
    hdr[112:112 + len(BOARD) + 1] = BOARD + b"\x00"
    hdr[132:132 + len(REGION) + 1] = REGION + b"\x00"

    body = bytes(hdr) + img
    out = body + struct.pack(">I", tbs_crc(body, table))
    open(args.output, "wb").write(out)
    print(f"{args.output}: {len(out)} bytes "
          f"(erase {erase:#x}, kernel lzma props {out[144]:#02x} — must be 5d)")


if __name__ == "__main__":
    main()
