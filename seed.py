"""
Script de seed: crea una empresa de prueba con su admin y una sucursal.
Ejecutar: python seed.py
"""
from app import create_app
from models import db, Empresa, Usuario, Sucursal

app = create_app()

with app.app_context():
    # ── Limpiar y recrear tablas ──────────────────────────────────────────
    db.drop_all()
    db.create_all()
    print("✅ Base de datos recreada")

    # ── Empresa de prueba ─────────────────────────────────────────────────
    empresa = Empresa(nombre="Empresa Demo", rif="J-12345678-9")
    empresa.set_password("demo1234")
    db.session.add(empresa)
    db.session.flush()

    # ── Sucursal principal (matriz) ───────────────────────────────────────
    sucursal = Sucursal(
        nombre="Sede Principal",
        direccion="Av. Principal, Caracas",
        telefono="0212-0000000",
        es_matriz=True,
        empresa_id=empresa.id
    )
    db.session.add(sucursal)
    db.session.flush()

    # ── Admin de la empresa ───────────────────────────────────────────────
    admin = Usuario(
        username="admin",
        rol="admin_empresa",
        empresa_id=empresa.id,
        sucursal_id=sucursal.id
    )
    admin.set_password("admin")
    db.session.add(admin)

    # ── Usuario operativo ─────────────────────────────────────────────────
    operador = Usuario(
        username="operador_demo",
        rol="user",
        empresa_id=empresa.id,
        sucursal_id=sucursal.id
    )
    operador.set_password("oper1234")
    db.session.add(operador)

    db.session.commit()

    print("✅ Seed completado:")
    print(f"   Empresa : {empresa.nombre} (RIF: {empresa.rif})")
    print(f"   Sucursal: {sucursal.nombre}")
    print(f"   Admin   : admin_demo / admin1234")
    print(f"   Operador: operador_demo / oper1234")
