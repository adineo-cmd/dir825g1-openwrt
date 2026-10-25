# Device/DIR825G1 — add inside:  ifeq ($(SUBTARGET),rtl8197d)  in
# target/linux/realtek/image/Makefile of choryuidentify/openwrt-rtl8197f
#
# NOTE: pad-to must be 1715456 (0x1A2D00) — the sysupgrade kernel part is
# written raw to flash at 0x30000 by the TBS factory flow, and rootfs must
# land exactly on the 'rootfs' partition declared in DIR825G1.dts.

define Device/DIR825G1
  $(Device/RealtekDTS)
  DEVICE_DTS := DIR825G1
  DEV_PROFILE := DIR825G1
  BLOCKSIZE := 64k
  IMAGE_SIZE := 7872k
  KERNEL_SIZE := 1676k
  DEVICE_TITLE := D-Link DIR-825 G1
  SUPPORTED_DEVICES := dir-825-g1
  IMAGES := sysupgrade.bin
  IMAGE/sysupgrade.bin := append-kernel | pad-to 1715456 | append-rootfs | pad-rootfs | append-metadata
endef
TARGET_DEVICES += DIR825G1

# The stock DIR815D1 definition (factory.bin with tbs_dlink_big) is DISABLED
# in our tree: the tbs_dlink host tool was never committed upstream. Use
# tools/make_factory_image.py to wrap sysupgrade.bin into the TBS factory
# format instead (fully reconstructed from the router's own upgrader).
