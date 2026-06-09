from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user

from app.auth.decorators import rol_required
from app.extensions import get_db_connection


logistica_bp = Blueprint("logistica", __name__, url_prefix="/logistica")


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


@logistica_bp.route("/dashboard")
@login_required
@rol_required("logistica")
def dashboard():
    connection = get_db_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT
                    (
                        SELECT COUNT(*)
                        FROM productos
                        WHERE estado = 'activo'
                    ) AS productos_activos,

                    (
                        SELECT COUNT(*)
                        FROM productos
                        WHERE estado = 'activo'
                        AND stock_actual <= stock_minimo
                        AND stock_actual > 0
                    ) AS productos_stock_bajo,

                    (
                        SELECT COUNT(*)
                        FROM productos
                        WHERE estado = 'activo'
                        AND stock_actual = 0
                    ) AS productos_agotados,

                    (
                        SELECT COUNT(*)
                        FROM proveedores
                        WHERE estado = 'activo'
                    ) AS proveedores_activos,

                    (
                        SELECT COUNT(*)
                        FROM producto_proveedor
                        WHERE estado = 'activo'
                    ) AS costos_registrados,

                    (
                        SELECT COUNT(*)
                        FROM producto_proveedor
                        WHERE estado = 'activo'
                        AND disponibilidad = 'por_confirmar'
                    ) AS costos_por_confirmar
            """)
            metricas = cursor.fetchone()

        return render_template(
            "logistica/dashboard.html",
            metricas=metricas
        )

    finally:
        connection.close()


@logistica_bp.route("/productos")
@login_required
@rol_required("logistica")
def productos():
    buscar = request.args.get("buscar", "").strip()
    categoria_id = request.args.get("categoria_id", "").strip()
    stock = request.args.get("stock", "").strip()

    filtros = []
    parametros = []

    if buscar:
        filtros.append("""
            (
                p.codigo LIKE %s
                OR p.nombre LIKE %s
                OR p.marca LIKE %s
                OR p.modelo LIKE %s
                OR c.nombre LIKE %s
            )
        """)
        parametro = f"%{buscar}%"
        parametros.extend([parametro, parametro, parametro, parametro, parametro])

    if categoria_id:
        filtros.append("p.categoria_id = %s")
        parametros.append(categoria_id)

    if stock == "disponible":
        filtros.append("p.stock_actual > p.stock_minimo")

    if stock == "bajo":
        filtros.append("p.stock_actual <= p.stock_minimo AND p.stock_actual > 0")

    if stock == "agotado":
        filtros.append("p.stock_actual = 0")

    where_sql = ""

    if filtros:
        where_sql = "WHERE " + " AND ".join(filtros)

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

            sql = f"""
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
                {where_sql}
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

            cursor.execute(sql, tuple(parametros))
            productos = cursor.fetchall()

        return render_template(
            "logistica/productos.html",
            productos=productos,
            categorias=categorias,
            filtros={
                "buscar": buscar,
                "categoria_id": categoria_id,
                "stock": stock
            }
        )

    finally:
        connection.close()


@logistica_bp.route("/productos/nuevo", methods=["GET", "POST"])
@login_required
@rol_required("logistica")
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
                    "logistica/nuevo_producto.html",
                    categorias=categorias,
                    unidades=unidades
                )

            if precio_venta_sugerido is None or stock_actual is None or stock_minimo is None:
                flash("Los valores numéricos no pueden ser negativos ni inválidos.", "warning")
                return render_template(
                    "logistica/nuevo_producto.html",
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
                        "logistica/nuevo_producto.html",
                        categorias=categorias,
                        unidades=unidades
                    )

                cursor.execute("""
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
                """, (
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
            return redirect(url_for("logistica.productos"))

        return render_template(
            "logistica/nuevo_producto.html",
            categorias=categorias,
            unidades=unidades
        )

    except Exception as e:
        connection.rollback()
        flash(f"No se pudo registrar el producto. Detalle: {str(e)}", "danger")
        return redirect(url_for("logistica.productos"))

    finally:
        connection.close()


@logistica_bp.route("/productos/<int:producto_id>/editar", methods=["GET", "POST"])
@login_required
@rol_required("logistica")
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
            return redirect(url_for("logistica.productos"))

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
                    "logistica/editar_producto.html",
                    producto=producto,
                    categorias=categorias,
                    unidades=unidades
                )

            if precio_venta_sugerido is None or stock_actual is None or stock_minimo is None:
                flash("Los valores numéricos no pueden ser negativos ni inválidos.", "warning")
                return render_template(
                    "logistica/editar_producto.html",
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
                        "logistica/editar_producto.html",
                        producto=producto,
                        categorias=categorias,
                        unidades=unidades
                    )

                cursor.execute("""
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
                """, (
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
            return redirect(url_for("logistica.productos"))

        return render_template(
            "logistica/editar_producto.html",
            producto=producto,
            categorias=categorias,
            unidades=unidades
        )

    except Exception as e:
        connection.rollback()
        flash(f"No se pudo procesar la operación. Detalle: {str(e)}", "danger")
        return redirect(url_for("logistica.productos"))

    finally:
        connection.close()


@logistica_bp.route("/productos/<int:producto_id>/eliminar", methods=["POST"])
@login_required
@rol_required("logistica")
def eliminar_producto(producto_id):
    connection = get_db_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT id FROM productos WHERE id = %s LIMIT 1", (producto_id,))
            producto = cursor.fetchone()

            if not producto:
                flash("El producto no existe.", "danger")
                return redirect(url_for("logistica.productos"))

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
                return redirect(url_for("logistica.productos"))

            cursor.execute("DELETE FROM productos WHERE id = %s", (producto_id,))

        connection.commit()

        flash("Producto eliminado correctamente.", "success")
        return redirect(url_for("logistica.productos"))

    except Exception as e:
        connection.rollback()
        flash(f"No se pudo eliminar el producto. Detalle: {str(e)}", "danger")
        return redirect(url_for("logistica.productos"))

    finally:
        connection.close()
# Gestionar Proveedores
@logistica_bp.route("/proveedores")
@login_required
@rol_required("logistica")
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
                        CONCAT(u.nombres, ' ', u.apellidos) AS creado_por_nombre,
                        COUNT(pp.id) AS productos_asociados
                    FROM proveedores p
                    LEFT JOIN usuarios u ON p.creado_por = u.id
                    LEFT JOIN producto_proveedor pp ON p.id = pp.proveedor_id
                    WHERE 
                        p.ruc LIKE %s
                        OR p.razon_social LIKE %s
                        OR p.nombre_comercial LIKE %s
                        OR p.email LIKE %s
                        OR p.telefono LIKE %s
                    GROUP BY
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
                        u.nombres,
                        u.apellidos
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
                        CONCAT(u.nombres, ' ', u.apellidos) AS creado_por_nombre,
                        COUNT(pp.id) AS productos_asociados
                    FROM proveedores p
                    LEFT JOIN usuarios u ON p.creado_por = u.id
                    LEFT JOIN producto_proveedor pp ON p.id = pp.proveedor_id
                    GROUP BY
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
                        u.nombres,
                        u.apellidos
                    ORDER BY p.id DESC
                """
                cursor.execute(sql)

            proveedores = cursor.fetchall()

        return render_template(
            "logistica/proveedores.html",
            proveedores=proveedores,
            buscar=buscar
        )

    finally:
        connection.close()


@logistica_bp.route("/proveedores/nuevo", methods=["GET", "POST"])
@login_required
@rol_required("logistica")
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
            return render_template("logistica/nuevo_proveedor.html")

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
                        return render_template("logistica/nuevo_proveedor.html")

                cursor.execute("""
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
                """, (
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
            return redirect(url_for("logistica.proveedores"))

        except Exception as e:
            connection.rollback()
            flash(f"No se pudo registrar el proveedor. Detalle: {str(e)}", "danger")
            return render_template("logistica/nuevo_proveedor.html")

        finally:
            connection.close()

    return render_template("logistica/nuevo_proveedor.html")


@logistica_bp.route("/proveedores/<int:proveedor_id>/editar", methods=["GET", "POST"])
@login_required
@rol_required("logistica")
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
            return redirect(url_for("logistica.proveedores"))

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
                return render_template("logistica/editar_proveedor.html", proveedor=proveedor)

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
                        return render_template("logistica/editar_proveedor.html", proveedor=proveedor)

                cursor.execute("""
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
                """, (
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
            return redirect(url_for("logistica.proveedores"))

        return render_template("logistica/editar_proveedor.html", proveedor=proveedor)

    except Exception as e:
        connection.rollback()
        flash(f"No se pudo procesar la operación. Detalle: {str(e)}", "danger")
        return redirect(url_for("logistica.proveedores"))

    finally:
        connection.close()


@logistica_bp.route("/proveedores/<int:proveedor_id>/eliminar", methods=["POST"])
@login_required
@rol_required("logistica")
def eliminar_proveedor(proveedor_id):
    connection = get_db_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT id 
                FROM proveedores 
                WHERE id = %s 
                LIMIT 1
            """, (proveedor_id,))
            proveedor = cursor.fetchone()

            if not proveedor:
                flash("El proveedor no existe.", "danger")
                return redirect(url_for("logistica.proveedores"))

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
                return redirect(url_for("logistica.proveedores"))

            cursor.execute("""
                DELETE FROM proveedores
                WHERE id = %s
            """, (proveedor_id,))

        connection.commit()

        flash("Proveedor eliminado correctamente.", "success")
        return redirect(url_for("logistica.proveedores"))

    except Exception as e:
        connection.rollback()
        flash(f"No se pudo eliminar el proveedor. Detalle: {str(e)}", "danger")
        return redirect(url_for("logistica.proveedores"))

    finally:
        connection.close()
# Modulo de Costos
@logistica_bp.route("/costos")
@login_required
@rol_required("logistica")
def costos():
    buscar = request.args.get("buscar", "").strip()
    producto_id = request.args.get("producto_id", "").strip()
    proveedor_id = request.args.get("proveedor_id", "").strip()
    disponibilidad = request.args.get("disponibilidad", "").strip()
    estado = request.args.get("estado", "").strip()

    filtros = []
    parametros = []

    if buscar:
        filtros.append("""
            (
                p.codigo LIKE %s
                OR p.nombre LIKE %s
                OR pr.razon_social LIKE %s
                OR pr.ruc LIKE %s
                OR pp.codigo_proveedor LIKE %s
            )
        """)
        parametro = f"%{buscar}%"
        parametros.extend([parametro, parametro, parametro, parametro, parametro])

    if producto_id:
        filtros.append("pp.producto_id = %s")
        parametros.append(producto_id)

    if proveedor_id:
        filtros.append("pp.proveedor_id = %s")
        parametros.append(proveedor_id)

    if disponibilidad:
        filtros.append("pp.disponibilidad = %s")
        parametros.append(disponibilidad)

    if estado:
        filtros.append("pp.estado = %s")
        parametros.append(estado)

    where_sql = ""

    if filtros:
        where_sql = "WHERE " + " AND ".join(filtros)

    connection = get_db_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    id,
                    codigo,
                    nombre
                FROM productos
                WHERE estado = 'activo'
                ORDER BY nombre ASC
            """)
            productos = cursor.fetchall()

            cursor.execute("""
                SELECT 
                    id,
                    ruc,
                    razon_social
                FROM proveedores
                WHERE estado = 'activo'
                ORDER BY razon_social ASC
            """)
            proveedores = cursor.fetchall()

            sql_costos = f"""
                SELECT
                    pp.id,
                    pp.producto_id,
                    pp.proveedor_id,
                    pp.codigo_proveedor,
                    pp.costo_unitario,
                    pp.disponibilidad,
                    pp.tiempo_entrega_dias,
                    pp.fecha_actualizacion,
                    pp.observacion,
                    pp.estado,
                    p.codigo AS codigo_producto,
                    p.nombre AS producto,
                    p.marca,
                    p.modelo,
                    p.precio_venta_sugerido,
                    pr.ruc AS ruc_proveedor,
                    pr.razon_social AS proveedor,
                    um.abreviatura AS unidad,

                    CASE
                        WHEN p.precio_venta_sugerido IS NOT NULL
                        THEN p.precio_venta_sugerido - pp.costo_unitario
                        ELSE 0
                    END AS margen_estimado,

                    CASE
                        WHEN p.precio_venta_sugerido > 0
                        THEN ROUND(((p.precio_venta_sugerido - pp.costo_unitario) / p.precio_venta_sugerido) * 100, 2)
                        ELSE 0
                    END AS margen_porcentaje_estimado

                FROM producto_proveedor pp
                INNER JOIN productos p ON pp.producto_id = p.id
                INNER JOIN proveedores pr ON pp.proveedor_id = pr.id
                LEFT JOIN unidades_medida um ON p.unidad_id = um.id
                {where_sql}
                ORDER BY pp.id DESC
            """

            cursor.execute(sql_costos, tuple(parametros))
            costos = cursor.fetchall()

            sql_resumen = f"""
                SELECT
                    COUNT(pp.id) AS total_costos,
                    IFNULL(SUM(CASE WHEN pp.estado = 'activo' THEN 1 ELSE 0 END), 0) AS costos_activos,
                    IFNULL(SUM(CASE WHEN pp.disponibilidad = 'disponible' THEN 1 ELSE 0 END), 0) AS disponibles,
                    IFNULL(SUM(CASE WHEN pp.disponibilidad = 'bajo_stock' THEN 1 ELSE 0 END), 0) AS bajo_stock,
                    IFNULL(SUM(CASE WHEN pp.disponibilidad = 'agotado' THEN 1 ELSE 0 END), 0) AS agotados,
                    IFNULL(SUM(CASE WHEN pp.disponibilidad = 'por_confirmar' THEN 1 ELSE 0 END), 0) AS por_confirmar,
                    IFNULL(AVG(pp.costo_unitario), 0) AS costo_promedio
                FROM producto_proveedor pp
                INNER JOIN productos p ON pp.producto_id = p.id
                INNER JOIN proveedores pr ON pp.proveedor_id = pr.id
                {where_sql}
            """

            cursor.execute(sql_resumen, tuple(parametros))
            resumen = cursor.fetchone()

        return render_template(
            "logistica/costos.html",
            costos=costos,
            productos=productos,
            proveedores=proveedores,
            resumen=resumen,
            filtros={
                "buscar": buscar,
                "producto_id": producto_id,
                "proveedor_id": proveedor_id,
                "disponibilidad": disponibilidad,
                "estado": estado
            }
        )

    finally:
        connection.close()


@logistica_bp.route("/costos/nuevo", methods=["GET", "POST"])
@login_required
@rol_required("logistica")
def nuevo_costo():
    connection = get_db_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    id,
                    codigo,
                    nombre
                FROM productos
                WHERE estado = 'activo'
                ORDER BY nombre ASC
            """)
            productos = cursor.fetchall()

            cursor.execute("""
                SELECT 
                    id,
                    ruc,
                    razon_social
                FROM proveedores
                WHERE estado = 'activo'
                ORDER BY razon_social ASC
            """)
            proveedores = cursor.fetchall()

        if request.method == "POST":
            producto_id = request.form.get("producto_id")
            proveedor_id = request.form.get("proveedor_id")
            codigo_proveedor = request.form.get("codigo_proveedor", "").strip()
            costo_unitario = convertir_decimal(request.form.get("costo_unitario"))
            disponibilidad = request.form.get("disponibilidad", "por_confirmar")
            tiempo_entrega_dias = request.form.get("tiempo_entrega_dias", "").strip()
            observacion = request.form.get("observacion", "").strip()
            estado = request.form.get("estado", "activo")

            if not producto_id or not proveedor_id:
                flash("Debes seleccionar un producto y un proveedor.", "warning")
                return render_template(
                    "logistica/nuevo_costo.html",
                    productos=productos,
                    proveedores=proveedores
                )

            if costo_unitario is None:
                flash("El costo unitario no puede ser negativo ni inválido.", "warning")
                return render_template(
                    "logistica/nuevo_costo.html",
                    productos=productos,
                    proveedores=proveedores
                )

            if tiempo_entrega_dias == "":
                tiempo_entrega_dias = 0

            try:
                tiempo_entrega_dias = int(tiempo_entrega_dias)

                if tiempo_entrega_dias < 0:
                    flash("El tiempo de entrega no puede ser negativo.", "warning")
                    return render_template(
                        "logistica/nuevo_costo.html",
                        productos=productos,
                        proveedores=proveedores
                    )

            except ValueError:
                flash("El tiempo de entrega debe ser un número entero.", "warning")
                return render_template(
                    "logistica/nuevo_costo.html",
                    productos=productos,
                    proveedores=proveedores
                )

            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT id
                    FROM producto_proveedor
                    WHERE producto_id = %s
                    AND proveedor_id = %s
                    LIMIT 1
                """, (producto_id, proveedor_id))
                existente = cursor.fetchone()

                if existente:
                    flash("Este producto ya tiene un costo registrado con ese proveedor.", "danger")
                    return render_template(
                        "logistica/nuevo_costo.html",
                        productos=productos,
                        proveedores=proveedores
                    )

                cursor.execute("""
                    INSERT INTO producto_proveedor
                    (
                        producto_id,
                        proveedor_id,
                        codigo_proveedor,
                        costo_unitario,
                        disponibilidad,
                        tiempo_entrega_dias,
                        fecha_actualizacion,
                        observacion,
                        estado
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, CURDATE(), %s, %s)
                """, (
                    producto_id,
                    proveedor_id,
                    codigo_proveedor,
                    costo_unitario,
                    disponibilidad,
                    tiempo_entrega_dias,
                    observacion,
                    estado
                ))

            connection.commit()

            flash("Costo registrado correctamente.", "success")
            return redirect(url_for("logistica.costos"))

        return render_template(
            "logistica/nuevo_costo.html",
            productos=productos,
            proveedores=proveedores
        )

    except Exception as e:
        connection.rollback()
        flash(f"No se pudo registrar el costo. Detalle: {str(e)}", "danger")
        return redirect(url_for("logistica.costos"))

    finally:
        connection.close()


@logistica_bp.route("/costos/<int:costo_id>/editar", methods=["GET", "POST"])
@login_required
@rol_required("logistica")
def editar_costo(costo_id):
    connection = get_db_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT
                    id,
                    producto_id,
                    proveedor_id,
                    codigo_proveedor,
                    costo_unitario,
                    disponibilidad,
                    tiempo_entrega_dias,
                    observacion,
                    estado
                FROM producto_proveedor
                WHERE id = %s
                LIMIT 1
            """, (costo_id,))
            costo = cursor.fetchone()

            cursor.execute("""
                SELECT 
                    id,
                    codigo,
                    nombre
                FROM productos
                WHERE estado = 'activo'
                ORDER BY nombre ASC
            """)
            productos = cursor.fetchall()

            cursor.execute("""
                SELECT 
                    id,
                    ruc,
                    razon_social
                FROM proveedores
                WHERE estado = 'activo'
                ORDER BY razon_social ASC
            """)
            proveedores = cursor.fetchall()

        if not costo:
            flash("El costo no existe.", "danger")
            return redirect(url_for("logistica.costos"))

        if request.method == "POST":
            producto_id = request.form.get("producto_id")
            proveedor_id = request.form.get("proveedor_id")
            codigo_proveedor = request.form.get("codigo_proveedor", "").strip()
            costo_unitario = convertir_decimal(request.form.get("costo_unitario"))
            disponibilidad = request.form.get("disponibilidad", "por_confirmar")
            tiempo_entrega_dias = request.form.get("tiempo_entrega_dias", "").strip()
            observacion = request.form.get("observacion", "").strip()
            estado = request.form.get("estado", "activo")

            if not producto_id or not proveedor_id:
                flash("Debes seleccionar un producto y un proveedor.", "warning")
                return render_template(
                    "logistica/editar_costo.html",
                    costo=costo,
                    productos=productos,
                    proveedores=proveedores
                )

            if costo_unitario is None:
                flash("El costo unitario no puede ser negativo ni inválido.", "warning")
                return render_template(
                    "logistica/editar_costo.html",
                    costo=costo,
                    productos=productos,
                    proveedores=proveedores
                )

            if tiempo_entrega_dias == "":
                tiempo_entrega_dias = 0

            try:
                tiempo_entrega_dias = int(tiempo_entrega_dias)

                if tiempo_entrega_dias < 0:
                    flash("El tiempo de entrega no puede ser negativo.", "warning")
                    return render_template(
                        "logistica/editar_costo.html",
                        costo=costo,
                        productos=productos,
                        proveedores=proveedores
                    )

            except ValueError:
                flash("El tiempo de entrega debe ser un número entero.", "warning")
                return render_template(
                    "logistica/editar_costo.html",
                    costo=costo,
                    productos=productos,
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
                """, (producto_id, proveedor_id, costo_id))
                duplicado = cursor.fetchone()

                if duplicado:
                    flash("Ya existe otro costo registrado para ese producto con ese proveedor.", "danger")
                    return render_template(
                        "logistica/editar_costo.html",
                        costo=costo,
                        productos=productos,
                        proveedores=proveedores
                    )

                cursor.execute("""
                    UPDATE producto_proveedor
                    SET 
                        producto_id = %s,
                        proveedor_id = %s,
                        codigo_proveedor = %s,
                        costo_unitario = %s,
                        disponibilidad = %s,
                        tiempo_entrega_dias = %s,
                        fecha_actualizacion = CURDATE(),
                        observacion = %s,
                        estado = %s
                    WHERE id = %s
                """, (
                    producto_id,
                    proveedor_id,
                    codigo_proveedor,
                    costo_unitario,
                    disponibilidad,
                    tiempo_entrega_dias,
                    observacion,
                    estado,
                    costo_id
                ))

            connection.commit()

            flash("Costo actualizado correctamente.", "success")
            return redirect(url_for("logistica.costos"))

        return render_template(
            "logistica/editar_costo.html",
            costo=costo,
            productos=productos,
            proveedores=proveedores
        )

    except Exception as e:
        connection.rollback()
        flash(f"No se pudo procesar la operación. Detalle: {str(e)}", "danger")
        return redirect(url_for("logistica.costos"))

    finally:
        connection.close()


@logistica_bp.route("/costos/<int:costo_id>/eliminar", methods=["POST"])
@login_required
@rol_required("logistica")
def eliminar_costo(costo_id):
    connection = get_db_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    id,
                    producto_id,
                    proveedor_id
                FROM producto_proveedor
                WHERE id = %s
                LIMIT 1
            """, (costo_id,))
            costo = cursor.fetchone()

            if not costo:
                flash("El costo no existe.", "danger")
                return redirect(url_for("logistica.costos"))

            cursor.execute("""
                SELECT COUNT(*) AS total_cotizaciones
                FROM cotizacion_detalles
                WHERE producto_id = %s
                AND proveedor_id = %s
            """, (costo["producto_id"], costo["proveedor_id"]))
            resultado = cursor.fetchone()

            if resultado["total_cotizaciones"] > 0:
                cursor.execute("""
                    UPDATE producto_proveedor
                    SET estado = 'inactivo'
                    WHERE id = %s
                """, (costo_id,))

                connection.commit()

                flash(
                    "Este costo ya fue usado en cotizaciones, por eso fue marcado como inactivo.",
                    "warning"
                )
                return redirect(url_for("logistica.costos"))

            cursor.execute("""
                DELETE FROM producto_proveedor
                WHERE id = %s
            """, (costo_id,))

        connection.commit()

        flash("Costo eliminado correctamente.", "success")
        return redirect(url_for("logistica.costos"))

    except Exception as e:
        connection.rollback()
        flash(f"No se pudo eliminar el costo. Detalle: {str(e)}", "danger")
        return redirect(url_for("logistica.costos"))

    finally:
        connection.close()
#Modulo de disponibilidad
@logistica_bp.route("/disponibilidad")
@login_required
@rol_required("logistica")
def disponibilidad():
    buscar = request.args.get("buscar", "").strip()
    proveedor_id = request.args.get("proveedor_id", "").strip()
    disponibilidad_filtro = request.args.get("disponibilidad", "").strip()
    stock = request.args.get("stock", "").strip()
    estado = request.args.get("estado", "").strip()

    filtros = []
    parametros = []

    if buscar:
        filtros.append("""
            (
                p.codigo LIKE %s
                OR p.nombre LIKE %s
                OR p.marca LIKE %s
                OR p.modelo LIKE %s
                OR pr.razon_social LIKE %s
                OR pr.ruc LIKE %s
            )
        """)
        parametro = f"%{buscar}%"
        parametros.extend([parametro, parametro, parametro, parametro, parametro, parametro])

    if proveedor_id:
        filtros.append("pp.proveedor_id = %s")
        parametros.append(proveedor_id)

    if disponibilidad_filtro:
        filtros.append("pp.disponibilidad = %s")
        parametros.append(disponibilidad_filtro)

    if stock == "disponible":
        filtros.append("p.stock_actual > p.stock_minimo")

    if stock == "bajo":
        filtros.append("p.stock_actual <= p.stock_minimo AND p.stock_actual > 0")

    if stock == "agotado":
        filtros.append("p.stock_actual = 0")

    if estado:
        filtros.append("pp.estado = %s")
        parametros.append(estado)

    where_sql = ""

    if filtros:
        where_sql = "WHERE " + " AND ".join(filtros)

    connection = get_db_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    id,
                    ruc,
                    razon_social
                FROM proveedores
                WHERE estado = 'activo'
                ORDER BY razon_social ASC
            """)
            proveedores = cursor.fetchall()

            sql_disponibilidad = f"""
                SELECT
                    pp.id,
                    pp.producto_id,
                    pp.proveedor_id,
                    pp.codigo_proveedor,
                    pp.costo_unitario,
                    pp.disponibilidad,
                    pp.tiempo_entrega_dias,
                    pp.fecha_actualizacion,
                    pp.observacion,
                    pp.estado,

                    p.codigo AS codigo_producto,
                    p.nombre AS producto,
                    p.descripcion,
                    p.marca,
                    p.modelo,
                    p.stock_actual,
                    p.stock_minimo,
                    p.precio_venta_sugerido,

                    pr.ruc AS ruc_proveedor,
                    pr.razon_social AS proveedor,
                    pr.telefono AS proveedor_telefono,
                    pr.email AS proveedor_email,

                    cp.nombre AS categoria,
                    um.abreviatura AS unidad

                FROM producto_proveedor pp
                INNER JOIN productos p ON pp.producto_id = p.id
                INNER JOIN proveedores pr ON pp.proveedor_id = pr.id
                LEFT JOIN categorias_productos cp ON p.categoria_id = cp.id
                LEFT JOIN unidades_medida um ON p.unidad_id = um.id
                {where_sql}
                ORDER BY 
                    CASE 
                        WHEN p.stock_actual = 0 THEN 1
                        WHEN p.stock_actual <= p.stock_minimo THEN 2
                        ELSE 3
                    END,
                    pp.fecha_actualizacion ASC,
                    p.nombre ASC
            """

            cursor.execute(sql_disponibilidad, tuple(parametros))
            registros = cursor.fetchall()

            sql_resumen = f"""
                SELECT
                    COUNT(pp.id) AS total_registros,
                    IFNULL(SUM(CASE WHEN p.stock_actual > p.stock_minimo THEN 1 ELSE 0 END), 0) AS stock_disponible,
                    IFNULL(SUM(CASE WHEN p.stock_actual <= p.stock_minimo AND p.stock_actual > 0 THEN 1 ELSE 0 END), 0) AS stock_bajo,
                    IFNULL(SUM(CASE WHEN p.stock_actual = 0 THEN 1 ELSE 0 END), 0) AS stock_agotado,
                    IFNULL(SUM(CASE WHEN pp.disponibilidad = 'disponible' THEN 1 ELSE 0 END), 0) AS proveedor_disponible,
                    IFNULL(SUM(CASE WHEN pp.disponibilidad = 'por_confirmar' THEN 1 ELSE 0 END), 0) AS por_confirmar
                FROM producto_proveedor pp
                INNER JOIN productos p ON pp.producto_id = p.id
                INNER JOIN proveedores pr ON pp.proveedor_id = pr.id
                {where_sql}
            """

            cursor.execute(sql_resumen, tuple(parametros))
            resumen = cursor.fetchone()

        return render_template(
            "logistica/disponibilidad.html",
            registros=registros,
            proveedores=proveedores,
            resumen=resumen,
            filtros={
                "buscar": buscar,
                "proveedor_id": proveedor_id,
                "disponibilidad": disponibilidad_filtro,
                "stock": stock,
                "estado": estado
            }
        )

    finally:
        connection.close()


@logistica_bp.route("/disponibilidad/<int:relacion_id>/editar", methods=["GET", "POST"])
@login_required
@rol_required("logistica")
def editar_disponibilidad(relacion_id):
    connection = get_db_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT
                    pp.id,
                    pp.producto_id,
                    pp.proveedor_id,
                    pp.codigo_proveedor,
                    pp.costo_unitario,
                    pp.disponibilidad,
                    pp.tiempo_entrega_dias,
                    pp.fecha_actualizacion,
                    pp.observacion,
                    pp.estado,

                    p.codigo AS codigo_producto,
                    p.nombre AS producto,
                    p.marca,
                    p.modelo,
                    p.stock_actual,
                    p.stock_minimo,

                    pr.razon_social AS proveedor,
                    pr.ruc AS ruc_proveedor,

                    um.abreviatura AS unidad
                FROM producto_proveedor pp
                INNER JOIN productos p ON pp.producto_id = p.id
                INNER JOIN proveedores pr ON pp.proveedor_id = pr.id
                LEFT JOIN unidades_medida um ON p.unidad_id = um.id
                WHERE pp.id = %s
                LIMIT 1
            """, (relacion_id,))
            registro = cursor.fetchone()

        if not registro:
            flash("El registro de disponibilidad no existe.", "danger")
            return redirect(url_for("logistica.disponibilidad"))

        if request.method == "POST":
            stock_actual = convertir_decimal(request.form.get("stock_actual"))
            stock_minimo = convertir_decimal(request.form.get("stock_minimo"))
            disponibilidad_valor = request.form.get("disponibilidad", "por_confirmar")
            tiempo_entrega_dias = request.form.get("tiempo_entrega_dias", "").strip()
            observacion = request.form.get("observacion", "").strip()
            estado = request.form.get("estado", "activo")

            if stock_actual is None or stock_minimo is None:
                flash("El stock actual y el stock mínimo no pueden ser negativos ni inválidos.", "warning")
                return render_template(
                    "logistica/editar_disponibilidad.html",
                    registro=registro
                )

            if tiempo_entrega_dias == "":
                tiempo_entrega_dias = 0

            try:
                tiempo_entrega_dias = int(tiempo_entrega_dias)

                if tiempo_entrega_dias < 0:
                    flash("El tiempo de entrega no puede ser negativo.", "warning")
                    return render_template(
                        "logistica/editar_disponibilidad.html",
                        registro=registro
                    )

            except ValueError:
                flash("El tiempo de entrega debe ser un número entero.", "warning")
                return render_template(
                    "logistica/editar_disponibilidad.html",
                    registro=registro
                )

            with connection.cursor() as cursor:
                cursor.execute("""
                    UPDATE productos
                    SET 
                        stock_actual = %s,
                        stock_minimo = %s
                    WHERE id = %s
                """, (
                    stock_actual,
                    stock_minimo,
                    registro["producto_id"]
                ))

                cursor.execute("""
                    UPDATE producto_proveedor
                    SET 
                        disponibilidad = %s,
                        tiempo_entrega_dias = %s,
                        fecha_actualizacion = CURDATE(),
                        observacion = %s,
                        estado = %s
                    WHERE id = %s
                """, (
                    disponibilidad_valor,
                    tiempo_entrega_dias,
                    observacion,
                    estado,
                    relacion_id
                ))

            connection.commit()

            flash("Disponibilidad actualizada correctamente.", "success")
            return redirect(url_for("logistica.disponibilidad"))

        return render_template(
            "logistica/editar_disponibilidad.html",
            registro=registro
        )

    except Exception as e:
        connection.rollback()
        flash(f"No se pudo actualizar la disponibilidad. Detalle: {str(e)}", "danger")
        return redirect(url_for("logistica.disponibilidad"))

    finally:
        connection.close()