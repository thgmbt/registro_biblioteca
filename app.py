from __future__ import annotations

import os
import re
import secrets
import smtplib
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from email.message import EmailMessage
from pathlib import Path
from typing import Any

import click
from flask import (
    Flask,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)



SEED_INVENTORY = (
    ("Cien años de soledad", "Libro", "Gabriel García Márquez / Editorial Diana", 5, "ejemplares"),
    ("La ciudad y los perros", "Libro", "Mario Vargas Llosa / Alfaguara", 4, "ejemplares"),
    ("Papelucho", "Libro", "Marcela Paz / SM", 6, "ejemplares"),
    ("Matilda", "Libro", "Roald Dahl / Alfaguara", 3, "ejemplares"),
    ("Proyector portátil", "Tecnología", "Epson PowerLite E20", 2, "unidades"),
    ("Parlante portátil", "Tecnología", "JBL Flip 6", 2, "unidades"),
    ("Calculadora científica", "Material didáctico", "Casio fx-82MS", 8, "unidades"),
    ("Globo terráqueo", "Material didáctico", "Mapamundi político, 30 cm", 3, "unidades"),
    ("Set de reglas geométricas", "Material didáctico", "Regla, escuadra y transportador", 10, "sets"),
    ("Microscopio escolar", "Material didáctico", "Monocular, aumento 40x-400x", 2, "unidades"),
    ("Cable HDMI", "Accesorio", "HDMI 2.0, 2 metros", 5, "unidades"),
    ("Juego de ajedrez", "Material didáctico", "Tablero plegable, piezas plásticas", 4, "sets"),
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS inventory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    model_or_publisher TEXT NOT NULL,
    total_quantity INTEGER NOT NULL CHECK (total_quantity >= 0),
    unit TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS members (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    role TEXT NOT NULL,
    email TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1))
);

CREATE TABLE IF NOT EXISTS loans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    member_id TEXT NOT NULL REFERENCES members(id),
    notification_email TEXT NOT NULL,
    due_date TEXT NOT NULL,
    created_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'returned')),
    returned_at TEXT,
    reminder_sent INTEGER NOT NULL DEFAULT 0 CHECK (reminder_sent IN (0, 1)),
    renewal_count INTEGER NOT NULL DEFAULT 0 CHECK (renewal_count IN (0, 1))
);

CREATE TABLE IF NOT EXISTS loan_items (
    loan_id INTEGER NOT NULL REFERENCES loans(id) ON DELETE CASCADE,
    inventory_id INTEGER NOT NULL REFERENCES inventory(id),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    PRIMARY KEY (loan_id, inventory_id)
);
"""

import os
app = app = Flask(__name__)
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)


def connect_db() -> sqlite3.Connection:
    connection = sqlite3.connect(current_app.config["DATABASE"], timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


@contextmanager
def database_connection():
    connection = connect_db()
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def initialize_database(database: str) -> None:
    Path(database).parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript(SCHEMA)
        member_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(members)")
        }
        if "active" not in member_columns:
            connection.execute(
                "ALTER TABLE members ADD COLUMN active INTEGER NOT NULL DEFAULT 1"
            )
        loan_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(loans)")
        }
        if "renewal_count" not in loan_columns:
            connection.execute(
                "ALTER TABLE loans ADD COLUMN renewal_count INTEGER NOT NULL DEFAULT 0"
            )
        connection.executemany(
            """
            INSERT OR IGNORE INTO inventory
                (name, category, model_or_publisher, total_quantity, unit)
            VALUES (?, ?, ?, ?, ?)
            """,
            SEED_INVENTORY,
        )
        connection.commit()
    finally:
        connection.close()


def csrf_token() -> str:
    token = session.get("_csrf_token")
    if token is None:
        token = secrets.token_urlsafe(32)
        session["_csrf_token"] = token
    return token


def is_institutional_email(email: str) -> bool:
    domain = current_app.config["INSTITUTIONAL_EMAIL_DOMAIN"].strip().lower()
    return bool(
        domain
        and re.fullmatch(r"[^@\s]+@[^@\s]+", email)
        and email.lower().endswith(domain)
    )


def inventory_with_availability() -> list[sqlite3.Row]:
    with database_connection() as connection:
        return connection.execute(
            """
            SELECT i.*,
                i.total_quantity - COALESCE(SUM(
                    CASE WHEN l.status = 'active' THEN li.quantity ELSE 0 END
                ), 0) AS available
            FROM inventory AS i
            LEFT JOIN loan_items AS li ON li.inventory_id = i.id
            LEFT JOIN loans AS l ON l.id = li.loan_id
            GROUP BY i.id
            ORDER BY i.category, i.name
            """
        ).fetchall()


def create_app(test_config: dict[str, Any] | None = None) -> Flask:
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("FLASK_SECRET_KEY", "dev-only-change-this-key"),
        DATABASE=os.environ.get(
            "BIBLIOTECA_DATABASE",
            str(Path(app.instance_path) / "biblioteca.sqlite3"),
        ),
        MAIL_HOST=os.environ.get("MAIL_HOST", ""),
        MAIL_PORT=int(os.environ.get("MAIL_PORT", "587")),
        MAIL_USERNAME=os.environ.get("MAIL_USERNAME", ""),
        MAIL_PASSWORD=os.environ.get("MAIL_PASSWORD", ""),
        MAIL_FROM=os.environ.get("MAIL_FROM", ""),
        INSTITUTIONAL_EMAIL_DOMAIN=os.environ.get(
            "INSTITUTIONAL_EMAIL_DOMAIN", "@colegiosanlorenzo.org"
        ),
    )
    if test_config:
        app.config.update(test_config)

    initialize_database(app.config["DATABASE"])

    @app.before_request
    def validate_csrf() -> None:
        if request.method == "POST":
            submitted_token = request.form.get("_csrf_token", "")
            if not secrets.compare_digest(submitted_token, session.get("_csrf_token", "")):
                abort(400, description="El formulario expiró. Recarga la página e inténtalo otra vez.")

    @app.context_processor
    def inject_template_values() -> dict[str, Any]:
        return {"csrf_token": csrf_token}

    @app.get("/")
    def index():
        with database_connection() as connection:
            active_loans = connection.execute(
                "SELECT COUNT(*) FROM loans WHERE status = 'active'"
            ).fetchone()[0]
            member_count = connection.execute(
                "SELECT COUNT(*) FROM members"
            ).fetchone()[0]
        available_items = sum(item["available"] for item in inventory_with_availability())
        return render_template(
            "index.html",
            active_loans=active_loans,
            member_count=member_count,
            available_items=available_items,
        )

    @app.route("/solicitud", methods=["GET", "POST"])
    def new_loan():
        if request.method == "POST":
            member_id = request.form.get("member_id", "").strip()
            email = request.form.get("email", "").strip()
            due_date_value = request.form.get("due_date", "").strip()
            errors: list[str] = []

            if not member_id:
                errors.append("Ingresa el ID de la persona solicitante.")
            if not email or not is_institutional_email(email):
                errors.append(
                    "Usa tu correo institucional "
                    f"({current_app.config['INSTITUTIONAL_EMAIL_DOMAIN']})."
                )
            try:
                due_date = date.fromisoformat(due_date_value)
                if due_date <= date.today():
                    errors.append("La fecha de devolución debe ser posterior a hoy.")
                elif due_date > date.today() + timedelta(weeks=3):
                    errors.append("El plazo máximo de préstamo es de 3 semanas.")
            except ValueError:
                errors.append("Selecciona una fecha de devolución válida.")

            selected: dict[int, int] = {}
            item_ids = request.form.getlist("item_id")
            quantities = request.form.getlist("quantity")
            for item_id_value, quantity_value in zip(item_ids, quantities):
                if not item_id_value:
                    continue
                try:
                    item_id = int(item_id_value)
                    quantity = int(quantity_value)
                except ValueError:
                    errors.append("Selecciona materiales y cantidades válidas.")
                    continue
                if quantity < 1:
                    errors.append("Cada material seleccionado debe tener una cantidad de al menos 1.")
                    continue
                selected[item_id] = selected.get(item_id, 0) + quantity

            total_requested = sum(selected.values())
            if total_requested == 0:
                errors.append("Selecciona al menos un material.")
            elif total_requested > 3:
                errors.append("Una persona puede solicitar como máximo 3 objetos.")

            if errors:
                for error in dict.fromkeys(errors):
                    flash(error, "error")
                return redirect(url_for("new_loan"))

            connection = connect_db()
            try:
                connection.execute("BEGIN IMMEDIATE")
                member = connection.execute(
                    "SELECT id FROM members WHERE id = ? AND active = 1", (member_id,)
                ).fetchone()
                if member is None:
                    flash(
                        "No encontramos un miembro activo con ese ID. Verifica el dato o registra primero a la persona.",
                        "error",
                    )
                    return redirect(url_for("new_loan"))

                for item_id, quantity in selected.items():
                    item = connection.execute(
                        """
                        SELECT i.name, i.total_quantity - COALESCE(SUM(
                            CASE WHEN l.status = 'active' THEN li.quantity ELSE 0 END
                        ), 0) AS available
                        FROM inventory AS i
                        LEFT JOIN loan_items AS li ON li.inventory_id = i.id
                        LEFT JOIN loans AS l ON l.id = li.loan_id
                        WHERE i.id = ?
                        GROUP BY i.id
                        """,
                        (item_id,),
                    ).fetchone()
                    if item is None:
                        flash("Uno de los materiales seleccionados ya no existe.", "error")
                        return redirect(url_for("new_loan"))
                    if quantity > item["available"]:
                        flash(
                            f"No hay suficientes unidades disponibles de «{item['name']}».",
                            "error",
                        )
                        return redirect(url_for("new_loan"))

                cursor = connection.execute(
                    """
                    INSERT INTO loans (member_id, notification_email, due_date, created_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (member_id, email, due_date.isoformat(), datetime.now().isoformat(timespec="seconds")),
                )
                connection.executemany(
                    "INSERT INTO loan_items (loan_id, inventory_id, quantity) VALUES (?, ?, ?)",
                    [(cursor.lastrowid, item_id, quantity) for item_id, quantity in selected.items()],
                )
                connection.commit()
                flash(f"Solicitud #{cursor.lastrowid} registrada correctamente.", "success")
                return redirect(url_for("requests_list"))
            except sqlite3.Error:
                connection.rollback()
                current_app.logger.exception("No se pudo registrar la solicitud")
                flash("No se pudo guardar la solicitud. Inténtalo de nuevo.", "error")
                return redirect(url_for("new_loan"))
            finally:
                connection.close()

        with database_connection() as connection:
            members = connection.execute(
                "SELECT id, name, role FROM members WHERE active = 1 ORDER BY name"
            ).fetchall()
        return render_template(
            "new_loan.html",
            members=members,
            inventory=inventory_with_availability(),
            min_due_date=(date.today() + timedelta(days=1)).isoformat(),
            max_due_date=(date.today() + timedelta(weeks=3)).isoformat(),
            email_domain=current_app.config["INSTITUTIONAL_EMAIL_DOMAIN"],
        )

    @app.route("/inventario", methods=["GET", "POST"])
    def inventory():
        if request.method == "POST":
            name = request.form.get("name", "").strip()
            category = request.form.get("category", "").strip()
            model_or_publisher = request.form.get("model_or_publisher", "").strip()
            unit = request.form.get("unit", "").strip()
            try:
                quantity = int(request.form.get("quantity", ""))
            except ValueError:
                quantity = 0
            if (
                not all((name, category, model_or_publisher, unit))
                or quantity < 1
                or quantity > 10000
            ):
                flash("Completa todos los campos y registra al menos una unidad.", "error")
                return redirect(url_for("inventory"))
            try:
                with database_connection() as connection:
                    connection.execute(
                        """
                        INSERT INTO inventory
                            (name, category, model_or_publisher, total_quantity, unit)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (name, category, model_or_publisher, quantity, unit),
                    )
            except sqlite3.Error:
                current_app.logger.exception("No se pudo agregar el material al inventario")
                flash("No se pudo guardar el material. Inténtalo de nuevo.", "error")
                return redirect(url_for("inventory"))
            flash(f"Se agregaron {quantity} {unit} de «{name}».", "success")
            return redirect(url_for("inventory"))

        available_inventory = inventory_with_availability()
        categories = sorted({item["category"] for item in available_inventory})
        return render_template(
            "inventory.html", inventory=available_inventory, categories=categories
        )

    @app.route("/miembros", methods=["GET", "POST"])
    def members():
        if request.method == "POST":
            name = request.form.get("name", "").strip()
            role = request.form.get("role", "").strip()
            email = request.form.get("email", "").strip()
            if not name or not role or not is_institutional_email(email):
                flash(
                    "Completa nombre, tipo de miembro y un correo institucional "
                    f"({current_app.config['INSTITUTIONAL_EMAIL_DOMAIN']}).",
                    "error",
                )
                return redirect(url_for("members"))
            email = email.lower()

            with database_connection() as connection:
                connection.execute("BEGIN IMMEDIATE")
                latest_id = connection.execute(
                    "SELECT MAX(CAST(id AS INTEGER)) FROM members"
                ).fetchone()[0]
                member_id = f"{(latest_id or 0) + 1:03d}"
                connection.execute(
                    "INSERT INTO members (id, name, role, email) VALUES (?, ?, ?, ?)",
                    (member_id, name, role, email),
                )
            flash(f"Miembro registrado con el ID {member_id}.", "success")
            return redirect(url_for("members"))

        with database_connection() as connection:
            member_list = connection.execute(
                """
                SELECT m.id, m.name, m.role, m.email, m.active,
                    EXISTS(
                        SELECT 1 FROM loans l
                        WHERE l.member_id = m.id AND l.status = 'active'
                    ) AS has_active_loans
                FROM members m
                ORDER BY m.active DESC, CAST(m.id AS INTEGER)
                """
            ).fetchall()
        return render_template("members.html", members=member_list)

    @app.post("/miembros/<member_id>/estado")
    def toggle_member_status(member_id: str):
        with database_connection() as connection:
            cursor = connection.execute(
                "UPDATE members SET active = 1 - active WHERE id = ?", (member_id,)
            )
            member = connection.execute(
                "SELECT name, active FROM members WHERE id = ?", (member_id,)
            ).fetchone()
        if cursor.rowcount == 0 or member is None:
            flash("No encontramos ese miembro.", "error")
        elif member["active"]:
            flash(f"{member['name']} volvió a quedar habilitado.", "success")
        else:
            flash(f"{member['name']} fue dado de baja. Su historial se conservó.", "success")
        return redirect(url_for("members"))

    @app.get("/solicitudes")
    def requests_list():
        with database_connection() as connection:
            loans = connection.execute(
                """
                SELECT l.id, l.member_id, m.name AS member_name, l.notification_email,
                    l.due_date, l.created_at, l.status, l.renewal_count,
                    GROUP_CONCAT(i.name || ' ×' || li.quantity, ', ') AS materials
                FROM loans AS l
                JOIN members AS m ON m.id = l.member_id
                JOIN loan_items AS li ON li.loan_id = l.id
                JOIN inventory AS i ON i.id = li.inventory_id
                GROUP BY l.id
                ORDER BY CASE WHEN l.status = 'active' THEN 0 ELSE 1 END,
                    l.due_date, l.id DESC
                """
            ).fetchall()
        return render_template("requests.html", loans=loans, today=date.today().isoformat())

    @app.post("/solicitudes/<int:loan_id>/devolver")
    def return_loan(loan_id: int):
        with database_connection() as connection:
            cursor = connection.execute(
                """
                UPDATE loans SET status = 'returned', returned_at = ?
                WHERE id = ? AND status = 'active'
                """,
                (datetime.now().isoformat(timespec="seconds"), loan_id),
            )
            if cursor.rowcount == 0:
                flash("La solicitud no existe o ya fue devuelta.", "error")
            else:
                flash(f"Solicitud #{loan_id} marcada como devuelta.", "success")
        return redirect(url_for("requests_list"))

    @app.post("/solicitudes/<int:loan_id>/renovar")
    def renew_loan(loan_id: int):
        with database_connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            loan = connection.execute(
                "SELECT due_date, renewal_count FROM loans WHERE id = ? AND status = 'active'",
                (loan_id,),
            ).fetchone()
            if loan is None:
                flash("La solicitud no existe o ya fue devuelta.", "error")
            elif loan["renewal_count"] >= 1:
                flash("Esta solicitud ya utilizó su única renovación.", "error")
            else:
                current_due_date = date.fromisoformat(loan["due_date"])
                new_due_date = max(current_due_date, date.today()) + timedelta(weeks=3)
                connection.execute(
                    """
                    UPDATE loans
                    SET due_date = ?, renewal_count = renewal_count + 1, reminder_sent = 0
                    WHERE id = ? AND status = 'active' AND renewal_count = 0
                    """,
                    (new_due_date.isoformat(), loan_id),
                )
                flash(
                    f"Solicitud #{loan_id} renovada hasta el {new_due_date.isoformat()}.",
                    "success",
                )
        return redirect(url_for("requests_list"))

    @app.cli.command("send-reminders")
    @click.option("--days", default=2, show_default=True, type=click.IntRange(min=0))
    def send_reminders(days: int) -> None:
        """Envía por correo recordatorios de devoluciones próximas."""
        required_settings = ("MAIL_HOST", "MAIL_USERNAME", "MAIL_PASSWORD", "MAIL_FROM")
        missing = [key for key in required_settings if not app.config.get(key)]
        if missing:
            raise click.ClickException(
                "Configura estas variables de correo antes de enviar recordatorios: "
                + ", ".join(missing)
            )

        through_date = (date.today() + timedelta(days=days)).isoformat()
        with app.app_context():
            with database_connection() as connection:
                due_loans = connection.execute(
                    """
                    SELECT l.id, l.notification_email, l.due_date, m.name AS member_name,
                        GROUP_CONCAT(i.name || ' ×' || li.quantity, ', ') AS materials
                    FROM loans AS l
                    JOIN members AS m ON m.id = l.member_id
                    JOIN loan_items AS li ON li.loan_id = l.id
                    JOIN inventory AS i ON i.id = li.inventory_id
                    WHERE l.status = 'active' AND l.reminder_sent = 0
                        AND l.due_date BETWEEN ? AND ?
                    GROUP BY l.id
                    """,
                    (date.today().isoformat(), through_date),
                ).fetchall()
                sent = 0
                with smtplib.SMTP(app.config["MAIL_HOST"], app.config["MAIL_PORT"], timeout=15) as smtp:
                    smtp.starttls()
                    smtp.login(app.config["MAIL_USERNAME"], app.config["MAIL_PASSWORD"])
                    for loan in due_loans:
                        message = EmailMessage()
                        message["Subject"] = f"Recordatorio de devolución — solicitud #{loan['id']}"
                        message["From"] = app.config["MAIL_FROM"]
                        message["To"] = loan["notification_email"]
                        message.set_content(
                            f"Hola {loan['member_name']},\n\n"
                            f"Recuerda devolver {loan['materials']} el {loan['due_date']}.\n"
                            "Si ya lo devolviste, contacta al staff de la biblioteca.\n"
                        )
                        smtp.send_message(message)
                        connection.execute(
                            "UPDATE loans SET reminder_sent = 1 WHERE id = ?", (loan["id"],)
                        )
                        sent += 1
                click.echo(f"Recordatorios enviados: {sent}")

    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1")
