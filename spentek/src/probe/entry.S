    .syntax unified
    .thumb
    .section .entry, "ax"
    .global _entry
_entry:
    b.w   s_helper          @ +0  speaker dispatch (r0 = 40 kHz tick), ends by jumping on
    b.w   boot              @ +4  replaces bl delay_ms in main
    b.w   s_keyrel          @ +8  key released: replaces cmp r1,#6 ; blo skip (r5 = key, r1 = scans held)
s_helper:
    push  {r0, r1, r2, r3, lr}
    sub   sp, #4
    bl    helper
    mov   ip, r0
    add   sp, #4
    pop   {r0, r1, r2, r3, lr}
    bx    ip
s_keyrel:
    push  {r1, r2, r3, lr}
    mov   r0, r5
    bl    key_release
    cmp   r0, #0
    pop   {r1, r2, r3, lr}
    it    ne
    bxne  lr
    ldr   r0, =0x08008355
    bx    r0
    .ltorg
