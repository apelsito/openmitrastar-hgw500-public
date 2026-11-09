# Fuentes de la versión instalada

SOURCE_INPUTS.json liga la imagen R2 a la receta actual, el directorio de
fuentes ARC/Realtek/Ethernet, configuración, herramientas y archivos públicos
del sistema empaquetado. Se han leído los registros de dependencias de la
compilación existente; no se ha compilado ni probado nada de nuevo.

La imagen privada, las claves por dispositivo y sus directorios permanecen
en sus ubicaciones originales. Las claves y credenciales no aparecen como
contenido ni hashes en este registro.

Para reconstruir localmente en REA-Linux, la receta es:

python3 /workspace/user-home/Desktop/MitraStar/work/kernel-port/linux-7.3-doom-open-persistent-r2/build.py --output /home/rea/openmitrastar-linux73-20261022T135100Z/NEW-ABSENT-OUTPUT-DIRECTORY

El destino debe ser nuevo. El builder no accede al router. Requiere los
contextos padre y el root ya preparados. El registro no constituye una
entrega portable ni una compilación limpia desde un checkout vacío.

No ejecutar el instalador por un STOP antiguo. Para el estado programado
actual consultar ../linux73-doom-open-r2-programmed-20261023-v1/manifest.json.
5GHz, configuración editable persistente y validación física completa
siguen pendientes. No se han autorizado nuevas operaciones sobre el HGW.
