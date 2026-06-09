from flask_login import UserMixin
from app.extensions import get_db_connection


class Usuario(UserMixin):
    def __init__(
        self,
        id,
        rol_id,
        rol_nombre,
        nombres,
        apellidos,
        email,
        estado,
        password_hash=None
    ):
        self.id = id
        self.rol_id = rol_id
        self.rol_nombre = rol_nombre
        self.nombres = nombres
        self.apellidos = apellidos
        self.email = email
        self.estado = estado
        self.password_hash = password_hash

    @staticmethod
    def buscar_por_id(usuario_id):
        connection = get_db_connection()

        try:
            with connection.cursor() as cursor:
                sql = """
                    SELECT 
                        u.id,
                        u.rol_id,
                        r.nombre AS rol_nombre,
                        u.nombres,
                        u.apellidos,
                        u.email,
                        u.estado
                    FROM usuarios u
                    INNER JOIN roles r ON u.rol_id = r.id
                    WHERE u.id = %s
                    LIMIT 1
                """
                cursor.execute(sql, (usuario_id,))
                usuario = cursor.fetchone()

            if usuario:
                return Usuario(
                    id=usuario["id"],
                    rol_id=usuario["rol_id"],
                    rol_nombre=usuario["rol_nombre"],
                    nombres=usuario["nombres"],
                    apellidos=usuario["apellidos"],
                    email=usuario["email"],
                    estado=usuario["estado"]
                )

            return None

        finally:
            connection.close()

    @staticmethod
    def buscar_por_email(email):
        connection = get_db_connection()

        try:
            with connection.cursor() as cursor:
                sql = """
                    SELECT 
                        u.id,
                        u.rol_id,
                        r.nombre AS rol_nombre,
                        u.nombres,
                        u.apellidos,
                        u.email,
                        u.estado,
                        u.password_hash
                    FROM usuarios u
                    INNER JOIN roles r ON u.rol_id = r.id
                    WHERE u.email = %s
                    LIMIT 1
                """
                cursor.execute(sql, (email,))
                usuario = cursor.fetchone()

            if usuario:
                return Usuario(
                    id=usuario["id"],
                    rol_id=usuario["rol_id"],
                    rol_nombre=usuario["rol_nombre"],
                    nombres=usuario["nombres"],
                    apellidos=usuario["apellidos"],
                    email=usuario["email"],
                    estado=usuario["estado"],
                    password_hash=usuario["password_hash"]
                )

            return None

        finally:
            connection.close()