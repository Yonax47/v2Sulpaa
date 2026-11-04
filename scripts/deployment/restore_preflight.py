"""Restaura únicamente en un Docker nuevo sin red ni puertos publicados.

No tiene código de conexión a Alwaysdata. Los dumps y claves quedan fuera de Git.
"""

import hashlib
import argparse
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import time


SCHEMAS = {
    "base1sulpaa_identidad": 12,
    "base1sulpaa_comercio": 36,
    "base1sulpaa_inventario": 9,
    "base1sulpaa_operaciones": 34,
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--combined-backup", type=Path)
    args = parser.parse_args()
    base = Path(os.environ["LOCALAPPDATA"]) / "Temp/opencode" / ("sulpaa-restore-" + secrets.token_hex(5))
    dumps = base / "dumps"
    private = base / "secrets"
    dumps.mkdir(parents=True)
    private.mkdir()
    password = secrets.token_urlsafe(40)
    (private / "root-password").write_text(password, encoding="ascii")
    (private / "client.cnf").write_text("[client]\nuser=root\npassword=" + password + "\n", encoding="ascii")
    container = base.name
    manifest = {"container": container, "restoration_verified": False, "backups": {}}

    def docker(*args, data=None, timeout=120):
        result = subprocess.run(["docker", *args], input=data, capture_output=True, timeout=timeout)
        if result.returncode:
            (base / "private-error.log").write_bytes(result.stderr)
            raise RuntimeError("Docker/SQL falló; diagnóstico privado conservado fuera de Git.")
        return result.stdout.decode("utf-8", errors="replace")

    def sql(query, timeout=120):
        return docker("exec", "-i", container, "mariadb", "--defaults-extra-file=/run/secrets/client.cnf",
                      "--batch", "--skip-column-names", data=query.encode("utf-8"), timeout=timeout)

    if args.combined_backup:
        source = args.combined_backup.resolve(strict=True)
        raw = source.read_bytes()
        if b"Dump completed on" not in raw[-2000:]:
            raise RuntimeError("No restaurar un respaldo combinado incompleto.")
        manifest["combined_backup"] = {
            "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
        }
        shutil.copyfile(source, dumps / "combined.sql")
        manifest["backups"] = {s: {} for s in SCHEMAS}
    else:
        for schema in SCHEMAS:
            source = Path.home() / "Downloads" / (schema + ".sql")
            raw = source.read_bytes()
            manifest["backups"][schema] = {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
            shutil.copyfile(source, dumps / source.name)

    docker("run", "--detach", "--name", container, "--network", "none", "--memory", "1g",
           "--cpus", "2", "--label", "sulpaa-purpose=isolated-restore",
           "--mount", f"type=bind,src={dumps},dst=/restore,readonly",
           "--mount", f"type=bind,src={private},dst=/run/secrets,readonly",
           "--env", "MARIADB_ROOT_PASSWORD_FILE=/run/secrets/root-password", "mariadb:11.4.13")
    info = json.loads(docker("inspect", container))[0]
    if info["HostConfig"]["NetworkMode"] != "none" or info["HostConfig"].get("PortBindings"):
        raise RuntimeError("El contenedor no cumple el aislamiento requerido.")
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        ready = subprocess.run(["docker", "exec", container, "healthcheck.sh", "--connect", "--innodb_initialized"],
                               capture_output=True, timeout=15)
        if ready.returncode == 0:
            break
        time.sleep(2)
    else:
        raise RuntimeError("MariaDB aislada no inició dentro del plazo.")

    if args.combined_backup:
        docker("exec", "-i", container, "mariadb", "--defaults-extra-file=/run/secrets/client.cnf",
               data=(dumps / "combined.sql").read_bytes())
    for schema, expected in SCHEMAS.items():
        if not args.combined_backup:
            sql(f"CREATE DATABASE `{schema}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;")
            # Entrada directa a cliente SQL dentro del contenedor sin red.
            raw = (dumps / (schema + ".sql")).read_bytes()
            docker("exec", "-i", container, "mariadb", "--defaults-extra-file=/run/secrets/client.cnf",
                   schema, data=raw)
        count = int(sql(f"SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA='{schema}' AND TABLE_TYPE='BASE TABLE';").strip())
        if count != expected:
            raise RuntimeError("El número de tablas restauradas no coincide con el precheck.")
        check = docker("exec", container, "mariadb-check", "--defaults-extra-file=/run/secrets/client.cnf", schema)
        if "error" in check.lower() or "corrupt" in check.lower():
            raise RuntimeError("La comprobación de integridad reportó errores.")
        manifest["backups"][schema]["restored_tables"] = count
        manifest["backups"][schema]["table_check"] = "OK"

    # Validar huérfanos de todas las FKs, incluso cuando el dump desactivó checks.
    keys = sql("""SELECT TABLE_SCHEMA,TABLE_NAME,CONSTRAINT_NAME,COLUMN_NAME,
        REFERENCED_TABLE_SCHEMA,REFERENCED_TABLE_NAME,REFERENCED_COLUMN_NAME
        FROM information_schema.KEY_COLUMN_USAGE
        WHERE TABLE_SCHEMA LIKE 'base1sulpaa\\_%' AND REFERENCED_TABLE_NAME IS NOT NULL
        ORDER BY TABLE_SCHEMA,TABLE_NAME,CONSTRAINT_NAME,ORDINAL_POSITION;""")
    groups = {}
    for line in keys.splitlines():
        schema, table, constraint, column, refschema, reftable, refcolumn = line.split("\t")
        groups.setdefault((schema, table, constraint, refschema, reftable), []).append((column, refcolumn))
    for (schema, table, constraint, refschema, reftable), columns in groups.items():
        if schema not in SCHEMAS or refschema not in SCHEMAS:
            raise RuntimeError("Referencia fuera de los cuatro esquemas restaurados.")
        join = " AND ".join(f"p.`{r}`=c.`{c}`" for c, r in columns)
        nonnull = " AND ".join(f"c.`{c}` IS NOT NULL" for c, _ in columns)
        query = (f"SELECT COUNT(*) FROM `{schema}`.`{table}` c WHERE {nonnull} AND NOT EXISTS "
                 f"(SELECT 1 FROM `{refschema}`.`{reftable}` p WHERE {join});")
        if int(sql(query).strip()):
            raise RuntimeError("Se detectaron referencias huérfanas en el respaldo restaurado.")

    manifest["foreign_keys_checked"] = len(groups)
    manifest["restoration_verified"] = True
    (base / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps({"restoration_verified": True, "container": container,
                      "tables": sum(SCHEMAS.values()), "foreign_keys_checked": len(groups),
                      "manifest": str(base / "manifest.json")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
