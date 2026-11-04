"""
Servicios del módulo Identidad.

Aquí se encuentran las reglas de negocio relacionadas con
registro, autenticación y gestión de usuarios.

Esta capa no contiene rutas Flask ni SQL directo.
"""

import uuid
import logging
from dataclasses import dataclass

import bcrypt
from flask import current_app, has_app_context

import re
import unicodedata

from app.identidad.apisperu import (
    consultar_dni,
    consultar_ruc,
)

from app.identidad.repositories import (
    actualizar_ultimo_acceso,
    buscar_perfil_por_dni,
    buscar_usuario_por_correo,
    crear_usuario_y_perfil,
    obtener_datos_checkout_usuario,
    obtener_departamentos_activos,
    obtener_provincias_por_departamento,
    obtener_distritos_por_provincia,
    crear_direccion_usuario,
    buscar_distrito_activo,
    guardar_datos_facturacion,
    listar_direcciones_usuario,
    listar_roles_usuario,
    obtener_contexto_autorizacion_usuario,
    obtener_bloqueo_vigente,
    registrar_fallo_login,
    registrar_intento_bloqueado,
    registrar_login_exitoso,
)
from app.config.security import politica_bloqueos
from app.identidad.email_verification import preparar_solicitud

from app.shared.validators import (
    normalizar_telefono,
    validar_correo,
    validar_dni,
    validar_nombre,
    validar_password,
    validar_telefono_peru,
)


# Este hash pertenece a una clave ficticia que nunca se usa para iniciar
# sesión. Permite ejecutar bcrypt aunque el correo no exista, de modo que un
# atacante no pueda distinguir cuentas válidas midiendo una respuesta rápida.
_HASH_BCRYPT_FICTICIO = (
    b"$2b$12$D0j.JGrC8NcnYP/4f6T2S.f82K3/jicG/ApQF/CvbGrwKCgCyLwz6"
)
_MENSAJE_LOGIN_GENERICO = (
    "No fue posible iniciar sesión con los datos proporcionados."
)

logger = logging.getLogger(__name__)


def normalizar_correo_objetivo(correo):
    """Normaliza la cuenta objetivo sin revelar si está registrada."""

    return str(correo or "").strip().lower()[:150]


def _politica_login_actual():
    """Mantiene el flujo anterior cuando la protección no está habilitada."""

    if not has_app_context():
        return {"habilitado": False}
    return politica_bloqueos(current_app)




def registrar_usuario(
    correo: str,
    password: str,
    nombres: str,
    apellido_paterno: str,
    apellido_materno: str | None,
    dni: str | None,
    telefono: str,
):
    """Registra una cuenta usando exclusivamente la identidad de APIsPERU."""
    correo = (correo or "").strip().lower()
    dni = str(dni or "").strip()
    telefono = normalizar_telefono(telefono)

    valido, mensaje = validar_dni(dni, obligatorio=True)
    if not valido:
        return {"ok": False, "mensaje": mensaje}
    valido, mensaje = validar_telefono_peru(telefono, obligatorio=True)
    if not valido:
        return {"ok": False, "mensaje": mensaje}
    valido, mensaje = validar_correo(correo)
    if not valido:
        return {"ok": False, "mensaje": mensaje}
    valido, mensaje = validar_password(password)
    if not valido:
        return {"ok": False, "mensaje": mensaje}

    # La respuesta no distingue correo o DNI para reducir enumeración.
    if buscar_usuario_por_correo(correo) or buscar_perfil_por_dni(dni):
        return {
            "ok": False,
            "mensaje": "No fue posible completar el registro con esos datos.",
        }

    # Se consulta otra vez al enviar el formulario. Los nombres recibidos del
    # navegador se ignoran deliberadamente.
    verificacion = verificar_dni_registro(dni, comprobar_duplicado=False)
    if not verificacion.get("ok"):
        return {
            "ok": False,
            "mensaje": verificacion.get("mensaje")
            or "No fue posible verificar el DNI.",
        }
    persona = verificacion["persona"]
    nombres = persona["nombres"]
    apellido_paterno = persona["apellido_paterno"]
    apellido_materno = persona.get("apellido_materno") or None

    for valor, etiqueta, obligatorio in (
        (nombres, "Los nombres", True),
        (apellido_paterno, "El apellido paterno", True),
        (apellido_materno, "El apellido materno", False),
    ):
        valido, mensaje = validar_nombre(valor, etiqueta, obligatorio=obligatorio)
        if not valido:
            return {"ok": False, "mensaje": mensaje}

    usuario_id = str(uuid.uuid4())
    perfil_id = str(uuid.uuid4())
    password_hash = bcrypt.hashpw(
        password.encode("utf-8"),
        bcrypt.gensalt(),
    ).decode("utf-8")
    try:
        solicitud_correo = preparar_solicitud(
            usuario_id, correo, nombres
        )
        crear_usuario_y_perfil(
            usuario_id=usuario_id,
            perfil_id=perfil_id,
            correo=correo,
            password_hash=password_hash,
            nombres=nombres,
            apellido_paterno=apellido_paterno,
            apellido_materno=apellido_materno,
            dni=dni,
            telefono=telefono,
            rol_codigo="CLIENTE",
            verificacion_correo=solicitud_correo,
        )
    except Exception:
        # Las excepciones SQL de unicidad pueden incluir correo o DNI en su
        # texto. No se adjunta la excepción para evitar datos personales en
        # logs; el cliente recibe el mismo mensaje no enumerable.
        logger.error("No se pudo completar un registro de usuario")
        return {
            "ok": False,
            "mensaje": "No fue posible completar el registro con esos datos.",
        }
    return {
        "ok": True,
        "mensaje": "Usuario registrado correctamente.",
        "usuario_id": usuario_id,
        "correo_pendiente": bool(solicitud_correo),
    }


def autenticar_usuario(
    correo: str,
    password: str,
    direccion_ip=None,
    user_agent=None,
):
    """
    Autentica un usuario utilizando correo y contraseña.

    Flujo:
    1. Normaliza el correo.
    2. Busca la cuenta y elige su hash o un hash ficticio.
    3. Compara siempre la contraseña con bcrypt.
    4. Comprueba que la cuenta exista y siga activa.
    5. Actualiza el último acceso.
    6. Devuelve únicamente los datos necesarios para la sesión.

    Todas las credenciales rechazadas reciben el mismo mensaje. Además, el
    trabajo de bcrypt se realiza para cuentas existentes e inexistentes, lo
    que reduce diferencias de tiempo que podrían revelar un correo registrado.
    """

    correo = normalizar_correo_objetivo(correo)
    password = password or ""
    politica = _politica_login_actual()

    # La protección persistente solo se consulta cuando fue activada. Esto
    # permite aplicar primero la migración y validar Railway antes de cambiar
    # el comportamiento de producción.
    if politica.get("habilitado"):
        if not direccion_ip:
            logger.error(
                "Se rechazó un login porque no existe una IP confiable."
            )
            return {"ok": False, "mensaje": _MENSAJE_LOGIN_GENERICO}
        try:
            bloqueo = obtener_bloqueo_vigente(correo, direccion_ip)
            if bloqueo:
                registrar_intento_bloqueado(
                    correo=correo,
                    usuario_id=bloqueo.get("usuario_id"),
                    direccion_ip=direccion_ip,
                    user_agent=user_agent,
                )
                return {"ok": False, "mensaje": _MENSAJE_LOGIN_GENERICO}
        except Exception:
            # Si la base de seguridad no responde, no se verifican credenciales.
            # Esta decisión impide saltar el límite provocando fallos técnicos.
            logger.exception("No se pudo comprobar el bloqueo de acceso")
            return {"ok": False, "mensaje": _MENSAJE_LOGIN_GENERICO}

    # --------------------------------------------------------
    # Buscar usuario
    # --------------------------------------------------------

    try:
        usuario = buscar_usuario_por_correo(
            correo
        )
    except Exception:
        logger.exception("No se pudo consultar la cuenta durante el login")
        return {"ok": False, "mensaje": _MENSAJE_LOGIN_GENERICO}

    # --------------------------------------------------------
    # Comparación segura de contraseña
    # --------------------------------------------------------

    # Si no encontramos la cuenta se usa un hash válido de prueba. No se usa
    # una contraseña real ni se guarda el resultado; solo iguala el trabajo
    # de bcrypt para dificultar la enumeración por tiempo de respuesta.
    hash_comparacion = (
        usuario["password_hash"].encode("utf-8")
        if usuario
        else _HASH_BCRYPT_FICTICIO
    )
    try:
        password_correcto = bcrypt.checkpw(
            password.encode("utf-8"),
            hash_comparacion,
        )
    except (ValueError, TypeError):
        logger.exception("El hash de autenticación no pudo verificarse")
        password_correcto = False

    # Se evalúan juntas las tres causas para no dar mensajes diferentes. Una
    # cuenta inactiva tampoco puede entrar aunque la contraseña sea correcta.
    if (
        not usuario
        or usuario["estado"] != "ACTIVO"
        or not password_correcto
        or not correo
        or not password
    ):

        if politica.get("habilitado"):
            try:
                registrar_fallo_login(
                    correo=correo,
                    usuario_id=usuario.get("id") if usuario else None,
                    direccion_ip=direccion_ip,
                    user_agent=user_agent,
                    max_cuenta_ip=politica["max_cuenta_ip"],
                    max_ip=politica["max_ip"],
                    ventana_minutos=politica["ventana_minutos"],
                    bloqueo_minutos=politica["bloqueo_minutos"],
                )
            except Exception:
                logger.exception("No se pudo registrar el fallo de acceso")

        return {
            "ok": False,
            "mensaje": _MENSAJE_LOGIN_GENERICO,
        }

    # --------------------------------------------------------
    # Último acceso
    # --------------------------------------------------------

    if politica.get("habilitado"):
        try:
            registrar_login_exitoso(
                usuario_id=usuario["id"],
                correo=correo,
                direccion_ip=direccion_ip,
                user_agent=user_agent,
            )
        except Exception:
            # El acceso no se concede si no puede quedar auditado ni limpiar
            # su contador de forma transaccional.
            logger.exception("No se pudo confirmar el acceso correcto")
            return {"ok": False, "mensaje": _MENSAJE_LOGIN_GENERICO}
    else:
        actualizar_ultimo_acceso(
            usuario["id"]
        )

    # --------------------------------------------------------
    # Resultado
    # --------------------------------------------------------
    #
    # Nunca devolvemos password_hash a la sesión.
    # --------------------------------------------------------

    return {
        "ok": True,
        "mensaje": "Inicio de sesión correcto.",
        "usuario": {
            "id": usuario["id"],
            "correo": usuario["correo"],
            "correo_verificado": bool(usuario.get("correo_verificado")),
            "requiere_verificacion_correo": bool(
                usuario.get("requiere_verificacion_correo")
            ),
        },
    }
# ============================================================
# ROLES DEL USUARIO (para el panel administrativo)
# ============================================================
#
# Tras autenticarse correctamente, el login consulta los
# roles ACTIVOS del usuario y los guarda en session["roles"].
#
# Esta función es la capa de negocios de esa operación:
# - Recibe el usuario_id autenticado.
# - Delega EN SOLO LECTURA en listar_roles_usuario()
#   (el repository que hace el INNER JOIN real sobre
#   usuario_roles -> roles del dump de identidad).
# - Devuelve los códigos de rol ACTIVOS (ej. ["GERENTE"]).
#
# IMPORTANTE:
# - No inventa roles.
# - No asigna GERENTE/ADMINISTRADOR automáticamente.
# - No crea ni modifica tablas (es de solo lectura).
# ============================================================

def obtener_roles_usuario(
    usuario_id: str,
):
    """
    Devuelve los códigos de rol ACTIVOS de un usuario.

    Es el puente entre la capa de rutas (que necesita poblar
    session["roles"] tras el login) y la capa de datos.

    Parece repetir el nombre de listar_roles_usuario() a
    propósito: así mantenemos la convención del resto del
    módulo (services.realizar_X -> repositories.buscar_X),
    separando el "qué" (negocio) del "cómo" (SQL).

    Returns:
        list[str]: Códigos de rol ACTIVOS (ej. ["GERENTE"]).
    """

    return listar_roles_usuario(
        usuario_id
    )


def obtener_contexto_sesion(usuario_id: str):
    """Devuelve el estado y los roles actuales para proteger una petición.

    El repositorio realiza una sola consulta. Esta función mantiene la regla
    del proyecto donde los decoradores piden información a Servicios y no
    escriben SQL directamente.
    """

    return obtener_contexto_autorizacion_usuario(usuario_id)
# ============================================================
# DATOS PARA CHECKOUT
# ============================================================

def obtener_checkout_usuario(
    usuario_id,
):
    """
    Devuelve los datos necesarios para
    precargar el checkout del cliente.
    """

    datos = obtener_datos_checkout_usuario(
        usuario_id
    )

    if not datos:

        return {
            "ok": False,
            "mensaje":
                "No se encontraron los datos del usuario.",
        }

    return {
        "ok": True,
        "cliente":
            datos["cliente"],

        "direccion":
            datos["direccion"],

        "facturacion":
            datos["facturacion"],
        "direcciones": listar_direcciones_usuario(usuario_id),
    }

# ============================================================
# UBICACIÓN PARA CHECKOUT Y PERFIL
# ============================================================

def listar_departamentos():
    """
    Devuelve los departamentos activos.
    """

    return obtener_departamentos_activos()


def listar_provincias(
    departamento_id,
):
    """
    Devuelve las provincias de un departamento.
    """

    departamento_id = (
        departamento_id or ""
    ).strip()

    if len(departamento_id) != 2:
        return []

    return obtener_provincias_por_departamento(
        departamento_id
    )


def listar_distritos(
    provincia_id,
):
    """
    Devuelve los distritos de una provincia.
    """

    provincia_id = (
        provincia_id or ""
    ).strip()

    if len(provincia_id) != 4:
        return []

    return obtener_distritos_por_provincia(
        provincia_id
    )

# ============================================================
# REGISTRO DE DIRECCIÓN
# ============================================================

def registrar_direccion_usuario(
    usuario_id,
    distrito_id,
    direccion,
    referencia=None,
    alias=None,
    latitud=None,
    longitud=None,
    es_principal=True,
):
    """
    Valida y registra una dirección del cliente.
    """

    if any(v is not None and not isinstance(v, str)
           for v in (distrito_id, direccion, referencia, alias)):
        return {"ok": False, "mensaje": "Los datos de dirección no son válidos."}
    try:
        latitud, longitud = validar_coordenadas_direccion(latitud, longitud)
    except ValueError as error:
        return {"ok": False, "mensaje": str(error)}

    distrito_id = (
        distrito_id or ""
    ).strip()

    direccion = (
        direccion or ""
    ).strip()

    referencia = (
        referencia or ""
    ).strip() or None

    alias = (
        alias or ""
    ).strip() or "Principal"

    # --------------------------------------------------------
    # Validar distrito
    # --------------------------------------------------------

    if len(distrito_id) != 6:

        return {
            "ok": False,
            "mensaje":
                "Selecciona un distrito válido.",
        }

    distrito = buscar_distrito_activo(
        distrito_id
    )

    if not distrito:

        return {
            "ok": False,
            "mensaje":
                "El distrito seleccionado no es válido.",
        }

    # --------------------------------------------------------
    # Validar dirección
    # --------------------------------------------------------

    if len(direccion) < 5:

        return {
            "ok": False,
            "mensaje":
                "Ingresa una dirección válida.",
        }

    if len(direccion) > 255:

        return {
            "ok": False,
            "mensaje":
                "La dirección es demasiado extensa.",
        }

    if referencia and len(referencia) > 255:

        return {
            "ok": False,
            "mensaje":
                "La referencia es demasiado extensa.",
        }

    if len(alias) > 50:

        return {
            "ok": False,
            "mensaje":
                "El nombre de la dirección es demasiado extenso.",
        }

    # --------------------------------------------------------
    # Guardar
    # --------------------------------------------------------

    direccion_id = str(
        uuid.uuid4()
    )

    crear_direccion_usuario(
        direccion_id=direccion_id,
        usuario_id=usuario_id,
        distrito_id=distrito_id,
        alias=alias,
        direccion=direccion,
        referencia=referencia,
        es_principal=bool(es_principal),
        latitud=latitud,
        longitud=longitud,
    )

    return {
        "ok": True,
        "mensaje":
            "Dirección guardada correctamente.",
        "direccion_id":
            direccion_id,
    }

# ============================================================
# VALIDACIÓN DE DNI CON APISPERU
# ============================================================


def verificar_dni_registro(dni, comprobar_duplicado=True):
    """Obtiene los nombres oficiales requeridos para crear una cuenta.

    La consulta solo comprueba que el documento exista y devuelve los datos
    asociados por el proveedor. No autentica que el solicitante sea su titular.
    """
    dni = str(dni or "").strip()
    valido, mensaje = validar_dni(dni, obligatorio=True)
    if not valido:
        return {"ok": False, "mensaje": mensaje, "estado": "INVALIDO"}

    if comprobar_duplicado and buscar_perfil_por_dni(dni):
        return {
            "ok": False,
            "mensaje": "No fue posible verificar el DNI ingresado.",
            "estado": "INVALIDO",
        }

    resultado = consultar_dni(dni)
    if not resultado.get("ok"):
        tipo_error = resultado.get("tipo_error")
        limitado = tipo_error == "LIMITE"
        no_disponible = tipo_error in {
            "NO_DISPONIBLE", "CONTADOR_NO_DISPONIBLE"
        }
        return {
            "ok": False,
            "mensaje": (
                "Demasiadas consultas. Intenta nuevamente más tarde."
                if limitado
                else
                "El servicio de consulta de DNI no está disponible. "
                "Intenta nuevamente más tarde."
                if no_disponible
                else "No fue posible verificar el DNI ingresado."
            ),
            "estado": (
                "LIMITE" if limitado
                else "ERROR" if no_disponible
                else "INVALIDO"
            ),
            "tipo_error": tipo_error,
            "reintentar_en": resultado.get("reintentar_en", 0),
        }

    persona = {
        "dni": str(resultado.get("dni") or "").strip(),
        "nombres": str(resultado.get("nombres") or "").strip(),
        "apellido_paterno": str(
            resultado.get("apellido_paterno") or ""
        ).strip(),
        "apellido_materno": str(
            resultado.get("apellido_materno") or ""
        ).strip(),
    }
    if persona["dni"] != dni or not persona["nombres"] \
            or not persona["apellido_paterno"]:
        return {
            "ok": False,
            "mensaje": "El servicio no devolvió datos suficientes del DNI.",
            "estado": "ERROR",
        }
    return {
        "ok": True,
        "mensaje": "DNI consultado correctamente.",
        "estado": "VERIFICADO",
        "persona": persona,
        "aviso": (
            "La consulta confirma datos asociados al DNI, pero no demuestra "
            "que quien realiza el registro sea su titular."
        ),
    }

def _normalizar_texto_identidad(texto):
    """
    Normaliza nombres para poder compararlos
    sin que tildes, espacios o mayúsculas generen
    falsos errores.
    """

    texto = (texto or "").strip().upper()

    texto = unicodedata.normalize(
        "NFD",
        texto
    )

    texto = "".join(
        caracter
        for caracter in texto
        if unicodedata.category(caracter) != "Mn"
    )

    texto = re.sub(
        r"\s+",
        " ",
        texto
    )

    return texto.strip()


def _nombres_perfil_coinciden(
    nombres_perfil,
    nombres_oficiales,
):
    """
    Comprueba que los nombres registrados en el perfil
    estén contenidos dentro de los nombres oficiales
    obtenidos mediante APIsPERU.

    Esto permite, por ejemplo:

    Perfil:
        CARLOS

    APIsPERU:
        CARLOS ALBERTO

    Resultado:
        VÁLIDO
    """

    perfil_normalizado = _normalizar_texto_identidad(
        nombres_perfil
    )

    oficial_normalizado = _normalizar_texto_identidad(
        nombres_oficiales
    )

    if not perfil_normalizado:
        return False

    if not oficial_normalizado:
        return False

    nombres_perfil_lista = (
        perfil_normalizado.split()
    )

    nombres_oficiales_lista = (
        oficial_normalizado.split()
    )

    return all(
        nombre in nombres_oficiales_lista
        for nombre in nombres_perfil_lista
    )


def validar_dni_con_perfil(
    usuario_id,
    dni,
):
    """
    Consulta un DNI mediante APIsPERU y comprueba
    que corresponda al titular de la cuenta SULPAA.

    El perfil puede contener solo uno de los nombres
    oficiales del usuario.

    Los apellidos deben coincidir con la identidad
    obtenida mediante APIsPERU.

    Los nombres completos obtenidos desde APIsPERU
    se conservan para utilizarlos posteriormente
    en la boleta.
    """

    dni = (dni or "").strip()

    # --------------------------------------------------------
    # 1. VALIDAR FORMATO DEL DNI
    # --------------------------------------------------------

    if (
        not dni.isdigit()
        or len(dni) != 8
    ):
        return {
            "ok": False,
            "mensaje": (
                "El DNI debe contener "
                "exactamente 8 dígitos."
            ),
        }

    # --------------------------------------------------------
    # 2. OBTENER PERFIL DEL USUARIO
    # --------------------------------------------------------

    datos_usuario = (
        obtener_datos_checkout_usuario(
            usuario_id
        )
    )

    if not datos_usuario:
        return {
            "ok": False,
            "mensaje": (
                "No se encontró el perfil "
                "del usuario."
            ),
        }

    perfil = datos_usuario.get(
        "cliente"
    )

    if not perfil:
        return {
            "ok": False,
            "mensaje": (
                "No se encontraron los datos "
                "del perfil del usuario."
            ),
        }

    # --------------------------------------------------------
    # 3. COMPROBAR DNI REGISTRADO EN EL PERFIL
    # --------------------------------------------------------
    #
    # Si la cuenta ya tiene un DNI registrado,
    # no permitimos verificar otro documento diferente.
    # --------------------------------------------------------

    dni_perfil = str(
        perfil.get("dni") or ""
    ).strip()

    if (
        dni_perfil
        and dni_perfil != dni
    ):
        return {
            "ok": False,
            "mensaje": (
                "El DNI ingresado no corresponde "
                "al DNI registrado en esta cuenta."
            ),
        }

    # --------------------------------------------------------
    # 4. CONSULTAR APISPERU
    # --------------------------------------------------------

    resultado_api = consultar_dni(
        dni
    )

    if not resultado_api.get("ok"):
        return resultado_api

    # --------------------------------------------------------
    # 5. OBTENER DATOS OFICIALES
    # --------------------------------------------------------

    nombres_api = (
        resultado_api.get("nombres")
        or ""
    ).strip()

    paterno_api = (
        resultado_api.get(
            "apellido_paterno"
        )
        or ""
    ).strip()

    materno_api = (
        resultado_api.get(
            "apellido_materno"
        )
        or ""
    ).strip()

    # --------------------------------------------------------
    # 6. COMPROBAR RESPUESTA DE IDENTIDAD
    # --------------------------------------------------------

    if (
        not nombres_api
        or not paterno_api
    ):
        return {
            "ok": False,
            "mensaje": (
                "No fue posible obtener "
                "los datos completos del DNI."
            ),
        }

    # --------------------------------------------------------
    # 7. COMPARAR NOMBRES
    # --------------------------------------------------------
    #
    # Ejemplo válido:
    #
    # Perfil SULPAA:
    # CARLOS
    #
    # APIsPERU:
    # CARLOS ALBERTO
    #
    # La identidad sigue siendo aceptada.
    # --------------------------------------------------------

    nombres_coinciden = (
        _nombres_perfil_coinciden(
            perfil.get("nombres"),
            nombres_api,
        )
    )

    # --------------------------------------------------------
    # 8. COMPARAR APELLIDO PATERNO
    # --------------------------------------------------------

    paterno_perfil = (
        _normalizar_texto_identidad(
            perfil.get(
                "apellido_paterno"
            )
        )
    )

    paterno_oficial = (
        _normalizar_texto_identidad(
            paterno_api
        )
    )

    paterno_coincide = (
        paterno_perfil
        == paterno_oficial
    )

    # --------------------------------------------------------
    # 9. COMPARAR APELLIDO MATERNO
    # --------------------------------------------------------

    materno_perfil = (
        _normalizar_texto_identidad(
            perfil.get(
                "apellido_materno"
            )
        )
    )

    materno_oficial = (
        _normalizar_texto_identidad(
            materno_api
        )
    )

    materno_coincide = (
        materno_perfil
        == materno_oficial
    )

    # --------------------------------------------------------
    # 10. RESULTADO DE LA COMPARACIÓN
    # --------------------------------------------------------

    if not (
        nombres_coinciden
        and paterno_coincide
        and materno_coincide
    ):
        return {
            "ok": False,
            "mensaje": (
                "Los datos obtenidos del DNI "
                "no coinciden con el titular "
                "registrado en esta cuenta."
            ),
        }

    # --------------------------------------------------------
    # 11. IDENTIDAD VERIFICADA
    # --------------------------------------------------------
    #
    # IMPORTANTE:
    #
    # Conservamos los nombres COMPLETOS obtenidos
    # desde APIsPERU.
    #
    # Estos datos serán los utilizados posteriormente
    # para la boleta y no el nombre abreviado que pueda
    # existir en el perfil.
    # --------------------------------------------------------

    nombre_completo = " ".join(
        parte
        for parte in [
            nombres_api,
            paterno_api,
            materno_api,
        ]
        if parte
    )

    return {
        "ok": True,

        "mensaje": (
            "DNI verificado correctamente."
        ),

        "persona": {
            "dni":
                dni,

            "nombres":
                nombres_api,

            "apellido_paterno":
                paterno_api,

            "apellido_materno":
                materno_api,

            "nombre_completo":
                nombre_completo,
        },
    }

# ============================================================
# VALIDACIÓN DE RUC CON APISPERU
# ============================================================

def validar_ruc_facturacion(ruc):
    """
    Consulta y valida un RUC mediante APIsPERU.

    A diferencia del DNI, el RUC no se compara con
    los nombres personales del perfil, ya que una
    cuenta SULPAA puede solicitar factura para una
    empresa con una razón social diferente.

    Los datos obtenidos serán utilizados posteriormente
    para registrar los datos de facturación.
    """

    ruc = (ruc or "").strip()

    # --------------------------------------------------------
    # 1. VALIDAR FORMATO
    # --------------------------------------------------------

    if (
        not ruc.isdigit()
        or len(ruc) != 11
    ):
        return {
            "ok": False,
            "mensaje": (
                "El RUC debe contener "
                "exactamente 11 dígitos."
            ),
        }

    # --------------------------------------------------------
    # 2. CONSULTAR APISPERU
    # --------------------------------------------------------

    resultado_api = consultar_ruc(
        ruc
    )

    if not resultado_api.get("ok"):
        return resultado_api

    # --------------------------------------------------------
    # 3. OBTENER DATOS DE LA EMPRESA
    # --------------------------------------------------------

    razon_social = (
        resultado_api.get("razon_social")
        or ""
    ).strip()

    direccion = (
        resultado_api.get("direccion")
        or ""
    ).strip()

    estado = (
        resultado_api.get("estado")
        or ""
    ).strip()

    condicion = (
        resultado_api.get("condicion")
        or ""
    ).strip()

    departamento = (
        resultado_api.get("departamento")
        or ""
    ).strip()

    provincia = (
        resultado_api.get("provincia")
        or ""
    ).strip()

    distrito = (
        resultado_api.get("distrito")
        or ""
    ).strip()

    # --------------------------------------------------------
    # 4. VALIDAR INFORMACIÓN MÍNIMA
    # --------------------------------------------------------

    if not razon_social:
        return {
            "ok": False,
            "mensaje": (
                "No fue posible obtener la razón social "
                "correspondiente al RUC."
            ),
        }

    # --------------------------------------------------------
    # 5. RUC VERIFICADO
    # --------------------------------------------------------

    return {
        "ok": True,

        "mensaje": (
            "RUC verificado correctamente."
        ),

        "empresa": {
            "ruc":
                ruc,

            "razon_social":
                razon_social,

            "direccion":
                direccion,

            "estado":
                estado,

            "condicion":
                condicion,

            "departamento":
                departamento,

            "provincia":
                provincia,

            "distrito":
                distrito,
        },
    }

# ============================================================
# GUARDAR FACTURACIÓN VERIFICADA DEL CHECKOUT
# Implementación rama: serna
# ============================================================

TIPO_CONTRIBUYENTE_POR_COMPROBANTE = {
    "BOLETA": "PERSONA",
    "FACTURA": "EMPRESA",
}


@dataclass(frozen=True)
class FacturacionPreparada:
    """Resultado interno efímero; nunca se acepta desde JSON, sesión o formulario."""

    usuario_id: str
    tipo_comprobante: str
    dni: str | None = None
    nombre_facturacion: str | None = None
    ruc: str | None = None
    razon_social: str | None = None
    direccion_fiscal: str | None = None


def preparar_facturacion_checkout(usuario_id, tipo_comprobante, documento):
    """Valida mediante backend antes de abrir la unidad de trabajo de compra."""

    tipo_comprobante = str(tipo_comprobante or "").strip().upper()
    documento = (documento or "").strip()
    if tipo_comprobante == "BOLETA":
        resultado = validar_dni_con_perfil(usuario_id=usuario_id, dni=documento)
        if not resultado.get("ok"):
            return resultado
        persona = resultado["persona"]
        preparada = FacturacionPreparada(
            usuario_id=usuario_id, tipo_comprobante=tipo_comprobante,
            dni=persona["dni"], nombre_facturacion=persona["nombre_completo"],
        )
    elif tipo_comprobante == "FACTURA":
        resultado = validar_ruc_facturacion(documento)
        if not resultado.get("ok"):
            return resultado
        empresa = resultado["empresa"]
        preparada = FacturacionPreparada(
            usuario_id=usuario_id, tipo_comprobante=tipo_comprobante,
            ruc=empresa["ruc"], razon_social=empresa["razon_social"],
            direccion_fiscal=empresa["direccion"] or None,
        )
    else:
        return {"ok": False, "mensaje": "Selecciona un tipo de comprobante válido."}
    return {"ok": True, "preparada": preparada}


def guardar_facturacion_preparada(usuario_id, preparada, conexion=None):
    """Escritura sin HTTP; participa del commit/rollback del checkout."""

    if (not isinstance(preparada, FacturacionPreparada)
            or preparada.usuario_id != usuario_id
            or preparada.tipo_comprobante not in TIPO_CONTRIBUYENTE_POR_COMPROBANTE):
        raise ValueError("La facturación preparada no corresponde a esta compra.")
    tipo = preparada.tipo_comprobante
    resultado_id = guardar_datos_facturacion(
        facturacion_id=str(uuid.uuid4()), usuario_id=usuario_id,
        tipo_contribuyente=TIPO_CONTRIBUYENTE_POR_COMPROBANTE[tipo],
        dni=preparada.dni, ruc=preparada.ruc,
        nombre_facturacion=preparada.nombre_facturacion,
        razon_social=preparada.razon_social, distrito_id=None,
        direccion_fiscal=preparada.direccion_fiscal, conexion=conexion,
    )
    return {
        "ok": True, "mensaje": f"Datos de {tipo.lower()} guardados correctamente.",
        "facturacion_id": resultado_id, "tipo": tipo, "tipo_comprobante": tipo,
        "tipo_contribuyente": TIPO_CONTRIBUYENTE_POR_COMPROBANTE[tipo],
    }


def registrar_facturacion_checkout(
    usuario_id,
    tipo=None,
    documento=None,
    conexion=None,
    *,
    tipo_comprobante=None,
):
    """
    Verifica nuevamente el documento desde el backend
    antes de guardar los datos de facturación.

    El navegador únicamente indica el tipo de comprobante
    y el documento. Los nombres oficiales, razón social
    y dirección fiscal provienen de la validación backend.

    Cuando se recibe una ``conexion`` externa (checkout), el
    guardado participa de esa misma transacción y NO se
    confirma por separado. Sin conexión, se conserva el
    comportamiento autónomo de siempre.
    ``BOLETA``/``FACTURA`` son tipos de comprobante. La columna histórica
    ``datos_facturacion.tipo`` almacena, en cambio, el tipo de contribuyente
    ``PERSONA``/``EMPRESA``. ``tipo`` se conserva como alias para los clientes
    existentes; el contrato nuevo debe usar ``tipo_comprobante``.
    """

    tipo_comprobante = str(
        tipo_comprobante if tipo_comprobante is not None else tipo or ""
    ).strip().upper()
    documento = (documento or "").strip()

    resultado = preparar_facturacion_checkout(usuario_id, tipo_comprobante, documento)
    if not resultado.get("ok"):
        return resultado
    return guardar_facturacion_preparada(usuario_id, resultado["preparada"], conexion)


def validar_coordenadas_direccion(latitud, longitud, obligatorias=False):
    """Mantiene compatibles las direcciones antiguas sin ubicación."""
    from decimal import Decimal, InvalidOperation
    if latitud in (None, "") and longitud in (None, "") and not obligatorias:
        return None, None
    try:
        lat, lon = Decimal(str(latitud)), Decimal(str(longitud))
        if not lat.is_finite() or not lon.is_finite():
            raise ValueError
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError
        return lat.quantize(Decimal("0.0000001")), lon.quantize(Decimal("0.0000001"))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("Selecciona una ubicación válida en el mapa.")
