    .syntax unified
    .thumb
    .section .entry, "ax"
    .global _entry
_entry:
    b.w t_poll
    b.w t_key
    b.w t_enter
    b.w t_log
    b.w t_debug
    b.w t_clear
    b.w t_msg
