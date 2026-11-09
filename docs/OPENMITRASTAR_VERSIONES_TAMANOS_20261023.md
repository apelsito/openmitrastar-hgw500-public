# OpenMitraStar: versiones, tamaños y prioridades

Inventario del 23 de octubre de 2026, 00:15 CEST. Los tamaños de los
componentes son bytes de archivos sin la compresión conjunta de SquashFS.
Los tamaños comprimidos de la composición se muestran por separado.
No son estimaciones del consumo RAM.

La prioridad indicada por el propietario es terminar primero las radios
2,4 y 5 GHz. Las optimizaciones de Doom quedan pendientes.

Actualización posterior: la propuesta del propietario con xzwasm se ha
medido y probado en navegador local. Conjunto jugable 1.963.925 bytes;
SquashFS aislado 1.933.312 bytes. Fuentes y ZIP original quedan conservados
por separado en el candidato completo, y no se ha cambiado el HGW.
Detalles y alcance: [Doom XZ](OPENMITRASTAR_DOOM_XZWASM_20261023.md).

## Hardware, kernel y drivers

| Componente | Versión o identidad | Tamaño | Evidencia |
| --- | --- | ---: | --- |
| Placa | HGW-500BNA-QCv2 A2, Topaz ARC750D, MMU v2, páginas8KiB | Hardware | Único target; OEM conservado. |
| Kernel actual | 7.3.0-openmitrastar-radio73-v1; upstream c03c1a14507dfaf8b856c2608f9ac216021fc222 | Imagen RAM completa6.980.384B | Arranque, nonce, memtest y servicios físicos. Este tamaño incluye initramfs; no es kernel aislado. |
| Realtek 2,4GHz | RTL8192EE, PCI10ec:818b; rtlwifi/mac80211 de Linux7.3 con port HGW | 1.594.352B para19módulos | WPA2 AUTH/ASSOC/AUTHORIZED y dos campañas GET/POSTTLS1.2/1.3. |
| Realtek rtl8192ee | Mismo port7.3 | 115.764B | Parte del conjunto anterior. |
| Realtek rtl_pci | Mismo port7.3 | 49.928B | Parte del conjunto anterior. |
| Realtek rtlwifi | Mismo port7.3 | 97.704B | Parte del conjunto anterior. |
| Realtek btcoexist | Mismo port7.3 | 170.816B | Parte del conjunto anterior. |
| mac80211 | Linux7.3 | 606.556B | Parte del conjunto anterior. |
| cfg80211 | Linux7.3 | 391.388B | Parte del conjunto anterior. |
| Realtek firmware | rtl8192eefw.bin | 31.818B | Identidad fijada por SHA; no versiónsemántica independiente confirmada. |
| Base regulatoria | wireless-regdb2026.09.03 | 6.348B+firma1.085B | Firma verificada y dominioES. |
| Quantenna5GHz | Fuente seleccionadaR20; candidato SRAMR22; ABIv37.4.0.89 | 1.651.560B para22módulosR22 | Dos builds idénticos,74Cunits, imports resueltos; reserva de placa y carga física pendientes. |
| Quantenna qdrv | R22 | 688.584B | Parte del conjunto anterior. |
| Quantenna wlan/net80211 | R22 | 691.548B | Parte del conjunto anterior. |
| Quantenna switch_tqe | R22 | 39.084B | Parte del conjunto anterior. |
| Quantenna hbm | R22 | 21.904B | Parte del conjunto anterior. |
| Quantenna om73_sram | R22 | 8.472B | NúcleoOEM+reserva/mapping/ownership; permanece cerrado sin admisión de placa. |
| FirmwareMuC5GHz | qtn_driver.qtn_ruby.0.bin, carrier retenido | 1.094.927B | Selección fijada por hash, no ejecutada en7.3. |
| FirmwareAuC5GHz | auc_driver.nomu.0.bin | 33.342B | Igual límite. |
| FirmwareDSP5GHz | rdsp_driver.0.bin | 246.244B | Igual límite. |
| Ethernet | qtn-topaz-emac-eth73, derivadoF352/MAC-init | 27.816B | eth1.91 y eth0.90 pasan GET/POST65536TLS1.2/1.3, por separado. |
| Firmwarepersistente conservado | F367r9, Linux5.10.260-openmitrastar-radiohw | No sumado a7.3 | Sigue en flash; toda campaña7.3 ha sidoRAM. |

El ABIv37.4.0.89 es el contrato Quantenna del port, no una versión upstream
de Linux ni prueba de aceptación del firmware por la radio.
Los19 módulos de2,4GHz incluyen crypto y framework; no sumarlos otra vez
a sus seis componentes principales. R20/R22 también necesitan módulosbase
del mismo kernel: todos deben reconstruirse con un único layout de paquetes.

Los tres carriers5GHz suman1.374.513B. No estaban incluidos en la medida
de capacidadv45; faltan además integración de servicios persistentes,
almacenamiento, controles/LED y recuperación. Esa medida no es un release.

## Sistema, seguridad y web

| Componente | Versión fijada | Bytes de archivo |
| --- | --- | ---: |
| BusyBox | 1.38.0, release de pruebas | 984.332 |
| uClibc-ng | 1.0.59, shared, EN/ES/UTF8 y atomics vía kernel | 534.536 |
| Loader uClibc | 1.0.59 | 25.572 |
| hostapd | 2.12, buildWPA2/WPA3/OWE/WPS | 628.288 |
| hostapd_cli | 2.12 | 42.252 |
| iw | 6.17 | 199.020 |
| Dropbear | 2026.94, PIEcorregido, key-only | 239.628 |
| wolfSSL | 5.9.4, perfil compartidoWPA/TLS | 946.612 |
| uhttpd | snapshot2026-10-19 ca796d7dec5697a2d1a7a42be79677f239b64282, MIMEwasmcorregido | 42.912 |
| libubox | snapshot2026-10-08 da2d205a5cf3e877c45a2eec488218cbaf452e7d | 50.496 |
| libustream-ssl | snapshot2026-07-08 cea28c5bc43ae80c3531c98f4e4dc67b7dcf0ebb | 17.904 |
| libjson_script | Del mismo libubox | 17.620 |
| libblobmsg_json | Del mismo libubox | 9.460 |
| json-c | 0.19 | 50.684 |
| libnl-tiny | snapshot2025-12-02 40493a655d8caa2ccf5206dde1e733abe2920432 | 26.152 |
| jshn | Del mismo libubox | 17.756 |
| LYOKO | UI existente de estiloMovistar; frontend.env/web-next.json fijados por hash | Recursosweb medidos1.288.201B |
| Toybox | 0.8.15, fuente adquirida | Sin build comparable; no instalado. |

TLS1.2/1.3 y SSH están probados físicamente. WPA3/OWE/WPS están compilados:
solo WPA2 tiene asociación y tráfico probado en esta campaña.
Los bytes de LYOKO incluyen fuentes, imágenes, CSS y JS; no versión de un
único ejecutable. Parte de la identidad visual aún muestraLinux5.10.
No se presenta este inventario como comprobación de las últimas releases
disponibles: son las versiones fijadas y construidas en el proyecto.

Herramientas de construcción: GCC15.2.0 build10504 y GNUbinutils2.45.1.
SquashFS es formato4.0, XZ; el mksquashfs utilizado es4.6.1 del25mar2023,
una herramienta de host, no un daemon instalado en el HGW.

## Doom

Motor atribuido a ChocolateDoom3.0.0/Cloudflare, fuentecommit
65e0d3ae2ffa604155eebd96ed40da6567bd08f4; binarioproveedorcommit
e892222b66fd943bf196f285292aa15b98d89a5b. ParcheOPLr3 para música.
La correspondencia exacta del binario a una reconstrucción de fuente permanece
como límite de procedencia. Episodio originalsharewareDoom1.9.

| Archivo | Bytes |
| --- | ---: |
| doom19s.zip: distribución originalDOS completa | 2.450.688 |
| chocolate-doom.wasm: motor con reparaciónOPL | 2.291.176 |
| doom-wasm-source.tar.gz: fuentes | 913.704 |
| chocolate-doom.js: glue de navegador | 276.666 |
| fflate.js | 32.665 |
| GPL-2.0.txt | 17.895 |
| index.html: interfaz/controles | 8.969 |
| upstream-engine.txt | 1.469 |
| source-equivalent.patch | 1.228 |
| fflate-LICENSE.txt | 1.069 |
| PROVENANCE.json | 803 |
| Total11archivos | 5.996.332 |

El motor no ocupa6MB: esa cifra suma el paquete entero. El WAD extraído
deZIP tiene4.196.020B y XZ independiente1.360.580B; WASM se comprime
independientemente a500.048B. Son medidas de alternativas de embalaje, no
un paquete nuevo ni una suma válida del SquashFS final. No se ha retirado
ZIPoriginal/fuentes/música/licencias. Se aparca su optimización para priorizarradios.
Doom pasa en navegador HTTPS, movimiento/disparo/táctil y PCM con música
activada; el juego ejecutaencliente, el HGW sirve todos los assets.

## Tamaño conjunto y flash

Composiciónv45 medida:14.511.379B sin compresión. Incluye raízdiagnóstica,
Doom11archivos y22 módulosQuantennaR22 como medida de capacidad.

| Grupo | Bytes sin compresión |
| --- | ---: |
| Doom completo | 5.996.332 |
| Bibliotecas y firmware2,4GHz/regdb | 1.718.287 |
| 22módulos5GHz después de retirar debug | 1.643.172 |
| 19módulos2,4GHz/crypto después de retirar debug | 1.586.936 |
| WebLYOKO y recursos | 1.288.201 |
| Servicios y herramientas | 1.169.856 |
| BusyBox | 984.332 |
| Restoinit/config/API | 124.263 |

| Composición comprimida | Bytes |
| --- | ---: |
| SquashFSXZ, bloque128KiB | 7.483.392 |
| SquashFSXZ, bloque1MiB | 7.303.168 |
| Ventanarootfs histórica, offset0x180000 | 4.587.520 |
| Prefix total permitido para kernel+rootfs,0x5e0000 | 6.160.384 |
| Cola store a preservar,0x1c0000 | 1.835.008 |
| Particiónmtd4 física completa,0x7a0000 | 7.995.392 |

La raízv45 excede sola elprefixpermitido en1.142.784B, antes delkernel
y de añadircarriers5GHz ausentes. Sobrelaventanarootfshistórica faltan
2.715.648B. Movereloffsetpor sísolono soluciona ese exceso.
Esta es una medida de capacidad; sus módulos no forman una imagen con ABI
común ni servicios persistentescompletos. NO_GO paraflash.

## Prioridad de continuación

1. 2,4GHz: integrar las correcciones ya probadas en un artefacto reproducible
   y repetir asociación/tráfico/soak tras cualquier cambio de ABI.
2. 5GHz: admisión/reserva de placa SRAM, mapping CPU/bus y ciclo de vidaTQE;
   cargar el conjunto común y demostrar SSID,WPA2,tráfico y estabilidad.
3. Mantener ambosEthernet/HTTPS/SSH/LYOKO y posteriormente resolver tamaño,
   persistencia y recuperación antes delflash.

Fuentes de evidencia: documentos y recibos físicos bajo
outputs/rea/movistar-port-20261022T1327175411798Z; inventariov45 en
/home/rea/openmitrastar-linux73-20261022T135100Z/complete-rootfs-fit-v45.
R22: outputs/rea/linux73-typed-sram-dma-r22-pair-receipt-20261023T042500Z-r1.
Doom: outputs/doom/linux73-https-browser-mime-v43.
