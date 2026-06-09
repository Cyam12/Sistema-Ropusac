from flask import Blueprint, render_template, request, redirect, url_for, flash, Response, current_app
from flask_login import login_required, current_user
from werkzeug.security import generate_password_hash

from app.auth.decorators import rol_required
from app.extensions import get_db_connection

import csv
from io import StringIO

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


@admin_bp.route("/dashboard")
@login_required
@rol_required("administrador")
def dashboard():
    connection = get_db_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM vw_dashboard_admin LIMIT 1")
            metricas = cursor.fetchone()

        if metricas is None:
            metricas = {
                "total_cotizaciones": 0,
                "cotizaciones_pendientes": 0,
                "cotizaciones_cerradas": 0,
                "ventas_mes": 0,
                "margen_mes": 0,
                "total_clientes": 0,
                "total_proveedores": 0,
                "total_productos": 0
            }

        return render_template("admin/dashboard.html", metricas=metricas)

    finally:
        connection.close()


@admin_bp.route("/usuarios")
@login_required
@rol_required("administrador")
def usuarios():
    connection = get_db_connection()

    try:
        with connection.cursor() as cursor:
            sql = """
                SELECT 
                    u.id,
                    u.nombres,
                    u.apellidos,
                    u.email,
                    u.telefono,
                    u.estado,
                    u.ultimo_login,
                    u.created_at,
                    r.nombre AS rol
                FROM usuarios u
                INNER JOIN roles r ON u.rol_id = r.id
                ORDER BY u.id DESC
            """
            cursor.execute(sql)
            usuarios = cursor.fetchall()

        return render_template("admin/usuarios.html", usuarios=usuarios)

    finally:
        connection.close()


@admin_bp.route("/usuarios/nuevo", methods=["GET", "POST"])
@login_required
@rol_required("administrador")
def nuevo_usuario():
    connection = get_db_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT id, nombre 
                FROM roles 
                WHERE estado = 'activo'
                ORDER BY nombre ASC
            """)
            roles = cursor.fetchall()

        if request.method == "POST":
            rol_id = request.form.get("rol_id")
            nombres = request.form.get("nombres", "").strip()
            apellidos = request.form.get("apellidos", "").strip()
            email = request.form.get("email", "").strip().lower()
            telefono = request.form.get("telefono", "").strip()
            password = request.form.get("password", "").strip()
            confirmar_password = request.form.get("confirmar_password", "").strip()
            estado = request.form.get("estado", "activo")

            if not rol_id or not nombres or not apellidos or not email or not password:
                flash("Completa todos los campos obligatorios.", "warning")
                return render_template("admin/nuevo_usuario.html", roles=roles)

            if password != confirmar_password:
                flash("Las contraseñas no coinciden.", "danger")
                return render_template("admin/nuevo_usuario.html", roles=roles)

            if len(password) < 8:
                flash("La contraseña debe tener mínimo 8 caracteres.", "warning")
                return render_template("admin/nuevo_usuario.html", roles=roles)

            with connection.cursor() as cursor:
                cursor.execute("SELECT id FROM usuarios WHERE email = %s", (email,))
                usuario_existente = cursor.fetchone()

                if usuario_existente:
                    flash("Ya existe un usuario registrado con ese correo.", "danger")
                    return render_template("admin/nuevo_usuario.html", roles=roles)

                password_hash = generate_password_hash(password)

                sql = """
                    INSERT INTO usuarios
                    (rol_id, nombres, apellidos, email, password_hash, telefono, estado)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """

                cursor.execute(sql, (
                    rol_id,
                    nombres,
                    apellidos,
                    email,
                    password_hash,
                    telefono,
                    estado
                ))

            connection.commit()

            flash("Usuario creado correctamente.", "success")
            return redirect(url_for("admin.usuarios"))

        return render_template("admin/nuevo_usuario.html", roles=roles)

    finally:
        connection.close()


@admin_bp.route("/usuarios/<int:usuario_id>/editar", methods=["GET", "POST"])
@login_required
@rol_required("administrador")
def editar_usuario(usuario_id):
    connection = get_db_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT id, nombre 
                FROM roles 
                WHERE estado = 'activo'
                ORDER BY nombre ASC
            """)
            roles = cursor.fetchall()

            cursor.execute("""
                SELECT 
                    id,
                    rol_id,
                    nombres,
                    apellidos,
                    email,
                    telefono,
                    estado
                FROM usuarios
                WHERE id = %s
                LIMIT 1
            """, (usuario_id,))
            usuario = cursor.fetchone()

        if not usuario:
            flash("El usuario no existe.", "danger")
            return redirect(url_for("admin.usuarios"))

        if request.method == "POST":
            rol_id = request.form.get("rol_id")
            nombres = request.form.get("nombres", "").strip()
            apellidos = request.form.get("apellidos", "").strip()
            email = request.form.get("email", "").strip().lower()
            telefono = request.form.get("telefono", "").strip()
            estado = request.form.get("estado", "activo")
            password = request.form.get("password", "").strip()
            confirmar_password = request.form.get("confirmar_password", "").strip()

            if not rol_id or not nombres or not apellidos or not email:
                flash("Completa todos los campos obligatorios.", "warning")
                return render_template("admin/editar_usuario.html", usuario=usuario, roles=roles)

            if password:
                if password != confirmar_password:
                    flash("Las contraseñas no coinciden.", "danger")
                    return render_template("admin/editar_usuario.html", usuario=usuario, roles=roles)

                if len(password) < 8:
                    flash("La nueva contraseña debe tener mínimo 8 caracteres.", "warning")
                    return render_template("admin/editar_usuario.html", usuario=usuario, roles=roles)

            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT id 
                    FROM usuarios 
                    WHERE email = %s AND id != %s
                    LIMIT 1
                """, (email, usuario_id))
                email_existente = cursor.fetchone()

                if email_existente:
                    flash("Ya existe otro usuario con ese correo.", "danger")
                    return render_template("admin/editar_usuario.html", usuario=usuario, roles=roles)

                if password:
                    password_hash = generate_password_hash(password)

                    sql = """
                        UPDATE usuarios
                        SET rol_id = %s,
                            nombres = %s,
                            apellidos = %s,
                            email = %s,
                            telefono = %s,
                            estado = %s,
                            password_hash = %s
                        WHERE id = %s
                    """

                    cursor.execute(sql, (
                        rol_id,
                        nombres,
                        apellidos,
                        email,
                        telefono,
                        estado,
                        password_hash,
                        usuario_id
                    ))

                else:
                    sql = """
                        UPDATE usuarios
                        SET rol_id = %s,
                            nombres = %s,
                            apellidos = %s,
                            email = %s,
                            telefono = %s,
                            estado = %s
                        WHERE id = %s
                    """

                    cursor.execute(sql, (
                        rol_id,
                        nombres,
                        apellidos,
                        email,
                        telefono,
                        estado,
                        usuario_id
                    ))

            connection.commit()

            flash("Usuario actualizado correctamente.", "success")
            return redirect(url_for("admin.usuarios"))

        return render_template("admin/editar_usuario.html", usuario=usuario, roles=roles)

    finally:
        connection.close()


@admin_bp.route("/usuarios/<int:usuario_id>/eliminar", methods=["POST"])
@login_required
@rol_required("administrador")
def eliminar_usuario(usuario_id):
    if usuario_id == int(current_user.id):
        flash("No puedes eliminar tu propio usuario mientras tienes la sesión activa.", "warning")
        return redirect(url_for("admin.usuarios"))

    connection = get_db_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT id FROM usuarios WHERE id = %s LIMIT 1", (usuario_id,))
            usuario = cursor.fetchone()

            if not usuario:
                flash("El usuario no existe.", "danger")
                return redirect(url_for("admin.usuarios"))

            cursor.execute("DELETE FROM usuarios WHERE id = %s", (usuario_id,))

        connection.commit()

        flash("Usuario eliminado correctamente.", "success")
        return redirect(url_for("admin.usuarios"))

    except Exception as e:
        connection.rollback()
        flash(f"No se pudo eliminar el usuario. Detalle: {str(e)}", "danger")
        return redirect(url_for("admin.usuarios"))

    finally:
        connection.close()
@admin_bp.route("/clientes")
@login_required
@rol_required("administrador")
def clientes():
    buscar = request.args.get("buscar", "").strip()

    connection = get_db_connection()

    try:
        with connection.cursor() as cursor:
            if buscar:
                sql = """
                    SELECT 
                        c.id,
                        c.tipo_documento,
                        c.numero_documento,
                        c.razon_social,
                        c.nombre_comercial,
                        c.contacto,
                        c.telefono,
                        c.email,
                        c.direccion,
                        c.distrito,
                        c.provincia,
                        c.departamento,
                        c.estado,
                        c.created_at,
                        CONCAT(u.nombres, ' ', u.apellidos) AS creado_por_nombre
                    FROM clientes c
                    LEFT JOIN usuarios u ON c.creado_por = u.id
                    WHERE 
                        c.razon_social LIKE %s
                        OR c.nombre_comercial LIKE %s
                        OR c.numero_documento LIKE %s
                        OR c.email LIKE %s
                        OR c.telefono LIKE %s
                    ORDER BY c.id DESC
                """
                parametro = f"%{buscar}%"
                cursor.execute(sql, (parametro, parametro, parametro, parametro, parametro))
            else:
                sql = """
                    SELECT 
                        c.id,
                        c.tipo_documento,
                        c.numero_documento,
                        c.razon_social,
                        c.nombre_comercial,
                        c.contacto,
                        c.telefono,
                        c.email,
                        c.direccion,
                        c.distrito,
                        c.provincia,
                        c.departamento,
                        c.estado,
                        c.created_at,
                        CONCAT(u.nombres, ' ', u.apellidos) AS creado_por_nombre
                    FROM clientes c
                    LEFT JOIN usuarios u ON c.creado_por = u.id
                    ORDER BY c.id DESC
                """
                cursor.execute(sql)

            clientes = cursor.fetchall()

        return render_template(
            "admin/clientes.html",
            clientes=clientes,
            buscar=buscar
        )

    finally:
        connection.close()


@admin_bp.route("/clientes/nuevo", methods=["GET", "POST"])
@login_required
@rol_required("administrador")
def nuevo_cliente():
    if request.method == "POST":
        tipo_documento = request.form.get("tipo_documento", "RUC")
        numero_documento = request.form.get("numero_documento", "").strip()
        razon_social = request.form.get("razon_social", "").strip()
        nombre_comercial = request.form.get("nombre_comercial", "").strip()
        contacto = request.form.get("contacto", "").strip()
        telefono = request.form.get("telefono", "").strip()
        email = request.form.get("email", "").strip().lower()
        direccion = request.form.get("direccion", "").strip()
        distrito = request.form.get("distrito", "").strip()
        provincia = request.form.get("provincia", "").strip()
        departamento = request.form.get("departamento", "").strip()
        estado = request.form.get("estado", "activo")

        if not razon_social:
            flash("La razón social o nombre del cliente es obligatorio.", "warning")
            return render_template("admin/nuevo_cliente.html")

        if tipo_documento != "SIN_DOCUMENTO" and not numero_documento:
            flash("El número de documento es obligatorio para el tipo seleccionado.", "warning")
            return render_template("admin/nuevo_cliente.html")

        if tipo_documento == "SIN_DOCUMENTO":
            numero_documento = None

        connection = get_db_connection()

        try:
            with connection.cursor() as cursor:
                if numero_documento:
                    cursor.execute("""
                        SELECT id 
                        FROM clientes 
                        WHERE numero_documento = %s
                        LIMIT 1
                    """, (numero_documento,))
                    cliente_existente = cursor.fetchone()

                    if cliente_existente:
                        flash("Ya existe un cliente con ese número de documento.", "danger")
                        return render_template("admin/nuevo_cliente.html")

                sql = """
                    INSERT INTO clientes
                    (
                        tipo_documento,
                        numero_documento,
                        razon_social,
                        nombre_comercial,
                        contacto,
                        telefono,
                        email,
                        direccion,
                        distrito,
                        provincia,
                        departamento,
                        estado,
                        creado_por
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """

                cursor.execute(sql, (
                    tipo_documento,
                    numero_documento,
                    razon_social,
                    nombre_comercial,
                    contacto,
                    telefono,
                    email,
                    direccion,
                    distrito,
                    provincia,
                    departamento,
                    estado,
                    current_user.id
                ))

            connection.commit()

            flash("Cliente registrado correctamente.", "success")
            return redirect(url_for("admin.clientes"))

        except Exception as e:
            connection.rollback()
            flash(f"No se pudo registrar el cliente. Detalle: {str(e)}", "danger")
            return render_template("admin/nuevo_cliente.html")

        finally:
            connection.close()

    return render_template("admin/nuevo_cliente.html")


@admin_bp.route("/clientes/<int:cliente_id>/editar", methods=["GET", "POST"])
@login_required
@rol_required("administrador")
def editar_cliente(cliente_id):
    connection = get_db_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    id,
                    tipo_documento,
                    numero_documento,
                    razon_social,
                    nombre_comercial,
                    contacto,
                    telefono,
                    email,
                    direccion,
                    distrito,
                    provincia,
                    departamento,
                    estado
                FROM clientes
                WHERE id = %s
                LIMIT 1
            """, (cliente_id,))
            cliente = cursor.fetchone()

        if not cliente:
            flash("El cliente no existe.", "danger")
            return redirect(url_for("admin.clientes"))

        if request.method == "POST":
            tipo_documento = request.form.get("tipo_documento", "RUC")
            numero_documento = request.form.get("numero_documento", "").strip()
            razon_social = request.form.get("razon_social", "").strip()
            nombre_comercial = request.form.get("nombre_comercial", "").strip()
            contacto = request.form.get("contacto", "").strip()
            telefono = request.form.get("telefono", "").strip()
            email = request.form.get("email", "").strip().lower()
            direccion = request.form.get("direccion", "").strip()
            distrito = request.form.get("distrito", "").strip()
            provincia = request.form.get("provincia", "").strip()
            departamento = request.form.get("departamento", "").strip()
            estado = request.form.get("estado", "activo")

            if not razon_social:
                flash("La razón social o nombre del cliente es obligatorio.", "warning")
                return render_template("admin/editar_cliente.html", cliente=cliente)

            if tipo_documento != "SIN_DOCUMENTO" and not numero_documento:
                flash("El número de documento es obligatorio para el tipo seleccionado.", "warning")
                return render_template("admin/editar_cliente.html", cliente=cliente)

            if tipo_documento == "SIN_DOCUMENTO":
                numero_documento = None

            with connection.cursor() as cursor:
                if numero_documento:
                    cursor.execute("""
                        SELECT id 
                        FROM clientes 
                        WHERE numero_documento = %s AND id != %s
                        LIMIT 1
                    """, (numero_documento, cliente_id))
                    cliente_existente = cursor.fetchone()

                    if cliente_existente:
                        flash("Ya existe otro cliente con ese número de documento.", "danger")
                        return render_template("admin/editar_cliente.html", cliente=cliente)

                sql = """
                    UPDATE clientes
                    SET 
                        tipo_documento = %s,
                        numero_documento = %s,
                        razon_social = %s,
                        nombre_comercial = %s,
                        contacto = %s,
                        telefono = %s,
                        email = %s,
                        direccion = %s,
                        distrito = %s,
                        provincia = %s,
                        departamento = %s,
                        estado = %s
                    WHERE id = %s
                """

                cursor.execute(sql, (
                    tipo_documento,
                    numero_documento,
                    razon_social,
                    nombre_comercial,
                    contacto,
                    telefono,
                    email,
                    direccion,
                    distrito,
                    provincia,
                    departamento,
                    estado,
                    cliente_id
                ))

            connection.commit()

            flash("Cliente actualizado correctamente.", "success")
            return redirect(url_for("admin.clientes"))

        return render_template("admin/editar_cliente.html", cliente=cliente)

    except Exception as e:
        connection.rollback()
        flash(f"No se pudo procesar la operación. Detalle: {str(e)}", "danger")
        return redirect(url_for("admin.clientes"))

    finally:
        connection.close()


@admin_bp.route("/clientes/<int:cliente_id>/eliminar", methods=["POST"])
@login_required
@rol_required("administrador")
def eliminar_cliente(cliente_id):
    connection = get_db_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT id FROM clientes WHERE id = %s LIMIT 1", (cliente_id,))
            cliente = cursor.fetchone()

            if not cliente:
                flash("El cliente no existe.", "danger")
                return redirect(url_for("admin.clientes"))

            cursor.execute("""
                SELECT COUNT(*) AS total
                FROM cotizaciones
                WHERE cliente_id = %s
            """, (cliente_id,))
            resultado = cursor.fetchone()

            if resultado["total"] > 0:
                cursor.execute("""
                    UPDATE clientes
                    SET estado = 'inactivo'
                    WHERE id = %s
                """, (cliente_id,))

                connection.commit()

                flash(
                    "El cliente tiene cotizaciones asociadas, por eso fue marcado como inactivo.",
                    "warning"
                )
                return redirect(url_for("admin.clientes"))

            cursor.execute("DELETE FROM clientes WHERE id = %s", (cliente_id,))

        connection.commit()

        flash("Cliente eliminado correctamente.", "success")
        return redirect(url_for("admin.clientes"))

    except Exception as e:
        connection.rollback()
        flash(f"No se pudo eliminar el cliente. Detalle: {str(e)}", "danger")
        return redirect(url_for("admin.clientes"))

    finally:
        connection.close()
@admin_bp.route("/proveedores")
@login_required
@rol_required("administrador")
def proveedores():
    buscar = request.args.get("buscar", "").strip()

    connection = get_db_connection()

    try:
        with connection.cursor() as cursor:
            if buscar:
                sql = """
                    SELECT 
                        p.id,
                        p.ruc,
                        p.razon_social,
                        p.nombre_comercial,
                        p.contacto,
                        p.telefono,
                        p.email,
                        p.direccion,
                        p.distrito,
                        p.provincia,
                        p.departamento,
                        p.estado,
                        p.created_at,
                        CONCAT(u.nombres, ' ', u.apellidos) AS creado_por_nombre
                    FROM proveedores p
                    LEFT JOIN usuarios u ON p.creado_por = u.id
                    WHERE 
                        p.ruc LIKE %s
                        OR p.razon_social LIKE %s
                        OR p.nombre_comercial LIKE %s
                        OR p.email LIKE %s
                        OR p.telefono LIKE %s
                    ORDER BY p.id DESC
                """
                parametro = f"%{buscar}%"
                cursor.execute(sql, (parametro, parametro, parametro, parametro, parametro))
            else:
                sql = """
                    SELECT 
                        p.id,
                        p.ruc,
                        p.razon_social,
                        p.nombre_comercial,
                        p.contacto,
                        p.telefono,
                        p.email,
                        p.direccion,
                        p.distrito,
                        p.provincia,
                        p.departamento,
                        p.estado,
                        p.created_at,
                        CONCAT(u.nombres, ' ', u.apellidos) AS creado_por_nombre
                    FROM proveedores p
                    LEFT JOIN usuarios u ON p.creado_por = u.id
                    ORDER BY p.id DESC
                """
                cursor.execute(sql)

            proveedores = cursor.fetchall()

        return render_template(
            "admin/proveedores.html",
            proveedores=proveedores,
            buscar=buscar
        )

    finally:
        connection.close()


@admin_bp.route("/proveedores/nuevo", methods=["GET", "POST"])
@login_required
@rol_required("administrador")
def nuevo_proveedor():
    if request.method == "POST":
        ruc = request.form.get("ruc", "").strip()
        razon_social = request.form.get("razon_social", "").strip()
        nombre_comercial = request.form.get("nombre_comercial", "").strip()
        contacto = request.form.get("contacto", "").strip()
        telefono = request.form.get("telefono", "").strip()
        email = request.form.get("email", "").strip().lower()
        direccion = request.form.get("direccion", "").strip()
        distrito = request.form.get("distrito", "").strip()
        provincia = request.form.get("provincia", "").strip()
        departamento = request.form.get("departamento", "").strip()
        estado = request.form.get("estado", "activo")

        if not razon_social:
            flash("La razón social del proveedor es obligatoria.", "warning")
            return render_template("admin/nuevo_proveedor.html")

        if not ruc:
            ruc = None

        connection = get_db_connection()

        try:
            with connection.cursor() as cursor:
                if ruc:
                    cursor.execute("""
                        SELECT id 
                        FROM proveedores 
                        WHERE ruc = %s
                        LIMIT 1
                    """, (ruc,))
                    proveedor_existente = cursor.fetchone()

                    if proveedor_existente:
                        flash("Ya existe un proveedor registrado con ese RUC.", "danger")
                        return render_template("admin/nuevo_proveedor.html")

                sql = """
                    INSERT INTO proveedores
                    (
                        ruc,
                        razon_social,
                        nombre_comercial,
                        contacto,
                        telefono,
                        email,
                        direccion,
                        distrito,
                        provincia,
                        departamento,
                        estado,
                        creado_por
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """

                cursor.execute(sql, (
                    ruc,
                    razon_social,
                    nombre_comercial,
                    contacto,
                    telefono,
                    email,
                    direccion,
                    distrito,
                    provincia,
                    departamento,
                    estado,
                    current_user.id
                ))

            connection.commit()

            flash("Proveedor registrado correctamente.", "success")
            return redirect(url_for("admin.proveedores"))

        except Exception as e:
            connection.rollback()
            flash(f"No se pudo registrar el proveedor. Detalle: {str(e)}", "danger")
            return render_template("admin/nuevo_proveedor.html")

        finally:
            connection.close()

    return render_template("admin/nuevo_proveedor.html")


@admin_bp.route("/proveedores/<int:proveedor_id>/editar", methods=["GET", "POST"])
@login_required
@rol_required("administrador")
def editar_proveedor(proveedor_id):
    connection = get_db_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    id,
                    ruc,
                    razon_social,
                    nombre_comercial,
                    contacto,
                    telefono,
                    email,
                    direccion,
                    distrito,
                    provincia,
                    departamento,
                    estado
                FROM proveedores
                WHERE id = %s
                LIMIT 1
            """, (proveedor_id,))
            proveedor = cursor.fetchone()

        if not proveedor:
            flash("El proveedor no existe.", "danger")
            return redirect(url_for("admin.proveedores"))

        if request.method == "POST":
            ruc = request.form.get("ruc", "").strip()
            razon_social = request.form.get("razon_social", "").strip()
            nombre_comercial = request.form.get("nombre_comercial", "").strip()
            contacto = request.form.get("contacto", "").strip()
            telefono = request.form.get("telefono", "").strip()
            email = request.form.get("email", "").strip().lower()
            direccion = request.form.get("direccion", "").strip()
            distrito = request.form.get("distrito", "").strip()
            provincia = request.form.get("provincia", "").strip()
            departamento = request.form.get("departamento", "").strip()
            estado = request.form.get("estado", "activo")

            if not razon_social:
                flash("La razón social del proveedor es obligatoria.", "warning")
                return render_template("admin/editar_proveedor.html", proveedor=proveedor)

            if not ruc:
                ruc = None

            with connection.cursor() as cursor:
                if ruc:
                    cursor.execute("""
                        SELECT id 
                        FROM proveedores 
                        WHERE ruc = %s AND id != %s
                        LIMIT 1
                    """, (ruc, proveedor_id))
                    proveedor_existente = cursor.fetchone()

                    if proveedor_existente:
                        flash("Ya existe otro proveedor con ese RUC.", "danger")
                        return render_template("admin/editar_proveedor.html", proveedor=proveedor)

                sql = """
                    UPDATE proveedores
                    SET 
                        ruc = %s,
                        razon_social = %s,
                        nombre_comercial = %s,
                        contacto = %s,
                        telefono = %s,
                        email = %s,
                        direccion = %s,
                        distrito = %s,
                        provincia = %s,
                        departamento = %s,
                        estado = %s
                    WHERE id = %s
                """

                cursor.execute(sql, (
                    ruc,
                    razon_social,
                    nombre_comercial,
                    contacto,
                    telefono,
                    email,
                    direccion,
                    distrito,
                    provincia,
                    departamento,
                    estado,
                    proveedor_id
                ))

            connection.commit()

            flash("Proveedor actualizado correctamente.", "success")
            return redirect(url_for("admin.proveedores"))

        return render_template("admin/editar_proveedor.html", proveedor=proveedor)

    except Exception as e:
        connection.rollback()
        flash(f"No se pudo procesar la operación. Detalle: {str(e)}", "danger")
        return redirect(url_for("admin.proveedores"))

    finally:
        connection.close()


@admin_bp.route("/proveedores/<int:proveedor_id>/eliminar", methods=["POST"])
@login_required
@rol_required("administrador")
def eliminar_proveedor(proveedor_id):
    connection = get_db_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT id FROM proveedores WHERE id = %s LIMIT 1", (proveedor_id,))
            proveedor = cursor.fetchone()

            if not proveedor:
                flash("El proveedor no existe.", "danger")
                return redirect(url_for("admin.proveedores"))

            cursor.execute("""
                SELECT 
                    (
                        SELECT COUNT(*) 
                        FROM producto_proveedor 
                        WHERE proveedor_id = %s
                    ) AS total_productos,
                    (
                        SELECT COUNT(*) 
                        FROM cotizacion_detalles 
                        WHERE proveedor_id = %s
                    ) AS total_cotizaciones
            """, (proveedor_id, proveedor_id))
            resultado = cursor.fetchone()

            if resultado["total_productos"] > 0 or resultado["total_cotizaciones"] > 0:
                cursor.execute("""
                    UPDATE proveedores
                    SET estado = 'inactivo'
                    WHERE id = %s
                """, (proveedor_id,))

                connection.commit()

                flash(
                    "El proveedor tiene productos o cotizaciones asociadas, por eso fue marcado como inactivo.",
                    "warning"
                )
                return redirect(url_for("admin.proveedores"))

            cursor.execute("DELETE FROM proveedores WHERE id = %s", (proveedor_id,))

        connection.commit()

        flash("Proveedor eliminado correctamente.", "success")
        return redirect(url_for("admin.proveedores"))

    except Exception as e:
        connection.rollback()
        flash(f"No se pudo eliminar el proveedor. Detalle: {str(e)}", "danger")
        return redirect(url_for("admin.proveedores"))

    finally:
        connection.close()
def convertir_decimal(valor, defecto=0):
    try:
        if valor is None or str(valor).strip() == "":
            return defecto

        numero = float(valor)

        if numero < 0:
            return None

        return numero

    except ValueError:
        return None


@admin_bp.route("/productos")
@login_required
@rol_required("administrador")
def productos():
    buscar = request.args.get("buscar", "").strip()

    connection = get_db_connection()

    try:
        with connection.cursor() as cursor:
            if buscar:
                sql = """
                    SELECT 
                        p.id,
                        p.codigo,
                        p.nombre,
                        p.descripcion,
                        p.marca,
                        p.modelo,
                        p.precio_venta_sugerido,
                        p.stock_actual,
                        p.stock_minimo,
                        p.estado,
                        p.created_at,
                        c.nombre AS categoria,
                        u.abreviatura AS unidad,
                        COUNT(pp.id) AS total_proveedores,
                        MIN(pp.costo_unitario) AS menor_costo
                    FROM productos p
                    LEFT JOIN categorias_productos c ON p.categoria_id = c.id
                    LEFT JOIN unidades_medida u ON p.unidad_id = u.id
                    LEFT JOIN producto_proveedor pp 
                        ON p.id = pp.producto_id 
                        AND pp.estado = 'activo'
                    WHERE 
                        p.codigo LIKE %s
                        OR p.nombre LIKE %s
                        OR p.marca LIKE %s
                        OR p.modelo LIKE %s
                        OR c.nombre LIKE %s
                    GROUP BY 
                        p.id,
                        p.codigo,
                        p.nombre,
                        p.descripcion,
                        p.marca,
                        p.modelo,
                        p.precio_venta_sugerido,
                        p.stock_actual,
                        p.stock_minimo,
                        p.estado,
                        p.created_at,
                        c.nombre,
                        u.abreviatura
                    ORDER BY p.id DESC
                """
                parametro = f"%{buscar}%"
                cursor.execute(sql, (parametro, parametro, parametro, parametro, parametro))
            else:
                sql = """
                    SELECT 
                        p.id,
                        p.codigo,
                        p.nombre,
                        p.descripcion,
                        p.marca,
                        p.modelo,
                        p.precio_venta_sugerido,
                        p.stock_actual,
                        p.stock_minimo,
                        p.estado,
                        p.created_at,
                        c.nombre AS categoria,
                        u.abreviatura AS unidad,
                        COUNT(pp.id) AS total_proveedores,
                        MIN(pp.costo_unitario) AS menor_costo
                    FROM productos p
                    LEFT JOIN categorias_productos c ON p.categoria_id = c.id
                    LEFT JOIN unidades_medida u ON p.unidad_id = u.id
                    LEFT JOIN producto_proveedor pp 
                        ON p.id = pp.producto_id 
                        AND pp.estado = 'activo'
                    GROUP BY 
                        p.id,
                        p.codigo,
                        p.nombre,
                        p.descripcion,
                        p.marca,
                        p.modelo,
                        p.precio_venta_sugerido,
                        p.stock_actual,
                        p.stock_minimo,
                        p.estado,
                        p.created_at,
                        c.nombre,
                        u.abreviatura
                    ORDER BY p.id DESC
                """
                cursor.execute(sql)

            productos = cursor.fetchall()

        return render_template(
            "admin/productos.html",
            productos=productos,
            buscar=buscar
        )

    finally:
        connection.close()


@admin_bp.route("/productos/nuevo", methods=["GET", "POST"])
@login_required
@rol_required("administrador")
def nuevo_producto():
    connection = get_db_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT id, nombre 
                FROM categorias_productos 
                WHERE estado = 'activo'
                ORDER BY nombre ASC
            """)
            categorias = cursor.fetchall()

            cursor.execute("""
                SELECT id, nombre, abreviatura 
                FROM unidades_medida 
                WHERE estado = 'activo'
                ORDER BY nombre ASC
            """)
            unidades = cursor.fetchall()

        if request.method == "POST":
            categoria_id = request.form.get("categoria_id") or None
            unidad_id = request.form.get("unidad_id") or None
            codigo = request.form.get("codigo", "").strip().upper()
            nombre = request.form.get("nombre", "").strip()
            descripcion = request.form.get("descripcion", "").strip()
            marca = request.form.get("marca", "").strip()
            modelo = request.form.get("modelo", "").strip()
            precio_venta_sugerido = convertir_decimal(request.form.get("precio_venta_sugerido"))
            stock_actual = convertir_decimal(request.form.get("stock_actual"))
            stock_minimo = convertir_decimal(request.form.get("stock_minimo"))
            estado = request.form.get("estado", "activo")

            if not codigo or not nombre:
                flash("El código y el nombre del producto son obligatorios.", "warning")
                return render_template(
                    "admin/nuevo_producto.html",
                    categorias=categorias,
                    unidades=unidades
                )

            if precio_venta_sugerido is None or stock_actual is None or stock_minimo is None:
                flash("Los valores numéricos no pueden ser negativos ni inválidos.", "warning")
                return render_template(
                    "admin/nuevo_producto.html",
                    categorias=categorias,
                    unidades=unidades
                )

            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT id 
                    FROM productos 
                    WHERE codigo = %s
                    LIMIT 1
                """, (codigo,))
                producto_existente = cursor.fetchone()

                if producto_existente:
                    flash("Ya existe un producto registrado con ese código.", "danger")
                    return render_template(
                        "admin/nuevo_producto.html",
                        categorias=categorias,
                        unidades=unidades
                    )

                sql = """
                    INSERT INTO productos
                    (
                        categoria_id,
                        unidad_id,
                        codigo,
                        nombre,
                        descripcion,
                        marca,
                        modelo,
                        precio_venta_sugerido,
                        stock_actual,
                        stock_minimo,
                        estado,
                        creado_por
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """

                cursor.execute(sql, (
                    categoria_id,
                    unidad_id,
                    codigo,
                    nombre,
                    descripcion,
                    marca,
                    modelo,
                    precio_venta_sugerido,
                    stock_actual,
                    stock_minimo,
                    estado,
                    current_user.id
                ))

            connection.commit()

            flash("Producto registrado correctamente.", "success")
            return redirect(url_for("admin.productos"))

        return render_template(
            "admin/nuevo_producto.html",
            categorias=categorias,
            unidades=unidades
        )

    except Exception as e:
        connection.rollback()
        flash(f"No se pudo registrar el producto. Detalle: {str(e)}", "danger")
        return redirect(url_for("admin.productos"))

    finally:
        connection.close()


@admin_bp.route("/productos/<int:producto_id>/editar", methods=["GET", "POST"])
@login_required
@rol_required("administrador")
def editar_producto(producto_id):
    connection = get_db_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    id,
                    categoria_id,
                    unidad_id,
                    codigo,
                    nombre,
                    descripcion,
                    marca,
                    modelo,
                    precio_venta_sugerido,
                    stock_actual,
                    stock_minimo,
                    estado
                FROM productos
                WHERE id = %s
                LIMIT 1
            """, (producto_id,))
            producto = cursor.fetchone()

            cursor.execute("""
                SELECT id, nombre 
                FROM categorias_productos 
                WHERE estado = 'activo'
                ORDER BY nombre ASC
            """)
            categorias = cursor.fetchall()

            cursor.execute("""
                SELECT id, nombre, abreviatura 
                FROM unidades_medida 
                WHERE estado = 'activo'
                ORDER BY nombre ASC
            """)
            unidades = cursor.fetchall()

        if not producto:
            flash("El producto no existe.", "danger")
            return redirect(url_for("admin.productos"))

        if request.method == "POST":
            categoria_id = request.form.get("categoria_id") or None
            unidad_id = request.form.get("unidad_id") or None
            codigo = request.form.get("codigo", "").strip().upper()
            nombre = request.form.get("nombre", "").strip()
            descripcion = request.form.get("descripcion", "").strip()
            marca = request.form.get("marca", "").strip()
            modelo = request.form.get("modelo", "").strip()
            precio_venta_sugerido = convertir_decimal(request.form.get("precio_venta_sugerido"))
            stock_actual = convertir_decimal(request.form.get("stock_actual"))
            stock_minimo = convertir_decimal(request.form.get("stock_minimo"))
            estado = request.form.get("estado", "activo")

            if not codigo or not nombre:
                flash("El código y el nombre del producto son obligatorios.", "warning")
                return render_template(
                    "admin/editar_producto.html",
                    producto=producto,
                    categorias=categorias,
                    unidades=unidades
                )

            if precio_venta_sugerido is None or stock_actual is None or stock_minimo is None:
                flash("Los valores numéricos no pueden ser negativos ni inválidos.", "warning")
                return render_template(
                    "admin/editar_producto.html",
                    producto=producto,
                    categorias=categorias,
                    unidades=unidades
                )

            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT id 
                    FROM productos 
                    WHERE codigo = %s AND id != %s
                    LIMIT 1
                """, (codigo, producto_id))
                producto_existente = cursor.fetchone()

                if producto_existente:
                    flash("Ya existe otro producto con ese código.", "danger")
                    return render_template(
                        "admin/editar_producto.html",
                        producto=producto,
                        categorias=categorias,
                        unidades=unidades
                    )

                sql = """
                    UPDATE productos
                    SET 
                        categoria_id = %s,
                        unidad_id = %s,
                        codigo = %s,
                        nombre = %s,
                        descripcion = %s,
                        marca = %s,
                        modelo = %s,
                        precio_venta_sugerido = %s,
                        stock_actual = %s,
                        stock_minimo = %s,
                        estado = %s
                    WHERE id = %s
                """

                cursor.execute(sql, (
                    categoria_id,
                    unidad_id,
                    codigo,
                    nombre,
                    descripcion,
                    marca,
                    modelo,
                    precio_venta_sugerido,
                    stock_actual,
                    stock_minimo,
                    estado,
                    producto_id
                ))

            connection.commit()

            flash("Producto actualizado correctamente.", "success")
            return redirect(url_for("admin.productos"))

        return render_template(
            "admin/editar_producto.html",
            producto=producto,
            categorias=categorias,
            unidades=unidades
        )

    except Exception as e:
        connection.rollback()
        flash(f"No se pudo procesar la operación. Detalle: {str(e)}", "danger")
        return redirect(url_for("admin.productos"))

    finally:
        connection.close()


@admin_bp.route("/productos/<int:producto_id>/eliminar", methods=["POST"])
@login_required
@rol_required("administrador")
def eliminar_producto(producto_id):
    connection = get_db_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT id FROM productos WHERE id = %s LIMIT 1", (producto_id,))
            producto = cursor.fetchone()

            if not producto:
                flash("El producto no existe.", "danger")
                return redirect(url_for("admin.productos"))

            cursor.execute("""
                SELECT 
                    (
                        SELECT COUNT(*) 
                        FROM cotizacion_detalles 
                        WHERE producto_id = %s
                    ) AS total_cotizaciones,
                    (
                        SELECT COUNT(*) 
                        FROM producto_proveedor 
                        WHERE producto_id = %s
                    ) AS total_proveedores
            """, (producto_id, producto_id))
            resultado = cursor.fetchone()

            if resultado["total_cotizaciones"] > 0 or resultado["total_proveedores"] > 0:
                cursor.execute("""
                    UPDATE productos
                    SET estado = 'inactivo'
                    WHERE id = %s
                """, (producto_id,))

                connection.commit()

                flash(
                    "El producto tiene proveedores o cotizaciones asociadas, por eso fue marcado como inactivo.",
                    "warning"
                )
                return redirect(url_for("admin.productos"))

            cursor.execute("DELETE FROM productos WHERE id = %s", (producto_id,))

        connection.commit()

        flash("Producto eliminado correctamente.", "success")
        return redirect(url_for("admin.productos"))

    except Exception as e:
        connection.rollback()
        flash(f"No se pudo eliminar el producto. Detalle: {str(e)}", "danger")
        return redirect(url_for("admin.productos"))

    finally:
        connection.close()


@admin_bp.route("/productos/<int:producto_id>/proveedores")
@login_required
@rol_required("administrador")
def producto_proveedores(producto_id):
    connection = get_db_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    p.id,
                    p.codigo,
                    p.nombre,
                    p.marca,
                    p.modelo
                FROM productos p
                WHERE p.id = %s
                LIMIT 1
            """, (producto_id,))
            producto = cursor.fetchone()

            if not producto:
                flash("El producto no existe.", "danger")
                return redirect(url_for("admin.productos"))

            cursor.execute("""
                SELECT
                    pp.id,
                    pp.codigo_proveedor,
                    pp.costo_unitario,
                    pp.precio_anterior,
                    pp.disponibilidad,
                    pp.tiempo_entrega_dias,
                    pp.fecha_actualizacion,
                    pp.observacion,
                    pp.estado,
                    pr.razon_social AS proveedor,
                    pr.ruc
                FROM producto_proveedor pp
                INNER JOIN proveedores pr ON pp.proveedor_id = pr.id
                WHERE pp.producto_id = %s
                ORDER BY pp.costo_unitario ASC
            """, (producto_id,))
            proveedores_producto = cursor.fetchall()

        return render_template(
            "admin/producto_proveedores.html",
            producto=producto,
            proveedores_producto=proveedores_producto
        )

    finally:
        connection.close()


@admin_bp.route("/productos/<int:producto_id>/proveedores/nuevo", methods=["GET", "POST"])
@login_required
@rol_required("administrador")
def nuevo_producto_proveedor(producto_id):
    connection = get_db_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT id, codigo, nombre
                FROM productos
                WHERE id = %s
                LIMIT 1
            """, (producto_id,))
            producto = cursor.fetchone()

            if not producto:
                flash("El producto no existe.", "danger")
                return redirect(url_for("admin.productos"))

            cursor.execute("""
                SELECT id, ruc, razon_social
                FROM proveedores
                WHERE estado = 'activo'
                ORDER BY razon_social ASC
            """)
            proveedores = cursor.fetchall()

        if request.method == "POST":
            proveedor_id = request.form.get("proveedor_id")
            codigo_proveedor = request.form.get("codigo_proveedor", "").strip()
            costo_unitario = convertir_decimal(request.form.get("costo_unitario"))
            precio_anterior = convertir_decimal(request.form.get("precio_anterior"))
            disponibilidad = request.form.get("disponibilidad", "por_confirmar")
            tiempo_entrega_dias = request.form.get("tiempo_entrega_dias", "0").strip()
            fecha_actualizacion = request.form.get("fecha_actualizacion")
            observacion = request.form.get("observacion", "").strip()
            estado = request.form.get("estado", "activo")

            if not proveedor_id or not fecha_actualizacion:
                flash("El proveedor y la fecha de actualización son obligatorios.", "warning")
                return render_template(
                    "admin/nuevo_producto_proveedor.html",
                    producto=producto,
                    proveedores=proveedores
                )

            if costo_unitario is None or precio_anterior is None:
                flash("Los precios no pueden ser negativos ni inválidos.", "warning")
                return render_template(
                    "admin/nuevo_producto_proveedor.html",
                    producto=producto,
                    proveedores=proveedores
                )

            try:
                tiempo_entrega_dias = int(tiempo_entrega_dias)

                if tiempo_entrega_dias < 0:
                    raise ValueError

            except ValueError:
                flash("El tiempo de entrega debe ser un número entero positivo.", "warning")
                return render_template(
                    "admin/nuevo_producto_proveedor.html",
                    producto=producto,
                    proveedores=proveedores
                )

            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT id
                    FROM producto_proveedor
                    WHERE producto_id = %s AND proveedor_id = %s
                    LIMIT 1
                """, (producto_id, proveedor_id))
                relacion_existente = cursor.fetchone()

                if relacion_existente:
                    flash("Este proveedor ya está asociado al producto.", "danger")
                    return render_template(
                        "admin/nuevo_producto_proveedor.html",
                        producto=producto,
                        proveedores=proveedores
                    )

                sql = """
                    INSERT INTO producto_proveedor
                    (
                        producto_id,
                        proveedor_id,
                        codigo_proveedor,
                        costo_unitario,
                        precio_anterior,
                        disponibilidad,
                        tiempo_entrega_dias,
                        fecha_actualizacion,
                        observacion,
                        estado,
                        actualizado_por
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """

                cursor.execute(sql, (
                    producto_id,
                    proveedor_id,
                    codigo_proveedor,
                    costo_unitario,
                    precio_anterior,
                    disponibilidad,
                    tiempo_entrega_dias,
                    fecha_actualizacion,
                    observacion,
                    estado,
                    current_user.id
                ))

            connection.commit()

            flash("Proveedor asociado correctamente al producto.", "success")
            return redirect(url_for("admin.producto_proveedores", producto_id=producto_id))

        return render_template(
            "admin/nuevo_producto_proveedor.html",
            producto=producto,
            proveedores=proveedores
        )

    except Exception as e:
        connection.rollback()
        flash(f"No se pudo asociar el proveedor. Detalle: {str(e)}", "danger")
        return redirect(url_for("admin.producto_proveedores", producto_id=producto_id))

    finally:
        connection.close()


@admin_bp.route("/productos/<int:producto_id>/proveedores/<int:relacion_id>/editar", methods=["GET", "POST"])
@login_required
@rol_required("administrador")
def editar_producto_proveedor(producto_id, relacion_id):
    connection = get_db_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT id, codigo, nombre
                FROM productos
                WHERE id = %s
                LIMIT 1
            """, (producto_id,))
            producto = cursor.fetchone()

            if not producto:
                flash("El producto no existe.", "danger")
                return redirect(url_for("admin.productos"))

            cursor.execute("""
                SELECT 
                    pp.id,
                    pp.producto_id,
                    pp.proveedor_id,
                    pp.codigo_proveedor,
                    pp.costo_unitario,
                    pp.precio_anterior,
                    pp.disponibilidad,
                    pp.tiempo_entrega_dias,
                    pp.fecha_actualizacion,
                    pp.observacion,
                    pp.estado
                FROM producto_proveedor pp
                WHERE pp.id = %s AND pp.producto_id = %s
                LIMIT 1
            """, (relacion_id, producto_id))
            relacion = cursor.fetchone()

            if not relacion:
                flash("La asociación producto-proveedor no existe.", "danger")
                return redirect(url_for("admin.producto_proveedores", producto_id=producto_id))

            cursor.execute("""
                SELECT id, ruc, razon_social
                FROM proveedores
                WHERE estado = 'activo'
                ORDER BY razon_social ASC
            """)
            proveedores = cursor.fetchall()

        if request.method == "POST":
            proveedor_id = request.form.get("proveedor_id")
            codigo_proveedor = request.form.get("codigo_proveedor", "").strip()
            costo_unitario = convertir_decimal(request.form.get("costo_unitario"))
            precio_anterior = convertir_decimal(request.form.get("precio_anterior"))
            disponibilidad = request.form.get("disponibilidad", "por_confirmar")
            tiempo_entrega_dias = request.form.get("tiempo_entrega_dias", "0").strip()
            fecha_actualizacion = request.form.get("fecha_actualizacion")
            observacion = request.form.get("observacion", "").strip()
            estado = request.form.get("estado", "activo")

            if not proveedor_id or not fecha_actualizacion:
                flash("El proveedor y la fecha de actualización son obligatorios.", "warning")
                return render_template(
                    "admin/editar_producto_proveedor.html",
                    producto=producto,
                    relacion=relacion,
                    proveedores=proveedores
                )

            if costo_unitario is None or precio_anterior is None:
                flash("Los precios no pueden ser negativos ni inválidos.", "warning")
                return render_template(
                    "admin/editar_producto_proveedor.html",
                    producto=producto,
                    relacion=relacion,
                    proveedores=proveedores
                )

            try:
                tiempo_entrega_dias = int(tiempo_entrega_dias)

                if tiempo_entrega_dias < 0:
                    raise ValueError

            except ValueError:
                flash("El tiempo de entrega debe ser un número entero positivo.", "warning")
                return render_template(
                    "admin/editar_producto_proveedor.html",
                    producto=producto,
                    relacion=relacion,
                    proveedores=proveedores
                )

            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT id
                    FROM producto_proveedor
                    WHERE producto_id = %s 
                    AND proveedor_id = %s 
                    AND id != %s
                    LIMIT 1
                """, (producto_id, proveedor_id, relacion_id))
                relacion_existente = cursor.fetchone()

                if relacion_existente:
                    flash("Este proveedor ya está asociado al producto.", "danger")
                    return render_template(
                        "admin/editar_producto_proveedor.html",
                        producto=producto,
                        relacion=relacion,
                        proveedores=proveedores
                    )

                sql = """
                    UPDATE producto_proveedor
                    SET 
                        proveedor_id = %s,
                        codigo_proveedor = %s,
                        costo_unitario = %s,
                        precio_anterior = %s,
                        disponibilidad = %s,
                        tiempo_entrega_dias = %s,
                        fecha_actualizacion = %s,
                        observacion = %s,
                        estado = %s,
                        actualizado_por = %s
                    WHERE id = %s AND producto_id = %s
                """

                cursor.execute(sql, (
                    proveedor_id,
                    codigo_proveedor,
                    costo_unitario,
                    precio_anterior,
                    disponibilidad,
                    tiempo_entrega_dias,
                    fecha_actualizacion,
                    observacion,
                    estado,
                    current_user.id,
                    relacion_id,
                    producto_id
                ))

            connection.commit()

            flash("Costo del proveedor actualizado correctamente.", "success")
            return redirect(url_for("admin.producto_proveedores", producto_id=producto_id))

        return render_template(
            "admin/editar_producto_proveedor.html",
            producto=producto,
            relacion=relacion,
            proveedores=proveedores
        )

    except Exception as e:
        connection.rollback()
        flash(f"No se pudo procesar la operación. Detalle: {str(e)}", "danger")
        return redirect(url_for("admin.producto_proveedores", producto_id=producto_id))

    finally:
        connection.close()


@admin_bp.route("/productos/<int:producto_id>/proveedores/<int:relacion_id>/eliminar", methods=["POST"])
@login_required
@rol_required("administrador")
def eliminar_producto_proveedor(producto_id, relacion_id):
    connection = get_db_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT id
                FROM producto_proveedor
                WHERE id = %s AND producto_id = %s
                LIMIT 1
            """, (relacion_id, producto_id))
            relacion = cursor.fetchone()

            if not relacion:
                flash("La asociación no existe.", "danger")
                return redirect(url_for("admin.producto_proveedores", producto_id=producto_id))

            cursor.execute("""
                DELETE FROM producto_proveedor
                WHERE id = %s AND producto_id = %s
            """, (relacion_id, producto_id))

        connection.commit()

        flash("Proveedor retirado del producto correctamente.", "success")
        return redirect(url_for("admin.producto_proveedores", producto_id=producto_id))

    except Exception as e:
        connection.rollback()
        flash(f"No se pudo eliminar la asociación. Detalle: {str(e)}", "danger")
        return redirect(url_for("admin.producto_proveedores", producto_id=producto_id))

    finally:
        connection.close()
@admin_bp.route("/cotizaciones")
@login_required
@rol_required("administrador")
def cotizaciones():
    vendedor_id = request.args.get("vendedor_id", "").strip()
    cliente = request.args.get("cliente", "").strip()
    estado_id = request.args.get("estado_id", "").strip()
    fecha_inicio = request.args.get("fecha_inicio", "").strip()
    fecha_fin = request.args.get("fecha_fin", "").strip()

    filtros = []
    parametros = []

    if vendedor_id:
        filtros.append("c.vendedor_id = %s")
        parametros.append(vendedor_id)

    if cliente:
        filtros.append("(cl.razon_social LIKE %s OR cl.numero_documento LIKE %s)")
        parametros.append(f"%{cliente}%")
        parametros.append(f"%{cliente}%")

    if estado_id:
        filtros.append("c.estado_id = %s")
        parametros.append(estado_id)

    if fecha_inicio:
        filtros.append("c.fecha_emision >= %s")
        parametros.append(fecha_inicio)

    if fecha_fin:
        filtros.append("c.fecha_emision <= %s")
        parametros.append(fecha_fin)

    where_sql = ""

    if filtros:
        where_sql = "WHERE " + " AND ".join(filtros)

    connection = get_db_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    u.id,
                    CONCAT(u.nombres, ' ', u.apellidos) AS nombre
                FROM usuarios u
                INNER JOIN roles r ON u.rol_id = r.id
                WHERE r.nombre = 'vendedor'
                ORDER BY u.nombres ASC
            """)
            vendedores = cursor.fetchall()

            cursor.execute("""
                SELECT id, nombre
                FROM estados_cotizacion
                WHERE estado = 'activo'
                ORDER BY id ASC
            """)
            estados = cursor.fetchall()

            sql_cotizaciones = f"""
                SELECT 
                    c.id,
                    c.codigo,
                    c.fecha_emision,
                    c.fecha_vencimiento,
                    c.moneda,
                    c.subtotal,
                    c.igv,
                    c.total,
                    c.costo_total,
                    c.margen_total,
                    c.margen_porcentaje,
                    cl.razon_social AS cliente,
                    cl.numero_documento AS documento_cliente,
                    ec.nombre AS estado,
                    CONCAT(u.nombres, ' ', u.apellidos) AS vendedor,
                    COUNT(cd.id) AS total_items
                FROM cotizaciones c
                INNER JOIN clientes cl ON c.cliente_id = cl.id
                INNER JOIN estados_cotizacion ec ON c.estado_id = ec.id
                LEFT JOIN usuarios u ON c.vendedor_id = u.id
                LEFT JOIN cotizacion_detalles cd ON c.id = cd.cotizacion_id
                {where_sql}
                GROUP BY 
                    c.id,
                    c.codigo,
                    c.fecha_emision,
                    c.fecha_vencimiento,
                    c.moneda,
                    c.subtotal,
                    c.igv,
                    c.total,
                    c.costo_total,
                    c.margen_total,
                    c.margen_porcentaje,
                    cl.razon_social,
                    cl.numero_documento,
                    ec.nombre,
                    u.nombres,
                    u.apellidos
                ORDER BY c.id DESC
            """

            cursor.execute(sql_cotizaciones, parametros)
            cotizaciones = cursor.fetchall()

            sql_resumen = f"""
                SELECT
                    COUNT(DISTINCT c.id) AS total_cotizaciones,
                    IFNULL(SUM(c.total), 0) AS total_ventas,
                    IFNULL(SUM(c.costo_total), 0) AS total_costos,
                    IFNULL(SUM(c.margen_total), 0) AS total_margen,
                    CASE 
                        WHEN IFNULL(SUM(c.total), 0) > 0 
                        THEN ROUND((SUM(c.margen_total) / SUM(c.total)) * 100, 2)
                        ELSE 0
                    END AS margen_promedio
                FROM cotizaciones c
                INNER JOIN clientes cl ON c.cliente_id = cl.id
                INNER JOIN estados_cotizacion ec ON c.estado_id = ec.id
                LEFT JOIN usuarios u ON c.vendedor_id = u.id
                {where_sql}
            """

            cursor.execute(sql_resumen, parametros)
            resumen = cursor.fetchone()

        return render_template(
            "admin/cotizaciones.html",
            cotizaciones=cotizaciones,
            vendedores=vendedores,
            estados=estados,
            resumen=resumen,
            filtros={
                "vendedor_id": vendedor_id,
                "cliente": cliente,
                "estado_id": estado_id,
                "fecha_inicio": fecha_inicio,
                "fecha_fin": fecha_fin
            }
        )

    finally:
        connection.close()


@admin_bp.route("/cotizaciones/<int:cotizacion_id>")
@login_required
@rol_required("administrador")
def detalle_cotizacion(cotizacion_id):
    connection = get_db_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    c.id,
                    c.codigo,
                    c.fecha_emision,
                    c.fecha_vencimiento,
                    c.moneda,
                    c.tipo_cambio,
                    c.subtotal,
                    c.descuento_total,
                    c.igv_porcentaje,
                    c.igv,
                    c.total,
                    c.costo_total,
                    c.margen_total,
                    c.margen_porcentaje,
                    c.observaciones,
                    c.condiciones,
                    c.created_at,
                    c.updated_at,
                    cl.razon_social AS cliente,
                    cl.tipo_documento,
                    cl.numero_documento,
                    cl.contacto,
                    cl.telefono AS cliente_telefono,
                    cl.email AS cliente_email,
                    cl.direccion AS cliente_direccion,
                    ec.id AS estado_id,
                    ec.nombre AS estado,
                    CONCAT(u.nombres, ' ', u.apellidos) AS vendedor
                FROM cotizaciones c
                INNER JOIN clientes cl ON c.cliente_id = cl.id
                INNER JOIN estados_cotizacion ec ON c.estado_id = ec.id
                LEFT JOIN usuarios u ON c.vendedor_id = u.id
                WHERE c.id = %s
                LIMIT 1
            """, (cotizacion_id,))
            cotizacion = cursor.fetchone()

            if not cotizacion:
                flash("La cotización no existe.", "danger")
                return redirect(url_for("admin.cotizaciones"))

            cursor.execute("""
                SELECT 
                    cd.id,
                    cd.descripcion_producto,
                    cd.cantidad,
                    cd.precio_unitario,
                    cd.costo_unitario,
                    cd.descuento_porcentaje,
                    cd.descuento_monto,
                    cd.subtotal,
                    cd.costo_total,
                    cd.margen,
                    cd.margen_porcentaje,
                    cd.observacion,
                    p.codigo AS codigo_producto,
                    p.nombre AS producto,
                    pr.razon_social AS proveedor,
                    um.abreviatura AS unidad
                FROM cotizacion_detalles cd
                LEFT JOIN productos p ON cd.producto_id = p.id
                LEFT JOIN proveedores pr ON cd.proveedor_id = pr.id
                LEFT JOIN unidades_medida um ON cd.unidad_id = um.id
                WHERE cd.cotizacion_id = %s
                ORDER BY cd.id ASC
            """, (cotizacion_id,))
            detalles = cursor.fetchall()

            cursor.execute("""
                SELECT id, nombre
                FROM estados_cotizacion
                WHERE estado = 'activo'
                ORDER BY id ASC
            """)
            estados = cursor.fetchall()

        return render_template(
            "admin/detalle_cotizacion.html",
            cotizacion=cotizacion,
            detalles=detalles,
            estados=estados
        )

    finally:
        connection.close()


@admin_bp.route("/cotizaciones/<int:cotizacion_id>/estado", methods=["POST"])
@login_required
@rol_required("administrador")
def cambiar_estado_cotizacion(cotizacion_id):
    estado_id = request.form.get("estado_id")

    if not estado_id:
        flash("Selecciona un estado válido.", "warning")
        return redirect(url_for("admin.detalle_cotizacion", cotizacion_id=cotizacion_id))

    connection = get_db_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT id
                FROM cotizaciones
                WHERE id = %s
                LIMIT 1
            """, (cotizacion_id,))
            cotizacion = cursor.fetchone()

            if not cotizacion:
                flash("La cotización no existe.", "danger")
                return redirect(url_for("admin.cotizaciones"))

            cursor.execute("""
                SELECT id
                FROM estados_cotizacion
                WHERE id = %s AND estado = 'activo'
                LIMIT 1
            """, (estado_id,))
            estado = cursor.fetchone()

            if not estado:
                flash("El estado seleccionado no existe.", "danger")
                return redirect(url_for("admin.detalle_cotizacion", cotizacion_id=cotizacion_id))

            cursor.execute("""
                UPDATE cotizaciones
                SET estado_id = %s,
                    actualizado_por = %s
                WHERE id = %s
            """, (estado_id, current_user.id, cotizacion_id))

        connection.commit()

        flash("Estado de cotización actualizado correctamente.", "success")
        return redirect(url_for("admin.detalle_cotizacion", cotizacion_id=cotizacion_id))

    except Exception as e:
        connection.rollback()
        flash(f"No se pudo actualizar el estado. Detalle: {str(e)}", "danger")
        return redirect(url_for("admin.detalle_cotizacion", cotizacion_id=cotizacion_id))

    finally:
        connection.close()


@admin_bp.route("/cotizaciones/<int:cotizacion_id>/eliminar", methods=["POST"])
@login_required
@rol_required("administrador")
def eliminar_cotizacion(cotizacion_id):
    connection = get_db_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT id, codigo
                FROM cotizaciones
                WHERE id = %s
                LIMIT 1
            """, (cotizacion_id,))
            cotizacion = cursor.fetchone()

            if not cotizacion:
                flash("La cotización no existe.", "danger")
                return redirect(url_for("admin.cotizaciones"))

            cursor.execute("""
                DELETE FROM cotizaciones
                WHERE id = %s
            """, (cotizacion_id,))

        connection.commit()

        flash("Cotización eliminada correctamente.", "success")
        return redirect(url_for("admin.cotizaciones"))

    except Exception as e:
        connection.rollback()
        flash(f"No se pudo eliminar la cotización. Detalle: {str(e)}", "danger")
        return redirect(url_for("admin.cotizaciones"))

    finally:
        connection.close()
#Modulo de Reportes
def obtener_filtros_fecha():
    fecha_inicio = request.args.get("fecha_inicio", "").strip()
    fecha_fin = request.args.get("fecha_fin", "").strip()

    filtros = []
    parametros = []

    if fecha_inicio:
        filtros.append("c.fecha_emision >= %s")
        parametros.append(fecha_inicio)

    if fecha_fin:
        filtros.append("c.fecha_emision <= %s")
        parametros.append(fecha_fin)

    where_sql = ""

    if filtros:
        where_sql = "WHERE " + " AND ".join(filtros)

    return where_sql, parametros, {
        "fecha_inicio": fecha_inicio,
        "fecha_fin": fecha_fin
    }


def obtener_filtros_fecha_on():
    fecha_inicio = request.args.get("fecha_inicio", "").strip()
    fecha_fin = request.args.get("fecha_fin", "").strip()

    condiciones = []
    parametros = []

    if fecha_inicio:
        condiciones.append("c.fecha_emision >= %s")
        parametros.append(fecha_inicio)

    if fecha_fin:
        condiciones.append("c.fecha_emision <= %s")
        parametros.append(fecha_fin)

    on_sql = ""

    if condiciones:
        on_sql = " AND " + " AND ".join(condiciones)

    return on_sql, parametros


@admin_bp.route("/reportes")
@login_required
@rol_required("administrador")
def reportes():
    where_sql, parametros, filtros = obtener_filtros_fecha()
    on_fecha_sql, parametros_on = obtener_filtros_fecha_on()

    connection = get_db_connection()

    try:
        with connection.cursor() as cursor:
            sql_resumen = f"""
                SELECT
                    COUNT(c.id) AS total_cotizaciones,
                    IFNULL(SUM(c.total), 0) AS total_cotizado,
                    IFNULL(SUM(c.costo_total), 0) AS total_costos,
                    IFNULL(SUM(c.margen_total), 0) AS total_margen,
                    IFNULL(AVG(c.margen_porcentaje), 0) AS margen_promedio,

                    IFNULL(SUM(
                        CASE 
                            WHEN ec.nombre = 'cerrada' THEN c.total 
                            ELSE 0 
                        END
                    ), 0) AS ventas_cerradas,

                    IFNULL(SUM(
                        CASE 
                            WHEN ec.nombre = 'cerrada' THEN c.margen_total 
                            ELSE 0 
                        END
                    ), 0) AS margen_cerrado

                FROM cotizaciones c
                INNER JOIN estados_cotizacion ec ON c.estado_id = ec.id
                {where_sql}
            """
            cursor.execute(sql_resumen, tuple(parametros))
            resumen = cursor.fetchone()

            sql_estados = f"""
                SELECT
                    ec.nombre AS estado,
                    COUNT(c.id) AS cantidad,
                    IFNULL(SUM(c.total), 0) AS total
                FROM estados_cotizacion ec
                LEFT JOIN cotizaciones c 
                    ON c.estado_id = ec.id
                    {on_fecha_sql}
                WHERE ec.estado = 'activo'
                GROUP BY ec.id, ec.nombre
                ORDER BY ec.id ASC
            """
            cursor.execute(sql_estados, tuple(parametros_on))
            cotizaciones_estado = cursor.fetchall()

            sql_vendedores = f"""
                SELECT
                    u.id,
                    CONCAT(u.nombres, ' ', u.apellidos) AS vendedor,
                    COUNT(c.id) AS total_cotizaciones,
                    IFNULL(SUM(c.total), 0) AS total_cotizado,
                    IFNULL(SUM(c.margen_total), 0) AS margen_total,
                    IFNULL(SUM(
                        CASE 
                            WHEN ec.nombre = 'cerrada' THEN c.total 
                            ELSE 0 
                        END
                    ), 0) AS ventas_cerradas
                FROM usuarios u
                INNER JOIN roles r ON u.rol_id = r.id
                LEFT JOIN cotizaciones c 
                    ON c.vendedor_id = u.id
                    {on_fecha_sql}
                LEFT JOIN estados_cotizacion ec ON c.estado_id = ec.id
                WHERE r.nombre = 'vendedor'
                GROUP BY u.id, u.nombres, u.apellidos
                ORDER BY ventas_cerradas DESC, total_cotizado DESC
                LIMIT 10
            """
            cursor.execute(sql_vendedores, tuple(parametros_on))
            top_vendedores = cursor.fetchall()

            sql_productos_cotizados = f"""
                SELECT
                    cd.descripcion_producto AS producto,
                    p.codigo AS codigo_producto,
                    SUM(cd.cantidad) AS cantidad_total,
                    COUNT(DISTINCT c.id) AS total_cotizaciones,
                    IFNULL(SUM(cd.subtotal), 0) AS venta_total,
                    IFNULL(SUM(cd.margen), 0) AS margen_total
                FROM cotizacion_detalles cd
                INNER JOIN cotizaciones c ON cd.cotizacion_id = c.id
                LEFT JOIN productos p ON cd.producto_id = p.id
                {where_sql}
                GROUP BY cd.descripcion_producto, p.codigo
                ORDER BY cantidad_total DESC
                LIMIT 10
            """
            cursor.execute(sql_productos_cotizados, tuple(parametros))
            productos_cotizados = cursor.fetchall()

            sql_margenes_productos = f"""
                SELECT
                    cd.descripcion_producto AS producto,
                    p.codigo AS codigo_producto,
                    IFNULL(SUM(cd.subtotal), 0) AS venta_total,
                    IFNULL(SUM(cd.costo_total), 0) AS costo_total,
                    IFNULL(SUM(cd.margen), 0) AS margen_total,
                    CASE
                        WHEN IFNULL(SUM(cd.subtotal), 0) > 0
                        THEN ROUND((SUM(cd.margen) / SUM(cd.subtotal)) * 100, 2)
                        ELSE 0
                    END AS margen_porcentaje
                FROM cotizacion_detalles cd
                INNER JOIN cotizaciones c ON cd.cotizacion_id = c.id
                LEFT JOIN productos p ON cd.producto_id = p.id
                {where_sql}
                GROUP BY cd.descripcion_producto, p.codigo
                ORDER BY margen_total DESC
                LIMIT 10
            """
            cursor.execute(sql_margenes_productos, tuple(parametros))
            margenes_productos = cursor.fetchall()

            sql_clientes = f"""
                SELECT
                    cl.razon_social AS cliente,
                    cl.numero_documento,
                    COUNT(c.id) AS total_cotizaciones,
                    IFNULL(SUM(c.total), 0) AS total_cotizado,
                    IFNULL(SUM(c.margen_total), 0) AS margen_total
                FROM cotizaciones c
                INNER JOIN clientes cl ON c.cliente_id = cl.id
                {where_sql}
                GROUP BY cl.id, cl.razon_social, cl.numero_documento
                ORDER BY total_cotizado DESC
                LIMIT 10
            """
            cursor.execute(sql_clientes, tuple(parametros))
            top_clientes = cursor.fetchall()

            cursor.execute("""
                SELECT
                    producto,
                    codigo_producto,
                    categoria,
                    proveedor,
                    costo_unitario,
                    precio_anterior,
                    disponibilidad,
                    tiempo_entrega_dias,
                    fecha_actualizacion
                FROM vw_comparacion_precios_proveedores
                ORDER BY producto ASC, costo_unitario ASC
                LIMIT 30
            """)
            comparacion_proveedores = cursor.fetchall()

        return render_template(
            "admin/reportes.html",
            resumen=resumen,
            filtros=filtros,
            cotizaciones_estado=cotizaciones_estado,
            top_vendedores=top_vendedores,
            productos_cotizados=productos_cotizados,
            margenes_productos=margenes_productos,
            top_clientes=top_clientes,
            comparacion_proveedores=comparacion_proveedores
        )

    finally:
        connection.close()


@admin_bp.route("/reportes/exportar-csv")
@login_required
@rol_required("administrador")
def exportar_reporte_cotizaciones_csv():
    where_sql, parametros, filtros = obtener_filtros_fecha()

    connection = get_db_connection()

    try:
        with connection.cursor() as cursor:
            sql = f"""
                SELECT
                    c.codigo,
                    c.fecha_emision,
                    c.fecha_vencimiento,
                    cl.razon_social AS cliente,
                    cl.numero_documento AS documento_cliente,
                    CONCAT(u.nombres, ' ', u.apellidos) AS vendedor,
                    ec.nombre AS estado,
                    c.moneda,
                    c.subtotal,
                    c.igv,
                    c.total,
                    c.costo_total,
                    c.margen_total,
                    c.margen_porcentaje
                FROM cotizaciones c
                INNER JOIN clientes cl ON c.cliente_id = cl.id
                INNER JOIN estados_cotizacion ec ON c.estado_id = ec.id
                LEFT JOIN usuarios u ON c.vendedor_id = u.id
                {where_sql}
                ORDER BY c.fecha_emision DESC, c.id DESC
            """
            cursor.execute(sql, tuple(parametros))
            cotizaciones = cursor.fetchall()

        output = StringIO()
        output.write("\ufeff")

        writer = csv.writer(output)

        writer.writerow([
            "Código",
            "Fecha emisión",
            "Fecha vencimiento",
            "Cliente",
            "Documento cliente",
            "Vendedor",
            "Estado",
            "Moneda",
            "Subtotal",
            "IGV",
            "Total",
            "Costo total",
            "Margen total",
            "Margen porcentaje"
        ])

        for item in cotizaciones:
            writer.writerow([
                item["codigo"],
                item["fecha_emision"],
                item["fecha_vencimiento"],
                item["cliente"],
                item["documento_cliente"],
                item["vendedor"],
                item["estado"],
                item["moneda"],
                item["subtotal"],
                item["igv"],
                item["total"],
                item["costo_total"],
                item["margen_total"],
                item["margen_porcentaje"]
            ])

        response = Response(
            output.getvalue(),
            mimetype="text/csv"
        )

        response.headers["Content-Disposition"] = "attachment; filename=reporte_cotizaciones_ropusac.csv"

        return response

    finally:
        connection.close()
# Modulo de Configuraciones
CONFIGURACIONES_PROTEGIDAS = {
    "empresa_nombre",
    "empresa_ruc",
    "empresa_direccion",
    "empresa_telefono",
    "empresa_email",
    "igv_porcentaje",
    "moneda_principal",
    "dias_validez_cotizacion"
}


def obtener_configuraciones_dict():
    connection = get_db_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT clave, valor
                FROM configuracion_sistema
            """)
            registros = cursor.fetchall()

        return {item["clave"]: item["valor"] for item in registros}

    finally:
        connection.close()


def guardar_configuracion(clave, valor, descripcion=None):
    connection = get_db_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT id
                FROM configuracion_sistema
                WHERE clave = %s
                LIMIT 1
            """, (clave,))
            existente = cursor.fetchone()

            if existente:
                cursor.execute("""
                    UPDATE configuracion_sistema
                    SET valor = %s,
                        descripcion = COALESCE(%s, descripcion),
                        actualizado_por = %s
                    WHERE clave = %s
                """, (valor, descripcion, current_user.id, clave))
            else:
                cursor.execute("""
                    INSERT INTO configuracion_sistema
                    (clave, valor, descripcion, actualizado_por)
                    VALUES (%s, %s, %s, %s)
                """, (clave, valor, descripcion, current_user.id))

        connection.commit()

    finally:
        connection.close()


@admin_bp.route("/configuracion")
@login_required
@rol_required("administrador")
def configuracion():
    connection = get_db_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    id,
                    clave,
                    valor,
                    descripcion,
                    updated_at
                FROM configuracion_sistema
                ORDER BY clave ASC
            """)
            configuraciones = cursor.fetchall()

            cursor.execute("""
                SELECT 
                    DATABASE() AS base_datos_actual,
                    VERSION() AS version_mysql
            """)
            info_bd = cursor.fetchone()

            cursor.execute("""
                SELECT COUNT(*) AS total_tablas
                FROM information_schema.tables
                WHERE table_schema = DATABASE()
            """)
            total_tablas = cursor.fetchone()

        config_dict = {item["clave"]: item["valor"] for item in configuraciones}

        bd = {
            "host": current_app.config["MYSQL_HOST"],
            "usuario": current_app.config["MYSQL_USER"],
            "base_datos": current_app.config["MYSQL_DB"],
            "puerto": current_app.config["MYSQL_PORT"],
            "base_datos_actual": info_bd["base_datos_actual"],
            "version_mysql": info_bd["version_mysql"],
            "total_tablas": total_tablas["total_tablas"]
        }

        return render_template(
            "admin/configuracion.html",
            config=config_dict,
            configuraciones=configuraciones,
            bd=bd,
            protegidas=CONFIGURACIONES_PROTEGIDAS
        )

    finally:
        connection.close()


@admin_bp.route("/configuracion/general", methods=["POST"])
@login_required
@rol_required("administrador")
def actualizar_configuracion_general():
    empresa_nombre = request.form.get("empresa_nombre", "").strip()
    empresa_ruc = request.form.get("empresa_ruc", "").strip()
    empresa_direccion = request.form.get("empresa_direccion", "").strip()
    empresa_telefono = request.form.get("empresa_telefono", "").strip()
    empresa_email = request.form.get("empresa_email", "").strip().lower()
    igv_porcentaje = request.form.get("igv_porcentaje", "").strip()
    moneda_principal = request.form.get("moneda_principal", "PEN").strip()
    dias_validez_cotizacion = request.form.get("dias_validez_cotizacion", "").strip()

    if not empresa_nombre:
        flash("El nombre de la empresa es obligatorio.", "warning")
        return redirect(url_for("admin.configuracion"))

    try:
        igv_float = float(igv_porcentaje)

        if igv_float < 0:
            flash("El IGV no puede ser negativo.", "warning")
            return redirect(url_for("admin.configuracion"))

    except ValueError:
        flash("El IGV debe ser un número válido.", "warning")
        return redirect(url_for("admin.configuracion"))

    try:
        dias_int = int(dias_validez_cotizacion)

        if dias_int < 0:
            flash("Los días de validez no pueden ser negativos.", "warning")
            return redirect(url_for("admin.configuracion"))

    except ValueError:
        flash("Los días de validez deben ser un número entero.", "warning")
        return redirect(url_for("admin.configuracion"))

    guardar_configuracion("empresa_nombre", empresa_nombre, "Nombre comercial de la empresa")
    guardar_configuracion("empresa_ruc", empresa_ruc, "RUC de la empresa")
    guardar_configuracion("empresa_direccion", empresa_direccion, "Dirección fiscal de la empresa")
    guardar_configuracion("empresa_telefono", empresa_telefono, "Teléfono de contacto")
    guardar_configuracion("empresa_email", empresa_email, "Correo de contacto")
    guardar_configuracion("igv_porcentaje", str(igv_float), "Porcentaje de IGV aplicado a las cotizaciones")
    guardar_configuracion("moneda_principal", moneda_principal, "Moneda principal del sistema")
    guardar_configuracion("dias_validez_cotizacion", str(dias_int), "Días de vigencia por defecto de una cotización")

    flash("Configuración general actualizada correctamente.", "success")
    return redirect(url_for("admin.configuracion"))


@admin_bp.route("/configuracion/nueva", methods=["GET", "POST"])
@login_required
@rol_required("administrador")
def nueva_configuracion():
    if request.method == "POST":
        clave = request.form.get("clave", "").strip().lower()
        valor = request.form.get("valor", "").strip()
        descripcion = request.form.get("descripcion", "").strip()

        if not clave:
            flash("La clave de configuración es obligatoria.", "warning")
            return render_template("admin/nueva_configuracion.html")

        clave = clave.replace(" ", "_")

        connection = get_db_connection()

        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT id
                    FROM configuracion_sistema
                    WHERE clave = %s
                    LIMIT 1
                """, (clave,))
                existente = cursor.fetchone()

                if existente:
                    flash("Ya existe una configuración con esa clave.", "danger")
                    return render_template("admin/nueva_configuracion.html")

                cursor.execute("""
                    INSERT INTO configuracion_sistema
                    (clave, valor, descripcion, actualizado_por)
                    VALUES (%s, %s, %s, %s)
                """, (clave, valor, descripcion, current_user.id))

            connection.commit()

            flash("Configuración creada correctamente.", "success")
            return redirect(url_for("admin.configuracion"))

        except Exception as e:
            connection.rollback()
            flash(f"No se pudo crear la configuración. Detalle: {str(e)}", "danger")
            return render_template("admin/nueva_configuracion.html")

        finally:
            connection.close()

    return render_template("admin/nueva_configuracion.html")


@admin_bp.route("/configuracion/<int:configuracion_id>/editar", methods=["GET", "POST"])
@login_required
@rol_required("administrador")
def editar_configuracion(configuracion_id):
    connection = get_db_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    id,
                    clave,
                    valor,
                    descripcion
                FROM configuracion_sistema
                WHERE id = %s
                LIMIT 1
            """, (configuracion_id,))
            configuracion_item = cursor.fetchone()

        if not configuracion_item:
            flash("La configuración no existe.", "danger")
            return redirect(url_for("admin.configuracion"))

        if request.method == "POST":
            clave = request.form.get("clave", "").strip().lower()
            valor = request.form.get("valor", "").strip()
            descripcion = request.form.get("descripcion", "").strip()

            if not clave:
                flash("La clave de configuración es obligatoria.", "warning")
                return render_template(
                    "admin/editar_configuracion.html",
                    configuracion_item=configuracion_item,
                    protegidas=CONFIGURACIONES_PROTEGIDAS
                )

            clave = clave.replace(" ", "_")

            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT id
                    FROM configuracion_sistema
                    WHERE clave = %s AND id != %s
                    LIMIT 1
                """, (clave, configuracion_id))
                duplicado = cursor.fetchone()

                if duplicado:
                    flash("Ya existe otra configuración con esa clave.", "danger")
                    return render_template(
                        "admin/editar_configuracion.html",
                        configuracion_item=configuracion_item,
                        protegidas=CONFIGURACIONES_PROTEGIDAS
                    )

                cursor.execute("""
                    UPDATE configuracion_sistema
                    SET clave = %s,
                        valor = %s,
                        descripcion = %s,
                        actualizado_por = %s
                    WHERE id = %s
                """, (
                    clave,
                    valor,
                    descripcion,
                    current_user.id,
                    configuracion_id
                ))

            connection.commit()

            flash("Configuración actualizada correctamente.", "success")
            return redirect(url_for("admin.configuracion"))

        return render_template(
            "admin/editar_configuracion.html",
            configuracion_item=configuracion_item,
            protegidas=CONFIGURACIONES_PROTEGIDAS
        )

    except Exception as e:
        connection.rollback()
        flash(f"No se pudo procesar la configuración. Detalle: {str(e)}", "danger")
        return redirect(url_for("admin.configuracion"))

    finally:
        connection.close()


@admin_bp.route("/configuracion/<int:configuracion_id>/eliminar", methods=["POST"])
@login_required
@rol_required("administrador")
def eliminar_configuracion(configuracion_id):
    connection = get_db_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT id, clave
                FROM configuracion_sistema
                WHERE id = %s
                LIMIT 1
            """, (configuracion_id,))
            configuracion_item = cursor.fetchone()

            if not configuracion_item:
                flash("La configuración no existe.", "danger")
                return redirect(url_for("admin.configuracion"))

            if configuracion_item["clave"] in CONFIGURACIONES_PROTEGIDAS:
                flash("Esta configuración principal no se puede eliminar.", "warning")
                return redirect(url_for("admin.configuracion"))

            cursor.execute("""
                DELETE FROM configuracion_sistema
                WHERE id = %s
            """, (configuracion_id,))

        connection.commit()

        flash("Configuración eliminada correctamente.", "success")
        return redirect(url_for("admin.configuracion"))

    except Exception as e:
        connection.rollback()
        flash(f"No se pudo eliminar la configuración. Detalle: {str(e)}", "danger")
        return redirect(url_for("admin.configuracion"))

    finally:
        connection.close()