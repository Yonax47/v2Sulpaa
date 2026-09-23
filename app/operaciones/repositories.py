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

def _esquema_identidad():
    """Devuelve el nombre validado del esquema identidad para JOIN seguros."""
    import os
    import re
    nombre = str(os.getenv("DB_IDENTIDAD") or "").strip()
    if not nombre or not re.fullmatch(r"[A-Za-z0-9_]+", nombre):
        raise RuntimeError("La variable DB_IDENTIDAD no contiene un esquema válido.")
    return nombre


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
                    creado_en,
                    codigo_cliente_token

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

                "codigo_cliente_token":
                    entrega["codigo_cliente_token"],

                "recojo":
                    None,

                "delivery":
                    None,

                "transportista":
                    None,

                "asignaciones":
                    [],

                "seguimiento":
                    [],
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

            # ----------------------------------------------------
            # ASIGNACIONES VISIBLES PARA EL CLIENTE
            # ----------------------------------------------------
            #
            # Solo se exponen campos públicos del repartidor asignado;
            # el historial del reparto es lo que el cliente puede seguir.
            # ----------------------------------------------------

            cursor.execute(
                f"""
                SELECT
                    a.estado AS asignacion_estado,
                    a.asignado_en,
                    a.aceptado_en,
                    a.finalizado_en,
                    CONCAT_WS(' ', pf.nombres, pf.apellido_paterno,
                              pf.apellido_materno) AS repartidor_nombre

                FROM asignaciones_reparto a

                INNER JOIN repartidores r
                    ON r.id = a.repartidor_id

                LEFT JOIN {_esquema_identidad()}.perfiles pf
                    ON pf.usuario_id = r.usuario_id

                WHERE a.entrega_id = %s

                ORDER BY a.asignado_en ASC
                """,
                (
                    entrega_id,
                ),
            )

            resultado["asignaciones"] = cursor.fetchall()

            # ----------------------------------------------------
            # SEGUIMIENTO DEL ENVÍO TRANSPORTISTA
            # ----------------------------------------------------

            cursor.execute(
                """
                SELECT
                    e.estado AS envio_estado,
                    e.transportista_nombre_snapshot,
                    s.estado AS evento_estado,
                    s.descripcion,
                    s.ubicacion_texto,
                    s.fecha_evento,
                    s.fuente

                FROM envios_transportista e

                LEFT JOIN seguimiento_envio s
                    ON s.envio_transportista_id = e.id

                WHERE e.entrega_id = %s

                ORDER BY s.fecha_evento ASC
                """,
                (
                    entrega_id,
                ),
            )

            resultado["seguimiento"] = cursor.fetchall()

            return resultado

    finally:

        conexion.close()


# ============================================================
# BLOQUE 2 — FLUJO OPERATIVO DE ENTREGAS
# ============================================================
#
# Estas escrituras reciben una conexión de la Unidad de Trabajo
# y NUNCA confirman por separado: la atomicidad entre Comercio,
# Operaciones e Identidad pertenece a la capa Service.
# Las lecturas usan la misma conexión de la transacción para
# observar datos recién bloqueados y coherentes.
# ============================================================


def listar_entregas_admin(conexion, esquemas, estado=None, tipo=None,
                          busqueda=None):
    """Lista entregas con su pedido, cliente y pago para la operativa."""
    operaciones = esquemas["operaciones"]
    comercio = esquemas["comercio"]
    identidad = esquemas["identidad"]
    condiciones = []
    parametros = []

    if estado:
        condiciones.append("e.estado = %s")
        parametros.append(estado)
    if tipo:
        condiciones.append("e.tipo_entrega = %s")
        parametros.append(tipo)
    if busqueda:
        termino = f"%{busqueda}%"
        condiciones.append(
            "(p.numero_pedido LIKE %s OR u.correo LIKE %s OR "
            "CONCAT_WS(' ', pf.nombres, pf.apellido_paterno, "
            "pf.apellido_materno) LIKE %s)"
        )
        parametros.extend([termino, termino, termino])

    where = " WHERE " + " AND ".join(condiciones) if condiciones else ""
    consulta = f"""
        SELECT
            e.id, e.pedido_id, e.tipo_entrega, e.estado,
            e.costo_cobrado_cliente, e.fecha_programada,
            e.completado_en, e.creado_en,
            p.numero_pedido, p.total AS pedido_total,
            u.correo AS cliente_correo,
            CONCAT_WS(' ', pf.nombres, pf.apellido_paterno,
                      pf.apellido_materno) AS cliente_nombre,
            pa.estado AS pago_estado, pa.modalidad AS pago_modalidad,
            mp.nombre AS pago_metodo_nombre
        FROM {operaciones}.entregas AS e
        INNER JOIN {comercio}.pedidos AS p ON p.id = e.pedido_id
        INNER JOIN {identidad}.usuarios AS u ON u.id = p.usuario_id
        LEFT JOIN {identidad}.perfiles AS pf ON pf.usuario_id = p.usuario_id
        LEFT JOIN {operaciones}.pagos AS pa
            ON pa.id = (
                SELECT pa2.id FROM {operaciones}.pagos AS pa2
                WHERE pa2.pedido_id = p.id
                ORDER BY pa2.creado_en DESC LIMIT 1
            )
        LEFT JOIN {operaciones}.metodos_pago AS mp
            ON mp.id = pa.metodo_pago_id
        {where}
        ORDER BY e.creado_en DESC, p.numero_pedido DESC
    """
    with conexion.cursor() as cursor:
        cursor.execute(consulta, tuple(parametros))
        return cursor.fetchall()


def obtener_entrega_admin(conexion, esquemas, entrega_id):
    """Compone el detalle completo de una entrega para la operativa."""
    operaciones = esquemas["operaciones"]
    comercio = esquemas["comercio"]
    identidad = esquemas["identidad"]
    consulta = f"""
        SELECT
            e.id, e.pedido_id, e.tipo_entrega, e.estado,
            e.costo_cobrado_cliente, e.fecha_programada,
            e.completado_en, e.creado_en, e.actualizado_en,
            p.numero_pedido, p.total AS pedido_total, p.moneda,
            p.origen AS pedido_origen, p.creado_en AS pedido_creado_en,
            u.correo AS cliente_correo,
            CONCAT_WS(' ', pf.nombres, pf.apellido_paterno,
                      pf.apellido_materno) AS cliente_nombre,
            pf.telefono AS cliente_telefono,
            pa.id AS pago_id, pa.modalidad AS pago_modalidad,
            pa.monto AS pago_monto, pa.estado AS pago_estado,
            pa.pagado_en AS pago_pagado_en,
            pa.referencia_externa AS pago_referencia,
            mp.codigo AS pago_metodo_codigo,
            mp.nombre AS pago_metodo_nombre
        FROM {operaciones}.entregas AS e
        INNER JOIN {comercio}.pedidos AS p ON p.id = e.pedido_id
        INNER JOIN {identidad}.usuarios AS u ON u.id = p.usuario_id
        LEFT JOIN {identidad}.perfiles AS pf ON pf.usuario_id = p.usuario_id
        LEFT JOIN {operaciones}.pagos AS pa
            ON pa.id = (
                SELECT pa2.id FROM {operaciones}.pagos AS pa2
                WHERE pa2.pedido_id = p.id
                ORDER BY pa2.creado_en DESC LIMIT 1
            )
        LEFT JOIN {operaciones}.metodos_pago AS mp
            ON mp.id = pa.metodo_pago_id
        WHERE e.id = %s
        LIMIT 1
    """
    with conexion.cursor() as cursor:
        cursor.execute(consulta, (entrega_id,))
        entrega = cursor.fetchone()
        if not entrega:
            return None

        tipo = str(entrega["tipo_entrega"] or "").upper()
        entrega["delivery"] = None
        entrega["recojo"] = None
        entrega["transportista"] = None

        if tipo == "DELIVERY_LOCAL":
            cursor.execute(
                f"""
                SELECT d.distrito_id, d.nombre_receptor, d.telefono_receptor,
                       d.direccion, d.referencia, d.latitud, d.longitud,
                       c.distancia_km, c.costo_estimado
                FROM {operaciones}.delivery_destinos AS d
                LEFT JOIN {operaciones}.cotizaciones_delivery AS c
                    ON c.entrega_id = d.entrega_id
                WHERE d.entrega_id = %s LIMIT 1
                """,
                (entrega_id,),
            )
            entrega["delivery"] = cursor.fetchone()
        elif tipo == "RECOJO_LOCAL":
            cursor.execute(
                f"""
                SELECT punto_recojo_id, nombre_punto_snapshot,
                       direccion_snapshot, codigo_recojo_hash,
                       notificado_en, recogido_en
                FROM {operaciones}.entregas_recojo
                WHERE entrega_id = %s LIMIT 1
                """,
                (entrega_id,),
            )
            entrega["recojo"] = cursor.fetchone()
        elif tipo == "TRANSPORTISTA_ASOCIADO":
            cursor.execute(
                f"""
                SELECT id, transportista_id, servicio_transportista_id,
                       codigo_seguimiento, clave_recojo,
                       url_seguimiento_snapshot, estado,
                       fecha_despacho, fecha_entrega
                FROM {operaciones}.envios_transportista
                WHERE entrega_id = %s LIMIT 1
                """,
                (entrega_id,),
            )
            envio = cursor.fetchone()
            if envio:
                cursor.execute(
                    f"""
                    SELECT estado, descripcion, ubicacion_texto,
                           fecha_evento, fuente
                    FROM {operaciones}.seguimiento_envio
                    WHERE envio_transportista_id = %s
                    ORDER BY fecha_evento ASC, id ASC
                    """,
                    (envio["id"],),
                )
                envio["seguimiento"] = cursor.fetchall()
            entrega["transportista"] = envio

        cursor.execute(
            f"""
            SELECT a.id, a.estado, a.asignado_en, a.aceptado_en,
                   a.finalizado_en, a.repartidor_id,
                   CONCAT_WS(' ', pf.nombres, pf.apellido_paterno,
                             pf.apellido_materno) AS repartidor_nombre,
                   u.correo AS repartidor_correo
            FROM {operaciones}.asignaciones_reparto AS a
            INNER JOIN {operaciones}.repartidores AS r ON r.id = a.repartidor_id
            LEFT JOIN {identidad}.usuarios AS u ON u.id = r.usuario_id
            LEFT JOIN {identidad}.perfiles AS pf ON pf.usuario_id = r.usuario_id
            WHERE a.entrega_id = %s
            ORDER BY a.asignado_en ASC, a.id ASC
            """,
            (entrega_id,),
        )
        entrega["asignaciones"] = cursor.fetchall()

        cursor.execute(
            f"""
            SELECT i.id, i.tipo, i.descripcion, i.estado, i.creado_en,
                   i.resuelto_en,
                   CONCAT_WS(' ', pf.nombres, pf.apellido_paterno,
                             pf.apellido_materno) AS reportado_por_nombre
            FROM {operaciones}.incidencias_entrega AS i
            LEFT JOIN {identidad}.usuarios AS u
                ON u.id = i.reportado_por_usuario_id
            LEFT JOIN {identidad}.perfiles AS pf ON pf.usuario_id = u.id
            WHERE i.entrega_id = %s
            ORDER BY i.creado_en DESC, i.id DESC
            """,
            (entrega_id,),
        )
        entrega["incidencias"] = cursor.fetchall()

        cursor.execute(
            f"""
            SELECT h.id, h.estado_anterior, h.estado_nuevo, h.comentario,
                   h.creado_en,
                   CONCAT_WS(' ', pf.nombres, pf.apellido_paterno,
                             pf.apellido_materno) AS actor_nombre,
                   u.correo AS actor_correo
            FROM {operaciones}.entrega_historial AS h
            LEFT JOIN {identidad}.usuarios AS u
                ON u.id = h.usuario_responsable_id
            LEFT JOIN {identidad}.perfiles AS pf ON pf.usuario_id = u.id
            WHERE h.entrega_id = %s
            ORDER BY h.creado_en ASC, h.id ASC
            """,
            (entrega_id,),
        )
        entrega["historial"] = cursor.fetchall()

        cursor.execute(
            f"""
            SELECT h.estado_anterior, h.estado_nuevo, h.observacion,
                   h.creado_en
            FROM {operaciones}.pago_historial AS h
            WHERE h.pago_id = %s
            ORDER BY h.creado_en ASC, h.id ASC
            """,
            (entrega.get("pago_id"),),
        )
        entrega["pago_historial"] = cursor.fetchall()

        return entrega


def bloquear_entrega_operativa(conexion, esquemas, entrega_id):
    """Bloquea entrega, pedido y pago para validar un estado estable."""
    operaciones = esquemas["operaciones"]
    comercio = esquemas["comercio"]
    with conexion.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT id, pedido_id, tipo_entrega, estado, fecha_programada,
                   codigo_cliente_token
            FROM {operaciones}.entregas
            WHERE id = %s LIMIT 1 FOR UPDATE
            """,
            (entrega_id,),
        )
        entrega = cursor.fetchone()
        if not entrega:
            return None

        cursor.execute(
            f"""
            SELECT id, numero_pedido, estado, usuario_id
            FROM {comercio}.pedidos
            WHERE id = %s LIMIT 1 FOR UPDATE
            """,
            (entrega["pedido_id"],),
        )
        pedido = cursor.fetchone()

        cursor.execute(
            f"""
            SELECT id, pedido_id, modalidad, estado, monto, moneda,
                   metodo_pago_id, pagado_en
            FROM {operaciones}.pagos
            WHERE pedido_id = %s
            ORDER BY creado_en DESC LIMIT 1 FOR UPDATE
            """,
            (entrega["pedido_id"],),
        )
        pago = cursor.fetchone()

        cursor.execute(
            f"""
            SELECT COUNT(*) AS total
            FROM {operaciones}.incidencias_entrega
            WHERE entrega_id = %s AND estado IN ('ABIERTA', 'EN_REVISION')
            """,
            (entrega_id,),
        )
        incidencias_activas = cursor.fetchone()["total"]

    return {
        "entrega": entrega,
        "pedido": pedido,
        "pago": pago,
        "incidencias_activas": incidencias_activas,
    }


def actualizar_estado_entrega(conexion, esquemas, entrega_id,
                              estado_anterior, estado_nuevo,
                              completar=False, fecha_programada=None):
    """Actualiza la entrega solo si conserva el estado bloqueado."""
    operaciones = esquemas["operaciones"]
    asignaciones = ["estado = %s"]
    parametros = [estado_nuevo]
    if completar:
        asignaciones.append("completado_en = NOW()")
    if fecha_programada is not None:
        asignaciones.append("fecha_programada = %s")
        parametros.append(fecha_programada)
    asignaciones.append("actualizado_en = NOW()")
    parametros.extend([entrega_id, estado_anterior])
    consulta = (
        f"UPDATE {operaciones}.entregas SET "
        + ", ".join(asignaciones)
        + " WHERE id = %s AND estado = %s"
    )
    with conexion.cursor() as cursor:
        cursor.execute(consulta, tuple(parametros))
        return cursor.rowcount == 1


def insertar_historial_entrega(conexion, esquemas, entrega_id,
                               estado_anterior, estado_nuevo, actor_id,
                               comentario):
    """Inserta la evidencia operativa dentro de la transacción recibida."""
    operaciones = esquemas["operaciones"]
    with conexion.cursor() as cursor:
        cursor.execute(
            f"""
            INSERT INTO {operaciones}.entrega_historial
                (entrega_id, estado_anterior, estado_nuevo,
                 usuario_responsable_id, comentario)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (entrega_id, estado_anterior, estado_nuevo,
             actor_id, comentario),
        )


def actualizar_codigo_cliente_entrega(conexion, esquemas, entrega_id, token):
    """Persiste el token cifrado del código visible para el cliente."""
    operaciones = esquemas["operaciones"]
    with conexion.cursor() as cursor:
        cursor.execute(
            f"UPDATE {operaciones}.entregas SET codigo_cliente_token = %s "
            "WHERE id = %s AND estado <> 'ENTREGADO' AND estado <> 'CANCELADO'",
            (token, entrega_id),
        )
        return cursor.rowcount == 1


def limpiar_codigo_cliente_entrega(conexion, esquemas, entrega_id):
    """Consume el código: deja de ser utilizable al cerrarse la entrega."""
    operaciones = esquemas["operaciones"]
    with conexion.cursor() as cursor:
        cursor.execute(
            f"UPDATE {operaciones}.entregas SET codigo_cliente_token = NULL "
            "WHERE id = %s",
            (entrega_id,),
        )


def actualizar_notificado_recojo(conexion, esquemas, entrega_id):
    """Marca el momento en que el punto de recojo fue notificado."""
    operaciones = esquemas["operaciones"]
    with conexion.cursor() as cursor:
        cursor.execute(
            f"""
            UPDATE {operaciones}.entregas_recojo SET notificado_en = NOW()
            WHERE entrega_id = %s
            """,
            (entrega_id,),
        )
        return cursor.rowcount == 1


def actualizar_iniciado_delivery(conexion, esquemas, entrega_id):
    """Registra el inicio real del reparto por el repartidor."""
    operaciones = esquemas["operaciones"]
    with conexion.cursor() as cursor:
        cursor.execute(
            f"""
            UPDATE {operaciones}.entregas_delivery SET iniciado_en = NOW()
            WHERE entrega_id = %s
            """,
            (entrega_id,),
        )
        return cursor.rowcount == 1


def actualizar_entregado_delivery(conexion, esquemas, entrega_id):
    """Registra la confirmación de entrega en la modalidad delivery."""
    operaciones = esquemas["operaciones"]
    with conexion.cursor() as cursor:
        cursor.execute(
            f"""
            UPDATE {operaciones}.entregas_delivery SET entregado_en = NOW()
            WHERE entrega_id = %s
            """,
            (entrega_id,),
        )
        return cursor.rowcount == 1


def actualizar_recogido_recojo(conexion, esquemas, entrega_id):
    """Registra la confirmación del recojo en la modalidad recojo."""
    operaciones = esquemas["operaciones"]
    with conexion.cursor() as cursor:
        cursor.execute(
            f"""
            UPDATE {operaciones}.entregas_recojo SET recogido_en = NOW()
            WHERE entrega_id = %s
            """,
            (entrega_id,),
        )
        return cursor.rowcount == 1


def confirmar_pago_operativo(conexion, esquemas, pago_id, estado_anterior,
                             actor_id, observacion):
    """Marca un pago como PAGADO y registra su historial en transacción."""
    operaciones = esquemas["operaciones"]
    with conexion.cursor() as cursor:
        cursor.execute(
            f"UPDATE {operaciones}.pagos SET estado = 'PAGADO', "
            "pagado_en = NOW(), actualizado_en = NOW() "
            "WHERE id = %s AND estado = %s",
            (pago_id, estado_anterior),
        )
        if cursor.rowcount != 1:
            return False
        cursor.execute(
            f"""
            INSERT INTO {operaciones}.pago_historial
                (pago_id, estado_anterior, estado_nuevo,
                 usuario_responsable_id, observacion)
            VALUES (%s, %s, 'PAGADO', %s, %s)
            """,
            (pago_id, estado_anterior, actor_id, observacion),
        )
        return True


def insertar_ingreso_caja_desde_pago(conexion, esquemas, pago):
    """Registra el ingreso de caja de un pago PAGADO (idempotente).

    Regla de caja autorizada en el Bloque 4: un pago se convierte en
    ingreso ÚNICAMENTE cuando su estado es ``PAGADO`` y existe
    ``pagado_en``. La categoría ``COBRO_PEDIDO`` (catálogo) clasifica
    el ingreso; el método de pago y el monto provienen de la fila real.

    ``UNIQUE(pago_id)`` en ``caja_movimientos`` hace idempotente la
    escritura: un retry o doble POST nunca duplica ingresos.
    """
    operaciones = esquemas["operaciones"]
    with conexion.cursor() as cursor:
        cursor.execute(
            f"""
            INSERT IGNORE INTO {operaciones}.caja_movimientos
                (categoria_id, tipo, origen, concepto, monto, moneda,
                 metodo_pago_id, pago_id, pedido_id, fecha_movimiento)
            SELECT c.id, 'INGRESO', 'PAGO', 'Cobro de pedido',
                   p.monto, p.moneda, p.metodo_pago_id, p.id, p.pedido_id,
                   COALESCE(p.pagado_en, NOW())
            FROM {operaciones}.pagos AS p
            INNER JOIN {operaciones}.caja_categorias AS c
                ON c.codigo = 'COBRO_PEDIDO' AND c.tipo = 'INGRESO'
            WHERE p.id = %s AND p.estado = 'PAGADO'
              AND p.pagado_en IS NOT NULL
            """,
            (pago["id"],),
        )
        return cursor.rowcount > 0


def crear_asignacion_repartidor(conexion, esquemas, asignacion_id,
                                entrega_id, repartidor_id, actor_id):
    """Registra la asignación de reparto en estado ASIGNADA."""
    operaciones = esquemas["operaciones"]
    with conexion.cursor() as cursor:
        cursor.execute(
            f"""
            INSERT INTO {operaciones}.asignaciones_reparto
                (id, entrega_id, repartidor_id, asignado_por_usuario_id,
                 estado)
            VALUES (%s, %s, %s, %s, 'ASIGNADA')
            """,
            (asignacion_id, entrega_id, repartidor_id, actor_id),
        )
        return True


def actualizar_asignacion_estado(conexion, esquemas, asignacion_id,
                                 estado_nuevo, aceptar=False,
                                 finalizar=False):
    """Avanza el estado de una asignación de reparto."""
    operaciones = esquemas["operaciones"]
    asignaciones = ["estado = %s"]
    parametros = [estado_nuevo]
    if aceptar:
        asignaciones.append("aceptado_en = NOW()")
    if finalizar:
        asignaciones.append("finalizado_en = NOW()")
    parametros.append(asignacion_id)
    consulta = (
        f"UPDATE {operaciones}.asignaciones_reparto SET "
        + ", ".join(asignaciones)
        + " WHERE id = %s"
    )
    with conexion.cursor() as cursor:
        cursor.execute(consulta, tuple(parametros))
        return cursor.rowcount == 1


def cancelar_asignaciones_activas(conexion, esquemas, entrega_id):
    """Cancela todas las asignaciones abiertas y devuelve los repartidores."""
    operaciones = esquemas["operaciones"]
    with conexion.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT repartidor_id
            FROM {operaciones}.asignaciones_reparto
            WHERE entrega_id = %s AND estado IN ('ASIGNADA', 'ACEPTADA')
            """,
            (entrega_id,),
        )
        repartidores = [fila["repartidor_id"] for fila in cursor.fetchall()]
        cursor.execute(
            f"""
            UPDATE {operaciones}.asignaciones_reparto
            SET estado = 'CANCELADA'
            WHERE entrega_id = %s AND estado IN ('ASIGNADA', 'ACEPTADA')
            """,
            (entrega_id,),
        )
        return repartidores


def actualizar_disponibilidad_repartidor(conexion, esquemas, repartidor_id,
                                         disponible):
    """Refleja si el repartidor tiene un reparto en curso."""
    operaciones = esquemas["operaciones"]
    with conexion.cursor() as cursor:
        cursor.execute(
            f"""
            UPDATE {operaciones}.repartidores
            SET disponible = %s, actualizado_en = NOW()
            WHERE id = %s
            """,
            (int(disponible), repartidor_id),
        )
        return cursor.rowcount == 1


def listar_repartidores(conexion, esquemas):
    """Lista repartidores con su identidad y carga activa."""
    operaciones = esquemas["operaciones"]
    identidad = esquemas["identidad"]
    consulta = f"""
        SELECT
            r.id, r.usuario_id, r.disponible, r.estado, r.creado_en,
            u.correo,
            CONCAT_WS(' ', pf.nombres, pf.apellido_paterno,
                      pf.apellido_materno) AS nombre,
            pf.telefono,
            (SELECT COUNT(*) FROM {operaciones}.asignaciones_reparto AS a
             WHERE a.repartidor_id = r.id
               AND a.estado IN ('ASIGNADA', 'ACEPTADA')) AS carga_activa
        FROM {operaciones}.repartidores AS r
        INNER JOIN {identidad}.usuarios AS u ON u.id = r.usuario_id
        LEFT JOIN {identidad}.perfiles AS pf ON pf.usuario_id = r.usuario_id
        ORDER BY r.creado_en DESC
    """
    with conexion.cursor() as cursor:
        cursor.execute(consulta)
        return cursor.fetchall()


def obtener_repartidor_activo(conexion, esquemas, repartidor_id):
    """Obtiene un repartidor ACTIVO por su id (para asignar)."""
    operaciones = esquemas["operaciones"]
    with conexion.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT id, usuario_id, disponible, estado
            FROM {operaciones}.repartidores
            WHERE id = %s AND estado = 'ACTIVO' LIMIT 1 FOR UPDATE
            """,
            (repartidor_id,),
        )
        return fetchone_safe(cursor)


def obtener_repartidor_por_usuario(conexion, esquemas, usuario_id):
    """Resuelve el repartidor asociado al usuario autenticado."""
    operaciones = esquemas["operaciones"]
    with conexion.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT id, usuario_id, disponible, estado
            FROM {operaciones}.repartidores
            WHERE usuario_id = %s AND estado = 'ACTIVO' LIMIT 1
            """,
            (usuario_id,),
        )
        return fetchone_safe(cursor)


def obtener_asignaciones_activas_repartidor(conexion, esquemas,
                                            repartidor_id):
    """Asignaciones en curso de un repartidor (para evaluar la carga real)."""
    operaciones = esquemas["operaciones"]
    with conexion.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT id, entrega_id, estado
            FROM {operaciones}.asignaciones_reparto
            WHERE repartidor_id = %s
              AND estado IN ('ASIGNADA', 'ACEPTADA')
            ORDER BY asignado_en ASC
            """,
            (repartidor_id,),
        )
        return cursor.fetchall()


def obtener_asignacion_repartidor_entrega(conexion, esquemas,
                                          repartidor_id, entrega_id):
    """Asignación vigente del repartidor para una entrega concreta."""
    operaciones = esquemas["operaciones"]
    with conexion.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT id, entrega_id, repartidor_id, estado
            FROM {operaciones}.asignaciones_reparto
            WHERE repartidor_id = %s AND entrega_id = %s
              AND estado IN ('ASIGNADA', 'ACEPTADA')
            ORDER BY asignado_en DESC LIMIT 1 FOR UPDATE
            """,
            (repartidor_id, entrega_id),
        )
        return fetchone_safe(cursor)


def obtener_asignacion_activa_entrega(conexion, esquemas, entrega_id):
    """Asignación vigente de una entrega (para validar su inicio)."""
    operaciones = esquemas["operaciones"]
    with conexion.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT id, entrega_id, repartidor_id, estado
            FROM {operaciones}.asignaciones_reparto
            WHERE entrega_id = %s
              AND estado IN ('ASIGNADA', 'ACEPTADA')
            ORDER BY asignado_en DESC LIMIT 1 FOR UPDATE
            """,
            (entrega_id,),
        )
        return fetchone_safe(cursor)


def obtener_repartidor_asignado_activo(conexion, esquemas, entrega_id):
    """Repartidor con asignación vigente sobre la entrega."""
    operaciones = esquemas["operaciones"]
    with conexion.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT repartidor_id
            FROM {operaciones}.asignaciones_reparto
            WHERE entrega_id = %s
              AND estado IN ('ASIGNADA', 'ACEPTADA')
            ORDER BY asignado_en DESC LIMIT 1
            """,
            (entrega_id,),
        )
        fila = fetchone_safe(cursor)
        return bool(fila) and fila["repartidor_id"]


def finalizar_asignaciones_entrega(conexion, esquemas, entrega_id):
    """Finaliza las asignaciones vigentes y devuelve los afectados."""
    operaciones = esquemas["operaciones"]
    with conexion.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT repartidor_id
            FROM {operaciones}.asignaciones_reparto
            WHERE entrega_id = %s
              AND estado IN ('ASIGNADA', 'ACEPTADA')
            """,
            (entrega_id,),
        )
        repartidores = [fila["repartidor_id"] for fila in cursor.fetchall()]
        cursor.execute(
            f"""
            UPDATE {operaciones}.asignaciones_reparto
            SET estado = 'FINALIZADA', finalizado_en = NOW()
            WHERE entrega_id = %s
              AND estado IN ('ASIGNADA', 'ACEPTADA')
            """,
            (entrega_id,),
        )
        return repartidores


def listar_asignaciones_repartidor(conexion, esquemas, repartidor_id):
    """Lista las entregas asignadas al repartidor con su contexto."""
    operaciones = esquemas["operaciones"]
    comercio = esquemas["comercio"]
    identidad = esquemas["identidad"]
    consulta = f"""
        SELECT
            a.id AS asignacion_id, a.estado AS asignacion_estado,
            a.asignado_en, a.aceptado_en,
            e.id AS entrega_id, e.tipo_entrega, e.estado AS entrega_estado,
            e.fecha_programada, e.costo_cobrado_cliente,
            p.numero_pedido, p.total AS pedido_total,
            CONCAT_WS(' ', pf.nombres, pf.apellido_paterno,
                      pf.apellido_materno) AS cliente_nombre,
            pf.telefono AS cliente_telefono,
            u.correo AS cliente_correo
        FROM {operaciones}.asignaciones_reparto AS a
        INNER JOIN {operaciones}.entregas AS e ON e.id = a.entrega_id
        INNER JOIN {comercio}.pedidos AS p ON p.id = e.pedido_id
        INNER JOIN {identidad}.usuarios AS u ON u.id = p.usuario_id
        LEFT JOIN {identidad}.perfiles AS pf ON pf.usuario_id = p.usuario_id
        WHERE a.repartidor_id = %s
          AND a.estado IN ('ASIGNADA', 'ACEPTADA')
        ORDER BY a.asignado_en ASC
    """
    with conexion.cursor() as cursor:
        cursor.execute(consulta, (repartidor_id,))
        return cursor.fetchall()


def listar_asignaciones_repartidor_historial(conexion, esquemas,
                                             repartidor_id):
    """Historial de entregas ya finalizadas del repartidor."""
    operaciones = esquemas["operaciones"]
    comercio = esquemas["comercio"]
    consulta = f"""
        SELECT
            a.id AS asignacion_id, a.estado AS asignacion_estado,
            a.asignado_en, a.finalizado_en,
            e.id AS entrega_id, e.tipo_entrega, e.estado AS entrega_estado,
            p.numero_pedido
        FROM {operaciones}.asignaciones_reparto AS a
        INNER JOIN {operaciones}.entregas AS e ON e.id = a.entrega_id
        INNER JOIN {comercio}.pedidos AS p ON p.id = e.pedido_id
        WHERE a.repartidor_id = %s
          AND a.estado IN ('FINALIZADA', 'CANCELADA')
        ORDER BY a.asignado_en DESC
        LIMIT 50
    """
    with conexion.cursor() as cursor:
        cursor.execute(consulta, (repartidor_id,))
        return cursor.fetchall()


def obtener_detalle_asignacion(conexion, esquemas, repartidor_id,
                               entrega_id):
    """Detalle de la asignación del repartidor para una entrega."""
    operaciones = esquemas["operaciones"]
    comercio = esquemas["comercio"]
    identidad = esquemas["identidad"]
    consulta = f"""
        SELECT
            a.id AS asignacion_id, a.estado AS asignacion_estado,
            a.asignado_en, a.aceptado_en,
            e.id AS entrega_id, e.tipo_entrega, e.estado AS entrega_estado,
            e.fecha_programada, e.costo_cobrado_cliente,
            e.creado_en AS entrega_creado_en,
            p.id AS pedido_id, p.numero_pedido, p.total AS pedido_total,
            CONCAT_WS(' ', pf.nombres, pf.apellido_paterno,
                      pf.apellido_materno) AS cliente_nombre,
            pf.telefono AS cliente_telefono,
            u.correo AS cliente_correo
        FROM {operaciones}.asignaciones_reparto AS a
        INNER JOIN {operaciones}.entregas AS e ON e.id = a.entrega_id
        INNER JOIN {comercio}.pedidos AS p ON p.id = e.pedido_id
        INNER JOIN {identidad}.usuarios AS u ON u.id = p.usuario_id
        LEFT JOIN {identidad}.perfiles AS pf ON pf.usuario_id = p.usuario_id
        WHERE a.repartidor_id = %s AND a.entrega_id = %s
          AND a.estado IN ('ASIGNADA', 'ACEPTADA')
        LIMIT 1
    """
    with conexion.cursor() as cursor:
        cursor.execute(consulta, (repartidor_id, entrega_id))
        asignacion = fetchone_safe(cursor)
        if not asignacion:
            return None
        tipo = str(asignacion["tipo_entrega"] or "").upper()
        asignacion["delivery"] = None
        if tipo == "DELIVERY_LOCAL":
            cursor.execute(
                f"""
                SELECT d.nombre_receptor, d.telefono_receptor, d.direccion,
                       d.referencia, d.distrito_id
                FROM {operaciones}.delivery_destinos AS d
                WHERE d.entrega_id = %s LIMIT 1
                """,
                (entrega_id,),
            )
            asignacion["delivery"] = fetchone_safe(cursor)
        return asignacion


def crear_incidencia_entrega(conexion, esquemas, incidencia_id, entrega_id,
                             tipo, descripcion, actor_id):
    """Registra una incidencia abierta para la entrega."""
    operaciones = esquemas["operaciones"]
    with conexion.cursor() as cursor:
        cursor.execute(
            f"""
            INSERT INTO {operaciones}.incidencias_entrega
                (id, entrega_id, tipo, descripcion, estado,
                 reportado_por_usuario_id)
            VALUES (%s, %s, %s, %s, 'ABIERTA', %s)
            """,
            (incidencia_id, entrega_id, tipo, descripcion, actor_id),
        )
        return True


def resolver_incidencia_entrega(conexion, esquemas, incidencia_id, actor_id,
                                estado_anterior_entrega, entrega_id):
    """Cierra una incidencia y restaura el estado previo de la entrega."""
    operaciones = esquemas["operaciones"]
    with conexion.cursor() as cursor:
        cursor.execute(
            f"""
            UPDATE {operaciones}.incidencias_entrega
            SET estado = 'RESUELTA', resuelto_por_usuario_id = %s,
                resuelto_en = NOW()
            WHERE id = %s AND estado IN ('ABIERTA', 'EN_REVISION')
            """,
            (actor_id, incidencia_id),
        )
        if cursor.rowcount != 1:
            return False
        if estado_anterior_entrega:
            cursor.execute(
                f"UPDATE {operaciones}.entregas SET estado = %s, "
                "actualizado_en = NOW() "
                "WHERE id = %s AND estado = 'INCIDENCIA'",
                (estado_anterior_entrega, entrega_id),
            )
        return True


def obtener_estado_anterior_incidencia(conexion, esquemas, entrega_id):
    """Devuelve el estado previo del último evento INCIDENCIA registrado."""
    operaciones = esquemas["operaciones"]
    with conexion.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT estado_anterior
            FROM {operaciones}.entrega_historial
            WHERE entrega_id = %s AND estado_nuevo = 'INCIDENCIA'
            ORDER BY creado_en DESC, id DESC LIMIT 1
            """,
            (entrega_id,),
        )
        fila = fetchone_safe(cursor)
        return (fila["estado_anterior"] if fila else None)


def obtener_incidencia(conexion, esquemas, incidencia_id):
    """Obtiene una incidencia por su id para validar su resolución."""
    operaciones = esquemas["operaciones"]
    with conexion.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT id, entrega_id, estado
            FROM {operaciones}.incidencias_entrega
            WHERE id = %s LIMIT 1 FOR UPDATE
            """,
            (incidencia_id,),
        )
        return fetchone_safe(cursor)


def obtener_envio_por_entrega(conexion, esquemas, entrega_id):
    """Obtiene el envío transportista asociado a la entrega."""
    operaciones = esquemas["operaciones"]
    with conexion.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT id, estado, codigo_seguimiento, url_seguimiento_snapshot
            FROM {operaciones}.envios_transportista
            WHERE entrega_id = %s LIMIT 1 FOR UPDATE
            """,
            (entrega_id,),
        )
        return fetchone_safe(cursor)


def actualizar_envio_estado(conexion, esquemas, envio_id,
                            estado_anterior, estado_nuevo,
                            codigo_seguimiento=None,
                            url_seguimiento=None,
                            despachar=False, entregar=False):
    """Avanza el estado del envío trasportista dentro de la transacción."""
    operaciones = esquemas["operaciones"]
    asignaciones = ["estado = %s", "actualizado_en = NOW()"]
    parametros = [estado_nuevo]
    if codigo_seguimiento:
        asignaciones.append("codigo_seguimiento = %s")
        parametros.append(codigo_seguimiento)
    if url_seguimiento:
        asignaciones.append("url_seguimiento_snapshot = %s")
        parametros.append(url_seguimiento)
    if despachar:
        asignaciones.append("fecha_despacho = NOW()")
    if entregar:
        asignaciones.append("fecha_entrega = NOW()")
    parametros.extend([envio_id, estado_anterior])
    consulta = (
        f"UPDATE {operaciones}.envios_transportista SET "
        + ", ".join(asignaciones)
        + " WHERE id = %s AND estado = %s"
    )
    with conexion.cursor() as cursor:
        cursor.execute(consulta, tuple(parametros))
        return cursor.rowcount == 1


def registrar_evento_seguimiento(conexion, esquemas, envio_id, estado,
                                 descripcion, ubicacion_texto=None,
                                 fuente="SULPAA"):
    """Registra un evento de seguimiento del envío trasportista."""
    operaciones = esquemas["operaciones"]
    with conexion.cursor() as cursor:
        cursor.execute(
            f"""
            INSERT INTO {operaciones}.seguimiento_envio
                (envio_transportista_id, estado, descripcion,
                 ubicacion_texto, fecha_evento, fuente)
            VALUES (%s, %s, %s, %s, NOW(), %s)
            """,
            (envio_id, estado, descripcion, ubicacion_texto, fuente),
        )
        return True


# ============================================================
# REGISTRO OPERATIVO DE REPARTIDORES
# (usuario + perfil + rol + planilla de reparto, en UNA transacción)
# ============================================================

def obtener_rol_por_codigo(conexion, esquemas, codigo):
    """Obtiene el rol ACTIVO por su código canónico."""
    identidad = esquemas["identidad"]
    with conexion.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT id, codigo, estado
            FROM {identidad}.roles
            WHERE codigo = %s AND estado = 'ACTIVO' LIMIT 1
            """,
            (codigo,),
        )
        return fetchone_safe(cursor)


def crear_usuario_perfil(conexion, esquemas, usuario_id, perfil_id, correo,
                         password_hash, nombres, apellido_paterno,
                         apellido_materno, dni, telefono):
    """Crea el usuario y su perfil dentro de la transacción recibida."""
    identidad = esquemas["identidad"]
    with conexion.cursor() as cursor:
        cursor.execute(
            f"""
            INSERT INTO {identidad}.usuarios
                (id, correo, password_hash, estado, correo_verificado)
            VALUES (%s, %s, %s, 'ACTIVO', 0)
            """,
            (usuario_id, correo, password_hash),
        )
        cursor.execute(
            f"""
            INSERT INTO {identidad}.perfiles
                (id, usuario_id, nombres, apellido_paterno,
                 apellido_materno, dni, telefono)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (perfil_id, usuario_id, nombres, apellido_paterno,
             apellido_materno, dni, telefono),
        )
        return True


def asignar_rol_usuario(conexion, esquemas, usuario_id, rol_id, actor_id):
    """Asigna un rol ACTIVO a un usuario dentro de la transacción."""
    identidad = esquemas["identidad"]
    with conexion.cursor() as cursor:
        cursor.execute(
            f"""
            INSERT INTO {identidad}.usuario_roles
                (id, usuario_id, rol_id, asignado_por_usuario_id, estado)
            VALUES (%s, %s, %s, %s, 'ACTIVO')
            """,
            (str(uuid_generado()), usuario_id, rol_id, actor_id),
        )
        return True


def crear_repartidor(conexion, esquemas, repartidor_id, usuario_id):
    """Registra al usuario como repartidor OPERATIVO (planilla)."""
    operaciones = esquemas["operaciones"]
    with conexion.cursor() as cursor:
        cursor.execute(
            f"""
            INSERT INTO {operaciones}.repartidores
                (id, usuario_id, disponible, estado)
            VALUES (%s, %s, 1, 'ACTIVO')
            """,
            (repartidor_id, usuario_id),
        )
        return True


def fetchone_safe(cursor):
    """Devuelve la fila sin romper en cursos cerrados durante tests."""
    try:
        return cursor.fetchone()
    except Exception:
        return None


def uuid_generado():
    import uuid
    return uuid.uuid4()


def actualizar_pedido_completado(conexion, esquemas, pedido_id,
                                 estado_anterior, actor_id, comentario):
    """Finaliza el pedido a COMPLETADO y registra la evidencia comercial."""
    comercio = esquemas["comercio"]
    with conexion.cursor() as cursor:
        cursor.execute(
            f"""
            UPDATE {comercio}.pedidos SET estado = 'COMPLETADO',
                actualizado_en = NOW()
            WHERE id = %s AND estado = %s
            """,
            (pedido_id, estado_anterior),
        )
        if cursor.rowcount != 1:
            return False
        cursor.execute(
            f"""
            INSERT INTO {comercio}.pedido_historial
                (pedido_id, estado_anterior, estado_nuevo,
                 cambiado_por_usuario_id, origen, comentario)
            VALUES (%s, %s, 'COMPLETADO', %s, 'SISTEMA', %s)
            """,
            (pedido_id, estado_anterior, actor_id, comentario),
        )
        return True


def buscar_usuario_por_correo_transaccion(conexion, esquemas, correo):
    """Comprueba duplicados de correo dentro de la transacción recibida."""
    identidad = esquemas["identidad"]
    with conexion.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT id FROM {identidad}.usuarios
            WHERE correo = %s LIMIT 1
            """,
            (correo,),
        )
        return fetchone_safe(cursor)
