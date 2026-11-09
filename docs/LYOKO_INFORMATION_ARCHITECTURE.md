# Lyoko Information Architecture

Fecha: 2026-09-01

## Principios

- Una sola aplicacion y una sola jerarquia de paginas.
- Los modos Basico, Avanzado y Desarrollador cambian profundidad, no duplican funciones.
- Todo control depende del registro de capacidades y de un backend real.
- Cada dato indica su procedencia: emulador, candidato offline o router fisico.
- Las acciones mutables siguen `validate -> stage -> apply -> verify -> commit/rollback`.
- PSK, contrasenas, claves privadas, calibracion y MAC completas nunca se devuelven.

## Shell

La interfaz usa sidebar en escritorio y drawer en movil. El encabezado muestra:

- Lyoko y modelo HGW-500BNA-QCv2.
- origen del runtime;
- estado de conexion;
- version y build ID del frontend;
- cambios pendientes y sesion.

## Sitemap

| Dominio | Basico | Avanzado | Desarrollador |
|---|---|---|---|
| Inicio | Salud, radios, clientes, alarmas | Causas y cambios pendientes | Fuentes, timestamps y JSON |
| Mi red | Topologia y gestion | Bridge e interfaces | Contadores y tablas kernel |
| Wi-Fi | SSID, seguridad, canal | Multi-SSID, ACL, WPS, DFS | qdrv, rtlwifi, IRQ, NAPI, DMA |
| Servicios | Estado L2 | VLAN, multicast, IGMP | MDB, counters y trazas |
| Seguridad | Sesion y acceso | SSH, PMF, auditoria | Politicas y diagnostico redactado |
| Sistema | Version y reinicio | Backup, restore y paquetes | Slots, manifests y recovery |
| Diagnostico | Pruebas guiadas | Logs y soporte | EMAC, TQE, HBM, FWT y raw JSON |
| Ayuda | Explicaciones simples | Riesgo y recuperacion | Contratos y evidencia |

## Navegacion Y Estado

- Las rutas son estables y recuperables mediante hash o History API.
- Cada pagina conserva foco, breadcrumb y titulo unico.
- Una API que falla degrada solo su panel.
- Los controles `blocked`, `unsupported` o `certification_required` permanecen
  visibles cuando aportan contexto, pero deshabilitados y con causa.
- El modo nunca eleva permisos: solo cambia la cantidad de informacion visible.

## Primera Migracion

1. Resolver identidad y procedencia del frontend.
2. Introducir shell navegable manteniendo los paneles actuales.
3. Migrar Inicio, Wi-Fi basico y clientes.
4. Migrar sistema, paquetes y diagnostico.
5. Incorporar funciones OEM avanzadas solo tras backend y gate fisico.

