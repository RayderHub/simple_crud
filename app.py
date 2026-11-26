from functools import wraps
import os
from flask import (
    Flask,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from dotenv import load_dotenv
from supabase_client import SupabaseClient, SupabaseError, hash_password

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "clave-secreta-proyecto-crud-uteq-2026")
db = SupabaseClient()

try:
    from observability import setup_observability
    setup_observability(app)
except ImportError:
    pass

ROLES_VALIDOS = ("Administrador", "Editor", "Usuario")


@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "service": "simple-crud-flask",
        "supabase_configured": db.is_configured,
    }), 200


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            flash("Debes iniciar sesión para acceder al sistema.", "warning")
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


@app.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("usuarios"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not email or not password:
            flash("Ingresa tu correo electrónico y contraseña.", "error")
            return render_template("login.html", email=email, configured=db.is_configured)

        try:
            user = db.get_user_by_email(email)
        except SupabaseError as err:
            flash(str(err), "error")
            return render_template("login.html", email=email, configured=db.is_configured)

        if not user or user.get("password_hash") != hash_password(password):
            flash("Credenciales inválidas. Verifica tu correo y contraseña.", "error")
            return render_template("login.html", email=email, configured=db.is_configured)

        if not user.get("activo", True):
            flash("Tu cuenta se encuentra desactivada. Contacta al administrador.", "error")
            return render_template("login.html", email=email, configured=db.is_configured)

        session["user_id"] = user["id"]
        session["user_name"] = user["nombre"]
        session["user_email"] = user["email"]
        session["user_rol"] = user["rol"]
        flash(f"Bienvenido, {user['nombre']}.", "success")
        return redirect(url_for("usuarios"))

    return render_template("login.html", email="", configured=db.is_configured)


@app.route("/logout")
def logout():
    session.clear()
    flash("Has cerrado sesión correctamente.", "info")
    return redirect(url_for("login"))


@app.route("/")
@login_required
def index():
    return redirect(url_for("usuarios"))


@app.route("/usuarios")
@login_required
def usuarios():
    search = request.args.get("q", "").strip()
    lista = []
    try:
        lista = db.list_users(search=search)
    except SupabaseError as err:
        flash(str(err), "error")

    total = len(lista)
    activos = sum(1 for u in lista if u.get("activo"))
    admins = sum(1 for u in lista if u.get("rol") == "Administrador")

    return render_template(
        "usuarios.html",
        usuarios=lista,
        search=search,
        roles=ROLES_VALIDOS,
        stats={"total": total, "activos": activos, "admins": admins},
    )


@app.route("/usuarios/crear", methods=["POST"])
@login_required
def crear_usuario():
    nombre = request.form.get("nombre", "").strip()
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    rol = request.form.get("rol", "Usuario")
    activo = request.form.get("activo") == "on"

    if not nombre or not email or not password:
        flash("Nombre, correo y contraseña son campos obligatorios.", "error")
        return redirect(url_for("usuarios"))

    if len(password) < 6:
        flash("La contraseña debe tener al menos 6 caracteres.", "error")
        return redirect(url_for("usuarios"))

    if rol not in ROLES_VALIDOS:
        rol = "Usuario"

    try:
        db.create_user(nombre=nombre, email=email, password=password, rol=rol, activo=activo)
        flash(f"Usuario '{nombre}' creado correctamente.", "success")
    except SupabaseError as err:
        if "duplicate key" in str(err).lower() or "23505" in str(err):
            flash(f"Ya existe un usuario registrado con el correo {email}.", "error")
        else:
            flash(str(err), "error")

    return redirect(url_for("usuarios"))


@app.route("/usuarios/editar/<int:user_id>", methods=["POST"])
@login_required
def editar_usuario(user_id: int):
    nombre = request.form.get("nombre", "").strip()
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "").strip()
    rol = request.form.get("rol", "Usuario")
    activo = request.form.get("activo") == "on"

    if not nombre or not email:
        flash("Nombre y correo son obligatorios.", "error")
        return redirect(url_for("usuarios"))

    if password and len(password) < 6:
        flash("Si cambias la contraseña, debe tener al menos 6 caracteres.", "error")
        return redirect(url_for("usuarios"))

    if rol not in ROLES_VALIDOS:
        rol = "Usuario"

    try:
        db.update_user(
            user_id=user_id,
            nombre=nombre,
            email=email,
            rol=rol,
            activo=activo,
            password=password or None,
        )
        if session.get("user_id") == user_id:
            session["user_name"] = nombre
            session["user_email"] = email
            session["user_rol"] = rol
        flash(f"Usuario '{nombre}' actualizado correctamente.", "success")
    except SupabaseError as err:
        if "duplicate key" in str(err).lower() or "23505" in str(err):
            flash(f"El correo {email} ya pertenece a otro usuario.", "error")
        else:
            flash(str(err), "error")

    return redirect(url_for("usuarios"))


@app.route("/usuarios/eliminar/<int:user_id>", methods=["POST"])
@login_required
def eliminar_usuario(user_id: int):
    if session.get("user_id") == user_id:
        flash("No puedes eliminar tu propia cuenta mientras tienes sesión activa.", "warning")
        return redirect(url_for("usuarios"))

    try:
        db.delete_user(user_id)
        flash("Usuario eliminado correctamente.", "success")
    except SupabaseError as err:
        flash(str(err), "error")

    return redirect(url_for("usuarios"))


# Endpoint JSON opcional para pruebas de API o integración
@app.route("/api/usuarios", methods=["GET"])
@login_required
def api_listar_usuarios():
    try:
        data = db.list_users(search=request.args.get("q", ""))
        return jsonify({"ok": True, "total": len(data), "usuarios": data})
    except SupabaseError as err:
        return jsonify({"ok": False, "error": str(err)}), 500


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
