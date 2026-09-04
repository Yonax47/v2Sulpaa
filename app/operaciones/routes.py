"""Rutas HTTP para la confirmación de pedidos."""

from flask import Blueprint, jsonify, request, session

from app.operaciones.services import confirmar_pedido
from app.shared.decorators import login_required


operaciones_bp = Blueprint(
	"operaciones",
	__name__,
	url_prefix="/operaciones",
)


@operaciones_bp.route("/api/pedidos", methods=["POST"])
@login_required
def crear_pedido():
	"""Confirma el carrito del usuario autenticado."""

	datos = request.get_json(silent=True) or {}
	resultado = confirmar_pedido(
		usuario_id=session["usuario_id"],
		tipo_comprobante=datos.get("tipo_comprobante", "BOLETA"),
	)

	return jsonify(resultado), 200 if resultado["ok"] else 400
