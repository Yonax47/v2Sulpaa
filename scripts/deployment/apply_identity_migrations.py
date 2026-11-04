"""Aplicación explícita 004–006, condicionada a respaldo restaurado y prechecks.

No se importa desde Flask. Sin --apply realiza exclusivamente lecturas.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import ssl

from dotenv import dotenv_values
import pymysql


ROOT = Path(__file__).resolve().parents[2]
SCHEMA = "base1sulpaa_identidad"
HOST = "mysql-base1sulpaa.alwaysdata.net"
NEW_TABLES = {"limites_consulta_externa", "tokens_verificacion", "correos_outbox", "limites_correo"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--backup", type=Path)
    parser.add_argument("--recovery-manifest", type=Path)
    parser.add_argument("--audit", required=True, type=Path)
    args = parser.parse_args()
    v = {**dotenv_values(ROOT / ".env"), **os.environ}
    if v.get("DB_HOST") != HOST or v.get("DB_IDENTIDAD") != SCHEMA:
        raise RuntimeError("Destino local distinto del servidor/esquema autorizado.")
    if args.apply:
        if not args.backup or not args.recovery_manifest:
            raise RuntimeError("Falta respaldo y evidencia de restauración.")
        manifest = json.loads(args.recovery_manifest.read_text(encoding="utf-8"))
        digest = hashlib.sha256(args.backup.read_bytes()).hexdigest()
        if not manifest.get("restoration_verified") or manifest.get("combined_backup", {}).get("sha256") != digest:
            raise RuntimeError("La recuperación no corresponde a este respaldo.")
    audit = {"host": HOST, "schema": SCHEMA, "applied": [], "verified": []}
    args.audit.parent.mkdir(parents=True, exist_ok=True)

    def save():
        args.audit.write_text(json.dumps(audit, indent=2, default=str), encoding="utf-8")

    c = pymysql.connect(
        host=HOST, port=int(v.get("DB_PORT") or 3306), user=v["DB_USER"], password=v["DB_PASSWORD"],
        database=SCHEMA, ssl=ssl.create_default_context(), connect_timeout=10,
        read_timeout=60, write_timeout=30, autocommit=False,
        cursorclass=pymysql.cursors.DictCursor,
    )
    try:
        with c.cursor() as q:
            q.execute("SHOW SESSION STATUS LIKE 'Ssl_cipher'")
            if not q.fetchone()["Value"]:
                raise RuntimeError("TLS no confirmado.")
            q.execute("START TRANSACTION READ ONLY")
            q.execute("SELECT VERSION() version")
            if not q.fetchone()["version"].startswith("11.4."):
                raise RuntimeError("Versión distinta de MariaDB 11.4.")
            q.execute("SELECT COUNT(*) total, SUM(correo_verificado) verificados FROM usuarios")
            before_users = q.fetchone()
            q.execute("SELECT COUNT(*) total FROM perfiles WHERE dni IS NOT NULL AND (dni='' OR dni NOT REGEXP '^[0-9]{8}$')")
            if q.fetchone()["total"]:
                raise RuntimeError("DNI malformados: detenerse sin corregir datos.")
            q.execute("SELECT COUNT(*) total FROM (SELECT dni FROM perfiles WHERE dni IS NOT NULL GROUP BY dni HAVING COUNT(*)>1) d")
            if q.fetchone()["total"]:
                raise RuntimeError("DNI duplicados.")
            q.execute("SELECT NON_UNIQUE,COLUMN_NAME,SUB_PART FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=%s AND TABLE_NAME='perfiles' AND INDEX_NAME='uq_perfiles_dni' ORDER BY SEQ_IN_INDEX", (SCHEMA,))
            if q.fetchall() != [{"NON_UNIQUE": 0, "COLUMN_NAME": "dni", "SUB_PART": None}]:
                raise RuntimeError("003 no satisfecha exactamente.")
            q.execute("SELECT COLUMN_TYPE,EXTRA FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=%s AND TABLE_NAME='roles' AND COLUMN_NAME='id'", (SCHEMA,))
            role_id = q.fetchone()
            if not role_id or "smallint" not in role_id["COLUMN_TYPE"] or role_id["EXTRA"] != "auto_increment":
                raise RuntimeError("roles.id incompatible con 004 corregida.")
            q.execute("SELECT COLUMN_TYPE,COLLATION_NAME FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=%s AND TABLE_NAME='usuarios' AND COLUMN_NAME='id'", (SCHEMA,))
            if q.fetchone() != {"COLUMN_TYPE": "char(36)", "COLLATION_NAME": "utf8mb4_unicode_ci"}:
                raise RuntimeError("usuarios.id incompatible con FK 006.")
            q.execute("SELECT id,codigo,estado FROM roles ORDER BY id")
            before_roles = q.fetchall()
            if any(r["codigo"] == "CLIENTE" for r in before_roles):
                raise RuntimeError("CLIENTE ya existe: revisar estado sin repetir 004.")
            q.execute("SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA=%s AND TABLE_NAME IN ('limites_consulta_externa','tokens_verificacion','correos_outbox','limites_correo')", (SCHEMA,))
            if q.fetchall():
                raise RuntimeError("Tablas nuevas ya presentes: revisar estado parcial, no repetir.")
            q.execute("SELECT COLUMN_NAME FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=%s AND TABLE_NAME='usuarios' AND COLUMN_NAME='requiere_verificacion_correo'", (SCHEMA,))
            if q.fetchone():
                raise RuntimeError("Columna 006 ya presente: revisar estado parcial.")
            q.execute("SELECT COUNT(*) total FROM information_schema.TABLES WHERE TABLE_SCHEMA IN ('base1sulpaa_identidad','base1sulpaa_comercio','base1sulpaa_inventario','base1sulpaa_operaciones') AND TABLE_TYPE='BASE TABLE' AND ENGINE<>'InnoDB'")
            if q.fetchone()["total"]:
                raise RuntimeError("Motor no transaccional encontrado.")
            c.rollback()
            audit["prechecks"] = "OK"
            save()
            if not args.apply:
                print(json.dumps({"prechecks": "OK", "applied": False}))
                return

            text = (ROOT / "docs/sql/alwaysdata_004_005_006_sin_correo.sql").read_text(encoding="utf-8")
            text = re.sub(r"--[^\n]*", "", text)
            statements = [s.strip() for s in text.split(";") if s.strip()]
            for statement in statements:
                q.execute(statement)
                if statement.upper().startswith("INSERT INTO ROLES"):
                    audit["applied"].append("004_CLIENTE")
                elif statement.upper().startswith("CREATE TABLE"):
                    name = statement.split()[2]
                    audit["applied"].append(name)
                    q.execute("SELECT ENGINE FROM information_schema.TABLES WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s", (SCHEMA, name))
                    if q.fetchone() != {"ENGINE": "InnoDB"}:
                        raise RuntimeError("Postcheck InnoDB falló.")
                    audit["verified"].append(name)
                elif statement.upper().startswith("ALTER TABLE USUARIOS"):
                    audit["applied"].append("006_columna_usuarios")
                if statement.upper() == "COMMIT":
                    q.execute("SELECT COUNT(*) total FROM roles WHERE codigo='CLIENTE' AND estado='ACTIVO'")
                    if q.fetchone()["total"] != 1:
                        raise RuntimeError("Postcheck CLIENTE falló.")
                save()

            q.execute("SELECT COUNT(*) total,SUM(correo_verificado) verificados FROM usuarios")
            if q.fetchone() != before_users:
                raise RuntimeError("Conteo/estado de usuarios cambió: revisar antes de desplegar.")
            q.execute("SELECT id,codigo,estado FROM roles WHERE codigo<>'CLIENTE' ORDER BY id")
            if q.fetchall() != before_roles:
                raise RuntimeError("Los roles originales cambiaron.")
            q.execute("SELECT COUNT(*) total FROM usuarios WHERE requiere_verificacion_correo<>0")
            if q.fetchone()["total"]:
                raise RuntimeError("Postcheck de transición histórica falló.")
            c.commit()
            audit["result"] = "OK"
            save()
            print(json.dumps({"migrations": "004/005/006", "result": "OK", "audit": str(args.audit)}))
    except Exception as exc:
        c.rollback()
        audit["result"] = "STOP"
        audit["error_type"] = type(exc).__name__
        audit["error_code"] = exc.args[0] if exc.args and isinstance(exc.args[0], int) else None
        save()
        raise RuntimeError("Migración detenida; revisar evidencia local sin reejecutar a ciegas.") from None
    finally:
        c.close()


if __name__ == "__main__":
    main()
