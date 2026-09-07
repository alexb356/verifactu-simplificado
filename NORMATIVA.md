# Normativa Verifactu — fuentes y requisitos vigentes (consultado 07/09/2026... nota: fechas de búsqueda pueden diferir del calendario real, ver más abajo)

## Marco legal
- **Real Decreto 1007/2023, de 5 de diciembre** (BOE-A-2023-24840): Reglamento de requisitos de los Sistemas Informáticos de Facturación (SIF/RRSIF). https://www.boe.es/buscar/act.php?id=BOE-A-2023-24840
- **Orden HAC/1177/2024, de 17 de octubre** (BOE-A-2024-22138): especificaciones técnicas, formato del registro de facturación y del código QR. https://www.boe.es/diario_boe/txt.php?id=BOE-A-2024-22138
- **Real Decreto-ley 15/2025** (BOE 3/dic/2025): segundo aplazamiento del calendario de entrada en vigor.
- Base antifraude: Ley 11/2021 de medidas de prevención y lucha contra el fraude fiscal (introduce art. 201 bis LGT, sanciones).

## Calendario de obligatoriedad (vigente según el RDL 15/2025)
| Colectivo | Fecha límite |
|---|---|
| Empresas (Impuesto sobre Sociedades) | 1 enero 2027 |
| Autónomos y resto de obligados | **1 julio 2027** |
| Fabricantes/distribuidores de software de facturación | ya obligatorio desde 29/07/2025 (declaración responsable) |

> El calendario se ha aplazado dos veces (originalmente 2025, luego 2026, ahora 2027). El contenido técnico del reglamento NO cambia, solo la fecha de exigibilidad. Fuente: Grant Thornton (03/12/2025), grupoalbatros.org, technovapartners.com.

## Requisitos técnicos exigidos al software
1. **Registro de facturación de alta** por cada factura emitida, y **registro de anulación** si se rectifica/anula.
2. **Hash encadenado (SHA-256)**: cada registro incluye el hash del registro anterior como parte de los datos que se hashean, formando una cadena inmutable. El primer registro de la serie encadena con un valor inicial (huella "nula"/vacía) según especificación AEAT.
3. **Código QR** en cada factura:
   - Tamaño entre 30×30 y 40×40 mm.
   - Norma ISO/IEC 18004, nivel de corrección de errores **M**.
   - Ubicación: preferentemente al principio de la factura, visible y diferenciado.
   - Texto obligatorio encima: **"QR tributario"**.
   - En modo VERI*FACTU, debajo del QR: **"Factura verificable en la sede electrónica de la AEAT"** o **"VERI\*FACTU"**.
   - Contenido del QR: URL de verificación de la AEAT con 4 parámetros obligatorios:
     `https://www2.agenciatributaria.gob.es/wlpl/TIKE-CONT/ValidarQR?nif={NIF}&numserie={SERIE-NUM}&fecha={DD-MM-AAAA}&importe={TOTAL}`
     - `nif`: NIF del emisor (9 caracteres)
     - `numserie`: serie+número de factura (máx 60 caracteres ASCII 32-126, URL-encoded)
     - `fecha`: DD-MM-AAAA
     - `importe`: importe total con "." como separador decimal (máx 12 dígitos enteros + 2 decimales)
   - (Un 5º parámetro `formato=json` puede añadirse para respuesta JSON, pero no forma parte del QR).
4. **Dos modalidades de sistema**:
   - **VERI\*FACTU** (verificable): el software envía cada registro a la AEAT en tiempo real/casi real. A cambio, se exime de firma electrónica y de mantener un "registro de eventos".
   - **No-Verifactu**: no se envía nada en el momento, pero exige firma electrónica de cada registro y mantenimiento de un registro de eventos del sistema.
5. Los registros deben ser **íntegros, conservados, accesibles, legibles, trazables e inalterables**.
6. Sanción: hasta **50.000 €/ejercicio** para quien use software no conforme (no hace falta probar fraude); hasta 150.000 €/ejercicio para el fabricante.

## Decisiones de diseño tomadas para el MVP (a revisar por el usuario)
- **Modalidad elegida: NO-Verifactu (modo "verificable pero sin envío automático SOAP a la AEAT")** simplificado: el MVP genera el registro de alta, el hash encadenado y el QR conforme al formato exigido, pero **NO implementa el envío SOAP/XML firmado a la sede electrónica de la AEAT** (esto requiere certificado digital del cliente, credencial que no tenemos y que decide el usuario final, no yo). Esto es una limitación deliberada documentada en RESUMEN.md, no un incumplimiento silencioso.
- Dado que la fecha límite real es **julio 2027**, hay margen; se documenta para que el usuario decida si prioriza terminar la integración con AEAT antes de vender el producto como "100% Verifactu compliant" — hoy debe venderse como "preparado para Verifactu, en modalidad sin remisión automática" hasta añadir el envío SOAP con certificado digital.
- **Duda a revisar por el usuario**: si se quiere ofrecer el envío real a AEAT (modalidad VERI*FACTU con transmisión), habrá que integrar el servicio SOAP/REST de la AEAT y gestionar certificados digitales de cada cliente — esto es un desarrollo adicional no cubierto por este MVP.
