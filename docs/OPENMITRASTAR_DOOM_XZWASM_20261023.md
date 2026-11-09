# Doom: candidato XZ con descompresión en el cliente

Fecha: 23 de octubre de 2026, hora local de Madrid.

La propuesta del propietario queda comprobada en un candidato independiente:
el conjunto jugable ocupa 1.963.925 bytes de archivos y 1.933.312 bytes en
SquashFS XZ con bloques de 1 MiB. No cambia el motor ni el WAD del episodio
shareware original, y conserva la configuración de música y controles.

## Archivos del conjunto jugable

| Componente | Bytes almacenados |
| --- | ---: |
| chocolate-doom.wasm.xz | 499.548 |
| doom1.wad.xz | 1.362.736 |
| chocolate-doom.js.xz | 48.032 |
| xzwasm.min.js, descompresor autocontenido | 19.832 |
| Página, cargador, licencias y procedencia | 33.777 |
| Total del conjunto jugable | 1.963.925 |

El motor descomprimido es el WASM cualificado de 2.291.176 bytes, SHA-256
eb47045e861708f4263f994610ed2e58ab63838aff738e3577cca9b68797c20e.
El WAD de 4.196.020 bytes se extrae del ZIP original sin cambiar sus datos,
SHA-256 1d7d43be501e67d927e415e0b8f3e29c3bf33075e859721816f652a526cac771.
El JavaScript del motor también conserva su hash.

El navegador recibe XZ, comprueba tamaño y SHA-256 de los bytes comprimidos,
descomprime y vuelve a comprobar tamaño y SHA-256. Entrega el WASM mediante
Module.wasmBinary y el WAD al sistema de archivos del motor. El JavaScript
descomprimido se carga desde un Blob. No requiere CDN, HTTP ni WebSockets.

## Pruebas y alcance

La prueba local de navegador pasa arranque, inicio de partida, movimiento,
disparo, controles táctiles, audio PCM y configuración de música activada.
Verifica los tres assets descomprimidos, ausencia de descargas del WASM/JS/ZIP
sin comprimir y ausencia de solicitudes externas. Una entrada comprimida
corrupta del mismo tamaño se rechaza antes de descomprimirla o arrancar Doom.
El audio de pistas individuales no se ha vuelto a aislar en esta prueba.

La prueba utiliza un origen HTTPS interceptado por Playwright con archivos
locales. No demuestra transporte TLS desde el HGW ni aceptación física de
este candidato. No se modifica el router, la radio, flash o bootenv.

Recibos:

- [Empaquetado](../outputs/doom/xzwasm-candidate-20261023-v1/package-result.json).
- [Comparación SquashFS](../outputs/doom/xzwasm-candidate-20261023-v1/size-comparison.json).
- [Navegador](../outputs/doom/xzwasm-browser-20261023-v1/result.json).
- [Constructor](../work/kernel-port/xzwasm-evaluation-20261023/build_doom_xz_candidate.py).
- [Prueba](../work/kernel-port/xzwasm-evaluation-20261023/validate_browser.js).

## Separar ejecución, fuentes y distribución original

Los 1,96 MB describen el conjunto jugable. El candidato completo sigue
conservando doom19s.zip y doom-wasm-source.tar.gz: suman otros 3.364.392 bytes
y no participan en el arranque. Con ellos, los archivos del candidato completo
ocupan 5.328.317 bytes.

Para entregar la variante de 1,96 MB en flash, esos dos archivos tendrían que
quedar fuera de la imagen y mantenerse en el árbol local de distribución y
fuentes. Aún no se ha promovido esa variante a firmware; los enlaces de descarga
del candidato completo siguen disponibles. No se ha borrado ningún original.
La variante pequeña medida es un conjunto de capacidad, no una nueva entrega
con esos enlaces ya resueltos.

| Paquete aislado, mismos ajustes SquashFS | Bytes |
| --- | ---: |
| Anterior: once archivos completos | 3.944.448 |
| Nuevo XZ con fuentes y ZIP original retenidos | 5.300.224 |
| Nuevo XZ: conjunto jugable | 1.933.312 |

Comprimir previamente y además conservar ZIP+WAD duplicados puede aumentar el
coste dentro de SquashFS. No confundir tamaño bruto, descarga por red, paquete
jugable y firmware completo. El ajuste final de kernel, rootfs y drivers sigue
pendiente y no autoriza flash.

## Procedencia del descompresor

Repositorio: SteveSanderson/xzwasm. Checkout de evaluación:
75a7519c7c38fe641a9fa9809db1378fe339ac5c.
El binario utilizado es el asset xzwasm.min.js de la release v0.1.2,
publicada el 4 de julio de 2021, SHA-256
fb7e7a0e39df438276f290dd15865734d1b81674084cfa36ef0b77042391df9b.
El checkout actual y el binario de release no se presentan como una
reconstrucción idéntica entre sí. La declaración del paquete indica MIT;
la procedencia y avisos de la biblioteca deben acompañar la entrega final.

## Integración de radio R2, separada de este candidato

La receta R2 conserva inicialmente el paquete Doom anterior para no mezclar
la aceptación de radios con esta alternativa de embalaje.
El primer intento se detuvo por una comprobación demasiado estrecha del
shebang /bin/ash. El segundo recompiló los 19 módulos de radio con hashes
idénticos, pero se detuvo al comparar Ethernet: la ruta de __FILE__ en
include/linux/dma-mapping.h cambió al nuevo directorio. La receta ahora
normaliza esa ruta al origen del padre. La pareja completa R2 todavía no
está construida ni aceptada físicamente; no hay proceso de compilación activo.
