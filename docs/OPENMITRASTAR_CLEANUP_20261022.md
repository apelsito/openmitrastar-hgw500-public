# Limpieza local OpenMitraStar — 22 de octubre de 2026

Eliminados **23.18 GB** de archivos históricos y duplicados (26,282 archivos).

| Unidad | Archivos eliminados | GB de archivos |
|---|---:|---:|
| D: | 3,039 | 0.15 |
| C: | 23,243 | 23.03 |

Conservados: firmware OEM, volcados originales, identidad/calibración, fuentes, herramientas y toolchain, recuperación exacta F314/F365, firmware F367r9 registrado como instalado, candidatos F369/F371/F372 y sus dependencias F364r3/F367r8. Se conserva la entrega técnica actual.

Se han verificado 3,091 archivos fijados sin cambios y 13,189 copias canónicas. Las 8 imágenes completas conservadas pasan su contrato Bootbase offline. El contrato F372 vuelve a pasar con NO_GO físico.

Los registros antiguos de resultados y manifiestos se conservan como evidencia histórica. Sus rutas pueden referirse a binarios eliminados; la existencia de un manifiesto no acredita que el firmware siga disponible.

No se ha accedido al router, abierto UART, reiniciado, flasheado ni cambiado su configuración. Tampoco se ha modificado el desarrollo activo ni los proyectos de otros routers.

El espacio físico recuperado puede diferir de los bytes de archivo por compresión, enlaces duros y compilaciones simultáneas. El borrado principal aumentó el espacio libre de C de 13,79 GB a 35,03 GB; D tuvo escrituras simultáneas del desarrollo.

## Imágenes conservadas

| Imagen | Bytes | Motivo |
|---|---:|---|
| f314-device-bound | 5,292,032 | Recuperación histórica exacta |
| f364r3-f363r2-lifetime-device-bound | 5,382,144 | Dependencia fijada de F365 |
| f365-f364r3-temperature-data-device-bound | 5,382,144 | Recuperación y driver activo en RAM según registros |
| f367r8-f365-mode-contract-device-bound | 5,468,160 | Dependencia fijada de F367r9 |
| f367r9-f365-transition-observation-device-bound | 5,468,160 | Firmware vigente según evidencia local de hoy |
| f369-f367r9-store38-quarantine-device-bound | 5,468,160 | Candidato de cuarentena |
| f371-f365-normal-start-compat-device-bound | 5,382,144 | Donante exacto de F372 |
| f372-f371-auc-tqe-observation-device-bound | 5,382,144 | Candidato actual de observación |

## Evidencia

- Resultado final: `/workspace/user-home\Desktop\MitraStar\outputs\cleanup\final-20261022T135408032744Z\result.json`
- Manifiesto de borrado: `/workspace/user-home\Desktop\MitraStar\outputs\cleanup\executed-20261022T134114956984Z\deleted-manifest.json`
- Duplicados y copias conservadas: `/workspace/user-home\Desktop\MitraStar\outputs\cleanup\duplicates-20261022T134632454589Z\plan.json`
- Auditoría histórica F314–F319: `/workspace/user-home\Desktop\MitraStar\outputs\cleanup\executed-20261022T134114956984Z\objective-audit.json`
