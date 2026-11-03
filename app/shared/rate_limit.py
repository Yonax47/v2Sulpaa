"""Límite de frecuencia local para consultas externas sensibles.

Este módulo evita ráfagas dentro de **un proceso**. No es un límite global:
Gunicorn/Railway puede ejecutar varios workers y cada uno mantiene su propia
memoria. Para producción distribuida se necesita Redis o una tabla compartida;
hasta que esa infraestructura sea autorizada, este control reduce abuso simple
pero no debe presentarse como una garantía global.

No persiste documentos ni respuestas. Las claves deben ser identificadores
técnicos (por ejemplo la IP ya normalizada por el llamador), nunca DNI, correo
ni otro dato personal.
"""

from collections import OrderedDict, deque
from threading import Lock
from time import monotonic


_EVENTOS = OrderedDict()
_CERROJO = Lock()
_MAXIMO_CLAVES = 10000


def consumir_limite(clave, maximo=5, ventana_segundos=600, ahora=None):
    """Registra un intento y devuelve ``(permitido, reintentar_en)``.

    ``ahora`` permite probar la ventana deslizante sin esperas reales. La
    cantidad de claves se mantiene acotada para que una IP rotativa no haga
    crecer la memoria indefinidamente.
    """

    maximo = max(1, int(maximo))
    ventana_segundos = max(1, int(ventana_segundos))
    instante = monotonic() if ahora is None else float(ahora)
    inicio = instante - ventana_segundos
    clave = str(clave or "desconocido")[:180]

    with _CERROJO:
        eventos = _EVENTOS.get(clave)
        if eventos is None:
            # OrderedDict actúa como LRU acotado: al superar el límite se
            # descarta la clave usada menos recientemente, no una clave
            # arbitraria con eventos vigentes.
            if len(_EVENTOS) >= _MAXIMO_CLAVES:
                _EVENTOS.popitem(last=False)
            eventos = deque()
            _EVENTOS[clave] = eventos
        else:
            _EVENTOS.move_to_end(clave)

        while eventos and eventos[0] <= inicio:
            eventos.popleft()

        if len(eventos) >= maximo:
            espera = max(1, int(eventos[0] + ventana_segundos - instante))
            return False, espera

        eventos.append(instante)
        return True, 0


def limpiar_limites():
    """Limpia el estado local; se utiliza exclusivamente en pruebas."""

    with _CERROJO:
        _EVENTOS.clear()
