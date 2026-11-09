# Lyoko Design System

Fecha: 2026-09-01

## Objetivo

Interfaz local ligera para un appliance ARC700 con aproximadamente 23 MiB de
RAM disponible. No usa CDN, fuentes remotas ni frameworks pesados.

## Tokens

| Token | Uso |
|---|---|
| `--ink` | Texto principal |
| `--muted` | Texto secundario |
| `--surface` | Fondo de controles y datos |
| `--line` | Separadores y foco estructural |
| `--brand` | Accion primaria Movistar/Lyoko |
| `--green` | Disponible o verificado |
| `--amber` | Experimental o requiere atencion |
| `--red` | Bloqueado, fallo o destructivo |

## Componentes

- App shell con sidebar/drawer, header y area principal.
- Breadcrumb, busqueda local y selector de profundidad.
- Status pill con texto e icono; nunca solo color.
- Data grid para pares etiqueta/valor.
- Tabla responsive con alternativa apilada en movil.
- Formularios con valor actual no secreto, impacto y estado de staging.
- Dialogo de confirmacion para perdida de acceso o acciones destructivas.
- Toast con `role=status`; errores persistentes usan banner con foco.
- Capability badge: disponible, solo lectura, experimental, bloqueada,
  no soportada o pendiente de certificacion.

## Accesibilidad

- WCAG 2.2 AA, foco visible y orden DOM logico.
- Skip-link y landmarks de navegacion/contenido.
- Drawer, tabs y dialogos operables por teclado y con ARIA completa.
- 320 px sin overflow horizontal; zoom 200/400 por ciento.
- `prefers-reduced-motion` elimina transiciones no esenciales.
- Labels y errores quedan asociados al control correspondiente.

## Presupuesto

- HTML + CSS + JS inicial: objetivo menor de 64 KiB sin comprimir.
- Cero solicitudes remotas.
- Render progresivo y fallos parciales por panel.
- Polling adaptativo y suspendido cuando la pestaña no esta visible.
- El endpoint `/api/v1/frontend` prueba version, build ID, bytes y hashes.

