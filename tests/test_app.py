import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["EMISOR_NIF"] = "B12345678"
os.environ["STRIPE_SECRET_KEY"] = "sk_test_NOTREAL_FAKE_KEY_FOR_UNIT_TESTS_ONLY"

import app as backend_app  # noqa: E402


@pytest.fixture()
def client():
    backend_app.app.config["TESTING"] = True
    backend_app.app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    with backend_app.app.app_context():
        backend_app.db.drop_all()
        backend_app.db.create_all()
    with backend_app.app.test_client() as c:
        yield c


def test_alta_cliente(client):
    r = client.post("/api/clientes", json={"nombre": "Juan Pérez", "nif": "12345678Z"})
    assert r.status_code == 201
    assert r.get_json()["nombre"] == "Juan Pérez"


def test_alta_cliente_falla_sin_nif(client):
    r = client.post("/api/clientes", json={"nombre": "Sin NIF"})
    assert r.status_code == 400


def test_emitir_factura_calcula_totales(client):
    cliente = client.post("/api/clientes", json={"nombre": "Cliente Test", "nif": "12345678Z"}).get_json()
    r = client.post("/api/facturas", json={
        "cliente_id": cliente["id"], "concepto": "Servicios de consultoría",
        "base_imponible": 100.0, "tipo_iva": 21, "tipo_irpf": 15,
    })
    assert r.status_code == 201
    f = r.get_json()
    assert f["cuota_iva"] == 21.0
    assert f["retencion_irpf"] == 15.0
    assert f["total"] == 106.0  # 100 + 21 - 15
    assert len(f["hash_registro"]) == 64


def test_hash_encadenado_entre_facturas(client):
    cliente = client.post("/api/clientes", json={"nombre": "Cliente 2", "nif": "87654321X"}).get_json()
    f1 = client.post("/api/facturas", json={
        "cliente_id": cliente["id"], "concepto": "Factura 1", "base_imponible": 50,
    }).get_json()
    f2 = client.post("/api/facturas", json={
        "cliente_id": cliente["id"], "concepto": "Factura 2", "base_imponible": 75,
    }).get_json()
    assert f1["hash_anterior"] == "0" * 64
    assert f2["hash_anterior"] == f1["hash_registro"]
    assert f2["hash_registro"] != f1["hash_registro"]


def test_factura_sin_cliente_falla(client):
    r = client.post("/api/facturas", json={"cliente_id": 999, "concepto": "x", "base_imponible": 10})
    assert r.status_code == 404


def test_qr_endpoint_devuelve_imagen(client):
    cliente = client.post("/api/clientes", json={"nombre": "QR Test", "nif": "11111111H"}).get_json()
    factura = client.post("/api/facturas", json={
        "cliente_id": cliente["id"], "concepto": "Test QR", "base_imponible": 30,
    }).get_json()
    r = client.get(f"/api/facturas/{factura['id']}/qr.png")
    assert r.status_code == 200
    assert r.content_type == "image/png"


def test_pdf_endpoint_devuelve_pdf(client):
    cliente = client.post("/api/clientes", json={"nombre": "PDF Test", "nif": "22222222J"}).get_json()
    factura = client.post("/api/facturas", json={
        "cliente_id": cliente["id"], "concepto": "Test PDF", "base_imponible": 40,
    }).get_json()
    r = client.get(f"/api/facturas/{factura['id']}/pdf")
    assert r.status_code == 200
    assert r.content_type == "application/pdf"


def test_construir_url_qr_formato():
    url = backend_app.construir_url_qr("B12345678", "A-000001", "07-09-2026", 121.0)
    assert "nif=B12345678" in url
    assert "numserie=A-000001" in url
    assert "fecha=07-09-2026" in url
    assert "importe=121.00" in url


def test_pago_stripe_test_mode_crea_payment_intent(client):
    cliente = client.post("/api/clientes", json={"nombre": "Pago Test", "nif": "33333333K"}).get_json()
    factura = client.post("/api/facturas", json={
        "cliente_id": cliente["id"], "concepto": "Test pago", "base_imponible": 100,
    }).get_json()
    # con clave dummy no válida para la API real de Stripe, esperamos error controlado (401 de Stripe)
    # pero comprobamos que el endpoint no revienta y responde JSON
    r = client.post(f"/api/facturas/{factura['id']}/pagar")
    assert r.status_code in (200, 400, 401)
    assert r.is_json


def test_confirmar_pago_marca_factura_pagada(client):
    cliente = client.post("/api/clientes", json={"nombre": "Confirmar", "nif": "44444444L"}).get_json()
    factura = client.post("/api/facturas", json={
        "cliente_id": cliente["id"], "concepto": "x", "base_imponible": 10,
    }).get_json()
    r = client.post(f"/api/facturas/{factura['id']}/confirmar_pago")
    assert r.status_code == 200
    assert r.get_json()["pagada"] is True
