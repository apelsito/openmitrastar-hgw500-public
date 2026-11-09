# F347: compilación del observador SPI pasivo para F340

Resultado: `outputs/kernel-port/f347-passive-spi-control-20260921T145647Z/result.json`,
**PASS offline; ejecución física pendiente**.

Se reutiliza sin cambios el source F320, compilado dos veces contra el kernel
exacto F340. El módulo resultante es idéntico al anterior: 7.592 bytes,
SHA-256 `6ec075b4875890d5f366ff568932b591b59cc15231282274d77bb868a768a06a`.
Pasan sus nueve casos C, GCC analyzer, auditoría de imports y comprobación
de los dos helpers ARC de una lectura cada uno.

No se ha cargado el módulo ni contactado el HGW en este trabajo. No existe
un disparador de fallo de CPU. No sustituye ni reintenta la prueba F343 que
rechazó el control automático.

Con activación explícita, su alcance de source es comprobar el mapa en
`0xe0000004` y, sólo con los bits de alias desactivados, leer una vez el control
SPI en `0xe2000004`. No lee aperturas de órdenes SPI, no escribe registros ni
datos y no implementa un proveedor de transacciones. La reserva de recurso
coordina propietarios Linux; no acredita arbitraje eléctrico entre procesadores.

La compilación utiliza el contexto de módulos preparado de F341, cuya
configuración y vmlinux coinciden con F340. No modifica el kernel canónico.
Se conservan dos intentos fallidos por metadatos de build ausentes en el
directorio original: primero Module.symvers y después scripts/module.lds.
La tabla de exports y el contexto preparado se verifican antes de compilar.

Reproducción: `python tools/build_f347_spi_control_probe.py`. El resultado
no permite afirmar que el bus se haya leído correctamente ni que el watchdog
recupere un error de bus. Cualquier ejecución necesita su propia validación
de imagen/dispositivo, observación UART y recuperación.
