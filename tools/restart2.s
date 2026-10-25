# restart2.s — sys_reboot("image;9010;;;;") stub for stock DIR-825 G1 kernel
# (big-endian MIPS32, stock kernel base 0x80010000)
#
#   sys_reboot(magic1=0xfee1dead, magic2=0x28121969,
#              cmd=LINUX_REBOOT_CMD_RESTART /* 0x01234567 */, arg="image;9010;;;;")
#
# Build:
#   mips-linux-gnu-as -EB -mips32 -o restart2.o restart2.s
#   mips-linux-gnu-ld -EB -Ttext=0x400000 -o restart2 restart2.o -e __start
#
# The reboot command string matches the stock upgrader's own. The kernel's
# machine_restart handler then looks for /var/update_img and, if present,
# flashes /var/image.img via flash_update_img().
#
# LESSON (do not repeat): the cmd constant MUST be 0x01234567. An earlier
# build passed a made-up 0xa1b2c3d4 -> syscall returned -EINVAL, no reboot,
# while a staged flag+image sat in tmpfs waiting for the next reboot...

    .text
    .globl __start
__start:
    lui $4, 0xfee1
    ori $4, $4, 0xdead
    lui $5, 0x2812
    ori $5, $5, 0x1969
    li  $6, 0x1234567          # LINUX_REBOOT_CMD_RESTART
    lui $7, %hi(cmd)
    ori $7, $7, %lo(cmd)
    li  $2, 4164               # __NR_reboot on this kernel
    syscall
1:  b 1b
    nop
cmd:
    .asciz "image;9010;;;;"
