"""Contratos estáticos de SQL; no ejecutan ni importan scripts contra MariaDB."""

from pathlib import Path
import re
import unittest


RAIZ = Path(__file__).resolve().parents[1]


def sql_limpio(texto):
    return re.sub(r"--[^\n]*", "", texto)


def normalizar(texto):
    return re.sub(r"\s+", "", texto).lower()


class SQLAlwaysdataTest(unittest.TestCase):
    def setUp(self):
        self.original004 = (RAIZ / "migrations/004_fase43_rol_cliente.sql").read_text(encoding="utf-8")
        self.paquete = (RAIZ / "docs/sql/alwaysdata_004_005_006_sin_correo.sql").read_text(encoding="utf-8")

    def test_rol_id_numerico_autoincremental_no_recibe_uuid(self):
        for texto in (self.original004, self.paquete):
            sql = sql_limpio(texto)
            self.assertNotIn("UUID()", sql.upper())
            self.assertRegex(sql, r"INSERT INTO roles\s*\(codigo, nombre, descripcion, estado\)")

    def test_tablas_del_paquete_coinciden_con_migraciones_originales(self):
        patron = r"CREATE TABLE(?: IF NOT EXISTS)? (\w+)\s*(\(.*?\) ENGINE=InnoDB[^;]*;)"
        originales = "\n".join((RAIZ / ruta).read_text(encoding="utf-8") for ruta in (
            "migrations/005_fase43_limite_apisperu_compartido.sql",
            "migrations/006_fase44_correo_outbox.sql",
        ))
        esperado = {nombre: normalizar(ddl) for nombre, ddl in re.findall(patron, sql_limpio(originales), re.S)}
        actual = {nombre: normalizar(ddl) for nombre, ddl in re.findall(patron, sql_limpio(self.paquete), re.S)}
        self.assertEqual(len(actual), 4)
        self.assertEqual(actual, esperado)

    def test_destino_real_sin_operaciones_destructivas(self):
        sql = sql_limpio(self.paquete)
        self.assertIn("USE base1sulpaa_identidad;", sql)
        self.assertNotIn("v2sulpaa_", sql)
        self.assertNotRegex(sql.upper(), r"(?:^|;)\s*(DROP|DELETE|TRUNCATE)\b")
        self.assertNotIn("ALTER TABLE perfiles", sql)


if __name__ == "__main__":
    unittest.main()
