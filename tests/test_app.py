import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from app import create_app


class BibliotecaAppTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        database = str(Path(self.temp_dir.name) / "test.sqlite3")
        self.app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "test-secret",
                "DATABASE": database,
            }
        )
        self.client = self.app.test_client()
        self.register_member()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def token(self) -> str:
        response = self.client.get("/miembros")
        self.assertEqual(response.status_code, 200)
        with self.client.session_transaction() as session:
            return session["_csrf_token"]

    def register_member(self) -> None:
        response = self.client.get("/miembros")
        with self.client.session_transaction() as session:
            token = session["_csrf_token"]
        response = self.client.post(
            "/miembros",
            data={
                "_csrf_token": token,
                "name": "Ana Ejemplo",
                "role": "Estudiante",
                "email": "ana@colegiosanlorenzo.org",
            },
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"001", response.data)

    def seed_item_id(self, name: str) -> int:
        with self.app.app_context():
            import sqlite3

            connection = sqlite3.connect(self.app.config["DATABASE"])
            try:
                return connection.execute(
                    "SELECT id FROM inventory WHERE name = ?", (name,)
                ).fetchone()[0]
            finally:
                connection.close()

    def submit_loan(self, item_ids: list[int], quantities: list[int], **overrides):
        data = {
            "_csrf_token": self.token(),
            "member_id": "001",
            "email": "ana@colegiosanlorenzo.org",
            "due_date": (date.today() + timedelta(days=7)).isoformat(),
            "item_id": [str(item_id) for item_id in item_ids],
            "quantity": [str(quantity) for quantity in quantities],
        }
        data.update(overrides)
        return self.client.post("/solicitud", data=data, follow_redirects=True)

    def test_seeded_inventory_is_visible(self) -> None:
        response = self.client.get("/inventario")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Proyector portátil".encode(), response.data)
        self.assertIn(b"Editorial Diana", response.data)

    def test_request_reserves_stock_and_return_releases_it(self) -> None:
        item_id = self.seed_item_id("Proyector portátil")
        response = self.submit_loan([item_id], [1])
        self.assertIn(b"Solicitud #1 registrada correctamente", response.data)
        inventory = self.client.get("/inventario")
        self.assertIn(b"1 disp.", inventory.data)

        response = self.client.post(
            "/solicitudes/1/devolver",
            data={"_csrf_token": self.token()},
            follow_redirects=True,
        )
        self.assertIn(b"marcada como devuelta", response.data)
        self.assertIn(b"2 disp.", self.client.get("/inventario").data)

    def test_cannot_request_more_than_three_objects(self) -> None:
        item_id = self.seed_item_id("Calculadora científica")
        response = self.submit_loan([item_id, item_id], [2, 2])
        self.assertIn(b"como m\xc3\xa1ximo 3 objetos", response.data)
        self.assertNotIn(b"Solicitud #1 registrada correctamente", response.data)

    def test_requires_member_and_valid_return_date(self) -> None:
        item_id = self.seed_item_id("Cable HDMI")
        response = self.submit_loan(
            [item_id],
            [1],
            member_id="999",
            due_date=(date.today() + timedelta(days=2)).isoformat(),
        )
        self.assertIn(b"No encontramos un miembro activo", response.data)
        response = self.submit_loan(
            [item_id],
            [1],
            due_date=date.today().isoformat(),
        )
        self.assertIn(b"posterior a hoy", response.data)

    def test_rejects_due_date_beyond_three_weeks(self) -> None:
        item_id = self.seed_item_id("Cable HDMI")
        response = self.submit_loan(
            [item_id],
            [1],
            due_date=(date.today() + timedelta(days=22)).isoformat(),
        )
        self.assertIn(b"plazo m\xc3\xa1ximo de pr\xc3\xa9stamo", response.data)

    def test_renews_active_loan_once_for_three_weeks(self) -> None:
        item_id = self.seed_item_id("Cable HDMI")
        due_date = date.today() + timedelta(days=7)
        self.submit_loan([item_id], [1], due_date=due_date.isoformat())

        response = self.client.post(
            "/solicitudes/1/renovar",
            data={"_csrf_token": self.token()},
            follow_redirects=True,
        )
        renewed_date = due_date + timedelta(weeks=3)
        self.assertIn(renewed_date.isoformat().encode(), response.data)
        self.assertIn(b"Renovada", response.data)

        response = self.client.post(
            "/solicitudes/1/renovar",
            data={"_csrf_token": self.token()},
            follow_redirects=True,
        )
        self.assertIn(b"ya utiliz\xc3\xb3 su \xc3\xbanica renovaci\xc3\xb3n", response.data)

    def test_only_institutional_emails_are_accepted(self) -> None:
        response = self.client.post(
            "/miembros",
            data={
                "_csrf_token": self.token(),
                "name": "Invitado",
                "role": "Estudiante",
                "email": "persona@example.com",
            },
            follow_redirects=True,
        )
        self.assertIn(b"correo institucional", response.data)
        self.assertNotIn(b"Miembro registrado con el ID 002", response.data)

    def test_can_add_inventory_and_filter_by_category(self) -> None:
        response = self.client.post(
            "/inventario",
            data={
                "_csrf_token": self.token(),
                "name": "Atlas nuevo",
                "category": "Libro",
                "model_or_publisher": "Ediciones escolares",
                "quantity": "4",
                "unit": "ejemplares",
            },
            follow_redirects=True,
        )
        self.assertIn(b"Se agregaron 4 ejemplares", response.data)
        self.assertIn(b"Atlas nuevo", response.data)
        self.assertIn(b"Todas las categor\xc3\xadas", response.data)

    def test_deactivating_member_preserves_history_and_blocks_new_loans(self) -> None:
        item_id = self.seed_item_id("Cable HDMI")
        self.submit_loan([item_id], [1])
        response = self.client.post(
            "/miembros/001/estado",
            data={"_csrf_token": self.token()},
            follow_redirects=True,
        )
        self.assertIn(b"historial se conserv\xc3\xb3", response.data)
        response = self.submit_loan([item_id], [1])
        self.assertIn(b"miembro activo con ese ID", response.data)

    def test_rejects_post_without_csrf_token(self) -> None:
        response = self.client.post(
            "/miembros",
            data={"name": "No registrado", "role": "Estudiante", "email": "x@example.cl"},
        )
        self.assertEqual(response.status_code, 400)

    def test_member_ids_increment_from_001(self) -> None:
        self.client.post(
            "/miembros",
            data={
                "_csrf_token": self.token(),
                "name": "Docente Ejemplo",
                "role": "Docente",
                "email": "docente@colegiosanlorenzo.org",
            },
        )
        self.assertIn(b"002", self.client.get("/miembros").data)


if __name__ == "__main__":
    unittest.main()
