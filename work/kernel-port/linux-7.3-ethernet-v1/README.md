# Linux 7.3 Ethernet v1: resultado offline

> Public source snapshot. [Scope, provenance and verification](docs/PUBLIC_SNAPSHOT.md).

Kernel y EMAC compilan dos veces idénticos. OFFLINE PASS / NO_GO_HARDWARE.
DT Ethernet desactivado, módulo separado y PID1 BASIC sin comandos de red.
No RAS generado ni prueba física de esta variante. El hito BASIC físico sí
está aceptado; consultar PHYSICAL_BOOT_RESULT.json de la carpeta BASIC.

El candidato deriva de F374r3 y añade API7.3, hwirq/domain, gates19/20,
DMA-ranges, serialización RTNL del worker y quarantine de memoria si DMA
no se detiene. Reopen devuelve EIO; el timeout no libera buffers/rings.
Quarantine conserva memoria y no recupera un DMA bloqueado.

`candidate/manifest.json` conserva identidad de las fuentes generadas.
`prepare.py` es el generador del workspace original y requiere su baseline
F374r3 local. Para reproducir el build en un clon privado, usar el candidato
sellado incluido; no hace falta ejecutar prepare.py. Las fuentes originales
y Linux5.10 se conservan en sus ramas anteriores.

```sh
python3 build.py --archive /path/linux-7.3.tar.xz --toolchain /path/arc700 --candidate "$PWD/candidate" --output /path/new-build
python3 test_lifecycle.py --candidate "$PWD/candidate" --kernel-source /path/new-build/source/linux-7.3 --output /path/new-lifecycle
python3 test_rx_restart.py --candidate "$PWD/candidate" --kernel-source /path/new-build/source/linux-7.3 --output /path/new-rx-fixture
python3 audit.py --candidate "$PWD/candidate" --source /path/new-build/source/linux-7.3 --build /path/new-build --archive /path/linux-7.3.tar.xz --toolchain /path/arc700 --output /path/new-audit
```

Todos los outputs deben ser nuevos. La opción --composed-source permite
reutilizar sólo un árbol ya verificado; el auditor final coteja todos sus
archivos con upstream y el overlay, y rechaza adiciones inesperadas.
build.py exige CPU750D/8KiB/UP/PREEMPT_NONE,80importsresueltos y ausencia
deSWAPE/LLOCK/SCOND. Verifica identidad doble; audit.py extrae DT del ELF.

Resultado: kernel4455148bytes SHA
3c173455469c84ed46664a9f3b36b80dfd112ab77b77cc1f755413cbb2a6e19a;
módulo25808bytes SHA
067f040165348edcdc3d125cf284f6921802cc3590909df9fe3772c0b9adf798.
18casos/18340checks lifecycle,60casos/48606checks RX,4mutacionesrechazadas,
95978archivosupstream cotejados y DT incrustado idéntico. Pruebas simuladas
no demuestran hardware, tráfico, stop/reopen real, rollback ni release.

Falta initramfs de diagnóstico, identidad del propietario local, DT activo,
integración del módulo y RAS con contrato propio. Los caminos completos
worker/probe/remove y recursos compartidos necesitan pruebas adicionales.
No abrir UART/reiniciar/flash usando este resultado offline como autoridad.
