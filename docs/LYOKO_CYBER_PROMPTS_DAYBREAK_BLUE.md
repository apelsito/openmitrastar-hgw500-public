# Prompts de ciberseguridad para OpenMitraStar / Lyoko

Obtenidos el 11 de septiembre de 2026 en la cuenta Plus del propietario,
con GPT-5.6 Sol seleccionado y acceso Daybreak Blue confirmado por la cuenta.
Conversación privada: https://chatgpt.com/c/6aa3c57b-0000-83eb-a6d0-8a0c473eb269

La comprobación de acceso devolvió `status=granted`, `programs=[Daybreak Blue]`
y `stale=false` a las 09:05:11 UTC. La página de la cuenta también mostró
`Your identity is verified and your Daybreak access is now active`.
Esto acredita el acceso de la cuenta; la interfaz no expone una atestación
de enrutamiento Daybreak para cada respuesta.

Estos son prompts para una revisión futura, no resultados de una auditoría.
Se conserva el contenido de los cuatro prompts recibidos, corrigiendo únicamente
el error tipográfico `archivoínea` por `archivo:línea` y el formato Markdown.
Sustituir los marcadores de rutas antes de usarlos. Las instrucciones vigentes
del proyecto y la autorización concreta prevalecen sobre estas plantillas.

## 1. UI, CGI y API: autenticación, sesiones e inyección

```text
Actúa como auditor de seguridad defensiva sobre OpenMitraStar/Lyoko, router propio HGW-500BNA-QCv2 A2 con Linux 5.10, UI local y CGI/API. Analiza exclusivamente el código y artefactos suministrados bajo <RUTA_REPO> y <ARTEFACTOS>. Revisa autenticación, autorización, sesiones/cookies, CSRF, XSS, validación de entrada, command injection y exposición de secretos. Para cada hallazgo exige archivo:línea, flujo entrada→sink, hipótesis, precondiciones, alcance y límites. No inventes vulnerabilidades ni declares explotabilidad sin evidencia.

Cuando sea posible, demuestra impacto sólo mediante prueba controlada/local, payload inocuo y reversible, sin flashear, reiniciar ni modificar radios. No solicites contraseñas, claves, MAC de clientes ni datos de calibración. Firmware OEM y particiones de identidad/calibración son intocables.

Para cada defecto confirmado: causa raíz, severidad razonada, parche mínimo y prueba de regresión. Distingue claramente CONFIRMADO / HIPÓTESIS / NO VERIFICADO.

PASS: controles efectivos demostrados o defecto corregido con regresión verde.
FAIL: ruta reproducible hacia bypass, ejecución, modificación no autorizada o exposición sensible.

Entrega una matriz componente → evidencia → riesgo → prueba → parche → regresión, incluyendo limitaciones explícitas.
```

## 2. Seguridad e integridad de actualización de firmware

```text
Revisa defensivamente el mecanismo de actualización de firmware de OpenMitraStar/Lyoko y sus verificadores usando <RUTA_UPDATER>, <IMAGEN_CANDIDATA> y <METADATOS>. Analiza autenticidad, integridad, hashes, tamaños, parsing de metadatos, validación de destino, errores parciales, TOCTOU, downgrade/rollback accidental y comprobaciones previas al write. Toda conclusión debe citar archivo:línea, hipótesis, precondiciones y límites; no inventes resultados.

Durante esta auditoría queda prohibido flashear, reiniciar o cambiar cualquier radio. Firmware OEM y particiones de identidad/calibración deben permanecer protegidos. El único destino admisible para una futura instalación revisada es mtd4/linux_live, y sólo con artefacto exacto, hash esperado, backup verificable, contrato de arranque y procedimiento de recuperación previamente definidos.

Usa tests offline/mocks para demostrar impacto controlado: imagen truncada, hash incorrecto, destino inválido o metadatos inconsistentes, sin tocar flash real.

Para cada problema confirmado proporciona parche mínimo y regresión reproducible.

PASS: entradas inválidas fallan cerradas antes del write y destino/artefacto quedan inequívocamente ligados.
FAIL: datos manipulados pueden superar verificadores o alcanzar una operación destructiva.

No atribuyas arranque en frío exitoso a pruebas offline.
```

## 3. Parsers y drivers C: sanitizers y fuzzing offline

```text
Audita los parsers y drivers C de OpenMitraStar/Lyoko ubicados en <RUTAS_C>, priorizando límites de buffers, integer overflow/underflow, signedness, longitudes, lifetime, use-after-free, double-free, estados no inicializados y parsers de datos externos. Construye primero el flujo real desde entrada hasta operación sensible y cita siempre archivo:línea. Separa CONFIRMADO, HIPÓTESIS y NO ALCANZADO; no inventes crashes ni vulnerabilidades.

Diseña pruebas offline, deterministas y reproducibles mediante unit tests, harnesses mínimos, ASan/UBSan cuando la toolchain lo permita y fuzzing local sobre corpus <CORPUS>. Conserva seed, comando, flags, versión del compilador y caso mínimo que reproduzca cualquier fallo. No interactúes con radios reales, flash ni particiones OEM/identidad/calibración; tampoco reinicies el router.

Para cada crash confirmado explica causa raíz, entrada mínima, impacto controlado, parche mínimo y test de regresión. No extrapoles tests offline a arranque en frío, asociación de clientes, tráfico real ni conformidad RF.

PASS: corpus y casos límite terminan sin comportamiento indefinido y las invariantes quedan verificadas.
FAIL: sanitizer, assertion o test reproducible demuestra corrupción, acceso inválido o violación de invariantes.

Incluye límites de cobertura y código no ejercitado.
```

## 4. DFS, CAC y NOP: máquina de estados, concurrencia y UI

```text
Revisa la máquina de estados DFS/CAC/NOP de OpenMitraStar/Lyoko y su representación UI usando <RUTA_BACKEND>, <RUTA_UI> y <TEST_FIXTURES>. Modela explícitamente estados, eventos, transiciones, guards y fuentes de verdad. Cita archivo:línea para cada afirmación y prueba escenarios de concurrencia, eventos retrasados, datos obsoletos, reinicios lógicos simulados, pérdida del detector, errores del backend y recuperación parcial.

Trata backend_ready, contadores y temporizadores visuales únicamente como señales de UI: no demuestran que CAC haya terminado ni autorizan transmitir. La autorización deberá depender del estado regulatorio/backend realmente validado. No propongas desactivar, puentear o degradar detección de radar, DFS, CAC, NOP ni requisitos regulatorios.

Ejecuta sólo simulaciones/unit tests offline; ningún cambio de radio, reboot o flash. Para cada fallo confirmado aporta secuencia de eventos mínima, impacto controlado, causa raíz, parche mínimo y regresión determinista.

PASS: ninguna carrera, evento antiguo o pérdida del detector produce estado permisivo incorrecto.
FAIL: una secuencia reproducible permite que UI/backend indiquen disponibilidad o transmisión cuando las precondiciones regulatorias no están satisfechas.

No infieras conformidad RF, asociación o tráfico real desde estos tests.
```
