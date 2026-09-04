"""Rutas HTTP de consulta del inventario."""

from flask import Blueprint, jsonify, request

from app.inventario.services import obtener_disponibilidad_variantes


inventario_bp = Blueprint(
	"inventario",
	__name__,
	url_prefix="/inventario",
)


@inventario_bp.route("/api/disponibilidad", methods=["POST"])
def disponibilidad():
	"""Devuelve la disponibilidad de las variantes solicitadas."""

	datos = request.get_json(silent=True) or {}
	variantes_ids = datos.get("variantes_ids")

	if not isinstance(variantes_ids, list) or not variantes_ids:
		return jsonify({
			"ok": False,
			"mensaje": "Debes enviar una lista de variantes.",
		}), 400

	variantes_ids = list(dict.fromkeys(variantes_ids))
	resultado = obtener_disponibilidad_variantes(variantes_ids)

	return jsonify({
		"ok": True,
		"disponibilidad": resultado,
	})
