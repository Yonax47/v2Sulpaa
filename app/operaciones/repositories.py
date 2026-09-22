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
import uuid


def guardar_entrega_checkout(pedido_id, usuario_id, entrega):
    """Cabecera, cotización, destino e historial: una transacción local.

    Recibe exclusivamente datos normalizados por services. La cotización
    firmada del checkout se materializa como ACEPTADA al crear la entrega.
    """
    conexion = conexion_operaciones()
    entrega_id = str(uuid.uuid4())
    cotizacion_id = str(uuid.uuid4())
    tipo = entrega['tipo']
    try:
        with conexion.cursor() as cursor:
            cursor.execute("""
                INSERT INTO entregas
                (id, pedido_id, tipo_entrega, costo_cobrado_cliente, estado)
                VALUES (%s, %s, %s, %s, 'PENDIENTE')
            """, (entrega_id, pedido_id,
                  'TRANSPORTISTA_ASOCIADO' if tipo == 'TRANSPORTISTA' else tipo,
                  entrega['costo_entrega']))
            if tipo == 'RECOJO_LOCAL':
                punto = entrega['punto_recojo']
                cursor.execute("""
                    INSERT INTO entregas_recojo
                    (id, entrega_id, punto_recojo_id, nombre_punto_snapshot, direccion_snapshot)
                    VALUES (%s, %s, %s, %s, %s)
                """, (str(uuid.uuid4()), entrega_id, punto['id'], punto['nombre'], punto['direccion']))
            elif tipo == 'DELIVERY_LOCAL':
                tarifa = entrega['tarifa_snapshot']
                destino = entrega['destino']
                cursor.execute("""
                    INSERT INTO cotizaciones_delivery
                    (id, entrega_id, tarifa_delivery_id, distrito_destino_id,
                     distancia_km, tarifa_base_aplicada, km_incluidos_aplicados,
                     precio_km_aplicado, costo_estimado, estado, expira_en)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'ACEPTADA',
                            DATE_ADD(NOW(), INTERVAL 15 MINUTE))
                """, (cotizacion_id, entrega_id, entrega['tarifa_delivery_id'],
                      destino['distrito_id'], entrega['distancia_km'],
                      tarifa['tarifa_base'], tarifa['km_incluidos'],
                      tarifa['precio_km_adicional'], entrega['costo_entrega']))
                cursor.execute("""
                    INSERT INTO entregas_delivery
                    (id, entrega_id, cotizacion_delivery_id, distancia_km, costo_calculado)
                    VALUES (%s,%s,%s,%s,%s)
                """, (str(uuid.uuid4()), entrega_id, cotizacion_id,
                      entrega['distancia_km'], entrega['costo_entrega']))
                cursor.execute("""
                    INSERT INTO delivery_destinos
                    (id, entrega_id, distrito_id, nombre_receptor, telefono_receptor,
                     direccion, referencia, latitud, longitud)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """, (str(uuid.uuid4()), entrega_id, destino['distrito_id'],
                      entrega['nombre_receptor'], entrega['telefono_receptor'],
                      destino['direccion'], destino['referencia'], destino['latitud'], destino['longitud']))
            elif tipo == 'TRANSPORTISTA':
                sucursal = entrega.get('sucursal_destino') or {}
                cursor.execute("""
                    INSERT INTO cotizaciones_transportista
                    (id, pedido_id, transportista_id, servicio_transportista_id,
                     tarifario_id, sucursal_destino_id, distrito_destino_id,
                     peso_estimado_gramos, costo_estimado, estado, expira_en)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'ACEPTADA',
                            DATE_ADD(NOW(), INTERVAL 15 MINUTE))
                """, (cotizacion_id, pedido_id, entrega['transportista']['id'],
                      entrega['servicio']['id'], entrega['tarifario_id'], sucursal.get('id'),
                      entrega['distrito_destino_id'], entrega['peso_estimado_gramos'], entrega['costo_entrega']))
                cursor.execute("""
                    INSERT INTO envios_transportista
                    (id, entrega_id, transportista_id, servicio_transportista_id,
                     cotizacion_id, sucursal_destino_id, transportista_nombre_snapshot,
                     servicio_nombre_snapshot, sucursal_destino_nombre_snapshot,
                     direccion_destino_snapshot, peso_estimado_gramos,
                     costo_estimado, costo_cobrado_cliente, url_seguimiento_snapshot)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """, (str(uuid.uuid4()), entrega_id, entrega['transportista']['id'],
                      entrega['servicio']['id'], cotizacion_id, sucursal.get('id'),
                      entrega['transportista']['nombre'], entrega['servicio']['nombre'],
                      sucursal.get('nombre'), entrega['direccion_entrega'],
                      entrega['peso_estimado_gramos'], entrega['costo_entrega'],
                      entrega['costo_entrega'], entrega['transportista'].get('url_seguimiento')))
            else:
                raise ValueError('Modalidad de entrega inválida.')
            cursor.execute("""
                INSERT INTO entrega_historial
                (entrega_id, estado_anterior, estado_nuevo, usuario_responsable_id, comentario)
                VALUES (%s, NULL, 'PENDIENTE', %s, 'Entrega creada desde checkout.')
            """, (entrega_id, usuario_id))
        conexion.commit()
        return entrega_id
    except Exception:
        conexion.rollback()
        raise
    finally:
        conexion.close()


def cancelar_entrega_checkout(pedido_id, usuario_id):
    """Compensación idempotente: conserva snapshots e historial."""
    conexion = conexion_operaciones()
    try:
        with conexion.cursor() as cursor:
            cursor.execute('SELECT id, estado FROM entregas WHERE pedido_id=%s FOR UPDATE', (pedido_id,))
            entrega = cursor.fetchone()
            if entrega and entrega['estado'] == 'PENDIENTE':
                cursor.execute("UPDATE entregas SET estado='CANCELADO' WHERE id=%s", (entrega['id'],))
                cursor.execute("UPDATE envios_transportista SET estado='CANCELADO' WHERE entrega_id=%s", (entrega['id'],))
                cursor.execute("UPDATE cotizaciones_delivery SET estado='CANCELADA' WHERE entrega_id=%s", (entrega['id'],))
                cursor.execute("UPDATE cotizaciones_transportista SET estado='CANCELADA' WHERE pedido_id=%s", (pedido_id,))
                cursor.execute("""
                    INSERT INTO entrega_historial
                    (entrega_id, estado_anterior, estado_nuevo, usuario_responsable_id, comentario)
                    VALUES (%s,'PENDIENTE','CANCELADO',%s,'Compensación por fallo del checkout.')
                """, (entrega['id'], usuario_id))
        conexion.commit()
    except Exception:
        conexion.rollback()
        raise
    finally:
        conexion.close()


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


# ============================================================
# PAGO DE UN PEDIDO (LECTURA PARA SEGUIMIENTO)
# ============================================================

def obtener_pago_pedido(
    pedido_id,
):
    """
    Obtiene el pago más reciente de un pedido junto con
    los datos legibles del método de pago.

    Solo lectura para la pantalla de seguimiento:
    no modifica ningún dato.
    """

    conexion = conexion_operaciones()

    try:

        with conexion.cursor() as cursor:

            cursor.execute(
                """
                SELECT
                    p.id AS pago_id,
                    p.metodo_pago_id,
                    p.modalidad,
                    p.monto,
                    p.moneda,
                    p.estado,
                    p.referencia_externa,
                    p.creado_en,
                    m.codigo AS metodo_codigo,
                    m.nombre AS metodo_nombre,
                    m.tipo_confirmacion

                FROM pagos p

                INNER JOIN metodos_pago m
                    ON m.id = p.metodo_pago_id

                WHERE p.pedido_id = %s

                ORDER BY p.creado_en DESC

                LIMIT 1
                """,
                (
                    pedido_id,
                ),
            )

            pago = cursor.fetchone()

            if not pago:

                return None

            return {
                "pago_id":
                    pago["pago_id"],

                "metodo_pago_id":
                    pago["metodo_pago_id"],

                "modalidad":
                    pago["modalidad"],

                "monto":
                    float(
                        pago["monto"]
                    ),

                "moneda":
                    pago["moneda"],

                "estado":
                    pago["estado"],

                "referencia_externa":
                    pago["referencia_externa"],

                "creado_en":
                    pago["creado_en"],

                "metodo_codigo":
                    pago["metodo_codigo"],

                "metodo_nombre":
                    pago["metodo_nombre"],

                "tipo_confirmacion":
                    pago["tipo_confirmacion"],
            }

    finally:

        conexion.close()


# ============================================================
# HISTORIAL DE PAGO (LECTURA PARA SEGUIMIENTO)
# ============================================================

def obtener_historial_pago(
    pago_id,
):
    """
    Obtiene el historial de eventos de un pago.

    Solo lectura: no modifica ningún dato.
    """

    conexion = conexion_operaciones()

    try:

        with conexion.cursor() as cursor:

            cursor.execute(
                """
                SELECT
                    estado_anterior,
                    estado_nuevo,
                    usuario_responsable_id,
                    observacion,
                    creado_en

                FROM pago_historial

                WHERE pago_id = %s

                ORDER BY creado_en ASC
                """,
                (
                    pago_id,
                ),
            )

            filas = cursor.fetchall()

            return [
                {
                    "estado_anterior":
                        fila["estado_anterior"],

                    "estado_nuevo":
                        fila["estado_nuevo"],

                    "usuario_responsable_id":
                        fila["usuario_responsable_id"],

                    "observacion":
                        fila["observacion"],

                    "creado_en":
                        fila["creado_en"],
                }

                for fila in filas
            ]

    finally:

        conexion.close()


# ============================================================
# ENTREGA DE UN PEDIDO (LECTURA PARA SEGUIMIENTO)
# ============================================================

def obtener_entrega_pedido(
    pedido_id,
):
    """
    Obtiene la entrega de un pedido con:

    - cabecera de la entrega;
    - detalles específicos de la modalidad (RECOJO_LOCAL,
      DELIVERY_LOCAL, TRANSPORTISTA);
    - historial de estados de la entrega.

    Solo lectura: no modifica ningún dato.
    """

    conexion = conexion_operaciones()

    try:

        with conexion.cursor() as cursor:

            cursor.execute(
                """
                SELECT
                    id,
                    tipo_entrega,
                    costo_cobrado_cliente,
                    estado,
                    creado_en

                FROM entregas

                WHERE pedido_id = %s

                LIMIT 1
                """,
                (
                    pedido_id,
                ),
            )

            entrega = cursor.fetchone()

            if not entrega:

                return None

            entrega_id = entrega["id"]

            tipo = str(
                entrega["tipo_entrega"]
            ).upper()

            resultado = {
                "id":
                    entrega_id,

                "tipo_entrega":
                    entrega["tipo_entrega"],

                "costo_cobrado_cliente":
                    float(
                        entrega["costo_cobrado_cliente"]
                    ),

                "estado":
                    entrega["estado"],

                "creado_en":
                    entrega["creado_en"],

                "recojo":
                    None,

                "delivery":
                    None,

                "transportista":
                    None,
            }

            # ----------------------------------------------------
            # RECOJO LOCAL
            # ----------------------------------------------------

            if tipo == "RECOJO_LOCAL":

                cursor.execute(
                    """
                    SELECT
                        id,
                        punto_recojo_id,
                        nombre_punto_snapshot,
                        direccion_snapshot

                    FROM entregas_recojo

                    WHERE entrega_id = %s

                    LIMIT 1
                    """,
                    (
                        entrega_id,
                    ),
                )

                recojo = cursor.fetchone()

                if recojo:

                    resultado["recojo"] = {
                        "punto_recojo_id":
                            recojo["punto_recojo_id"],

                        "nombre_punto":
                            recojo["nombre_punto_snapshot"],

                        "direccion":
                            recojo["direccion_snapshot"],
                    }

            # ----------------------------------------------------
            # DELIVERY LOCAL
            # ----------------------------------------------------

            elif tipo == "DELIVERY_LOCAL":

                cursor.execute(
                    """
                    SELECT
                        d.distrito_id,
                        d.nombre_receptor,
                        d.telefono_receptor,
                        d.direccion,
                        d.referencia,
                        d.latitud,
                        d.longitud,
                        c.distancia_km,
                        c.costo_estimado,
                        c.estado AS cotizacion_estado

                    FROM delivery_destinos d

                    LEFT JOIN cotizaciones_delivery c
                        ON c.entrega_id = d.entrega_id

                    WHERE d.entrega_id = %s

                    LIMIT 1
                    """,
                    (
                        entrega_id,
                    ),
                )

                destino = cursor.fetchone()

                if destino:

                    resultado["delivery"] = {
                        "distrito_id":
                            destino["distrito_id"],

                        "nombre_receptor":
                            destino["nombre_receptor"],

                        "telefono_receptor":
                            destino["telefono_receptor"],

                        "direccion":
                            destino["direccion"],

                        "referencia":
                            destino["referencia"],

                        "latitud":
                            float(
                                destino["latitud"]
                            )
                            if destino["latitud"] is not None
                            else None,

                        "longitud":
                            float(
                                destino["longitud"]
                            )
                            if destino["longitud"] is not None
                            else None,

                        "distancia_km":
                            float(
                                destino["distancia_km"]
                            )
                            if destino["distancia_km"] is not None
                            else None,

                        "costo_estimado":
                            float(
                                destino["costo_estimado"]
                            )
                            if destino["costo_estimado"] is not None
                            else None,

                        "cotizacion_estado":
                            destino["cotizacion_estado"],
                    }

            # ----------------------------------------------------
            # TRANSPORTISTA
            # ----------------------------------------------------

            elif tipo == "TRANSPORTISTA_ASOCIADO":

                cursor.execute(
                    """
                    SELECT
                        e.id,
                        e.transportista_id,
                        e.servicio_transportista_id,
                        e.sucursal_destino_id,
                        e.transportista_nombre_snapshot,
                        e.servicio_nombre_snapshot,
                        e.sucursal_destino_nombre_snapshot,
                        e.direccion_destino_snapshot,
                        e.peso_estimado_gramos,
                        e.costo_estimado,
                        e.costo_cobrado_cliente,
                        e.url_seguimiento_snapshot,
                        e.estado,
                        c.distrito_destino_id

                    FROM envios_transportista e

                    LEFT JOIN cotizaciones_transportista c
                        ON c.id = e.cotizacion_id

                    WHERE e.entrega_id = %s

                    LIMIT 1
                    """,
                    (
                        entrega_id,
                    ),
                )

                envio = cursor.fetchone()

                if envio:

                    resultado["transportista"] = {
                        "envio_id":
                            envio["id"],

                        "transportista_id":
                            envio["transportista_id"],

                        "transportista_nombre":
                            envio["transportista_nombre_snapshot"],

                        "servicio_nombre":
                            envio["servicio_nombre_snapshot"],

                        "sucursal_destino":
                            envio["sucursal_destino_nombre_snapshot"],

                        "direccion_destino":
                            envio["direccion_destino_snapshot"],

                        "peso_estimado_gramos":
                            envio["peso_estimado_gramos"],

                        "costo_estimado":
                            float(
                                envio["costo_estimado"]
                            )
                            if envio["costo_estimado"] is not None
                            else None,

                        "url_seguimiento":
                            envio["url_seguimiento_snapshot"],

                        "estado":
                            envio["estado"],

                        "distrito_destino_id":
                            envio["distrito_destino_id"],
                    }

            # ----------------------------------------------------
            # HISTORIAL DE LA ENTREGA
            # ----------------------------------------------------

            cursor.execute(
                """
                SELECT
                    estado_anterior,
                    estado_nuevo,
                    usuario_responsable_id,
                    comentario,
                    creado_en

                FROM entrega_historial

                WHERE entrega_id = %s

                ORDER BY creado_en ASC
                """,
                (
                    entrega_id,
                ),
            )

            filas = cursor.fetchall()

            resultado["historial"] = [
                {
                    "estado_anterior":
                        fila["estado_anterior"],

                    "estado_nuevo":
                        fila["estado_nuevo"],

                    "usuario_responsable_id":
                        fila["usuario_responsable_id"],

                    "comentario":
                        fila["comentario"],

                    "creado_en":
                        fila["creado_en"],
                }

                for fila in filas
            ]

            return resultado

    finally:

        conexion.close()
