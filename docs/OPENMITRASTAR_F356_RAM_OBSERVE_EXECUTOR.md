# F356 — ejecutor de observación SPI con kernel RAM

21 de septiembre de 2026. **PASS_OFFLINE_F356_OBSERVE_EXECUTOR**: 65 pruebas
del ejecutor, contexto y propietario real con backend simulado, más la
cualificación independiente de 43 comprobaciones de los artefactos.
**No se ha ejecutado hardware desde esta preparación.**

Plan: `outputs/preflight/f356-observe-20260921T171932Z/plan.json`.
SHA-256: `49dd5d92276f5c623e00df258ec6c40b6d01945ce4e4d10da5dc7e58334b0d6c`.
Resultado y pruebas están en ese mismo directorio. El plan fija 99 archivos.
Las futuras evidencias físicas se guardan en
`/workspace/OpenMitraStar\f356-evidence\f356-observe-<UTC>-<UUID>`.

## Única operación permitida

Arrancar en RAM el kernel F350 exacto, cargar el proveedor F356 con
`allow_hw=1 allow_program=0`, ejecutar una sola vez `om-journal-cli observe`
y regresar al F340 persistente por lectura y boot directo desde Bootbase.
No se ejecutan LOAD, INSPECT ni SAVE del journal, PP02, D8, WREN/WRDI,
modificaciones de protección, flash de firmware ni cambios de bootenv persistentes.

OBSERVE consulta identificación, estado y security. La lectura de security OEM
necesita escribir temporalmente SPI_CONTROL y activar SCUR; el proveedor lo
hace **sólo tras comprobar ID c22018** y restaura el controlador. Por tanto,
F356 no es una repetición del probe F354 de cero escrituras MMIO. Las escrituras
de programación/borrado/protección siguen deshabilitadas por un parámetro 0400.

No se identifica 35F frente a 36E ni se exige BP0 para poder observar una
protección distinta. `common_bp0` se registra y valida sin desbloquear nada;
`exact_part_verified` permanece false. Una identificación diferente se conserva
en el diagnóstico parcial y provoca FAIL, sin probar otro comando vendor.

## Componentes fijados

Bundle final: `outputs/kernel-port/f356-observe-ram-20260921T171309Z/result.json`,
SHA `5ae7ad32f718da536787cb1008450a24ce4551861245ca3c64a5ebcf89fe7d0f`.
Cualificación: `outputs/preflight/f356-artifacts-qualified-20260921T171418Z/result.json`,
SHA `18dfc4ff9f52c83fe6df89534630df535300ddc7f72645509523b08a2057c292`.

| Componente | Bytes | SHA-256 |
| --- | ---: | --- |
| RAS RAM, kernel `#350 @1790006400` | 1.532.255 | `b4753dc8f2cbb0847011e7f3241a58d8dcb6d4c2fc18c12296f9f8b7161621d0` |
| `qtn_f356_journal.ko` final | 20.192 | `ab88ec603c18cd013f0de1d79eed1ea9c696ca97d2b589e0e8b9aaa8f9251cd4` |
| Supervisor RAM F356 | 33.720 | `3cb43d1686626c0df99fbce43912db6df54553da5bfb07fba820a8e5cf9062a5` |
| CLI F351 | 25.524 | `dee84fd30d41734e52d4627418028a1d15cd64db87cca1bc3eef261aacb0edef` |
| `ram-insmod-qtn` | 816 | `8eb902dcc5e1bdab1aba356aafca04102ab394352c1685434ac9a9a09c5baba6` |

No usar el proveedor anterior `94b032…` ni el bundle `170552Z`: la versión
final conserva también ID/validity parciales si el ID cambia durante el cierre.
El kernel F350, su DT y configuración permanecen exactos. El rootfs sigue
siendo el F340 persistente de sólo lectura, con release ABI compatible.

## Secuencia comprobada

1. Validación local de todos los hashes y consumo de un claim de ejecución
   único por plan. Por defecto no se entra en esta secuencia física.
2. F340 fresco por SSH, nonce observado en UART, PnP exacto y lease F319.
   Se reutiliza la autorización UDP existente, sin elevar privilegios ni
   modificar firewall, dirección o ruta del host.
3. RX UART continuo; reboot controlado a Bootbase. Se observa WDT inactivo
   y se verifican CRCs de protegidos y slot F340 antes del arranque RAM.
4. TFTP de un único kernel a `0x83000000`; se cierra el servidor y se comprueba
   CRC `26c4bc6e`, cabecera/entry, watchdog inactivo y bootargs temporales con
   readback. `bootm` recibe la cabecera en `0x83000000`; no usa `+4` ni selector.
5. El kernel debe ser exactamente `#350 @1790006400`, release
   `5.10.260-openmitrastar-radiohw`, DT F340 y boot ID nuevo. El gate de plataforma
   de 27 comprobaciones espera `boot-state=ready`, servicios y calibración;
   después se vuelve a comprobar #350 y el mismo boot ID. Sólo son consultas
   de estado, no pruebas Wi-Fi/RF, asociación, tráfico ni acceso a AELITA.
6. Se exige `/dev` montado como devtmpfs rw, almacenamiento RO, printk visible
   y supervisor RAM que reconoce el perfil #350. No se supone ni ejecuta mknod.
7. El supervisor real se separa de la shell y se comprueba por IPC: token,
   UID/credenciales del socket, PID/start ticks y boot ID. ARM+BEGIN comparten
   una orden SSH; fase `spi-identify-observe`, 60 s; sesión máxima 180 s.
8. `ram-insmod-qtn` recibe un solo `argv[2]` literal
   `allow_hw=1 allow_program=0`. Se verifican módulo/nodo y sysfs Y/N; antes del
   CLI se comprueba otra vez `allow_program=N`. No se usa BusyBox insmod.
9. Sólo un CLI exitoso con JSON íntegramente válido y un marcador UART idéntico,
   `valid=0f claimed=0 quarantined=0`, permite una retirada del módulo.
10. CEASE deja de alimentar y mantiene el FD del watchdog. Tras reset y prompt
    nuevos se exige EN=0; se verifica y arranca directamente el prefijo F340
    desde flash. Se comprueban boot ID nuevo, #340, plataforma 27 y WDT inactivo.

La ventana de autoboot usa el contrato real de Capture: máximo 120 segundos.
Los prompts anteriores quedan invalidados antes de cada handoff. Un reset ya
detectado permite esperar a su prompt nuevo; no se emite otro reboot por falta
momentánea del prompt.

## Fallos, cuarentena y evidencias

El marcador único `OMF356 observe` sólo imprime datos cacheados después de
release/quarantine: rc, ID, control, estado, security y máscara de validez.
Bit 1 acredita ID, 2 control, 4 estado y 8 security. `valid=07` no permite
presentar el cero de security como una lectura válida. Se espera hasta dos
segundos por el lector UART independiente y se conserva el marcador aun si
el CLI falla. El marcador por sí solo jamás convierte el resultado en PASS.

Cualquier error/timeout/respuesta parcial o claim/cuarentena implica **no
descargar el proveedor**, no repetir la observación, CEASE/reset y retorno
de sólo lectura a F340. Nunca se mata un posible propietario armado ni se
simula desarme cerrando el watchdog. Un fallo del retorno no dispara otro bootm.

El suelo de 500 MiB libres en C: y D: sólo limita admisión y trabajo nuevo.
No bloquea los guards de lease/PNP/pins, CEASE, UART, recuperación o evidencia
final pequeña. La carpeta D: está fijada y comprobada contra reparse points,
con prueba local de escritura/lectura. Los errores reales de evidencia se
conservan como FAIL; incluso un error del último progreso después de volver
a F340 no deja un PASS falso ni repite el retorno. Si la evidencia final o la
contención no se pueden demostrar, el launcher conserva la barrera del lease.

## Pruebas y ejecución reservada a root

37 pruebas Python, 24 de contexto PowerShell y 4 con los métodos reales del
Host y el supervisor C con watchdog simulado. Cubren flags, controlador/ID,
validity parcial, errores/timeout, cuarentena sin unload, recuperación y errores
de evidencia antes/durante/después del retorno. La función RAM/TFTP real se
prueba con respuestas simuladas de transferencia corta, CRC incorrecto y
servidor no contenido; Capture.stop_autoboot se ejecuta realmente en memoria.

Validación sin dispositivo:

```powershell
python tools/f356_observe_executor.py --plan outputs/preflight/f356-observe-20260921T171932Z/plan.json --plan-sha256 49dd5d92276f5c623e00df258ec6c40b6d01945ce4e4d10da5dc7e58334b0d6c
```

Comando preparado para root tras revisión:

```powershell
& tools/run_f356_observe.ps1 -PlanPath outputs/preflight/f356-observe-20260921T171932Z/plan.json -PlanSha256 49dd5d92276f5c623e00df258ec6c40b6d01945ce4e4d10da5dc7e58334b0d6c -Execute
```

No se ha ejecutado ese comando aquí. La recuperación por watchdog ante parada
de CPU, bus o chip completo sigue sin demostrarse; F343 permanece cancelado.
