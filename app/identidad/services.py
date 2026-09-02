"""
Servicios del módulo Identidad.

Aquí se encuentran las reglas de negocio relacionadas con
registro, autenticación y gestión de usuarios.

Esta capa no contiene rutas Flask ni SQL directo.
"""

import uuid

import bcrypt

import re
import unicodedata

from app.identidad.apisperu import (
    consultar_dni,
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
)

from app.shared.validators import (
    normalizar_telefono,
    validar_correo,
    validar_dni,
    validar_nombre,
    validar_password,
    validar_telefono_peru,
)




def registrar_usuario(
    correo: str,
    password: str,
    nombres: str,
    apellido_paterno: str,
    apellido_materno: str | None,
    dni: str | None,
    telefono: str,
):
    """
    Registra un nuevo usuario comprador.

    Flujo:
    1. Normaliza datos.
    2. Valida formatos.
    3. Evita duplicados.
    4. Genera UUID.
    5. Protege la contraseña con bcrypt.
    6. Guarda usuario y perfil en una transacción.
    """

    # ========================================================
    # 1. NORMALIZACIÓN
    # ========================================================

    correo = (correo or "").strip().lower()

    nombres = (nombres or "").strip()

    apellido_paterno = (
        apellido_paterno or ""
    ).strip()

    apellido_materno = (
        apellido_materno.strip()
        if apellido_materno
        else None
    )

    dni = (
        dni.strip()
        if dni
        else None
    )

    telefono = normalizar_telefono(
        telefono
    )


    # ========================================================
    # 2. VALIDACIÓN DE NOMBRES
    # ========================================================

    valido, mensaje = validar_nombre(
        nombres,
        "Los nombres",
        obligatorio=True,
    )

    if not valido:
        return {
            "ok": False,
            "mensaje": mensaje,
        }


    valido, mensaje = validar_nombre(
        apellido_paterno,
        "El apellido paterno",
        obligatorio=True,
    )

    if not valido:
        return {
            "ok": False,
            "mensaje": mensaje,
        }


    valido, mensaje = validar_nombre(
        apellido_materno,
        "El apellido materno",
        obligatorio=False,
    )

    if not valido:
        return {
            "ok": False,
            "mensaje": mensaje,
        }


    # ========================================================
    # 3. DNI
    # ========================================================

    valido, mensaje = validar_dni(
        dni,
        obligatorio=False,
    )

    if not valido:
        return {
            "ok": False,
            "mensaje": mensaje,
        }


    # ========================================================
    # 4. TELÉFONO
    # ========================================================

    valido, mensaje = validar_telefono_peru(
        telefono,
        obligatorio=True,
    )

    if not valido:
        return {
            "ok": False,
            "mensaje": mensaje,
        }


    # ========================================================
    # 5. CORREO
    # ========================================================

    valido, mensaje = validar_correo(
        correo
    )

    if not valido:
        return {
            "ok": False,
            "mensaje": mensaje,
        }


    # ========================================================
    # 6. CONTRASEÑA
    # ========================================================

    valido, mensaje = validar_password(
        password
    )

    if not valido:
        return {
            "ok": False,
            "mensaje": mensaje,
        }


    # ========================================================
    # 7. DUPLICADOS
    # ========================================================

    usuario_existente = buscar_usuario_por_correo(
        correo
    )

    if usuario_existente:
        return {
            "ok": False,
            "mensaje": (
                "Ya existe una cuenta registrada "
                "con ese correo."
            ),
        }


    if dni:

        perfil_existente = buscar_perfil_por_dni(
            dni
        )

        if perfil_existente:
            return {
                "ok": False,
                "mensaje": (
                    "El DNI ya se encuentra registrado."
                ),
            }


    # ========================================================
    # 8. UUID
    # ========================================================

    usuario_id = str(
        uuid.uuid4()
    )

    perfil_id = str(
        uuid.uuid4()
    )


    # ========================================================
    # 9. CONTRASEÑA SEGURA
    # ========================================================

    password_hash = bcrypt.hashpw(
        password.encode("utf-8"),
        bcrypt.gensalt(),
    ).decode("utf-8")


    # ========================================================
    # 10. PERSISTENCIA
    # ========================================================

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
    )


    return {
        "ok": True,
        "mensaje": "Usuario registrado correctamente.",
        "usuario_id": usuario_id,
    }


def autenticar_usuario(
    correo: str,
    password: str,
):
    """
    Autentica un usuario utilizando correo y contraseña.

    Flujo:
    1. Normaliza el correo.
    2. Comprueba que exista la cuenta.
    3. Verifica que esté activa.
    4. Compara la contraseña con bcrypt.
    5. Actualiza el último acceso.
    6. Devuelve únicamente los datos necesarios para la sesión.

    No revelamos al usuario si falló específicamente
    el correo o la contraseña. Esto evita filtrar información
    sobre las cuentas registradas.
    """

    correo = (correo or "").strip().lower()
    password = password or ""

    # --------------------------------------------------------
    # Validaciones mínimas de entrada
    # --------------------------------------------------------

    if not correo or not password:

        return {
            "ok": False,
            "mensaje": "Ingresa tu correo y contraseña.",
        }

    # --------------------------------------------------------
    # Buscar usuario
    # --------------------------------------------------------

    usuario = buscar_usuario_por_correo(
        correo
    )

    # Utilizamos un mensaje genérico deliberadamente.
    if not usuario:

        return {
            "ok": False,
            "mensaje": "Correo o contraseña incorrectos.",
        }

    # --------------------------------------------------------
    # Estado de cuenta
    # --------------------------------------------------------

    if usuario["estado"] != "ACTIVO":

        return {
            "ok": False,
            "mensaje": (
                "Tu cuenta no se encuentra disponible "
                "para iniciar sesión."
            ),
        }

    # --------------------------------------------------------
    # Comparación segura de contraseña
    # --------------------------------------------------------

    password_correcto = bcrypt.checkpw(
        password.encode("utf-8"),
        usuario["password_hash"].encode("utf-8"),
    )

    if not password_correcto:

        return {
            "ok": False,
            "mensaje": "Correo o contraseña incorrectos.",
        }

    # --------------------------------------------------------
    # Último acceso
    # --------------------------------------------------------

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
        },
    }
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
):
    """
    Valida y registra una dirección del cliente.
    """

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
        es_principal=True,
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