import os
import pymysql
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash

load_dotenv()


def crear_admin():
    connection = pymysql.connect(
        host=os.getenv("MYSQL_HOST"),
        user=os.getenv("MYSQL_USER"),
        password=os.getenv("MYSQL_PASSWORD"),
        database=os.getenv("MYSQL_DB"),
        port=int(os.getenv("MYSQL_PORT", 3306)),
        cursorclass=pymysql.cursors.DictCursor,
        charset="utf8mb4"
    )

    try:
        with connection.cursor() as cursor:
            email_admin = "admin@ropusac.com"
            password_admin = "Admin123456*"

            cursor.execute("SELECT id FROM roles WHERE nombre = 'administrador'")
            rol = cursor.fetchone()

            if not rol:
                print("No existe el rol administrador en la base de datos.")
                return

            cursor.execute("SELECT id FROM usuarios WHERE email = %s", (email_admin,))
            usuario_existente = cursor.fetchone()

            if usuario_existente:
                print("El usuario administrador ya existe.")
                return

            password_hash = generate_password_hash(password_admin)

            sql = """
                INSERT INTO usuarios 
                (rol_id, nombres, apellidos, email, password_hash, telefono, estado)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """

            cursor.execute(sql, (
                rol["id"],
                "Administrador",
                "ROPUSAC",
                email_admin,
                password_hash,
                "999999999",
                "activo"
            ))

            connection.commit()

            print("Usuario administrador creado correctamente.")
            print("Correo:", email_admin)
            print("Contraseña:", password_admin)

    except Exception as e:
        print("Error al crear administrador:", e)

    finally:
        connection.close()


if __name__ == "__main__":
    crear_admin()