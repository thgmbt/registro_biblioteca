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
                "email": "ana@example.cl",
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
            "email": "ana@example.cl",
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
            due_date=date.today().isoformat(),
        )
        self.assertIn(b"posterior a hoy", response.data)
        self.assertIn(b"No encontramos ese ID", response.data)

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
                "email": "docente@example.cl",
            },
        )
        self.assertIn(b"002", self.client.get("/miembros").data)


if __name__ == "__main__":
    unittest.main()
