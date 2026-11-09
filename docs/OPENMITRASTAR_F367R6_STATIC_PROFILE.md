# F367r6 — helper regulatorio estático

R6 cambia exclusivamente el enlace del helper `om-f367-dfs-profile` y los
metadatos de versión/perfil/catálogos. Su fuente C y header OEM son idénticos
a R5. Qdrv, proveedor, engine, kernel/DT, supervisor y todos los scripts se
reutilizan sin recompilar ni cambiar un byte.

Imagen sellada `PASS_OFFLINE_F367R6_STATIC_PROFILE_IMAGE`:
`/workspace/user-home/.openmitrastar/devices/hgw500bna-qcv2-a2-primary/analysis/f367r6-fullimage-20260922T184150Z/result.json`.
5.464.064 bytes; SHA256
`dfcf24b67d4494608c0228fcf69895748309222bde9849678808872e3986a332`.
Manifest SHA256
`f5c9c2ab463cb4a754db6d6db4323a5ee16ba5f3f42204eaca019429c550ff01`.
Full-slot CRC32 `e98fe8f2`; Bootbase/slot-fit y dos repacks idénticos PASS.
Margen rootfs696.320 bytes. Store `5d2ee646` y F365 recovery `118901d4` intactos.

## Causa comprobada de R5

La imagen R5 contenía el helper con el hash esperado. Su ELF solicitaba
`/lib/ld-uClibc.so.0` y `libc.so.0`, ausentes del rootfs. Por eso ash informó
`not found` al ejecutarlo. La cualificación anterior verificó el nombre del
intérprete pero omitió comprobar su presencia; el PASS offline de entonces
no demostraba que el binario pudiera arrancar en ese rootfs.

R6 usa el contrato estático existente del supervisor: sysroot
`/home/user/openmitrastar-uclibc-noatomic-sysroot`, `-static -mno-atomic` y
secciones eliminables. Dos compilaciones producen el mismo ELF ARC700,
32 bits little endian, flags `0x403`. No hay PT_INTERP, PT_DYNAMIC ni
DT_NEEDED; el desensamblado no contiene `llock` ni `scond`.

Helper:25.524 bytes,
SHA256 `f7c678995b205577690502351504e54268cb5ffcbf1c5010cadeab3162063f92`.
Cualificación:
`outputs/kernel-port/f367r6-static-qualified-20260922T183736Z/result.json`.

## Prueba física de ejecución

Root ejecutó el probe en F365 restaurada, dentro de un fixture privado nuevo,
con argumento `__F367R6_INVALID_ARGUMENT_PROBE__`. Es la primera rama de
rechazo de `main`, anterior a cualquier lectura del estado objetivo o socket.
El helper devolvió1 con `reason=arguments errno=22`; el probe devolvió0 y
`F367R6_STATIC_EXEC_PASS invalid_argument_exit=1`. El fixture se eliminó.

Evidencia:
`outputs/handoff-live/f367r6-static-probe-20260922T183941Z/result.json`,
SHA256 `a700450d7f2ada90973472c40f8980a5312299d95ba3e29b25eede5a6f387636`.
No se ejecutó publicación, control kernel, socket de radio ni escritura MTD.
Este PASS demuestra que arranca el ejecutable; la publicación regulatoria
completa y CAC/NOP siguen siendo gates físicos pendientes.

## Composición y alcance

La composición parte de la R5 sellada y comprueba su hash. El worker acepta
exactamente cinco cambios: helper binario, release, profile.json, catálogo
radio y catálogo storage. Verifica el ELF extraído de la imagen nuevamente,
conserva todas las demás entradas y produce dos repacks idénticos.

Se reutilizan las21 comprobaciones del productor/lookup/getters/sysfs/parser
y los tres recorridos del helper de R5. No se repiten ni cambian el banco
regulatorio, el supervisor, CAC70s, NOP1800s o la cuarentena local1800s. El
destino continúa limitado a AP52/20 con bootstrap36/80 y evacuación36.

No se realizó hardware desde este subagente. Root conserva el gate físico y
el retorno automático a la F365 exacta; no se declara release PASS.
