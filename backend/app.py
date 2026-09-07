"""
MVP de facturación electrónica simplificada, preparada para Verifactu.

IMPORTANTE (ver NORMATIVA.md y RESUMEN.md):
- Este sistema implementa: registro de facturación de alta, hash encadenado SHA-256,
  y código QR conforme al formato exigido por la Orden HAC/1177/2024.
- NO implementa el envío SOAP/XML firmado a la sede electrónica de la AEAT (modalidad
  VERI*FACTU con remisión). Eso requiere certificado digital del cliente final.
- Fecha límite legal para autónomos: 1 julio 2027 (RD-ley 15/2025).
"""
import os
import hashlib
import io
from datetime import datetime, timezone
from urllib.parse import urlencode

from flask import Flask, request, jsonify, send_file, render_template
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv
import qrcode
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm

load_dotenv()

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("FLASK_SECRET_KEY", "dev-only-not-secure")
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///verifactu.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

AEAT_QR_BASE_URL = "https://www2.agenciatributaria.gob.es/wlpl/TIKE-CONT/ValidarQR"

# ---------------------------------------------------------------------------
# Modelos
# ---------------------------------------------------------------------------

class Cliente(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(200), nullable=False)
    nif = db.Column(db.String(20), nullable=False)
    direccion = db.Column(db.String(300))
    email = db.Column(db.String(200))

    def to_dict(self):
        return {"id": self.id, "nombre": self.nombre, "nif": self.nif,
                "direccion": self.direccion, "email": self.email}


class Factura(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    serie = db.Column(db.String(20), nullable=False, default="A")
    numero = db.Column(db.Integer, nullable=False)
    cliente_id = db.Column(db.Integer, db.ForeignKey("cliente.id"), nullable=False)
    concepto = db.Column(db.String(500), nullable=False)
    base_imponible = db.Column(db.Float, nullable=False)
    tipo_iva = db.Column(db.Float, nullable=False, default=21.0)
    tipo_irpf = db.Column(db.Float, nullable=False, default=0.0)
    fecha_emision = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    hash_registro = db.Column(db.String(64), nullable=False)
    hash_anterior = db.Column(db.String(64), nullable=False)
    anulada = db.Column(db.Boolean, default=False)
    pagada = db.Column(db.Boolean, default=False)
    stripe_payment_intent = db.Column(db.String(120))

    cliente = db.relationship("Cliente")

    @property
    def numserie(self):
        return f"{self.serie}-{self.numero:06d}"

    @property
    def cuota_iva(self):
        return round(self.base_imponible * self.tipo_iva / 100, 2)

    @property
    def retencion_irpf(self):
        return round(self.base_imponible * self.tipo_irpf / 100, 2)

    @property
    def total(self):
        return round(self.base_imponible + self.cuota_iva - self.retencion_irpf, 2)

    def to_dict(self):
        return {
            "id": self.id,
            "numserie": self.numserie,
            "cliente": self.cliente.to_dict() if self.cliente else None,
            "concepto": self.concepto,
            "base_imponible": self.base_imponible,
            "tipo_iva": self.tipo_iva,
            "cuota_iva": self.cuota_iva,
            "tipo_irpf": self.tipo_irpf,
            "retencion_irpf": self.retencion_irpf,
            "total": self.total,
            "fecha_emision": self.fecha_emision.strftime("%d-%m-%Y"),
            "hash_registro": self.hash_registro,
            "hash_anterior": self.hash_anterior,
            "anulada": self.anulada,
            "pagada": self.pagada,
        }


# ---------------------------------------------------------------------------
# Lógica Verifactu: hash encadenado + QR
# ---------------------------------------------------------------------------

HASH_INICIAL = "0" * 64  # huella inicial de la cadena para la primera factura


def calcular_hash_registro(emisor_nif, numserie, fecha_str, total, hash_anterior):
    """
    Genera el hash SHA-256 del registro de facturación, encadenado con el hash
    del registro anterior, siguiendo el principio de encadenamiento exigido por
    el Reglamento (RD 1007/2023 / Orden HAC/1177/2024).
    """
    payload = "|".join([
        emisor_nif, numserie, fecha_str, f"{total:.2f}", hash_anterior,
    ])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def construir_url_qr(nif_emisor, numserie, fecha_str, total):
    """Construye la URL de verificación AEAT con los 4 parámetros obligatorios."""
    params = {
        "nif": nif_emisor,
        "numserie": numserie,
        "fecha": fecha_str,
        "importe": f"{total:.2f}",
    }
    return f"{AEAT_QR_BASE_URL}?{urlencode(params)}"


def generar_qr_png_bytes(url):
    qr = qrcode.QRCode(
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=6,
        border=2,
    )
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


def ultimo_hash():
    ultima = Factura.query.order_by(Factura.id.desc()).first()
    return ultima.hash_registro if ultima else HASH_INICIAL


def siguiente_numero(serie):
    ultima = Factura.query.filter_by(serie=serie).order_by(Factura.numero.desc()).first()
    return (ultima.numero + 1) if ultima else 1


# ---------------------------------------------------------------------------
# Rutas API
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/clientes", methods=["GET", "POST"])
def clientes():
    if request.method == "POST":
        data = request.get_json(force=True, silent=True) or {}
        nombre = (data.get("nombre") or "").strip()
        nif = (data.get("nif") or "").strip().upper()
        if not nombre or not nif:
            return jsonify({"error": "nombre y nif son obligatorios"}), 400
        if len(nif) < 8 or len(nif) > 12:
            return jsonify({"error": "NIF/CIF con formato inválido"}), 400
        cliente = Cliente(
            nombre=nombre,
            nif=nif,
            direccion=(data.get("direccion") or "").strip()[:300],
            email=(data.get("email") or "").strip()[:200],
        )
        db.session.add(cliente)
        db.session.commit()
        return jsonify(cliente.to_dict()), 201
    return jsonify([c.to_dict() for c in Cliente.query.order_by(Cliente.id.desc()).all()])


@app.route("/api/facturas", methods=["GET", "POST"])
def facturas():
    if request.method == "POST":
        data = request.get_json(force=True, silent=True) or {}
        cliente_id = data.get("cliente_id")
        concepto = (data.get("concepto") or "").strip()
        base_imponible = data.get("base_imponible")
        tipo_iva = data.get("tipo_iva", 21.0)
        tipo_irpf = data.get("tipo_irpf", 0.0)

        if not cliente_id or not concepto:
            return jsonify({"error": "cliente_id y concepto son obligatorios"}), 400
        try:
            base_imponible = float(base_imponible)
        except (TypeError, ValueError):
            return jsonify({"error": "base_imponible debe ser numérica"}), 400
        if base_imponible <= 0:
            return jsonify({"error": "base_imponible debe ser positiva"}), 400
        try:
            tipo_iva = float(tipo_iva)
            tipo_irpf = float(tipo_irpf)
        except (TypeError, ValueError):
            return jsonify({"error": "tipo_iva/tipo_irpf deben ser numéricos"}), 400
        if not (0 <= tipo_iva <= 100) or not (0 <= tipo_irpf <= 100):
            return jsonify({"error": "tipos de IVA/IRPF fuera de rango"}), 400

        cliente = Cliente.query.get(cliente_id)
        if not cliente:
            return jsonify({"error": "cliente no encontrado"}), 404

        emisor_nif = os.environ.get("EMISOR_NIF", "B00000000")
        serie = "A"
        numero = siguiente_numero(serie)
        fecha = datetime.now(timezone.utc)
        fecha_str = fecha.strftime("%d-%m-%Y")
        numserie = f"{serie}-{numero:06d}"

        base_r = round(base_imponible, 2)
        cuota_iva = round(base_r * tipo_iva / 100, 2)
        retencion = round(base_r * tipo_irpf / 100, 2)
        total = round(base_r + cuota_iva - retencion, 2)

        hash_anterior = ultimo_hash()
        hash_registro = calcular_hash_registro(emisor_nif, numserie, fecha_str, total, hash_anterior)

        factura = Factura(
            serie=serie, numero=numero, cliente_id=cliente.id, concepto=concepto,
            base_imponible=base_r, tipo_iva=tipo_iva, tipo_irpf=tipo_irpf,
            fecha_emision=fecha, hash_registro=hash_registro, hash_anterior=hash_anterior,
        )
        db.session.add(factura)
        db.session.commit()
        return jsonify(factura.to_dict()), 201

    return jsonify([f.to_dict() for f in Factura.query.order_by(Factura.id.desc()).all()])


@app.route("/api/facturas/<int:factura_id>/qr.png")
def factura_qr(factura_id):
    factura = Factura.query.get_or_404(factura_id)
    emisor_nif = os.environ.get("EMISOR_NIF", "B00000000")
    url = construir_url_qr(emisor_nif, factura.numserie, factura.fecha_emision.strftime("%d-%m-%Y"), factura.total)
    buf = generar_qr_png_bytes(url)
    return send_file(buf, mimetype="image/png")


@app.route("/api/facturas/<int:factura_id>/pdf")
def factura_pdf(factura_id):
    factura = Factura.query.get_or_404(factura_id)
    emisor_nif = os.environ.get("EMISOR_NIF", "B00000000")
    emisor_nombre = os.environ.get("EMISOR_NOMBRE", "Mi Negocio")
    url_qr = construir_url_qr(emisor_nif, factura.numserie, factura.fecha_emision.strftime("%d-%m-%Y"), factura.total)
    qr_buf = generar_qr_png_bytes(url_qr)

    pdf_buf = io.BytesIO()
    c = canvas.Canvas(pdf_buf, pagesize=A4)
    width, height = A4

    # Texto "QR tributario" + QR arriba, centrado, tamaño ~35mm (regla: 30-40mm)
    qr_size = 35 * mm
    qr_x = (width - qr_size) / 2
    qr_y = height - 20 * mm - qr_size
    c.setFont("Helvetica", 8)
    c.drawCentredString(width / 2, height - 15 * mm, "QR tributario")
    from reportlab.lib.utils import ImageReader
    c.drawImage(ImageReader(qr_buf), qr_x, qr_y, width=qr_size, height=qr_size)
    c.drawCentredString(width / 2, qr_y - 10, "Factura verificable en la sede electrónica de la AEAT (VERI*FACTU)")

    y = qr_y - 40
    c.setFont("Helvetica-Bold", 14)
    c.drawString(20 * mm, y, f"Factura {factura.numserie}")
    y -= 20
    c.setFont("Helvetica", 10)
    c.drawString(20 * mm, y, f"Emisor: {emisor_nombre} ({emisor_nif})"); y -= 15
    c.drawString(20 * mm, y, f"Cliente: {factura.cliente.nombre} ({factura.cliente.nif})"); y -= 15
    c.drawString(20 * mm, y, f"Fecha: {factura.fecha_emision.strftime('%d-%m-%Y')}"); y -= 20
    c.drawString(20 * mm, y, f"Concepto: {factura.concepto}"); y -= 20
    c.drawString(20 * mm, y, f"Base imponible: {factura.base_imponible:.2f} €"); y -= 15
    c.drawString(20 * mm, y, f"IVA ({factura.tipo_iva:.0f}%): {factura.cuota_iva:.2f} €"); y -= 15
    if factura.tipo_irpf:
        c.drawString(20 * mm, y, f"Retención IRPF ({factura.tipo_irpf:.0f}%): -{factura.retencion_irpf:.2f} €"); y -= 15
    c.setFont("Helvetica-Bold", 12)
    c.drawString(20 * mm, y, f"TOTAL: {factura.total:.2f} €"); y -= 25
    c.setFont("Helvetica", 7)
    c.drawString(20 * mm, y, f"Hash registro: {factura.hash_registro}"); y -= 10
    c.drawString(20 * mm, y, f"Hash anterior: {factura.hash_anterior}")

    c.showPage()
    c.save()
    pdf_buf.seek(0)
    return send_file(pdf_buf, mimetype="application/pdf", download_name=f"factura_{factura.numserie}.pdf")


@app.route("/api/facturas/<int:factura_id>/pagar", methods=["POST"])
def pagar_factura(factura_id):
    """Crea un PaymentIntent de Stripe en modo TEST para la cuota de suscripción del SaaS
    (no para la factura del cliente final, que es entre el autónomo y su propio cliente)."""
    import stripe
    factura = Factura.query.get_or_404(factura_id)
    stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "")
    if not stripe.api_key or not stripe.api_key.startswith("sk_test_"):
        return jsonify({"error": "Stripe no configurado en modo TEST (falta STRIPE_SECRET_KEY sk_test_...)"}), 400
    try:
        intent = stripe.PaymentIntent.create(
            amount=int(round(factura.total * 100)),
            currency="eur",
            metadata={"factura_id": str(factura.id), "numserie": factura.numserie},
        )
    except stripe.error.StripeError as exc:
        return jsonify({"error": f"Stripe rechazó la petición: {exc.user_message or str(exc)}"}), 400
    factura.stripe_payment_intent = intent.id
    db.session.commit()
    return jsonify({"client_secret": intent.client_secret, "payment_intent_id": intent.id})


@app.route("/api/facturas/<int:factura_id>/confirmar_pago", methods=["POST"])
def confirmar_pago(factura_id):
    """Simula la confirmación de webhook de Stripe en test (marca la factura como pagada)."""
    factura = Factura.query.get_or_404(factura_id)
    factura.pagada = True
    db.session.commit()
    return jsonify(factura.to_dict())


def crear_tablas():
    with app.app_context():
        db.create_all()


if __name__ == "__main__":
    crear_tablas()
    app.run(debug=True, port=5001)
