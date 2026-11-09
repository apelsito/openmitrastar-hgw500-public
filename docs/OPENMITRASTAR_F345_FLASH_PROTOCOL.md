# F345: protocolo de la memoria NOR, sin transporte MMIO

Estado a 21 de septiembre de 2026: **codificador de comandos offline PASS**.
No es un controlador de almacenamiento operativo. No accede al HGW, no
identifica físicamente su chip y no habilita escrituras persistentes.

El resultado es `outputs/kernel-port/f345-protocol-20260921T141539Z/result.json`:
8.488 comprobaciones, análisis estático GCC y dos archivos ARC idénticos.
`libf345protocol.a` ocupa 2.696 bytes. El primer build fallido por formato de
una condición permanece en su directorio original; no fue un fallo de hardware.

## Diferencia que debe resolverse antes de elegir órdenes

Las referencias antiguas del proyecto alternan MX25L12835F y MX25L12836E.
Una tabla GPL llama `mx25l12836e` al ID `c22018`, pero la rama MACRONIX de
`drivers/ruby/spi_api.c` utiliza DPB. Ese nombre no acredita el marcaje del
componente instalado. Tampoco lo acredita una nota histórica de cableado.
Se ha solicitado al propietario el marcaje exacto; no se presupone la respuesta.

La documentación del fabricante distingue estos contratos:

| Operación | MX25L12836E | MX25L12835F |
|---|---|---|
| Leer protección volátil | `3C`, dirección de 24 bits | `E0`, dirección de 32 bits |
| Cambiar protección volátil | `36`/`39`, dirección de 24 bits | `E1`, dirección de 32 bits y byte separado |
| Protección adicional no volátil | No forma parte de este contrato | SPB: debe observarse desprotegida antes de programar |

Ambas referencias comparten el ID JEDEC indicado. El cambio WPSEL es permanente;
F345 lo comprueba como condición previa y no genera esa orden. Tampoco genera
cambios de protección global, OTP, SPB, contraseña, reloj o modo de lectura.
Las escrituras codificadas se limitan a los dos bloques de journal `dc0000`
y `dd0000`; la programación no puede cruzar una página de 256 bytes.

## Alcance exacto de la implementación

`work/kernel-port/modules/f345_spi_nor_protocol/` contiene el contrato C, el
codificador y las pruebas. Produce bytes SPI en orden de transmisión, incluidos
los cuatro bytes de dirección y el byte DPB independiente del modelo F.
No convierte esos bytes en valores de registros del controlador Topaz.

El contexto de prueba representa identidad/protección aportadas por un futuro
propietario del bus. Rellenarlo no demuestra identidad ni estado físico. El
transporte deberá observar WIP/WEL, conservar la configuración del controlador,
verificar los resultados y compartir exclusión con todos los lectores de flash.
El mutex de un módulo nuevo no protege por sí solo las lecturas del `mtd-rom`
actual. No existe todavía un adaptador F342 → F345 → MMIO.

El helper OEM localizado sólo limpia DPB y después utiliza protección global.
No se ha encontrado allí una restauración individual de un byte arbitrario.
No debe suponerse que hacer OR del byte de protección en una dirección MMIO
genere el paquete correcto: hace falta demostrar el transporte del byte final.

## Fuentes verificadas

Los documentos originales descargados de Macronix y sus hashes están en
`outputs/research/f345-nor-datasheet-20260921T135832Z/`:

- MX25L12836E, revisión 1.7: páginas 15, 28–34 y 59.
- MX25L12835F, revisión 1.7 de 2025: páginas 70–71.
- AN0177, revisión 3: páginas 3–6 y 10–12; diferencia de instrucciones e IDs.

Se inspeccionaron visualmente las tablas y diagramas relevantes. La petición
de un antiguo enlace a la revisión 1.6 devolvió 404 y queda registrada como
fallo; no se utilizó un archivo inexistente como fuente.

Reproducción: `python tools/build_f345_protocol.py`. Sólo crea artefactos
locales; la identificación del chip, el transporte, la exclusión y la prueba
de persistencia tras un corte permanecen pendientes.
