"""
Acceso a datos del módulo administrativo de Inventario de SULPAA V2.

Responsabilidades:

- Leer existencias reales y enriquecerlas con el nombre comercial
  de la variante (Comercio) y su presentación/sabor.
- Registrar verificaciones físicas, movimientos de entrada y ajustes
  sobre las tablas REALES del dominio Inventario.

Convenciones (patrón de la casa):

- Cada función abre su propia conexión con el conector del dominio
  correcto y la cierra SIEMPRE en ``finally``.
- Los esquemas externos se califican únicamente con variables de
  entorno validadas (``os.getenv`` + ``fullmatch``), nunca con
  texto recibido desde HTTP.
- El stock NUNCA se modifica sin que la operación registre antes el
  movimiento correspondiente. Los repositorios no deciden reglas de
  negocio; los Services validan y aquí solo se persiste.
"""

import os
import re
import uuid

from app.config.database import conexion_inventario

_IDENTIFICADOR_SQL = re.compile(r"^[A-Za-z0-9_]+$")


def _esquema(nombre_variable):
    """Devuelve un nombre de esquema validado desde entorno."""
    valor = str(os.getenv(nombre_variable) or "").strip()
    if not valor or not _IDENTIFICADOR_SQL.fullmatch(valor):
        raise RuntimeError(
            f"La variable {nombre_variable} no contiene un esquema MySQL válido."
        )
    return valor


# ============================================================
# LECTURA DE EXISTENCIAS ENRIQUECIDAS
# ============================================================

def listar_existencias_detalladas(busqueda=None, solo_bajo_minimo=False):
    """
    Lista el inventario real enriquecido con catálogo Comercio.

    Devuelve por cada existencia:
    - existencia_id, almacen_id, almacen_codigo;
    - variante_id, sku, nombre_comercial, sabor, presentacion;
    - stock_fisico, stock_reservado, stock_disponible, stock_minimo;
    - bajo_minimo (bool: físico menor que el mínimo).

    Args:
        busqueda: Texto para filtrar por sku o nombre comercial.
        solo_bajo_minimo: Si True, solo filas con stock bajo el mínimo.
    """

    inventario = _esquema("DB_INVENTARIO")
    comercio = _esquema("DB_COMERCIO")

    condiciones = []
    parametros = []

    if solo_bajo_minimo:
        condiciones.append("ex.stock_fisico < ex.stock_minimo")

    if busqueda:
        condiciones.append(
            "(v.sku LIKE %s OR v.nombre_comercial LIKE %s)"
        )
        patron = f"%{busqueda}%"
        parametros.extend([patron, patron])

    where_sql = (
        ("WHERE " + " AND ".join(condiciones))
        if condiciones
        else ""
    )

    consulta = f"""
        SELECT
            ex.id AS existencia_id,
            ex.almacen_id,
            al.codigo AS almacen_codigo,
            ex.variante_id,
            v.sku,
            v.nombre_comercial,
            COALESCE(s.nombre, 'Sin sabor') AS sabor,
            COALESCE(p.nombre, 'Sin presentación') AS presentacion,
            ex.stock_fisico,
            ex.stock_reservado,
            (ex.stock_fisico - ex.stock_reservado) AS stock_disponible,
            ex.stock_minimo,
            (ex.stock_fisico < ex.stock_minimo) AS bajo_minimo,
            ex.actualizado_en
        FROM {inventario}.existencias AS ex
        INNER JOIN {inventario}.almacenes AS al
            ON al.id = ex.almacen_id
        LEFT JOIN {comercio}.variantes AS v
            ON v.id = ex.variante_id
        LEFT JOIN {comercio}.sabores AS s
            ON s.id = v.sabor_id
        LEFT JOIN {comercio}.presentaciones AS p
            ON p.id = v.presentacion_id
        {where_sql}
        ORDER BY
            v.nombre_comercial ASC,
            ex.stock_fisico ASC
    """

    conexion = conexion_inventario()

    try:
        with conexion.cursor() as cursor:
            cursor.execute(consulta, tuple(parametros))
            filas = cursor.fetchall()
    finally:
        conexion.close()

    resultado = []
    for fila in filas:
        resultado.append({
            **fila,
            "stock_disponible": int(fila["stock_disponible"] or 0),
            "bajo_minimo": bool(fila["bajo_minimo"]),
        })
    return resultado


def obtener_existencia_detalle(existencia_id):
    """
    Devuelve una sola existencia enriquecida (o None).

    Incluye los datos del catálogo y el stock mínimo, que el
    Service usa para los controles de ajuste.
    """

    inventario = _esquema("DB_INVENTARIO")
    comercio = _esquema("DB_COMERCIO")

    consulta = f"""
        SELECT
            ex.id AS existencia_id,
            ex.almacen_id,
            al.codigo AS almacen_codigo,
            al.nombre AS almacen_nombre,
            ex.variante_id,
            v.sku,
            v.nombre_comercial,
            v.peso_gramos,
            COALESCE(s.nombre, 'Sin sabor') AS sabor,
            COALESCE(p.nombre, 'Sin presentación') AS presentacion,
            ex.stock_fisico,
            ex.stock_reservado,
            (ex.stock_fisico - ex.stock_reservado) AS stock_disponible,
            ex.stock_minimo,
            ex.creado_en,
            ex.actualizado_en
        FROM {inventario}.existencias AS ex
        INNER JOIN {inventario}.almacenes AS al
            ON al.id = ex.almacen_id
        LEFT JOIN {comercio}.variantes AS v
            ON v.id = ex.variante_id
        LEFT JOIN {comercio}.sabores AS s
            ON s.id = v.sabor_id
        LEFT JOIN {comercio}.presentaciones AS p
            ON p.id = v.presentacion_id
        WHERE ex.id = %s
        LIMIT 1
    """

    conexion = conexion_inventario()

    try:
        with conexion.cursor() as cursor:
            cursor.execute(consulta, (existencia_id,))
            fila = cursor.fetchone()
    finally:
        conexion.close()

    if not fila:
        return None

    return {
        **fila,
        "stock_disponible": int(fila["stock_disponible"] or 0),
    }


def obtener_existencia_por_variante(variante_id, almacen_id=None):
    """
    Devuelve la existencia activa de una variante para un almacén.

    Si no se indica almacén, se usa el primer almacén activo
    (patrón del resto del dominio Inventario).
    """

    inventario = _esquema("DB_INVENTARIO")
    conexion = conexion_inventario()

    try:
        with conexion.cursor() as cursor:

            if not almacen_id:
                cursor.execute(
                    f"""
                    SELECT id
                    FROM {inventario}.almacenes
                    WHERE estado = 'ACTIVO'
                    ORDER BY creado_en ASC
                    LIMIT 1
                    """
                )
                almacen = cursor.fetchone()
                if not almacen:
                    return None
                almacen_id = almacen["id"]

            cursor.execute(
                f"""
                SELECT
                    id AS existencia_id,
                    almacen_id,
                    variante_id,
                    stock_fisico,
                    stock_reservado,
                    stock_minimo
                FROM {inventario}.existencias
                WHERE
                    almacen_id = %s
                    AND variante_id = %s
                LIMIT 1
                """,
                (almacen_id, variante_id),
            )

            return cursor.fetchone()
    finally:
        conexion.close()


# ============================================================
# HISTÓRICO DE MOVIMIENTOS
# ============================================================

def listar_movimientos(existencia_id, limite=20):
    """
    Lista los movimientos recientes de una existencia.

    Devuelve movimientos reales con motivo, tipo, cantidades y
    responsable. Se ordena de más reciente a más antiguo.
    """

    inventario = _esquema("DB_INVENTARIO")
    identidad = _esquema("DB_IDENTIDAD")

    consulta = f"""
        SELECT
            mv.id AS movimiento_id,
            mv.tipo_movimiento,
            mv.cantidad,
            mv.stock_anterior,
            mv.stock_posterior,
            mv.origen,
            mv.referencia_tipo,
            mv.referencia_id,
            mv.observacion,
            mv.creado_en,
            mt.codigo AS motivo_codigo,
            mt.nombre AS motivo_nombre,
            mt.categoria AS motivo_categoria,
            us.correo AS responsable_correo
        FROM {inventario}.movimientos_inventario AS mv
        INNER JOIN {inventario}.motivos_movimiento AS mt
            ON mt.id = mv.motivo_id
        LEFT JOIN {identidad}.usuarios AS us
            ON us.id = mv.usuario_responsable_id
        WHERE
            mv.almacen_id = (
                SELECT ex.almacen_id
                FROM {inventario}.existencias AS ex
                WHERE ex.id = %s
            )
            AND mv.variante_id = (
                SELECT ex.variante_id
                FROM {inventario}.existencias AS ex
                WHERE ex.id = %s
            )
        ORDER BY mv.creado_en DESC, mv.id DESC
        LIMIT %s
    """

    conexion = conexion_inventario()

    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                consulta,
                (existencia_id, existencia_id, int(limite)),
            )
            return cursor.fetchall()
    finally:
        conexion.close()


def listar_verificaciones(existencia_id, limite=10):
    """
    Lista las verificaciones físicas recientes de una existencia.
    """

    inventario = _esquema("DB_INVENTARIO")
    identidad = _esquema("DB_IDENTIDAD")

    consulta = f"""
        SELECT
            vf.id AS verificacion_id,
            vf.codigo_verificacion,
            vf.stock_sistema,
            vf.stock_fisico,
            vf.diferencia,
            vf.coincide,
            vf.observacion,
            vf.creado_en AS verificada_en,
            us.correo AS responsable_correo
        FROM {inventario}.verificaciones_fisicas AS vf
        INNER JOIN {inventario}.existencias AS ex
            ON ex.almacen_id = vf.almacen_id
            AND ex.variante_id = vf.variante_id
        LEFT JOIN {identidad}.usuarios AS us
            ON us.id = vf.usuario_responsable_id
        WHERE ex.id = %s
        ORDER BY vf.creado_en DESC
        LIMIT %s
    """

    conexion = conexion_inventario()

    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                consulta,
                (existencia_id, int(limite)),
            )
            return cursor.fetchall()
    finally:
        conexion.close()


# ============================================================
# MOTIVOS DE MOVIMIENTO
# ============================================================

def listar_motivos_activos():
    """Lista los motivos ACTIVOS del dominio (catálogo real)."""

    inventario = _esquema("DB_INVENTARIO")

    conexion = conexion_inventario()

    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT
                    id,
                    codigo,
                    nombre,
                    categoria,
                    requiere_observacion
                FROM {inventario}.motivos_movimiento
                WHERE estado = 'ACTIVO'
                ORDER BY
                    FIELD(categoria, 'ENTRADA', 'AJUSTE', 'SALIDA'),
                    id
                """
            )
            return cursor.fetchall()
    finally:
        conexion.close()


def obtener_motivo_por_codigo(codigo):
    """Devuelve el motivo ACTIVO que coincide con el código indicado."""

    inventario = _esquema("DB_INVENTARIO")

    conexion = conexion_inventario()

    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT
                    id,
                    codigo,
                    nombre,
                    categoria,
                    requiere_observacion
                FROM {inventario}.motivos_movimiento
                WHERE
                    codigo = %s
                    AND estado = 'ACTIVO'
                LIMIT 1
                """,
                (codigo,),
            )
            return cursor.fetchone()
    finally:
        conexion.close()


# ============================================================
# OPERACIONES TRANSACCIONALES (verificación, entrada, ajuste)
# ============================================================

def _obtener_codigo_verificacion(conexion):
    """Genera un código de verificación legible y sin colisiones."""
    codigo = "VER-" + uuid.uuid4().hex[:12].upper()
    with conexion.cursor() as cursor:
        cursor.execute(
            "SELECT COUNT(*) AS total "
            "FROM verificaciones_fisicas WHERE codigo_verificacion = %s",
            (codigo,),
        )
        if cursor.fetchone()["total"] == 0:
            return codigo
    return _obtener_codigo_verificacion(conexion)


def registrar_verificacion_fisica(
    existencia_id,
    conteo_fisico,
    usuario_responsable_id,
    observacion=None,
):
    """
    Persiste una verificación física como FOTOGRAFÍA histórica.

    No modifica existencias. Conserva:
    - stock_sistema: valor esperado al momento de la verificación;
    - stock_fisico: conteo real capturado;
    - diferencia = stock_fisico - stock_sistema;
    - coincide = (diferencia == 0).

    El ajuste posterior debe usar AJUSTE_CONTEO y puede referenciar
    esta verificación mediante movimientos_inventario.referencia.
    """

    inventario = _esquema("DB_INVENTARIO")

    conexion = conexion_inventario()

    try:
        with conexion.cursor() as cursor:

            # 1. Bloquear la existencia para lectura exacta.
            cursor.execute(
                f"""
                SELECT
                    ex.id AS existencia_id,
                    ex.almacen_id,
                    ex.variante_id,
                    ex.stock_fisico
                FROM {inventario}.existencias AS ex
                WHERE ex.id = %s
                LIMIT 1
                FOR UPDATE
                """,
                (existencia_id,),
            )

            existencia = cursor.fetchone()

            if not existencia:
                raise ValueError(
                    "La existencia indicada no existe."
                )

            stock_sistema = int(existencia["stock_fisico"] or 0)

            if int(conteo_fisico) < 0:
                raise ValueError(
                    "El conteo físico no puede ser negativo."
                )

            conteo = int(conteo_fisico)
            diferencia = conteo - stock_sistema

            verificacion_id = str(uuid.uuid4())

            # 2. Insertar la fotografía de la verificación.
            cursor.execute(
                f"""
                INSERT INTO {inventario}.verificaciones_fisicas (
                    id,
                    codigo_verificacion,
                    almacen_id,
                    variante_id,
                    stock_sistema,
                    stock_fisico,
                    diferencia,
                    coincide,
                    observacion,
                    usuario_responsable_id,
                    creado_en
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW()
                )
                """,
                (
                    verificacion_id,
                    _obtener_codigo_verificacion(conexion),
                    existencia["almacen_id"],
                    existencia["variante_id"],
                    stock_sistema,
                    conteo,
                    diferencia,
                    1 if diferencia == 0 else 0,
                    (observacion or None),
                    usuario_responsable_id,
                ),
            )

            conexion.commit()

            return {
                "ok": True,
                "verificacion_id": verificacion_id,
                "stock_sistema": stock_sistema,
                "stock_fisico": conteo,
                "diferencia": diferencia,
                "coincide": diferencia == 0,
            }

    except Exception:
        conexion.rollback()
        raise

    finally:
        conexion.close()


def registrar_movimiento_stock(
    existencia_id,
    motivo_codigo,
    cantidad,
    tipo_movimiento,
    usuario_responsable_id,
    observacion=None,
    referencia_tipo=None,
    referencia_id=None,
):
    """
    Actualiza el stock físico y registra el movimiento real.

    Flujo interno (una sola transacción):

    1. Bloquea la existencia (FOR UPDATE).
    2. Valida que el motivo exista y pertenezca a la categoría.
    3. Actualiza stock_fisico nunca por debajo de stock_reservado
       (preserva las reservas activas de checkout).
    4. Inserta el movimiento en `movimientos_inventario` con el
       estado anterior/posterior real.

    Se utiliza para ENTRADA (REPOSICION/PRODUCCION_RECIBIDA/
    DEVOLUCION_CLIENTE) y AJUSTE (AJUSTE_CONTEO/OTRO).
    """

    inventario = _esquema("DB_INVENTARIO")

    cantidad = int(cantidad)

    if cantidad <= 0:
        raise ValueError(
            "La cantidad debe ser mayor a cero."
        )

    conexion = conexion_inventario()

    try:
        with conexion.cursor() as cursor:

            # 1. Bloquear existencia.
            cursor.execute(
                f"""
                SELECT
                    ex.id AS existencia_id,
                    ex.almacen_id,
                    ex.variante_id,
                    ex.stock_fisico,
                    ex.stock_reservado
                FROM {inventario}.existencias AS ex
                WHERE ex.id = %s
                LIMIT 1
                FOR UPDATE
                """,
                (existencia_id,),
            )

            existencia = cursor.fetchone()

            if not existencia:
                raise ValueError(
                    "La existencia indicada no existe."
                )

            # 2. Motivo real y su categoría.
            cursor.execute(
                f"""
                SELECT
                    id,
                    codigo,
                    categoria,
                    requiere_observacion
                FROM {inventario}.motivos_movimiento
                WHERE
                    codigo = %s
                    AND estado = 'ACTIVO'
                LIMIT 1
                """,
                (motivo_codigo,),
            )

            motivo = cursor.fetchone()

            if not motivo:
                raise ValueError(
                    "El motivo de movimiento indicado no está activo."
                )

            categoria = motivo["categoria"]

            if motivo["requiere_observacion"] and not observacion:
                raise ValueError(
                    "Este motivo requiere una observación obligatoria."
                )

            stock_fisico = int(existencia["stock_fisico"] or 0)
            stock_reservado = int(existencia["stock_reservado"] or 0)

            # 3. Cálculo del nuevo stock según el sentido del movimiento.
            if categoria == "ENTRADA":
                if tipo_movimiento != "ENTRADA":
                    raise ValueError(
                        "Movimiento ENTRADA requiere un motivo de entrada."
                    )
                stock_posterior = stock_fisico + cantidad

            elif categoria == "AJUSTE":
                if tipo_movimiento == "AJUSTE_POSITIVO":
                    stock_posterior = stock_fisico + cantidad
                elif tipo_movimiento == "AJUSTE_NEGATIVO":
                    stock_posterior = stock_fisico - cantidad
                else:
                    raise ValueError(
                        "Movimiento AJUSTE requiere un tipo de ajuste."
                    )
            else:
                raise ValueError(
                    "Este repositorio solo administra ENTRADA y AJUSTE."
                )

            # 4. Guardas de integridad.
            if stock_posterior < 0:
                raise ValueError(
                    "El stock no puede quedar negativo."
                )

            # Preserva reservas activas (checkout): el stock que queda
            # siempre debe respaldar lo reservado.
            if stock_posterior < stock_reservado:
                raise ValueError(
                    "El nuevo stock quedaría por debajo del stock "
                    "reservado. Preserva las reservas activas."
                )

            # 5. Actualizar stock físico.
            cursor.execute(
                f"""
                UPDATE {inventario}.existencias
                SET stock_fisico = %s
                WHERE id = %s
                """,
                (stock_posterior, existencia_id),
            )

            # 6. Insertar movimiento con trazabilidad.
            movimiento_id = str(uuid.uuid4())

            cursor.execute(
                f"""
                INSERT INTO {inventario}.movimientos_inventario (
                    id,
                    almacen_id,
                    variante_id,
                    motivo_id,
                    tipo_movimiento,
                    cantidad,
                    stock_anterior,
                    stock_posterior,
                    origen,
                    referencia_tipo,
                    referencia_id,
                    usuario_responsable_id,
                    observacion,
                    creado_en
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, 'EMPLEADO',
                    %s, %s, %s, %s, NOW()
                )
                """,
                (
                    movimiento_id,
                    existencia["almacen_id"],
                    existencia["variante_id"],
                    motivo["id"],
                    tipo_movimiento,
                    cantidad,
                    stock_fisico,
                    stock_posterior,
                    referencia_tipo,
                    referencia_id,
                    usuario_responsable_id,
                    observacion,
                ),
            )

            conexion.commit()

            return {
                "ok": True,
                "movimiento_id": movimiento_id,
                "motivo_codigo": motivo_codigo,
                "categoria": categoria,
                "stock_anterior": stock_fisico,
                "stock_posterior": stock_posterior,
            }

    except Exception:
        conexion.rollback()
        raise

    finally:
        conexion.close()