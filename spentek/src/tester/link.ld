SECTIONS {
  . = BASE;
  .text : { KEEP(*(.entry)) *(.text*) *(.rodata*) }
  /DISCARD/ : { *(.ARM.*) *(.comment) *(.note*) }
  .data : { *(.data*) }
  .bss : { *(.bss*) *(COMMON) }
}
