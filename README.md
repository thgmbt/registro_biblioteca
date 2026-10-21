# Registro de biblioteca escolar

Aplicación web en Flask para registrar miembros de la comunidad escolar, controlar el inventario y llevar solicitudes de préstamo y devoluciones. La interfaz es adaptable a móviles y computadores. La base de datos SQLite se crea automáticamente en `instance/biblioteca.sqlite3`.

## Requisitos y ejecución

Requiere Python 3.10 o posterior.

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
flask --app app run --debug
```

Abre `http://127.0.0.1:5000`. También puedes iniciar la aplicación con `py app.py`.

## Funciones

- **Inventario:** lista de ejemplo con libros, equipos tecnológicos y material didáctico; permite agregar registros y filtrar por categoría o búsqueda.
- **Miembros:** registro de estudiantes, docentes y funcionarios con correo `@colegiosanlorenzo.org`. Los identificadores se asignan correlativamente desde `001`. Dar de baja conserva el historial de préstamos y evita nuevos préstamos.
- **Solicitudes:** exige ID de miembro activo, correo institucional y fecha de devolución futura; permite entre 1 y 3 unidades por solicitud y evita prestar más unidades de las disponibles. El plazo máximo es de tres semanas.
- **Renovaciones:** cada préstamo activo puede renovarse una vez por otras tres semanas. Se reinicia el recordatorio de devolución al renovar.
- **Devoluciones:** el staff puede marcar préstamos como devueltos para reponer disponibilidad.
- **Recordatorios:** el comando `flask --app app send-reminders` envía recordatorios de préstamos con devolución dentro de los próximos dos días. Se puede ejecutar diariamente con el programador de tareas del sistema.

Los 12 registros de `SEED_INVENTORY` en `app.py` son **datos ficticios de ejemplo**, no corresponden al stock de un colegio específico. Reemplázalos por los materiales reales antes de usar la aplicación. Los datos de ejemplo se insertan al crear la base de datos; no sobrescriben existencias ya guardadas.

El dominio institucional se configura con `INSTITUTIONAL_EMAIL_DOMAIN` (por defecto `@colegiosanlorenzo.org`) si el colegio cambia de dominio. En instalaciones existentes, la aplicación añade automáticamente los campos de renovación y estado de miembro.

## Configurar correo para recordatorios

Define las variables SMTP en el entorno antes de ejecutar el comando. Por ejemplo, en PowerShell:

```powershell
$env:MAIL_HOST = "smtp.example.cl"
$env:MAIL_PORT = "587"
$env:MAIL_USERNAME = "cuenta@example.cl"
$env:MAIL_PASSWORD = "contraseña-de-aplicación"
$env:MAIL_FROM = "Biblioteca <cuenta@example.cl>"
$env:INSTITUTIONAL_EMAIL_DOMAIN = "@colegiosanlorenzo.org"
flask --app app send-reminders --days 2
```

El comando marca cada recordatorio como enviado solo después de enviarlo correctamente. Sin configuración SMTP, las solicitudes se siguen registrando, pero no se envían correos.

## Consideraciones antes de publicar

Este proyecto es una base funcional para desarrollo y demostración. La vista de staff no tiene autenticación: antes de exponerla en una red pública, añade inicio de sesión y permisos para proteger datos personales y acciones de devolución. En despliegue, define también `FLASK_SECRET_KEY` con un secreto aleatorio y usa HTTPS.

## Pruebas

```powershell
py -m unittest discover -s tests
```
