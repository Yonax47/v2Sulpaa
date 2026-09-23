"""Acceso SQL del módulo administrativo de pedidos.

Las lecturas abren conexiones breves. Las escrituras reciben una conexión de
la Unidad de Trabajo y nunca ejecutan commit: la atomicidad entre Comercio y
Operaciones pertenece a la capa Service.
"""


def listar_pedidos(conexion, esquemas, busqueda=None, estado=None,
                   fecha_desde=None, fecha_hasta=None):
    """Lista pedidos reales con su cliente, pago y entrega asociados."""
    comercio = esquemas["comercio"]
    operaciones = esquemas["operaciones"]
    identidad = esquemas["identidad"]
    condiciones = []
    parametros = []

    if busqueda:
        termino = f"%{busqueda}%"
        condiciones.append(
            "(p.numero_pedido LIKE %s OR u.correo LIKE %s OR "
            "CONCAT_WS(' ', pf.nombres, pf.apellido_paterno, "
            "pf.apellido_materno) LIKE %s)"
        )
        parametros.extend([termino, termino, termino])
    if estado:
        condiciones.append("p.estado = %s")
        parametros.append(estado)
    if fecha_desde:
        condiciones.append("DATE(p.creado_en) >= %s")
        parametros.append(fecha_desde)
    if fecha_hasta:
        condiciones.append("DATE(p.creado_en) <= %s")
        parametros.append(fecha_hasta)

    where = " WHERE " + " AND ".join(condiciones) if condiciones else ""
    consulta = f"""
        SELECT
            p.id, p.numero_pedido, p.usuario_id, p.total, p.moneda,
            p.estado, p.creado_en,
            u.correo AS cliente_correo,
            CONCAT_WS(' ', pf.nombres, pf.apellido_paterno,
                      pf.apellido_materno) AS cliente_nombre,
            pa.estado AS pago_estado, pa.modalidad AS pago_modalidad,
            mp.nombre AS pago_metodo,
            e.tipo_entrega, e.estado AS entrega_estado
        FROM {comercio}.pedidos AS p
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
        LEFT JOIN {operaciones}.entregas AS e ON e.pedido_id = p.id
        {where}
        ORDER BY p.creado_en DESC, p.numero_pedido DESC
    """
    with conexion.cursor() as cursor:
        cursor.execute(consulta, tuple(parametros))
        return cursor.fetchall()


def obtener_cabecera_pedido(conexion, esquemas, pedido_id):
    """Obtiene la cabecera administrativa y datos mínimos del cliente."""
    comercio = esquemas["comercio"]
    operaciones = esquemas["operaciones"]
    identidad = esquemas["identidad"]
    consulta = f"""
        SELECT
            p.id, p.numero_pedido, p.usuario_id, p.origen, p.subtotal,
            p.descuento_total, p.costo_entrega, p.total, p.moneda,
            p.estado, p.creado_en, p.actualizado_en,
            u.correo AS cliente_correo,
            CONCAT_WS(' ', pf.nombres, pf.apellido_paterno,
                      pf.apellido_materno) AS cliente_nombre,
            pf.telefono AS cliente_telefono,
            pa.id AS pago_id, pa.modalidad AS pago_modalidad,
            pa.monto AS pago_monto, pa.moneda AS pago_moneda,
            pa.estado AS pago_estado,
            pa.referencia_externa AS pago_referencia,
            mp.codigo AS pago_metodo_codigo,
            mp.nombre AS pago_metodo_nombre,
            e.id AS entrega_id, e.tipo_entrega,
            e.estado AS entrega_estado,
            e.costo_cobrado_cliente AS entrega_costo
        FROM {comercio}.pedidos AS p
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
        LEFT JOIN {operaciones}.entregas AS e ON e.pedido_id = p.id
        WHERE p.id = %s
        LIMIT 1
    """
    with conexion.cursor() as cursor:
        cursor.execute(consulta, (pedido_id,))
        return cursor.fetchone()


def obtener_productos_pedido(conexion, esquemas, pedido_id):
    """Lee los snapshots de productos y composiciones del pedido."""
    comercio = esquemas["comercio"]
    with conexion.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT id AS pedido_detalle_id, nombre_articulo, cantidad,
                   precio_unitario, descuento_unitario, subtotal_linea
            FROM {comercio}.pedido_detalles
            WHERE pedido_id = %s
            ORDER BY id ASC
            """,
            (pedido_id,),
        )
        productos = cursor.fetchall()
        cursor.execute(
            f"""
            SELECT pc.pedido_detalle_id, pc.nombre_variante, pc.cantidad
            FROM {comercio}.pedido_composiciones AS pc
            INNER JOIN {comercio}.pedido_detalles AS pd
                ON pd.id = pc.pedido_detalle_id
            WHERE pd.pedido_id = %s
            ORDER BY pc.pedido_detalle_id, pc.nombre_variante
            """,
            (pedido_id,),
        )
        composiciones = cursor.fetchall()

    por_detalle = {}
    for composicion in composiciones:
        por_detalle.setdefault(composicion["pedido_detalle_id"], []).append(
            composicion
        )
    for producto in productos:
        producto["composicion"] = por_detalle.get(
            producto["pedido_detalle_id"], []
        )
    return productos


def obtener_historial_pedido(conexion, esquemas, pedido_id):
    """Lee el historial comercial y resuelve el actor cuando existe."""
    comercio = esquemas["comercio"]
    identidad = esquemas["identidad"]
    consulta = f"""
        SELECT
            h.id, h.estado_anterior, h.estado_nuevo, h.origen,
            h.comentario, h.creado_en, h.cambiado_por_usuario_id,
            u.correo AS actor_correo,
            CONCAT_WS(' ', pf.nombres, pf.apellido_paterno,
                      pf.apellido_materno) AS actor_nombre
        FROM {comercio}.pedido_historial AS h
        LEFT JOIN {identidad}.usuarios AS u
            ON u.id = h.cambiado_por_usuario_id
        LEFT JOIN {identidad}.perfiles AS pf ON pf.usuario_id = u.id
        WHERE h.pedido_id = %s
        ORDER BY h.creado_en ASC, h.id ASC
    """
    with conexion.cursor() as cursor:
        cursor.execute(consulta, (pedido_id,))
        return cursor.fetchall()


def obtener_entrega_detalle(conexion, esquemas, entrega_id, tipo_entrega):
    """Lee únicamente los datos propios de la modalidad existente."""
    if not entrega_id:
        return None
    operaciones = esquemas["operaciones"]
    tipo = str(tipo_entrega or "").upper()
    with conexion.cursor() as cursor:
        if tipo == "RECOJO_LOCAL":
            cursor.execute(
                f"""
                SELECT nombre_punto_snapshot AS nombre,
                       direccion_snapshot AS direccion
                FROM {operaciones}.entregas_recojo
                WHERE entrega_id = %s LIMIT 1
                """,
                (entrega_id,),
            )
        elif tipo == "DELIVERY_LOCAL":
            cursor.execute(
                f"""
                SELECT direccion, referencia, nombre_receptor,
                       telefono_receptor, distrito_id
                FROM {operaciones}.delivery_destinos
                WHERE entrega_id = %s LIMIT 1
                """,
                (entrega_id,),
            )
        elif tipo == "TRANSPORTISTA_ASOCIADO":
            cursor.execute(
                f"""
                SELECT transportista_nombre_snapshot AS transportista,
                       servicio_nombre_snapshot AS servicio,
                       sucursal_destino_nombre_snapshot AS sucursal,
                       direccion_destino_snapshot AS direccion
                FROM {operaciones}.envios_transportista
                WHERE entrega_id = %s LIMIT 1
                """,
                (entrega_id,),
            )
        else:
            return None
        return cursor.fetchone()


def bloquear_contexto_operativo(conexion, esquemas, pedido_id):
    """Bloquea pedido, pago y entrega para validar un estado estable."""
    comercio = esquemas["comercio"]
    operaciones = esquemas["operaciones"]
    with conexion.cursor() as cursor:
        cursor.execute(
            f"SELECT id, numero_pedido, estado FROM {comercio}.pedidos "
            "WHERE id = %s LIMIT 1 FOR UPDATE",
            (pedido_id,),
        )
        pedido = cursor.fetchone()
        if not pedido:
            return None

        cursor.execute(
            f"""
            SELECT id, modalidad, estado, monto
            FROM {operaciones}.pagos
            WHERE pedido_id = %s
            ORDER BY creado_en DESC LIMIT 1 FOR UPDATE
            """,
            (pedido_id,),
        )
        pago = cursor.fetchone()
        cursor.execute(
            f"""
            SELECT id, tipo_entrega, estado
            FROM {operaciones}.entregas
            WHERE pedido_id = %s LIMIT 1 FOR UPDATE
            """,
            (pedido_id,),
        )
        entrega = cursor.fetchone()
    return {"pedido": pedido, "pago": pago, "entrega": entrega}


def actualizar_estado_pedido(conexion, esquemas, pedido_id,
                             estado_anterior, estado_nuevo):
    """Actualiza el pedido solo si conserva el estado previamente bloqueado."""
    comercio = esquemas["comercio"]
    with conexion.cursor() as cursor:
        cursor.execute(
            f"UPDATE {comercio}.pedidos SET estado = %s "
            "WHERE id = %s AND estado = %s",
            (estado_nuevo, pedido_id, estado_anterior),
        )
        return cursor.rowcount == 1


def insertar_historial_pedido(conexion, esquemas, pedido_id,
                              estado_anterior, estado_nuevo, actor_id,
                              origen, comentario):
    """Inserta la evidencia comercial dentro de la transacción recibida."""
    comercio = esquemas["comercio"]
    with conexion.cursor() as cursor:
        cursor.execute(
            f"""
            INSERT INTO {comercio}.pedido_historial
                (pedido_id, estado_anterior, estado_nuevo,
                 cambiado_por_usuario_id, origen, comentario)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (pedido_id, estado_anterior, estado_nuevo,
             actor_id, origen, comentario),
        )


def actualizar_entrega_a_preparacion(conexion, esquemas, entrega_id):
    """Sincroniza la entrega pendiente sin aceptar saltos de estado."""
    operaciones = esquemas["operaciones"]
    with conexion.cursor() as cursor:
        cursor.execute(
            f"UPDATE {operaciones}.entregas SET estado = 'EN_PREPARACION' "
            "WHERE id = %s AND estado = 'PENDIENTE'",
            (entrega_id,),
        )
        return cursor.rowcount == 1


def insertar_historial_entrega(conexion, esquemas, entrega_id, actor_id,
                               comentario):
    """Registra la sincronización de entrega en la misma transacción."""
    operaciones = esquemas["operaciones"]
    with conexion.cursor() as cursor:
        cursor.execute(
            f"""
            INSERT INTO {operaciones}.entrega_historial
                (entrega_id, estado_anterior, estado_nuevo,
                 usuario_responsable_id, comentario)
            VALUES (%s, 'PENDIENTE', 'EN_PREPARACION', %s, %s)
            """,
            (entrega_id, actor_id, comentario),
        )


def ejecutar_backfill_historial(conexion, esquemas):
    """Regulariza exclusivamente pedidos sin evidencia base observable.

    La operación bloquea las filas candidatas, inserta un único evento basado
    en el estado actualmente persistido y verifica los conteos antes de que el
    Service autorice el commit. Nunca reconstruye transiciones no observadas.
    """
    comercio = esquemas["comercio"]
    with conexion.cursor() as cursor:
        cursor.execute(f"SELECT COUNT(*) AS total FROM {comercio}.pedidos")
        total_antes = int(cursor.fetchone()["total"])
        cursor.execute(
            f"""
            SELECT p.id, p.estado, p.creado_en, p.actualizado_en
            FROM {comercio}.pedidos AS p
            WHERE NOT EXISTS (
                SELECT 1 FROM {comercio}.pedido_historial AS h
                WHERE h.pedido_id = p.id
            )
            ORDER BY p.creado_en, p.id
            FOR UPDATE
            """
        )
        pendientes = cursor.fetchall()
        no_admitidos = [
            pedido for pedido in pendientes
            if pedido["estado"] not in {"CREADO", "CANCELADO"}
        ]
        if no_admitidos:
            raise RuntimeError(
                "El backfill encontró estados distintos de CREADO/CANCELADO."
            )

        comentario = (
            "Estado base incorporado durante regularización histórica; "
            "no representa una secuencia de transiciones observada."
        )
        for pedido in pendientes:
            fecha = (
                pedido["actualizado_en"]
                if pedido["estado"] == "CANCELADO"
                else pedido["creado_en"]
            )
            cursor.execute(
                f"""
                INSERT INTO {comercio}.pedido_historial
                    (pedido_id, estado_anterior, estado_nuevo,
                     cambiado_por_usuario_id, origen, comentario, creado_en)
                VALUES (%s, NULL, %s, NULL, 'BACKFILL', %s, %s)
                """,
                (pedido["id"], pedido["estado"], comentario, fecha),
            )

        cursor.execute(
            f"""
            SELECT COUNT(*) AS total
            FROM {comercio}.pedidos AS p
            WHERE NOT EXISTS (
                SELECT 1 FROM {comercio}.pedido_historial AS h
                WHERE h.pedido_id = p.id
            )
            """
        )
        sin_historial_despues = int(cursor.fetchone()["total"])
        cursor.execute(
            f"SELECT COUNT(DISTINCT pedido_id) AS total "
            f"FROM {comercio}.pedido_historial"
        )
        con_historial_despues = int(cursor.fetchone()["total"])

    insertados = len(pendientes)
    if sin_historial_despues != 0 or con_historial_despues != total_antes:
        raise RuntimeError(
            "La verificación del backfill no coincide; se requiere rollback."
        )
    return {
        "total_pedidos": total_antes,
        "sin_historial_antes": insertados,
        "insertados": insertados,
        "sin_historial_despues": sin_historial_despues,
        "con_historial_despues": con_historial_despues,
    }
