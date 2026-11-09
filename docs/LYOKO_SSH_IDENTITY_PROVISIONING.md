# Lyoko SSH Identity Provisioning

Fecha: 2026-09-01

## Problema

F170-F188 contienen una clave privada Dropbear dentro del SquashFS. Eso ofrece
una identidad estable, pero no es aceptable para una imagen redistribuible:
varias unidades podrian compartir la misma clave privada.

F190 elimina esa clave. Si no encuentra una identidad provisionada genera una
clave Ed25519 en `/run`, por lo que SSH funciona pero la huella cambia tras un
cold boot. F190 no es apta para release mientras esa limitacion permanezca.

## Destino Persistente

La identidad definitiva debe vivir en `lyoko_store`, dentro del espacio libre
de `mtd4/linux_live`, nunca en `mtd5/data`.

Requisitos previos:

1. Probar en hardware el mapa read-only F180/F182.
2. Confirmar que el rango no solapa kernel, SquashFS ni mtd5.
3. Crear un filesystem para NOR con limites de desgaste y montaje `nodev`,
   `nosuid`, `noexec`.
4. Generar la clave en tmpfs despues del gate de entropia.
5. Escribir `host_key.new`, sincronizar, verificar con `dropbearkey -y` y
   renombrar atomicamente.
6. Remontar el store como solo lectura durante operacion normal.
7. Publicar unicamente fingerprint y estado mediante `/api/v1/ssh`.

## Estados

- `persisted`: identidad unica verificada en `lyoko_store`.
- `ephemeral`: identidad generada en `/run`; cambiara tras cold boot.
- `failed`: la clave no pudo generarse o validarse; Dropbear no arranca.

## Migracion

El primer firmware con store certificado debe generar una identidad nueva por
dispositivo. El operador aceptara una unica rotacion de fingerprint. No se
copiara la antigua clave privada embebida a una imagen publica ni a logs.

