# Facturación Verifactu simplificada — MVP

Backend Flask + SQLite. Frontend HTML/JS simple servido por el propio Flask.

## Cómo ejecutar
```bash
cd backend
cp ../.env.example ../.env   # y rellena tus valores (Stripe TEST, NIF emisor...)
../.venv/Scripts/python app.py
# abre http://localhost:5001
```

## Cómo correr los tests
```bash
.venv/Scripts/python -m pytest tests/ -v
```

Ver `NORMATIVA.md` para los requisitos legales de Verifactu y `RESUMEN.md` para decisiones de negocio, limitaciones y pasos a producción.
