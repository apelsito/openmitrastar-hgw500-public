# Preserved component notes

Editorial copy of the previous README. Workstation paths are normalized; original source and immutable evidence are not modified. Earlier status claims belong to their named checkpoints, not the live device. Start with the current [README](../README.md).

# OpenMitraStar · HGW500

Estado final del 8 de noviembre: API v2 R3 instalada y validada, con control de los cinco canales LED, tráfico bidireccional en las dos radios y ambos puertos, encendido normal OEM y preservación completa de la SPI. La selección vigente está en el manifiesto API v2 R3 y SOURCE_MAP_RELEASE.json. QDRV/reinicio por software, RF calibrada/radar, carga prolongada y ROM/DDR propia conservan gates independientes.

**Última instalación demostrada: API v2 R3, 8 de noviembre.**
Imagen de 6.105.504 bytes, SHA-256
`c713355262273183abe83f29ced4a24f7f2f929c36d4bed4e26b12e4cb1742d1`.
Tras aceptación RAM completa y autorización del artefacto exacto, pasan
instalación, arranque desde `linux_live`, doble readback de la SPI y preservación
de todos los bytes fuera de la imagen. SPI final:
`2e839b0402a3e40d95701e626c79d44ee3bff9c756258aabe5942a7715e9014f`.
El control de los cinco canales LED, las dos radios y ambos puertos Ethernet
ya tienen aceptación propia desde flash. El encendido normal OEM y el SPI
completo también están verificados; cada recibo conserva su arranque de origen.

La selección de release (`docs/RELEASE.md`; maintainer-workspace reference) enlaza la configuración Linux R51,
el mapa de fuentes, la receta conservada y los assets web exactos de esa
imagen. Los cuerpos de unidad permanecen locales e ignorados.

La API v2 nativa está en la imagen instalada. `linux-7.3-integrated-r1`
(seguridad RX/radar) conserva sus pruebas offline y sigue separado de esta
release. Foundation R3 y R39 permanecen como rollback. RF medido, DFS/CAC físico y parada global QDRV
siguen pendientes; ninguna versión hereda pruebas de otra.

Este checkout integra el producto. Los ocho repositorios independientes de
drivers, microfirmware y análisis de firmware están en ${WORKSPACE} y se
inventarían en el README.md y REPOSITORIES.json de esa raíz. drivers/ mantiene
las revisiones fijadas para construir la integración.

La preservación nativa de MuC, AuC y DSP se mantiene en los tres repositorios
hijos de [5 GHz Firmwares](https://github.com/apelsito/hgw500-5ghz-firmwares-public).
Usa Ghidra 12.1.3 con ARCompact:LE:32:default y la extensión fijada en
41703a7bbac5a316e6e72381af67d5ee0e1d9d25. Cada entrega conserva sus resultados
y limitaciones en ghidra/. Los tres GZF pasan reimportación con trece facetas
idénticas y el ensamblador exportado coincide en bytes con los carriers.
Los bucles lp conservan limitaciones de p-code en algunas funciones MuC/AuC.
Las pruebas físicas de la radio se registran en el estado de esta integración.

Port privado del **MitraStar HGW-500BNA-QCv2 A2** desde su Linux OEM
2.6.35.12 a Linux 7.3, con drivers Realtek y Quantenna, interfaz LYOKO y Doom.

Las instalaciones Core Boot R1, FW35.7, R39 y las pruebas RAM R52
se conservan con sus hashes y gates en el estado; son antecedentes de R3.
Los pins de los submódulos `drivers/` describen la selección histórica R26,
no las fuentes exactas de la última flash. El mapa de release fija esa relación.

- Estado exacto y pendientes (`docs/STATUS.md`; maintainer-workspace reference).
- Preparación y construcción (`docs/BUILD.md`; maintainer-workspace reference).
- Arranque, reinicio, lectura UART/RJ45 y flasheo por Ethernet (`docs/DEVICE.md`; maintainer-workspace reference).
- Ethernet, 5 GHz, enrutamiento y repetidor: estado y pendientes (`docs/NETWORK.md`; maintainer-workspace reference).
- AP por cable con Internet: activación RAM y controlador (`packages/network/README.md`; maintainer-workspace reference).
- Drivers y revisiones fijadas (`drivers/README.md`; maintainer-workspace reference).
- Firmware OEM y referencias de release (`firmware/README.md`; maintainer-workspace reference).
- Museo de los drivers originales (`museum/README.md`; maintainer-workspace reference).
- Cambios (`CHANGELOG.md`; maintainer-workspace reference).

Comprobar el checkout sin red ni hardware: `python tools/check_repository.py`.

```text
drivers/    fuentes Realtek y Quantenna fijadas mediante submódulos
build/      recetas actuales de producto, integración y servicios
web/        interfaz LYOKO
packages/   componentes de producto
tools/      herramientas seleccionadas de construcción y contratos
firmware/   manifiestos de release y cuerpos OEM/de unidad locales, fuera de Git
private/    identidad y claves de la unidad, fuera de Git
museum/     comentarios originales y procedencia
docs/       estado y construcción
```

El árbol activo contiene la selección de código inventariada en CURRENT. Las fuentes exclusivas R2
están en sources/ (`sources/README.md`; maintainer-workspace reference), con hashes comprobados. Las campañas de trabajo y los readbacks permanecen en `out/`; la referencia
de release sólo incorpora las fuentes y evidencias seleccionadas.
Los datos privados y las imágenes de la unidad permanecen locales; no se
suben por el hecho de que el repositorio sea privado. Licencias y autores
originales se conservan en sus componentes.

## Arquitectura de procesamiento del HGW500

El esquema y sus evidencias (`docs/HARDWARE_ARCHITECTURE.md`; maintainer-workspace reference), conservados el
3 de noviembre de 2026, identifican una CPU LHost ARC750 a 500 MHz y cuatro
coprocesadores: MuC, AuC, DSP y la MCU 8051 del RTL8192EE. Incluyen el inventario
SPI NOR de 16 MiB y el perfil DDR3 OEM de 128 MiB, con fuentes y límites.

Arquitectura de procesamiento del HGW500 (`docs/hardware/hgw500-processing-architecture.png`; maintainer-workspace reference)

El diagrama es una vista conceptual. La etiqueta qdrv describe el papel del
host; los gates físicos de cada revisión se registran en docs/STATUS.md.
