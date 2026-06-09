from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file
from flask_login import login_required, current_user

from app.auth.decorators import rol_required
from app.extensions import get_db_connection
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer

vendedor_bp = Blueprint("vendedor", __name__, url_prefix="/vendedor")


@vendedor_bp.route("/dashboard")
@login_required
@rol_required("vendedor")
def dashboard():
    connection = get_db_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT
                    (
                        SELECT COUNT(*)
                        FROM cotizaciones
                        WHERE vendedor_id = %s
                    ) AS mis_cotizaciones,

                    (
                        SELECT COUNT(*)
                        FROM cotizaciones c
                        INNER JOIN estados_cotizacion ec ON c.estado_id = ec.id
                        WHERE c.vendedor_id = %s
                        AND ec.nombre = 'pendiente'
                    ) AS cotizaciones_pendientes,

                    (
                        SELECT IFNULL(SUM(c.total), 0)
                        FROM cotizaciones c
                        INNER JOIN estados_cotizacion ec ON c.estado_id = ec.id
                        WHERE c.vendedor_id = %s
                        AND ec.nombre = 'cerrada'
                    ) AS total_vendido,

                    (
                        SELECT COUNT(*)
                        FROM clientes
                        WHERE creado_por = %s
                    ) AS clientes_registrados
            """, (
                current_user.id,
                current_user.id,
                current_user.id,
                current_user.id
            ))

            metricas = cursor.fetchone()

        return render_template(
            "vendedor/dashboard.html",
            metricas=metricas
        )

    finally:
        connection.close()


@vendedor_bp.route("/clientes")
@login_required
@rol_required("vendedor")
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
                        c.creado_por,
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
                        c.creado_por,
                        c.created_at,
                        CONCAT(u.nombres, ' ', u.apellidos) AS creado_por_nombre
                    FROM clientes c
                    LEFT JOIN usuarios u ON c.creado_por = u.id
                    ORDER BY c.id DESC
                """
                cursor.execute(sql)

            clientes = cursor.fetchall()

        return render_template(
            "vendedor/clientes.html",
            clientes=clientes,
            buscar=buscar
        )

    finally:
        connection.close()


@vendedor_bp.route("/clientes/nuevo", methods=["GET", "POST"])
@login_required
@rol_required("vendedor")
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

        if not razon_social:
            flash("La razón social o nombre del cliente es obligatorio.", "warning")
            return render_template("vendedor/nuevo_cliente.html")

        if tipo_documento != "SIN_DOCUMENTO" and not numero_documento:
            flash("El número de documento es obligatorio para el tipo seleccionado.", "warning")
            return render_template("vendedor/nuevo_cliente.html")

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
                        flash("Ya existe un cliente registrado con ese número de documento.", "danger")
                        return render_template("vendedor/nuevo_cliente.html")

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
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'activo', %s)
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
                    current_user.id
                ))

            connection.commit()

            flash("Cliente registrado correctamente.", "success")
            return redirect(url_for("vendedor.clientes"))

        except Exception as e:
            connection.rollback()
            flash(f"No se pudo registrar el cliente. Detalle: {str(e)}", "danger")
            return render_template("vendedor/nuevo_cliente.html")

        finally:
            connection.close()

    return render_template("vendedor/nuevo_cliente.html")


@vendedor_bp.route("/clientes/<int:cliente_id>/editar", methods=["GET", "POST"])
@login_required
@rol_required("vendedor")
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
                    estado,
                    creado_por
                FROM clientes
                WHERE id = %s
                LIMIT 1
            """, (cliente_id,))
            cliente = cursor.fetchone()

        if not cliente:
            flash("El cliente no existe.", "danger")
            return redirect(url_for("vendedor.clientes"))

        if cliente["creado_por"] is not None and int(cliente["creado_por"]) != int(current_user.id):
            flash("Solo puedes editar clientes registrados por tu usuario.", "warning")
            return redirect(url_for("vendedor.clientes"))

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

            if not razon_social:
                flash("La razón social o nombre del cliente es obligatorio.", "warning")
                return render_template("vendedor/editar_cliente.html", cliente=cliente)

            if tipo_documento != "SIN_DOCUMENTO" and not numero_documento:
                flash("El número de documento es obligatorio para el tipo seleccionado.", "warning")
                return render_template("vendedor/editar_cliente.html", cliente=cliente)

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
                        return render_template("vendedor/editar_cliente.html", cliente=cliente)

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
                        departamento = %s
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
                    cliente_id
                ))

            connection.commit()

            flash("Cliente actualizado correctamente.", "success")
            return redirect(url_for("vendedor.clientes"))

        return render_template("vendedor/editar_cliente.html", cliente=cliente)

    except Exception as e:
        connection.rollback()
        flash(f"No se pudo procesar la operación. Detalle: {str(e)}", "danger")
        return redirect(url_for("vendedor.clientes"))

    finally:
        connection.close()
def decimal_seguro(valor, defecto="0"):
    try:
        if valor is None or str(valor).strip() == "":
            return Decimal(defecto)

        numero = Decimal(str(valor))

        if numero < 0:
            return None

        return numero

    except InvalidOperation:
        return None


def obtener_configuracion_valor(clave, defecto=None):
    connection = get_db_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT valor
                FROM configuracion_sistema
                WHERE clave = %s
                LIMIT 1
            """, (clave,))
            resultado = cursor.fetchone()

        if resultado:
            return resultado["valor"]

        return defecto

    finally:
        connection.close()


def obtener_estado_cotizacion_id(nombre_estado):
    connection = get_db_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT id
                FROM estados_cotizacion
                WHERE nombre = %s
                LIMIT 1
            """, (nombre_estado,))
            estado = cursor.fetchone()

        if estado:
            return estado["id"]

        return None

    finally:
        connection.close()


def generar_codigo_cotizacion(cursor):
    fecha_actual = date.today()
    prefijo = fecha_actual.strftime("COT-%Y%m%d")

    cursor.execute("""
        SELECT COUNT(*) AS total
        FROM cotizaciones
        WHERE codigo LIKE %s
    """, (f"{prefijo}-%",))

    resultado = cursor.fetchone()
    correlativo = int(resultado["total"]) + 1

    return f"{prefijo}-{correlativo:04d}"
# Modulo de Cotizaciones
@vendedor_bp.route("/cotizaciones/nueva", methods=["GET", "POST"])
@login_required
@rol_required("vendedor")
def nueva_cotizacion():
    connection = get_db_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    id,
                    tipo_documento,
                    numero_documento,
                    razon_social
                FROM clientes
                WHERE estado = 'activo'
                ORDER BY razon_social ASC
            """)
            clientes = cursor.fetchall()

            cursor.execute("""
                SELECT
                    p.id,
                    p.codigo,
                    p.nombre,
                    p.descripcion,
                    p.precio_venta_sugerido,
                    p.stock_actual,
                    p.unidad_id,
                    um.abreviatura AS unidad,

                    (
                        SELECT pp.proveedor_id
                        FROM producto_proveedor pp
                        INNER JOIN proveedores pr ON pp.proveedor_id = pr.id
                        WHERE pp.producto_id = p.id
                        AND pp.estado = 'activo'
                        AND pr.estado = 'activo'
                        ORDER BY pp.costo_unitario ASC
                        LIMIT 1
                    ) AS proveedor_id,

                    (
                        SELECT pr.razon_social
                        FROM producto_proveedor pp
                        INNER JOIN proveedores pr ON pp.proveedor_id = pr.id
                        WHERE pp.producto_id = p.id
                        AND pp.estado = 'activo'
                        AND pr.estado = 'activo'
                        ORDER BY pp.costo_unitario ASC
                        LIMIT 1
                    ) AS proveedor,

                    (
                        SELECT pp.costo_unitario
                        FROM producto_proveedor pp
                        INNER JOIN proveedores pr ON pp.proveedor_id = pr.id
                        WHERE pp.producto_id = p.id
                        AND pp.estado = 'activo'
                        AND pr.estado = 'activo'
                        ORDER BY pp.costo_unitario ASC
                        LIMIT 1
                    ) AS costo_unitario

                FROM productos p
                LEFT JOIN unidades_medida um ON p.unidad_id = um.id
                WHERE p.estado = 'activo'
                ORDER BY p.nombre ASC
            """)
            productos = cursor.fetchall()

        igv_porcentaje = Decimal(str(obtener_configuracion_valor("igv_porcentaje", "18")))
        moneda_principal = obtener_configuracion_valor("moneda_principal", "PEN")
        dias_validez = int(obtener_configuracion_valor("dias_validez_cotizacion", "7"))

        fecha_emision_default = date.today()
        fecha_vencimiento_default = fecha_emision_default + timedelta(days=dias_validez)

        productos_json = []

        for producto in productos:
            productos_json.append({
                "id": producto["id"],
                "codigo": producto["codigo"],
                "nombre": producto["nombre"],
                "descripcion": producto["descripcion"] or producto["nombre"],
                "precio_venta_sugerido": float(producto["precio_venta_sugerido"] or 0),
                "stock_actual": float(producto["stock_actual"] or 0),
                "unidad_id": producto["unidad_id"],
                "unidad": producto["unidad"] or "",
                "proveedor_id": producto["proveedor_id"],
                "proveedor": producto["proveedor"] or "",
                "costo_unitario": float(producto["costo_unitario"] or 0)
            })

        if request.method == "POST":
            cliente_id = request.form.get("cliente_id")
            fecha_emision = request.form.get("fecha_emision")
            fecha_vencimiento = request.form.get("fecha_vencimiento")
            moneda = request.form.get("moneda", moneda_principal)
            observaciones = request.form.get("observaciones", "").strip()
            condiciones = request.form.get("condiciones", "").strip()

            producto_ids = request.form.getlist("producto_id[]")
            proveedor_ids = request.form.getlist("proveedor_id[]")
            unidad_ids = request.form.getlist("unidad_id[]")
            descripciones = request.form.getlist("descripcion_producto[]")
            cantidades = request.form.getlist("cantidad[]")
            precios_unitarios = request.form.getlist("precio_unitario[]")
            costos_unitarios = request.form.getlist("costo_unitario[]")
            descuentos_porcentaje = request.form.getlist("descuento_porcentaje[]")
            observaciones_items = request.form.getlist("observacion_item[]")

            if not cliente_id:
                flash("Selecciona un cliente para generar la cotización.", "warning")
                return render_template(
                    "vendedor/nueva_cotizacion.html",
                    clientes=clientes,
                    productos=productos,
                    productos_json=productos_json,
                    igv_porcentaje=igv_porcentaje,
                    moneda_principal=moneda_principal,
                    fecha_emision_default=fecha_emision_default,
                    fecha_vencimiento_default=fecha_vencimiento_default
                )

            estado_id = obtener_estado_cotizacion_id("pendiente")

            if not estado_id:
                flash("No existe el estado 'pendiente' en la base de datos.", "danger")
                return redirect(url_for("vendedor.dashboard"))

            detalles_validos = []

            subtotal_cotizacion = Decimal("0.00")
            descuento_total = Decimal("0.00")
            costo_total_cotizacion = Decimal("0.00")
            margen_total_cotizacion = Decimal("0.00")

            for i in range(len(descripciones)):
                producto_id = producto_ids[i] if i < len(producto_ids) and producto_ids[i] else None
                proveedor_id = proveedor_ids[i] if i < len(proveedor_ids) and proveedor_ids[i] else None
                unidad_id = unidad_ids[i] if i < len(unidad_ids) and unidad_ids[i] else None

                descripcion_producto = descripciones[i].strip() if i < len(descripciones) else ""

                cantidad = decimal_seguro(cantidades[i] if i < len(cantidades) else "0")
                precio_unitario = decimal_seguro(precios_unitarios[i] if i < len(precios_unitarios) else "0")
                costo_unitario = decimal_seguro(costos_unitarios[i] if i < len(costos_unitarios) else "0")
                descuento_porcentaje = decimal_seguro(descuentos_porcentaje[i] if i < len(descuentos_porcentaje) else "0")

                observacion_item = observaciones_items[i].strip() if i < len(observaciones_items) else ""

                if not descripcion_producto:
                    continue

                if cantidad is None or precio_unitario is None or costo_unitario is None or descuento_porcentaje is None:
                    flash("Hay valores numéricos inválidos en el detalle de la cotización.", "warning")
                    return redirect(url_for("vendedor.nueva_cotizacion"))

                if cantidad <= 0:
                    flash("La cantidad debe ser mayor a cero.", "warning")
                    return redirect(url_for("vendedor.nueva_cotizacion"))

                if descuento_porcentaje > 100:
                    flash("El descuento no puede ser mayor al 100%.", "warning")
                    return redirect(url_for("vendedor.nueva_cotizacion"))

                importe_bruto = cantidad * precio_unitario
                descuento_monto = importe_bruto * (descuento_porcentaje / Decimal("100"))
                subtotal_item = importe_bruto - descuento_monto

                costo_total_item = cantidad * costo_unitario
                margen_item = subtotal_item - costo_total_item

                if subtotal_item > 0:
                    margen_porcentaje_item = (margen_item / subtotal_item) * Decimal("100")
                else:
                    margen_porcentaje_item = Decimal("0.00")

                subtotal_cotizacion += subtotal_item
                descuento_total += descuento_monto
                costo_total_cotizacion += costo_total_item
                margen_total_cotizacion += margen_item

                detalles_validos.append({
                    "producto_id": producto_id,
                    "proveedor_id": proveedor_id,
                    "unidad_id": unidad_id,
                    "descripcion_producto": descripcion_producto,
                    "cantidad": cantidad,
                    "precio_unitario": precio_unitario,
                    "costo_unitario": costo_unitario,
                    "descuento_porcentaje": descuento_porcentaje,
                    "descuento_monto": descuento_monto,
                    "subtotal": subtotal_item,
                    "costo_total": costo_total_item,
                    "margen": margen_item,
                    "margen_porcentaje": margen_porcentaje_item,
                    "observacion": observacion_item
                })

            if not detalles_validos:
                flash("Agrega al menos un producto válido a la cotización.", "warning")
                return redirect(url_for("vendedor.nueva_cotizacion"))

            igv = subtotal_cotizacion * (igv_porcentaje / Decimal("100"))
            total = subtotal_cotizacion + igv

            if subtotal_cotizacion > 0:
                margen_porcentaje_cotizacion = (margen_total_cotizacion / subtotal_cotizacion) * Decimal("100")
            else:
                margen_porcentaje_cotizacion = Decimal("0.00")

            with connection.cursor() as cursor:
                codigo_cotizacion = generar_codigo_cotizacion(cursor)

                sql_cotizacion = """
                    INSERT INTO cotizaciones
                    (
                        codigo,
                        cliente_id,
                        vendedor_id,
                        estado_id,
                        fecha_emision,
                        fecha_vencimiento,
                        moneda,
                        tipo_cambio,
                        subtotal,
                        descuento_total,
                        igv_porcentaje,
                        igv,
                        total,
                        costo_total,
                        margen_total,
                        margen_porcentaje,
                        observaciones,
                        condiciones,
                        creado_por,
                        actualizado_por
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, 1.0000, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """

                cursor.execute(sql_cotizacion, (
                    codigo_cotizacion,
                    cliente_id,
                    current_user.id,
                    estado_id,
                    fecha_emision,
                    fecha_vencimiento,
                    moneda,
                    subtotal_cotizacion,
                    descuento_total,
                    igv_porcentaje,
                    igv,
                    total,
                    costo_total_cotizacion,
                    margen_total_cotizacion,
                    margen_porcentaje_cotizacion,
                    observaciones,
                    condiciones,
                    current_user.id,
                    current_user.id
                ))

                cotizacion_id = cursor.lastrowid

                sql_detalle = """
                    INSERT INTO cotizacion_detalles
                    (
                        cotizacion_id,
                        producto_id,
                        proveedor_id,
                        unidad_id,
                        descripcion_producto,
                        cantidad,
                        precio_unitario,
                        costo_unitario,
                        descuento_porcentaje,
                        descuento_monto,
                        subtotal,
                        costo_total,
                        margen,
                        margen_porcentaje,
                        observacion
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """

                for item in detalles_validos:
                    cursor.execute(sql_detalle, (
                        cotizacion_id,
                        item["producto_id"],
                        item["proveedor_id"],
                        item["unidad_id"],
                        item["descripcion_producto"],
                        item["cantidad"],
                        item["precio_unitario"],
                        item["costo_unitario"],
                        item["descuento_porcentaje"],
                        item["descuento_monto"],
                        item["subtotal"],
                        item["costo_total"],
                        item["margen"],
                        item["margen_porcentaje"],
                        item["observacion"]
                    ))

            connection.commit()

            flash(f"Cotización {codigo_cotizacion} generada correctamente.", "success")
            return redirect(url_for("vendedor.nueva_cotizacion"))

        return render_template(
            "vendedor/nueva_cotizacion.html",
            clientes=clientes,
            productos=productos,
            productos_json=productos_json,
            igv_porcentaje=igv_porcentaje,
            moneda_principal=moneda_principal,
            fecha_emision_default=fecha_emision_default,
            fecha_vencimiento_default=fecha_vencimiento_default
        )

    except Exception as e:
        connection.rollback()
        flash(f"No se pudo generar la cotización. Detalle: {str(e)}", "danger")
        return redirect(url_for("vendedor.nueva_cotizacion"))

    finally:
        connection.close()
# Mis Cotizaciones
@vendedor_bp.route("/cotizaciones")
@login_required
@rol_required("vendedor")
def mis_cotizaciones():
    cliente = request.args.get("cliente", "").strip()
    estado_id = request.args.get("estado_id", "").strip()
    fecha_inicio = request.args.get("fecha_inicio", "").strip()
    fecha_fin = request.args.get("fecha_fin", "").strip()

    filtros = ["c.vendedor_id = %s"]
    parametros = [current_user.id]

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

    where_sql = "WHERE " + " AND ".join(filtros)

    connection = get_db_connection()

    try:
        with connection.cursor() as cursor:
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
                    COUNT(cd.id) AS total_items
                FROM cotizaciones c
                INNER JOIN clientes cl ON c.cliente_id = cl.id
                INNER JOIN estados_cotizacion ec ON c.estado_id = ec.id
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
                    ec.nombre
                ORDER BY c.id DESC
            """

            cursor.execute(sql_cotizaciones, tuple(parametros))
            cotizaciones = cursor.fetchall()

            sql_resumen = f"""
                SELECT
                    COUNT(DISTINCT c.id) AS total_cotizaciones,
                    IFNULL(SUM(c.total), 0) AS total_cotizado,
                    IFNULL(SUM(c.costo_total), 0) AS total_costos,
                    IFNULL(SUM(c.margen_total), 0) AS total_margen,
                    CASE 
                        WHEN IFNULL(SUM(c.subtotal), 0) > 0
                        THEN ROUND((SUM(c.margen_total) / SUM(c.subtotal)) * 100, 2)
                        ELSE 0
                    END AS margen_promedio
                FROM cotizaciones c
                INNER JOIN clientes cl ON c.cliente_id = cl.id
                INNER JOIN estados_cotizacion ec ON c.estado_id = ec.id
                {where_sql}
            """

            cursor.execute(sql_resumen, tuple(parametros))
            resumen = cursor.fetchone()

        return render_template(
            "vendedor/mis_cotizaciones.html",
            cotizaciones=cotizaciones,
            estados=estados,
            resumen=resumen,
            filtros={
                "cliente": cliente,
                "estado_id": estado_id,
                "fecha_inicio": fecha_inicio,
                "fecha_fin": fecha_fin
            }
        )

    finally:
        connection.close()


@vendedor_bp.route("/cotizaciones/<int:cotizacion_id>")
@login_required
@rol_required("vendedor")
def detalle_mi_cotizacion(cotizacion_id):
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
                    ec.nombre AS estado
                FROM cotizaciones c
                INNER JOIN clientes cl ON c.cliente_id = cl.id
                INNER JOIN estados_cotizacion ec ON c.estado_id = ec.id
                WHERE c.id = %s
                AND c.vendedor_id = %s
                LIMIT 1
            """, (cotizacion_id, current_user.id))
            cotizacion = cursor.fetchone()

            if not cotizacion:
                flash("La cotización no existe o no pertenece a tu usuario.", "danger")
                return redirect(url_for("vendedor.mis_cotizaciones"))

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
            "vendedor/detalle_cotizacion.html",
            cotizacion=cotizacion,
            detalles=detalles,
            estados=estados
        )

    finally:
        connection.close()


@vendedor_bp.route("/cotizaciones/<int:cotizacion_id>/estado", methods=["POST"])
@login_required
@rol_required("vendedor")
def cambiar_estado_mi_cotizacion(cotizacion_id):
    estado_id = request.form.get("estado_id")

    if not estado_id:
        flash("Selecciona un estado válido.", "warning")
        return redirect(url_for("vendedor.detalle_mi_cotizacion", cotizacion_id=cotizacion_id))

    connection = get_db_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT id
                FROM cotizaciones
                WHERE id = %s
                AND vendedor_id = %s
                LIMIT 1
            """, (cotizacion_id, current_user.id))
            cotizacion = cursor.fetchone()

            if not cotizacion:
                flash("La cotización no existe o no pertenece a tu usuario.", "danger")
                return redirect(url_for("vendedor.mis_cotizaciones"))

            cursor.execute("""
                SELECT id
                FROM estados_cotizacion
                WHERE id = %s 
                AND estado = 'activo'
                LIMIT 1
            """, (estado_id,))
            estado = cursor.fetchone()

            if not estado:
                flash("El estado seleccionado no existe.", "danger")
                return redirect(url_for("vendedor.detalle_mi_cotizacion", cotizacion_id=cotizacion_id))

            cursor.execute("""
                UPDATE cotizaciones
                SET estado_id = %s,
                    actualizado_por = %s
                WHERE id = %s
                AND vendedor_id = %s
            """, (
                estado_id,
                current_user.id,
                cotizacion_id,
                current_user.id
            ))

        connection.commit()

        flash("Estado actualizado correctamente.", "success")
        return redirect(url_for("vendedor.detalle_mi_cotizacion", cotizacion_id=cotizacion_id))

    except Exception as e:
        connection.rollback()
        flash(f"No se pudo actualizar el estado. Detalle: {str(e)}", "danger")
        return redirect(url_for("vendedor.detalle_mi_cotizacion", cotizacion_id=cotizacion_id))

    finally:
        connection.close()


@vendedor_bp.route("/cotizaciones/<int:cotizacion_id>/eliminar", methods=["POST"])
@login_required
@rol_required("vendedor")
def eliminar_mi_cotizacion(cotizacion_id):
    connection = get_db_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT id, codigo
                FROM cotizaciones
                WHERE id = %s
                AND vendedor_id = %s
                LIMIT 1
            """, (cotizacion_id, current_user.id))
            cotizacion = cursor.fetchone()

            if not cotizacion:
                flash("La cotización no existe o no pertenece a tu usuario.", "danger")
                return redirect(url_for("vendedor.mis_cotizaciones"))

            cursor.execute("""
                DELETE FROM cotizaciones
                WHERE id = %s
                AND vendedor_id = %s
            """, (cotizacion_id, current_user.id))

        connection.commit()

        flash("Cotización eliminada correctamente.", "success")
        return redirect(url_for("vendedor.mis_cotizaciones"))

    except Exception as e:
        connection.rollback()
        flash(f"No se pudo eliminar la cotización. Detalle: {str(e)}", "danger")
        return redirect(url_for("vendedor.mis_cotizaciones"))

    finally:
        connection.close()
# Para descargar las cotizaciones
def formato_monto(valor):
    try:
        return f"S/ {float(valor):,.2f}"
    except Exception:
        return "S/ 0.00"


@vendedor_bp.route("/cotizaciones/<int:cotizacion_id>/pdf")
@login_required
@rol_required("vendedor")
def descargar_cotizacion_pdf(cotizacion_id):
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
                    cl.razon_social AS cliente,
                    cl.tipo_documento,
                    cl.numero_documento,
                    cl.contacto,
                    cl.telefono AS cliente_telefono,
                    cl.email AS cliente_email,
                    cl.direccion AS cliente_direccion,
                    ec.nombre AS estado,
                    CONCAT(u.nombres, ' ', u.apellidos) AS vendedor
                FROM cotizaciones c
                INNER JOIN clientes cl ON c.cliente_id = cl.id
                INNER JOIN estados_cotizacion ec ON c.estado_id = ec.id
                LEFT JOIN usuarios u ON c.vendedor_id = u.id
                WHERE c.id = %s
                AND c.vendedor_id = %s
                LIMIT 1
            """, (cotizacion_id, current_user.id))
            cotizacion = cursor.fetchone()

            if not cotizacion:
                flash("La cotización no existe o no pertenece a tu usuario.", "danger")
                return redirect(url_for("vendedor.mis_cotizaciones"))

            cursor.execute("""
                SELECT 
                    cd.descripcion_producto,
                    cd.cantidad,
                    cd.precio_unitario,
                    cd.descuento_porcentaje,
                    cd.subtotal,
                    um.abreviatura AS unidad
                FROM cotizacion_detalles cd
                LEFT JOIN unidades_medida um ON cd.unidad_id = um.id
                WHERE cd.cotizacion_id = %s
                ORDER BY cd.id ASC
            """, (cotizacion_id,))
            detalles = cursor.fetchall()

            cursor.execute("""
                SELECT clave, valor
                FROM configuracion_sistema
                WHERE clave IN (
                    'empresa_nombre',
                    'empresa_ruc',
                    'empresa_direccion',
                    'empresa_telefono',
                    'empresa_email'
                )
            """)
            config_rows = cursor.fetchall()

        config = {item["clave"]: item["valor"] for item in config_rows}

        buffer = BytesIO()

        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=1.5 * cm,
            leftMargin=1.5 * cm,
            topMargin=1.5 * cm,
            bottomMargin=1.5 * cm
        )

        styles = getSampleStyleSheet()

        title_style = ParagraphStyle(
            "TitleStyle",
            parent=styles["Title"],
            fontName="Helvetica-Bold",
            fontSize=18,
            textColor=colors.HexColor("#0f766e"),
            alignment=1,
            spaceAfter=12
        )

        subtitle_style = ParagraphStyle(
            "SubtitleStyle",
            parent=styles["Normal"],
            fontSize=9,
            textColor=colors.HexColor("#475569"),
            leading=12
        )

        normal_style = ParagraphStyle(
            "NormalCustom",
            parent=styles["Normal"],
            fontSize=9,
            leading=12
        )

        elements = []

        empresa_nombre = config.get("empresa_nombre", "ROPUSAC - Robinson Puse S.A.C.")
        empresa_ruc = config.get("empresa_ruc", "")
        empresa_direccion = config.get("empresa_direccion", "")
        empresa_telefono = config.get("empresa_telefono", "")
        empresa_email = config.get("empresa_email", "")

        elements.append(Paragraph("COTIZACIÓN", title_style))
        elements.append(Spacer(1, 8))

        empresa_data = [
            [
                Paragraph(
                    f"<b>{empresa_nombre}</b><br/>"
                    f"RUC: {empresa_ruc or '-'}<br/>"
                    f"Dirección: {empresa_direccion or '-'}<br/>"
                    f"Teléfono: {empresa_telefono or '-'}<br/>"
                    f"Correo: {empresa_email or '-'}",
                    subtitle_style
                ),
                Paragraph(
                    f"<b>Código:</b> {cotizacion['codigo']}<br/>"
                    f"<b>Fecha emisión:</b> {cotizacion['fecha_emision']}<br/>"
                    f"<b>Fecha vencimiento:</b> {cotizacion['fecha_vencimiento'] or '-'}<br/>"
                    f"<b>Moneda:</b> {cotizacion['moneda']}<br/>"
                    f"<b>Estado:</b> {cotizacion['estado'].capitalize()}",
                    subtitle_style
                )
            ]
        ]

        empresa_table = Table(empresa_data, colWidths=[10 * cm, 7 * cm])
        empresa_table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
            ("PADDING", (0, 0), (-1, -1), 8),
        ]))

        elements.append(empresa_table)
        elements.append(Spacer(1, 14))

        cliente_data = [
            [
                Paragraph(
                    f"<b>Cliente:</b> {cotizacion['cliente']}<br/>"
                    f"<b>{cotizacion['tipo_documento']}:</b> {cotizacion['numero_documento'] or '-'}<br/>"
                    f"<b>Contacto:</b> {cotizacion['contacto'] or '-'}<br/>"
                    f"<b>Teléfono:</b> {cotizacion['cliente_telefono'] or '-'}<br/>"
                    f"<b>Correo:</b> {cotizacion['cliente_email'] or '-'}<br/>"
                    f"<b>Dirección:</b> {cotizacion['cliente_direccion'] or '-'}",
                    subtitle_style
                )
            ]
        ]

        cliente_table = Table(cliente_data, colWidths=[17 * cm])
        cliente_table.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
            ("BACKGROUND", (0, 0), (-1, -1), colors.white),
            ("PADDING", (0, 0), (-1, -1), 8),
        ]))

        elements.append(cliente_table)
        elements.append(Spacer(1, 14))

        detalle_data = [
            [
                "Item",
                "Descripción",
                "Unidad",
                "Cant.",
                "P. Unit.",
                "Desc. %",
                "Subtotal"
            ]
        ]

        for index, item in enumerate(detalles, start=1):
            detalle_data.append([
                str(index),
                Paragraph(item["descripcion_producto"], normal_style),
                item["unidad"] or "-",
                f"{float(item['cantidad']):.2f}",
                formato_monto(item["precio_unitario"]),
                f"{float(item['descuento_porcentaje']):.2f}%",
                formato_monto(item["subtotal"])
            ])

        detalle_table = Table(
            detalle_data,
            colWidths=[
                1.2 * cm,
                6.5 * cm,
                1.7 * cm,
                1.7 * cm,
                2.2 * cm,
                1.8 * cm,
                2.4 * cm
            ]
        )

        detalle_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f766e")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("ALIGN", (0, 0), (0, -1), "CENTER"),
            ("ALIGN", (2, 1), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
            ("PADDING", (0, 0), (-1, -1), 5),
        ]))

        elements.append(detalle_table)
        elements.append(Spacer(1, 14))

        totales_data = [
            ["Subtotal", formato_monto(cotizacion["subtotal"])],
            ["Descuento total", formato_monto(cotizacion["descuento_total"])],
            [f"IGV {float(cotizacion['igv_porcentaje']):.2f}%", formato_monto(cotizacion["igv"])],
            ["Total", formato_monto(cotizacion["total"])],
        ]

        totales_table = Table(totales_data, colWidths=[4 * cm, 4 * cm], hAlign="RIGHT")
        totales_table.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
            ("BACKGROUND", (0, 3), (-1, 3), colors.HexColor("#0f766e")),
            ("TEXTCOLOR", (0, 3), (-1, 3), colors.white),
            ("FONTNAME", (0, 3), (-1, 3), "Helvetica-Bold"),
            ("ALIGN", (1, 0), (1, -1), "RIGHT"),
            ("PADDING", (0, 0), (-1, -1), 7),
        ]))

        elements.append(totales_table)
        elements.append(Spacer(1, 14))

        if cotizacion["observaciones"]:
            elements.append(Paragraph(f"<b>Observaciones:</b> {cotizacion['observaciones']}", normal_style))
            elements.append(Spacer(1, 8))

        if cotizacion["condiciones"]:
            elements.append(Paragraph(f"<b>Condiciones:</b> {cotizacion['condiciones']}", normal_style))
            elements.append(Spacer(1, 8))

        elements.append(Spacer(1, 20))
        elements.append(Paragraph(f"<b>Vendedor:</b> {cotizacion['vendedor'] or '-'}", normal_style))

        doc.build(elements)

        buffer.seek(0)

        return send_file(
            buffer,
            mimetype="application/pdf",
            as_attachment=True,
            download_name=f"{cotizacion['codigo']}.pdf"
        )

    finally:
        connection.close()
# Modulo Catalogo
@vendedor_bp.route("/catalogo")
@login_required
@rol_required("vendedor")
def catalogo():
    buscar = request.args.get("buscar", "").strip()
    categoria_id = request.args.get("categoria_id", "").strip()
    stock = request.args.get("stock", "").strip()

    filtros = ["p.estado = 'activo'"]
    parametros = []

    if buscar:
        filtros.append("""
            (
                p.codigo LIKE %s
                OR p.nombre LIKE %s
                OR p.marca LIKE %s
                OR p.modelo LIKE %s
                OR cp.nombre LIKE %s
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

            sql_productos = f"""
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
                    cp.nombre AS categoria,
                    um.abreviatura AS unidad,

                    (
                        SELECT pr.razon_social
                        FROM producto_proveedor pp
                        INNER JOIN proveedores pr ON pp.proveedor_id = pr.id
                        WHERE pp.producto_id = p.id
                        AND pp.estado = 'activo'
                        AND pr.estado = 'activo'
                        ORDER BY pp.costo_unitario ASC
                        LIMIT 1
                    ) AS proveedor_recomendado,

                    (
                        SELECT pp.disponibilidad
                        FROM producto_proveedor pp
                        INNER JOIN proveedores pr ON pp.proveedor_id = pr.id
                        WHERE pp.producto_id = p.id
                        AND pp.estado = 'activo'
                        AND pr.estado = 'activo'
                        ORDER BY pp.costo_unitario ASC
                        LIMIT 1
                    ) AS disponibilidad,

                    (
                        SELECT pp.tiempo_entrega_dias
                        FROM producto_proveedor pp
                        INNER JOIN proveedores pr ON pp.proveedor_id = pr.id
                        WHERE pp.producto_id = p.id
                        AND pp.estado = 'activo'
                        AND pr.estado = 'activo'
                        ORDER BY pp.costo_unitario ASC
                        LIMIT 1
                    ) AS tiempo_entrega_dias

                FROM productos p
                LEFT JOIN categorias_productos cp ON p.categoria_id = cp.id
                LEFT JOIN unidades_medida um ON p.unidad_id = um.id
                {where_sql}
                ORDER BY p.nombre ASC
            """

            cursor.execute(sql_productos, tuple(parametros))
            productos = cursor.fetchall()

            sql_resumen = f"""
                SELECT
                    COUNT(p.id) AS total_productos,
                    IFNULL(SUM(CASE WHEN p.stock_actual > p.stock_minimo THEN 1 ELSE 0 END), 0) AS disponibles,
                    IFNULL(SUM(CASE WHEN p.stock_actual <= p.stock_minimo AND p.stock_actual > 0 THEN 1 ELSE 0 END), 0) AS stock_bajo,
                    IFNULL(SUM(CASE WHEN p.stock_actual = 0 THEN 1 ELSE 0 END), 0) AS agotados
                FROM productos p
                LEFT JOIN categorias_productos cp ON p.categoria_id = cp.id
                {where_sql}
            """

            cursor.execute(sql_resumen, tuple(parametros))
            resumen = cursor.fetchone()

        return render_template(
            "vendedor/catalogo.html",
            productos=productos,
            categorias=categorias,
            resumen=resumen,
            filtros={
                "buscar": buscar,
                "categoria_id": categoria_id,
                "stock": stock
            }
        )

    finally:
        connection.close()


@vendedor_bp.route("/catalogo/<int:producto_id>")
@login_required
@rol_required("vendedor")
def detalle_producto_catalogo(producto_id):
    connection = get_db_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute("""
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
                    cp.nombre AS categoria,
                    um.nombre AS unidad_nombre,
                    um.abreviatura AS unidad
                FROM productos p
                LEFT JOIN categorias_productos cp ON p.categoria_id = cp.id
                LEFT JOIN unidades_medida um ON p.unidad_id = um.id
                WHERE p.id = %s
                AND p.estado = 'activo'
                LIMIT 1
            """, (producto_id,))
            producto = cursor.fetchone()

            if not producto:
                flash("El producto no existe o no está activo.", "danger")
                return redirect(url_for("vendedor.catalogo"))

            cursor.execute("""
                SELECT
                    pr.razon_social AS proveedor,
                    pr.ruc,
                    pp.codigo_proveedor,
                    pp.disponibilidad,
                    pp.tiempo_entrega_dias,
                    pp.fecha_actualizacion,
                    pp.observacion
                FROM producto_proveedor pp
                INNER JOIN proveedores pr ON pp.proveedor_id = pr.id
                WHERE pp.producto_id = %s
                AND pp.estado = 'activo'
                AND pr.estado = 'activo'
                ORDER BY pp.tiempo_entrega_dias ASC, pr.razon_social ASC
            """, (producto_id,))
            proveedores = cursor.fetchall()

        return render_template(
            "vendedor/detalle_producto_catalogo.html",
            producto=producto,
            proveedores=proveedores
        )

    finally:
        connection.close()