"""
Repositorios del módulo de Operaciones.

Este archivo contiene exclusivamente el acceso a
v2sulpaa_operaciones_db.

Reglas de arquitectura:
- No contiene lógica de presentación.
- No calcula totales comerciales.
- No accede directamente a otras bases de datos.
- Los servicios serán responsables de aplicar las reglas de negocio.
"""

from app.config.database import conexion_operaciones


# ============================================================
# TARIFAS DE DELIVERY LOCAL
# ============================================================

def obtener_tarifa_delivery_activa():
    """
    Obtiene la tarifa de delivery local vigente.

    La tarifa se obtiene siempre desde la base de datos para evitar
    costos de envío hardcodeados en el frontend o en los servicios.
    """
    conexion = conexion_operaciones()

    try:
        with conexion.cursor() as cursor:
            sql = """
                SELECT
                    id,
                    nombre,
                    tarifa_base,
                    km_incluidos,
                    precio_km_adicional,
                    peso_incluido_kg,
                    precio_kg_adicional,
                    peso_maximo_kg,
                    recargo_hora_pico,
                    recargo_feriado,
                    minutos_espera_gratis,
                    precio_minuto_espera,
                    cargo_cancelacion,
                    distancia_maxima_km,
                    monto_envio_gratis,
                    vigente_desde,
                    vigente_hasta,
                    estado
                FROM tarifas_delivery
                WHERE estado = 'ACTIVA'
                  AND vigente_desde <= NOW()
                  AND (
                        vigente_hasta IS NULL
                        OR vigente_hasta >= NOW()
                  )
                ORDER BY vigente_desde DESC
                LIMIT 1
            """

            cursor.execute(sql)
            return cursor.fetchone()

    finally:
        conexion.close()


# ============================================================
# PUNTOS DE RECOJO SULPAA
# ============================================================

def listar_puntos_recojo_activos():
    """
    Lista únicamente los puntos de recojo activos de SULPAA.

    Actualmente la tabla puede estar vacía. En ese caso simplemente
    se devolverá una lista vacía y el servicio decidirá si la opción
    RECOJO_LOCAL debe mostrarse al cliente.
    """
    conexion = conexion_operaciones()

    try:
        with conexion.cursor() as cursor:
            sql = """
                SELECT
                    id,
                    codigo,
                    nombre,
                    distrito_id,
                    direccion,
                    referencia,
                    latitud,
                    longitud,
                    horario,
                    telefono,
                    estado
                FROM puntos_recojo
                WHERE estado = 'ACTIVO'
                ORDER BY nombre ASC
            """

            cursor.execute(sql)
            return cursor.fetchall()

    finally:
        conexion.close()


# ============================================================
# TRANSPORTISTAS
# ============================================================

def listar_transportistas_activos():
    """
    Obtiene las empresas de transporte actualmente habilitadas.
    """
    conexion = conexion_operaciones()

    try:
        with conexion.cursor() as cursor:
            sql = """
                SELECT
                    id,
                    codigo,
                    nombre,
                    logo_ruta,
                    url_seguimiento,
                    telefono,
                    estado
                FROM transportistas
                WHERE estado = 'ACTIVO'
                ORDER BY nombre ASC
            """

            cursor.execute(sql)
            return cursor.fetchall()

    finally:
        conexion.close()


def obtener_transportista_activo(transportista_id):
    """
    Busca un transportista activo por su identificador.

    Se utilizará posteriormente para validar en backend que el
    transportista enviado desde el checkout realmente existe.
    """
    conexion = conexion_operaciones()

    try:
        with conexion.cursor() as cursor:
            sql = """
                SELECT
                    id,
                    codigo,
                    nombre,
                    logo_ruta,
                    url_seguimiento,
                    telefono,
                    estado
                FROM transportistas
                WHERE id = %s
                  AND estado = 'ACTIVO'
                LIMIT 1
            """

            cursor.execute(sql, (transportista_id,))
            return cursor.fetchone()

    finally:
        conexion.close()


# ============================================================
# SERVICIOS DE TRANSPORTISTA
# ============================================================

def listar_servicios_transportista_activos(transportista_id):
    """
    Obtiene los servicios activos pertenecientes a un transportista.
    """
    conexion = conexion_operaciones()

    try:
        with conexion.cursor() as cursor:
            sql = """
                SELECT
                    id,
                    transportista_id,
                    codigo,
                    nombre,
                    modalidad,
                    descripcion,
                    estado
                FROM servicios_transportista
                WHERE transportista_id = %s
                  AND estado = 'ACTIVO'
                ORDER BY nombre ASC
            """

            cursor.execute(sql, (transportista_id,))
            return cursor.fetchall()

    finally:
        conexion.close()


def obtener_servicio_transportista_activo(
    servicio_transportista_id,
    transportista_id=None,
):
    """
    Busca un servicio activo.

    Si se proporciona transportista_id también valida que el servicio
    realmente pertenezca a dicho transportista.
    """
    conexion = conexion_operaciones()

    try:
        with conexion.cursor() as cursor:
            sql = """
                SELECT
                    id,
                    transportista_id,
                    codigo,
                    nombre,
                    modalidad,
                    descripcion,
                    estado
                FROM servicios_transportista
                WHERE id = %s
                  AND estado = 'ACTIVO'
            """

            parametros = [servicio_transportista_id]

            if transportista_id:
                sql += " AND transportista_id = %s"
                parametros.append(transportista_id)

            sql += " LIMIT 1"

            cursor.execute(sql, tuple(parametros))
            return cursor.fetchone()

    finally:
        conexion.close()


# ============================================================
# SUCURSALES DE TRANSPORTISTAS
# ============================================================

def listar_sucursales_destino_activas(
    transportista_id,
    distrito_id=None,
):
    """
    Obtiene las sucursales activas que pueden recibir envíos.

    Si se proporciona distrito_id, se filtran las agencias disponibles
    para ese distrito.
    """
    conexion = conexion_operaciones()

    try:
        with conexion.cursor() as cursor:
            sql = """
                SELECT
                    id,
                    transportista_id,
                    codigo_externo,
                    nombre,
                    distrito_id,
                    direccion,
                    latitud,
                    longitud,
                    telefono,
                    permite_origen,
                    permite_destino,
                    verificado_en,
                    estado
                FROM sucursales_transportista
                WHERE transportista_id = %s
                  AND permite_destino = 1
                  AND estado = 'ACTIVA'
            """

            parametros = [transportista_id]

            if distrito_id:
                sql += " AND distrito_id = %s"
                parametros.append(distrito_id)

            sql += " ORDER BY nombre ASC"

            cursor.execute(sql, tuple(parametros))
            return cursor.fetchall()

    finally:
        conexion.close()


def obtener_sucursal_destino_activa(
    sucursal_id,
    transportista_id=None,
):
    """
    Obtiene una sucursal válida para destino.

    Esta comprobación será importante cuando el cliente seleccione una
    agencia en el checkout: el backend no confiará únicamente en el ID
    enviado por JavaScript.
    """
    conexion = conexion_operaciones()

    try:
        with conexion.cursor() as cursor:
            sql = """
                SELECT
                    id,
                    transportista_id,
                    codigo_externo,
                    nombre,
                    distrito_id,
                    direccion,
                    latitud,
                    longitud,
                    telefono,
                    permite_origen,
                    permite_destino,
                    verificado_en,
                    estado
                FROM sucursales_transportista
                WHERE id = %s
                  AND permite_destino = 1
                  AND estado = 'ACTIVA'
            """

            parametros = [sucursal_id]

            if transportista_id:
                sql += " AND transportista_id = %s"
                parametros.append(transportista_id)

            sql += " LIMIT 1"

            cursor.execute(sql, tuple(parametros))
            return cursor.fetchone()

    finally:
        conexion.close()


# ============================================================
# TARIFARIOS DE TRANSPORTISTAS
# ============================================================

def obtener_tarifario_activo_transportista(transportista_id):
    """
    Obtiene el tarifario vigente más reciente del transportista.
    """
    conexion = conexion_operaciones()

    try:
        with conexion.cursor() as cursor:
            sql = """
                SELECT
                    id,
                    transportista_id,
                    nombre,
                    version,
                    vigente_desde,
                    vigente_hasta,
                    estado
                FROM tarifarios_transportista
                WHERE transportista_id = %s
                  AND estado = 'ACTIVO'
                  AND vigente_desde <= NOW()
                  AND (
                        vigente_hasta IS NULL
                        OR vigente_hasta >= NOW()
                  )
                ORDER BY vigente_desde DESC
                LIMIT 1
            """

            cursor.execute(sql, (transportista_id,))
            return cursor.fetchone()

    finally:
        conexion.close()


# ============================================================
# REGLAS TARIFARIAS INTERPROVINCIALES
# ============================================================

def obtener_regla_tarifa_transportista(
    tarifario_id,
    servicio_transportista_id,
    distrito_destino_id,
):
    """
    Obtiene la regla tarifaria activa correspondiente a:
    - tarifario,
    - servicio,
    - distrito de destino.

    No se calcula todavía el precio aquí. El repositorio solamente
    recupera la configuración almacenada.
    """
    conexion = conexion_operaciones()

    try:
        with conexion.cursor() as cursor:
            sql = """
                SELECT
                    id,
                    tarifario_id,
                    servicio_transportista_id,
                    distrito_destino_id,
                    metodo_calculo,
                    divisor_peso_volumetrico,
                    precio_m3,
                    redondear_kg,
                    porcentaje_seguro,
                    valor_seguro_desde,
                    fuente_tarifa,
                    tarifa_base,
                    precio_kg_adicional,
                    peso_incluido_gramos,
                    peso_maximo_gramos,
                    recargo_fijo,
                    estado
                FROM reglas_tarifa_transportista
                WHERE tarifario_id = %s
                  AND servicio_transportista_id = %s
                  AND distrito_destino_id = %s
                  AND estado = 'ACTIVA'
                LIMIT 1
            """

            cursor.execute(
                sql,
                (
                    tarifario_id,
                    servicio_transportista_id,
                    distrito_destino_id,
                ),
            )

            return cursor.fetchone()

    finally:
        conexion.close()


def obtener_rango_tarifa_por_peso(
    regla_tarifa_id,
    peso_gramos,
):
    """
    Busca el rango de precio correspondiente al peso calculado.

    Ejemplo:
        0 - 1000 g
        1001 - 5000 g
        5001 - 10000 g

    Los rangos y precios provienen completamente de la BD.
    """
    conexion = conexion_operaciones()

    try:
        with conexion.cursor() as cursor:
            sql = """
                SELECT
                    id,
                    regla_tarifa_id,
                    peso_desde_gramos,
                    peso_hasta_gramos,
                    precio
                FROM rangos_tarifa_transportista
                WHERE regla_tarifa_id = %s
                  AND %s BETWEEN peso_desde_gramos
                             AND peso_hasta_gramos
                ORDER BY peso_desde_gramos ASC
                LIMIT 1
            """

            cursor.execute(
                sql,
                (
                    regla_tarifa_id,
                    peso_gramos,
                ),
            )

            return cursor.fetchone()

    finally:
        conexion.close()

# ============================================================
# MÉTODOS DE PAGO
# ============================================================

def listar_metodos_pago_activos():
    """
    Obtiene los métodos de pago actualmente habilitados.

    La disponibilidad proviene siempre de
    v2sulpaa_operaciones_db.metodos_pago.

    El repositorio no decide qué método corresponde
    a cada modalidad de entrega. Esa regla pertenece
    a la capa de servicios.
    """

    conexion = conexion_operaciones()

    try:
        with conexion.cursor() as cursor:
            sql = """
                SELECT
                    id,
                    codigo,
                    nombre,
                    tipo_confirmacion,
                    estado,
                    orden
                FROM metodos_pago
                WHERE estado = 'ACTIVO'
                ORDER BY orden ASC, id ASC
            """

            cursor.execute(sql)

            return cursor.fetchall()

    finally:
        conexion.close()

# ============================================================
# PAGOS
# ============================================================

def crear_pago_pedido(
    pago_id,
    pedido_id,
    metodo_pago_id,
    modalidad,
    monto,
    moneda="PEN",
    usuario_id=None,
):
    """
    Crea el pago inicial de un pedido.

    Todos los pagos nacen en estado PENDIENTE.

    Yape, Plin y transferencia cambiarán posteriormente a
    EN_REVISION cuando el cliente registre una operación
    mediante el simulador de pago.

    El pago y su primer historial se crean dentro de una sola
    transacción de Operaciones.
    """

    if not pago_id:
        raise ValueError(
            "No se recibió el identificador del pago."
        )

    if not pedido_id:
        raise ValueError(
            "No se recibió el identificador del pedido."
        )

    if not metodo_pago_id:
        raise ValueError(
            "No se recibió el método de pago."
        )

    modalidades_validas = {
        "ANTICIPADO",
        "CONTRA_ENTREGA",
        "PAGO_EN_LOCAL",
    }

    modalidad = str(
        modalidad or ""
    ).strip().upper()

    if modalidad not in modalidades_validas:

        raise ValueError(
            "La modalidad de pago no es válida."
        )

    from decimal import (
        Decimal,
        ROUND_HALF_UP,
    )

    try:

        monto = Decimal(
            str(monto)
        ).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )

    except Exception as error:

        raise ValueError(
            "El monto del pago no es válido."
        ) from error

    if monto <= 0:

        raise ValueError(
            "El monto del pago debe ser mayor que cero."
        )

    conexion = conexion_operaciones()

    try:

        with conexion.cursor() as cursor:

            # ----------------------------------------------------
            # 1. Verificar método de pago activo
            # ----------------------------------------------------

            cursor.execute(
                """
                SELECT
                    id,
                    codigo,
                    nombre,
                    tipo_confirmacion

                FROM metodos_pago

                WHERE
                    id = %s
                    AND estado = 'ACTIVO'

                LIMIT 1

                FOR UPDATE
                """,
                (
                    metodo_pago_id,
                ),
            )

            metodo = cursor.fetchone()

            if not metodo:

                raise ValueError(
                    "El método de pago ya no está disponible."
                )

            # ----------------------------------------------------
            # 2. Evitar pago duplicado para el pedido
            # ----------------------------------------------------

            cursor.execute(
                """
                SELECT id

                FROM pagos

                WHERE pedido_id = %s

                LIMIT 1

                FOR UPDATE
                """,
                (
                    pedido_id,
                ),
            )

            if cursor.fetchone():

                raise ValueError(
                    "El pedido ya tiene un pago registrado."
                )

            # ----------------------------------------------------
            # 3. Crear pago pendiente
            # ----------------------------------------------------

            cursor.execute(
                """
                INSERT INTO pagos (
                    id,
                    pedido_id,
                    metodo_pago_id,
                    modalidad,
                    monto,
                    moneda,
                    estado,
                    referencia_externa,
                    registrado_por_usuario_id
                )
                VALUES (
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    'PENDIENTE',
                    NULL,
                    %s
                )
                """,
                (
                    pago_id,
                    pedido_id,
                    metodo_pago_id,
                    modalidad,
                    monto,
                    moneda,
                    usuario_id,
                ),
            )

            # ----------------------------------------------------
            # 4. Historial inicial
            # ----------------------------------------------------

            cursor.execute(
                """
                INSERT INTO pago_historial (
                    pago_id,
                    estado_anterior,
                    estado_nuevo,
                    usuario_responsable_id,
                    observacion
                )
                VALUES (
                    %s,
                    NULL,
                    'PENDIENTE',
                    %s,
                    %s
                )
                """,
                (
                    pago_id,
                    usuario_id,
                    "Pago creado desde checkout.",
                ),
            )

            conexion.commit()

            return {
                "pago_id":
                    pago_id,

                "pedido_id":
                    pedido_id,

                "metodo_pago_id":
                    metodo_pago_id,

                "metodo_codigo":
                    metodo["codigo"],

                "metodo_nombre":
                    metodo["nombre"],

                "modalidad":
                    modalidad,

                "monto":
                    float(monto),

                "moneda":
                    moneda,

                "estado":
                    "PENDIENTE",
            }

    except Exception:

        conexion.rollback()
        raise

    finally:

        conexion.close()


# ============================================================
# CANCELAR PAGO POR COMPENSACIÓN
# ============================================================

def cancelar_pago_pedido(
    pedido_id,
    usuario_id=None,
    observacion=None,
):
    """
    Cancela un pago PENDIENTE o EN_REVISION cuando el checkout
    completo necesita revertirse.

    No modifica pagos ya PAGADOS.
    """

    if not pedido_id:
        return False

    conexion = conexion_operaciones()

    try:

        with conexion.cursor() as cursor:

            cursor.execute(
                """
                SELECT
                    id,
                    estado

                FROM pagos

                WHERE pedido_id = %s

                ORDER BY creado_en DESC

                LIMIT 1

                FOR UPDATE
                """,
                (
                    pedido_id,
                ),
            )

            pago = cursor.fetchone()

            if not pago:

                conexion.rollback()
                return False

            estado_actual = str(
                pago["estado"]
            ).upper()

            if estado_actual not in {
                "PENDIENTE",
                "EN_REVISION",
            }:

                conexion.rollback()
                return False

            cursor.execute(
                """
                UPDATE pagos

                SET estado = 'CANCELADO'

                WHERE id = %s
                """,
                (
                    pago["id"],
                ),
            )

            cursor.execute(
                """
                INSERT INTO pago_historial (
                    pago_id,
                    estado_anterior,
                    estado_nuevo,
                    usuario_responsable_id,
                    observacion
                )
                VALUES (
                    %s,
                    %s,
                    'CANCELADO',
                    %s,
                    %s
                )
                """,
                (
                    pago["id"],
                    estado_actual,
                    usuario_id,
                    observacion
                    or "Pago cancelado por compensación del checkout.",
                ),
            )

            conexion.commit()

            return True

    except Exception:

        conexion.rollback()
        raise

    finally:

        conexion.close()