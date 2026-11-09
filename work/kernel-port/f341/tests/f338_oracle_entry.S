.section .text.entry,"ax",@progbits
.global _start
_start:
 mov sp,0x803f0000
 mov fp,0
 bl f338_oracle_main
1:
 flag 1
 b 1b
