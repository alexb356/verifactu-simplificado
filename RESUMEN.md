# RESUMEN — Proyecto 1: Facturación Verifactu simplificada

## Qué se ha construido
MVP funcional en Flask (backend) + SQLite + frontend HTML/JS servido por el propio Flask:
- Alta de clientes (nombre, NIF, dirección, email) con validación básica.
- Emisión de facturas con IVA y retención IRPF configurables, cálculo automático de base/cuota/retención/total.
- **Registro de facturación de alta** con **hash SHA-256 encadenado** (cada factura incluye el hash de la anterior, cadena arranca en un hash "0"×64).
- **Código QR tributario** conforme a Orden HAC/1177/2024: tamaño 35mm (dentro del rango 30-40mm), nivel de corrección M, contenido = URL de verificación AEAT con los 4 parámetros obligatorios (nif, numserie, fecha, importe), texto "QR tributario" encima y leyenda VERI*FACTU debajo.
- Generación de PDF de factura con el QR embebido.
- Integración de Stripe **en modo TEST exclusivamente** (PaymentIntent + confirmación simulada del webhook) para cobrar la cuota de suscripción del propio SaaS.
- 10 tests automatizados (pytest) cubriendo alta de cliente, validaciones, emisión de factura, encadenamiento de hash, generación de QR/PDF, y flujo de pago en Stripe test — todos pasan.

## Decisiones de negocio/normativas tomadas y por qué
1. **Modalidad "no-Verifactu con QR" en vez de "VERI*FACTU con envío SOAP a la AEAT"**: implementar el envío real requiere un certificado digital del cliente final (autónomo) que no tengo y que debe aportar el usuario/cliente final, no algo que yo pueda generar. Documentado en NORMATIVA.md. **Esto significa que el producto tal cual NO cumple al 100% la modalidad de remisión en tiempo real** — cumple el formato de registro, hash y QR, pero el envío se deja como trabajo futuro.
2. **Fecha límite real usada**: 1 julio 2027 para autónomos (RD-ley 15/2025, segundo aplazamiento). Hay margen de tiempo — no es urgencia inmediata, pero la obligación de fondo no desaparece.
3. El hash se calcula sobre un payload simplificado (NIF|numserie|fecha|total|hash_anterior) en vez del XML completo del "registro de facturación" que exige la especificación técnica oficial (que incluye más campos y su propio esquema XSD publicado por la AEAT). Es una simplificación razonable para el MVP pero **no es literalmente el esquema XML oficial**.
4. Stripe se usa para cobrar la **suscripción del propio SaaS** (no la factura del cliente final del autónomo), en modo TEST únicamente. Nunca se ha usado ni se usará una clave sk_live.

## Qué debe hacer el usuario para pasar a producción
- Conseguir cuenta Stripe real y sustituir las claves de `.env` por las de producción (yo no las tengo ni las voy a generar).
- Decidir si se quiere ofrecer la modalidad VERI*FACTU con envío real a AEAT: eso exige integrar el servicio SOAP/XML de la AEAT y gestionar certificados digitales por cliente — desarrollo adicional no incluido aquí.
- Revisión legal/fiscal recomendada: aunque he seguido las fuentes oficiales (BOE, AEAT, Orden HAC/1177/2024), un asesor fiscal debería validar el formato exacto del XML del registro de facturación antes de vender esto como "100% conforme".
- Contratar dominio y hosting (por ahora corre solo en local).
- Migrar de SQLite a una base de datos más robusta (Postgres) si se espera más de un usuario concurrente.

## Riesgos / dudas a revisar
- **[DUDA NORMATIVA]** El hash simplificado no sigue el XSD exacto que publica la AEAT para el "registro de facturación" (es un JSON/XML con muchos más campos: tipo de factura, desglose por tipo impositivo, etc.). Antes de comercializar como "Verifactu compliant", habría que implementar el esquema oficial completo. Recomiendo que un especialista en la normativa lo revise.
- El NIF de cliente se valida solo por longitud (8-12 caracteres), no se verifica el dígito de control NIF/NIE/CIF — mejora pendiente.
- No hay autenticación de usuarios (multi-tenant) todavía: el MVP asume un solo emisor (variable de entorno EMISOR_NIF). Para vender a varios autónomos hace falta añadir login y aislar datos por cuenta.

## Revisión de bugs post-entrega (07/09/2026)
Se hizo una pasada de QA sobre el código antes de publicarlo: pyflakes (sin avisos), y pruebas manuales de casos límite (redondeos, IRPF>IVA, cliente_id inválido, PDF/QR con datos reales). No se encontraron bugs funcionales en este proyecto. Se modernizó `Cliente.query.get(...)` (deprecado en SQLAlchemy 2.0) a `db.session.get(...)`. Se corrigió además una vulnerabilidad de **HTML injection** en el frontend: nombre/NIF de cliente y datos de factura se insertaban sin escapar vía `innerHTML`; ahora se escapan con una función `escapeHtml()`.
