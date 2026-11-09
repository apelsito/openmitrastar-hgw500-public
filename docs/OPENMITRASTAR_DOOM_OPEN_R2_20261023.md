# OpenMitraStar: wanna play Doom

La red Wi-Fi **wanna play Doom** está abierta y guardada en la imagen R2
programada. La administración Movistar/LYOKO mantiene su contraseña.

| Acceso por Wi-Fi y Ethernet | Dirección |
| --- | --- |
| Movistar/LYOKO | https://192.168.1.90/ |
| Doom | https://192.168.1.90/Doom |

DHCP entrega direcciones 192.168.73.20–40 en Wi-Fi y una ruta específica
a 192.168.1.90 a través de 192.168.73.1. El juego no necesita Internet ni
descargas externas. Este perfil no comparte una conexión a Internet.

Imagen programada: 6.062.800 bytes, SHA-256
500b617b659f3b2c8ed075ed493f721ad112ef2fc6245df9422ec9462feab2b9.
La lectura de flash coincide byte a byte. Se conservaron las particiones
protegidas y el área de configuración. No se escribió bootenv.

El arranque desde la copia leída de flash confirmó kernel y PID1 exactos,
AP abierto ENABLED, DHCP y HTTPS automáticos. La comprobación final confirmó
login LYOKO en /, redirects de /Doom a /Doom/index.html, página de juego exacta
y rechazo403 de la API administrativa sin sesión.

El cliente real comprobó asociación abierta, DHCP y ambas rutas en
192.168.1.90 antes de programar R2. El propietario confirmó ejecución real
en iPhone; la dificultad de los controles táctiles queda como mejora futura.
Motor, música y datos del juego permanecen iguales a los ya probados.

Un encendido normal después de apagar se había demostrado con la imagen
anterior. No se ha repetido ese encendido con R2. La UART está cerrada y no
hay operación de escritura activa. 5GHz, configuración editable guardada
y pruebas de estabilidad/recuperación completas siguen pendientes.

- [Entrega y alcance](../outputs/releases/linux73-doom-open-r2-programmed-20261023-v1/manifest.json).
- [Guía](../outputs/releases/linux73-doom-open-r2-programmed-20261023-v1/LEEME.md).
- [Escritura y arranque](../outputs/rea/radio73-doom-open-r2-flash-physical-20261023-v1/result.json).
- [Conexión abierta y rutas](../outputs/rea/doom-open-client-common90-v3.json).

## Fuentes y reconstrucción local

El registro local de continuidad contiene 3.010 archivos de entrada del
kernel identificados en 1.452 registros de dependencias del compilador,
y 202 archivos públicos o enlaces del sistema empaquetado. También fija
la receta, las herramientas y la configuración con sus hashes.

Se creó leyendo los archivos existentes: no hubo nueva compilación,
prueba ni conexión al router. Describe los archivos presentes y sus
referencias de compilación; no acredita una reconstrucción limpia desde
un checkout vacío. Las claves y credenciales permanecen en sus ubicaciones
privadas y sus contenidos o hashes no se incluyen en este registro.

- [Entradas de construcción](../outputs/releases/linux73-doom-open-r2-source-inputs-20261023-v1/SOURCE_INPUTS.json).
- [Cómo reconstruir localmente](../outputs/releases/linux73-doom-open-r2-source-inputs-20261023-v1/REBUILD.md).
