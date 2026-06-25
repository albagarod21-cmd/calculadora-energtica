import io
import re

import pdfplumber
import requests
import streamlit as st
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle


# ============================================================
# ESTRUCTURA FIJA DEL INFORME
# ============================================================

ELECTRICIDAD = [
    ("Factor conversor a energía final", "1.954", "-"),
    ("IVA", "21", "%"),
    ("IGIC Reducido", "3", "%"),
    ("IGIC General", "7", "%"),
    ("Porcentaje energía PUNTA", "33.45", "%"),
    ("Porcentaje energía LLANO", "33.13", "%"),
    ("Porcentaje energía VALLE", "33.41", "%"),
    ("Impuesto electricidad", "5.11", "%"),
    ("Precio potencia PUNTA", "", "€/kW año"),
    ("Precio potencia VALLE", "", "€/kW año"),
    ("Precio energía PUNTA", "", "€/kWh"),
    ("Precio energía LLANO", "", "€/kWh"),
    ("Precio energía VALLE", "", "€/kWh"),
    ("Precio alquiler contadores", "", "€/mes"),
]

GAS = [
    ("Factor conversor a energía final", "1.19", "-"),
    ("Impuesto hidrocarburos", "0.00234", "€/kWh"),
    ("IVA", "21", "%"),
    ("IGIC Reducido", "3", "%"),
    ("IGIC General", "7", "%"),
    ("TUR 1 término fijo", "", "(€/cliente)/mes"),
    ("TUR 2 término fijo", "", "(€/cliente)/mes"),
    ("TUR 1 término variable", "", "cent/kWh"),
    ("TUR 2 término variable", "", "cent/kWh"),
    ("TUR 1 alquiler equipos", "", "€/mes"),
    ("TUR 2 alquiler equipos", "", "€/mes"),
]

GASOLEO = [
    ("Factor conversor a energía final", "1.179", "-"),
    ("Precio medio nacional", "", "c€/kWh"),
]


# ============================================================
# UTILIDADES
# ============================================================

def normalizar_texto(texto):
    if texto is None:
        return ""
    return str(texto).replace("\n", " ").strip()


def convertir_numero(texto):
    """
    Convierte valores tipo 3,93 / 23,324952 / 1.234,56 a float.
    """
    texto = str(texto).strip()
    texto = texto.replace("€", "")
    texto = texto.replace("%", "")
    texto = texto.replace(" ", "")

    # Si hay coma, asumimos coma decimal y quitamos puntos de miles.
    if "," in texto:
        texto = texto.replace(".", "")
        texto = texto.replace(",", ".")

    return float(texto)


def formatear_valor(valor):
    """
    Mantiene formato estable en el PDF.
    """
    if valor in ["", None]:
        return "NO_ENCONTRADO"

    if isinstance(valor, str):
        return valor

    if isinstance(valor, float):
        return f"{valor:.9f}".rstrip("0").rstrip(".")

    return str(valor)


def extraer_numeros(texto):
    texto = normalizar_texto(texto)
    encontrados = re.findall(r"\d+(?:[.,]\d+)?", texto)
    numeros = []

    for item in encontrados:
        try:
            numeros.append(convertir_numero(item))
        except ValueError:
            pass

    return numeros


def descargar_pdf(url):
    respuesta = requests.get(url, timeout=60)
    respuesta.raise_for_status()
    return respuesta.content


def leer_pdf(pdf_bytes):
    texto_total = []
    tablas = []

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for pagina in pdf.pages:
            texto_total.append(pagina.extract_text() or "")
            tablas_pagina = pagina.extract_tables() or []
            tablas.extend(tablas_pagina)

    return "\n".join(texto_total), tablas


def fila_texto(fila):
    return " ".join(normalizar_texto(celda) for celda in fila)


# ============================================================
# EXTRACCION PDF TARIFAS REGULADAS
# ============================================================

def extraer_potencia(tablas, periodo):
    """
    periodo = P1 para punta
    periodo = P2 para valle

    Regla:
    tabla baja tensión 2.0TD, potencia <= 15 kW,
    fila P1/P2, suma de peaje transporte y distribución + cargos.
    """
    for tabla in tablas:
        texto_tabla = " ".join(fila_texto(fila) for fila in tabla).lower()

        if "2.0td" not in texto_tabla:
            continue

        for fila in tabla:
            texto = fila_texto(fila)
            texto_lower = texto.lower()

            if re.search(rf"\b{periodo.lower()}\b", texto_lower):
                numeros = []

                for celda in fila:
                    celda_txt = normalizar_texto(celda)

                    # Evitar que 2.0TD o 15 kW entren como valores de cálculo.
                    if "2.0" in celda_txt or "15" == celda_txt.strip():
                        continue

                    numeros.extend(extraer_numeros(celda_txt))

                candidatos = [n for n in numeros if 0 <= n < 100]

                if len(candidatos) >= 2:
                    return candidatos[0] + candidatos[1]

    return "NO_ENCONTRADO"


def extraer_alquiler_contador_electrico(tablas, texto):
    """
    Tabla alquiler de contadores.
    Fila:
    Contadores monofásicos con discriminación horaria y con posibilidad de telegestión
    para consumidores domésticos.
    """
    claves = [
        "contadores monof",
        "discriminaci",
        "telegesti",
        "domest",
    ]

    for tabla in tablas:
        for fila in tabla:
            texto_fila = fila_texto(fila).lower()

            if all(clave in texto_fila for clave in claves):
                numeros = extraer_numeros(texto_fila)
                candidatos = [n for n in numeros if 0 < n < 10]

                if candidatos:
                    return candidatos[-1]

    # Respaldo
    texto_lower = texto.lower()
    if "telegest" in texto_lower:
        coincidencias = re.findall(r"\b0[,.]81\b", texto_lower)
        if coincidencias:
            return convertir_numero(coincidencias[0])

    return "NO_ENCONTRADO"


def extraer_tur_gas(tablas):
    resultado = {
        "TUR 1 término fijo": "NO_ENCONTRADO",
        "TUR 2 término fijo": "NO_ENCONTRADO",
        "TUR 1 término variable": "NO_ENCONTRADO",
        "TUR 2 término variable": "NO_ENCONTRADO",
    }

    for tabla in tablas:
        for fila in tabla:
            texto = fila_texto(fila).lower()

            if "tur" not in texto:
                continue

            numeros = []
            for celda in fila:
                numeros.extend(extraer_numeros(celda))

            candidatos = [n for n in numeros if 0 < n < 100]

            if len(candidatos) < 2:
                continue

            if re.search(r"tur\.?\s*1", texto) and ("5.000" in texto or "5000" in texto):
                resultado["TUR 1 término fijo"] = candidatos[0]
                resultado["TUR 1 término variable"] = candidatos[1]

            elif re.search(r"tur\.?\s*2", texto) and ("15.000" in texto or "15000" in texto):
                resultado["TUR 2 término fijo"] = candidatos[0]
                resultado["TUR 2 término variable"] = candidatos[1]

    return resultado


def extraer_alquiler_gas(tablas, texto):
    """
    Apartado alquiler de contadores.
    Fila 6 < Q <= 10 m3/hora.
    """
    for tabla in tablas:
        for fila in tabla:
            texto_fila = fila_texto(fila).lower()
            texto_limpio = texto_fila.replace(" ", "")

            if "6<q" in texto_limpio and "10" in texto_limpio:
                numeros = extraer_numeros(texto_fila)
                candidatos = [n for n in numeros if 0 < n < 10]

                if candidatos:
                    valor = candidatos[-1]
                    return valor, valor

    # Respaldo
    coincidencias = re.findall(r"\b0[,.]58\b", texto.lower())
    if coincidencias:
        valor = convertir_numero(coincidencias[0])
        return valor, valor

    return "NO_ENCONTRADO", "NO_ENCONTRADO"


# ============================================================
# EXTRACCION PDF COMBUSTIBLES
# ============================================================

def extraer_gasoleo_c(tablas, texto):
    """
    Apartado precios energéticos liberalizados,
    carburantes y productos petrolíferos,
    fila Gasóleo C, columna c€/kWh.
    """
    for tabla in tablas:
        for fila in tabla:
            texto_fila = fila_texto(fila).lower()

            if "gasóleo c" in texto_fila or "gasoleo c" in texto_fila:
                numeros = extraer_numeros(texto_fila)

                # En la fila puede haber varios precios. El c€/kWh suele ser un valor en rango 1-50.
                candidatos = [n for n in numeros if 1 <= n <= 50]

                if candidatos:
                    return candidatos[-1]

    # Respaldo por texto plano
    texto_lineal = re.sub(r"\s+", " ", texto)
    patron = r"Gas[oó]leo\s*C.*?(\d+[,.]\d+)"
    match = re.search(patron, texto_lineal, flags=re.IGNORECASE)

    if match:
        return convertir_numero(match.group(1))

    return "NO_ENCONTRADO"


# ============================================================
# TABLA PEGADA DE PRECIOS ELECTRICOS
# ============================================================

def parsear_precios_electricos(texto):
    resultado = {
        "Precio energía PUNTA": "NO_ENCONTRADO",
        "Precio energía LLANO": "NO_ENCONTRADO",
        "Precio energía VALLE": "NO_ENCONTRADO",
    }

    for linea in texto.splitlines():
        linea_l = linea.lower().strip()

        if not linea_l:
            continue

        numeros = extraer_numeros(linea)

        if not numeros:
            continue

        valor = numeros[-1]

        if "punta" in linea_l:
            resultado["Precio energía PUNTA"] = valor
        elif "llano" in linea_l:
            resultado["Precio energía LLANO"] = valor
        elif "valle" in linea_l:
            resultado["Precio energía VALLE"] = valor

    return resultado


# ============================================================
# GENERACION DE DATOS
# ============================================================

def completar_tabla(tabla_base, valores):
    filas = []

    for campo, valor_fijo, unidad in tabla_base:
        valor = valores.get(campo, valor_fijo)
        filas.append((campo, formatear_valor(valor), unidad))

    return filas


def construir_datos(url_tarifas, url_combustibles, tabla_precios):
    pdf_tarifas = descargar_pdf(url_tarifas)
    texto_tarifas, tablas_tarifas = leer_pdf(pdf_tarifas)

    pdf_combustibles = descargar_pdf(url_combustibles)
    texto_combustibles, tablas_combustibles = leer_pdf(pdf_combustibles)

    precios_electricos = parsear_precios_electricos(tabla_precios)

    tur_gas = extraer_tur_gas(tablas_tarifas)
    alquiler_gas_1, alquiler_gas_2 = extraer_alquiler_gas(tablas_tarifas, texto_tarifas)

    valores_electricidad = {
        "Precio potencia PUNTA": extraer_potencia(tablas_tarifas, "P1"),
        "Precio potencia VALLE": extraer_potencia(tablas_tarifas, "P2"),
        "Precio energía PUNTA": precios_electricos["Precio energía PUNTA"],
        "Precio energía LLANO": precios_electricos["Precio energía LLANO"],
        "Precio energía VALLE": precios_electricos["Precio energía VALLE"],
        "Precio alquiler contadores": extraer_alquiler_contador_electrico(tablas_tarifas, texto_tarifas),
    }

    valores_gas = {
        "TUR 1 término fijo": tur_gas["TUR 1 término fijo"],
        "TUR 2 término fijo": tur_gas["TUR 2 término fijo"],
        "TUR 1 término variable": tur_gas["TUR 1 término variable"],
        "TUR 2 término variable": tur_gas["TUR 2 término variable"],
        "TUR 1 alquiler equipos": alquiler_gas_1,
        "TUR 2 alquiler equipos": alquiler_gas_2,
    }

    valores_gasoleo = {
        "Precio medio nacional": extraer_gasoleo_c(tablas_combustibles, texto_combustibles),
    }

    return {
        "Electricidad": completar_tabla(ELECTRICIDAD, valores_electricidad),
        "Gas": completar_tabla(GAS, valores_gas),
        "Gasóleo": completar_tabla(GASOLEO, valores_gasoleo),
    }


# ============================================================
# PDF
# ============================================================

def crear_tabla_pdf(titulo, filas):
    styles = getSampleStyleSheet()

    elementos = [
        Paragraph(titulo, styles["Heading2"]),
        Spacer(1, 0.15 * cm),
    ]

    data = [["Campo", "Valor", "Unidad"]]
    data.extend(filas)

    tabla = Table(data, colWidths=[9.2 * cm, 4 * cm, 4 * cm])

    tabla.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E6E6E6")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("ALIGN", (1, 1), (1, -1), "RIGHT"),
                ("ALIGN", (2, 1), (2, -1), "CENTER"),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#BDBDBD")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8F8F8")]),
            ]
        )
    )

    elementos.append(tabla)
    elementos.append(Spacer(1, 0.6 * cm))

    return elementos


def generar_pdf(datos):
    buffer = io.BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=1.5 * cm,
        leftMargin=1.5 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm,
        title="Informe Calculadora Energética",
    )

    styles = getSampleStyleSheet()

    elementos = [
        Paragraph("Informe Calculadora Energética", styles["Title"]),
        Spacer(1, 0.4 * cm),
    ]

    elementos.extend(crear_tabla_pdf("Electricidad", datos["Electricidad"]))
    elementos.extend(crear_tabla_pdf("Gas", datos["Gas"]))
    elementos.extend(crear_tabla_pdf("Gasóleo", datos["Gasóleo"]))

    doc.build(elementos)
    buffer.seek(0)

    return buffer


def detectar_faltantes(datos):
    faltantes = []

    for bloque, filas in datos.items():
        for campo, valor, unidad in filas:
            if valor == "NO_ENCONTRADO":
                faltantes.append(f"{bloque} - {campo}")

    return faltantes


# ============================================================
# STREAMLIT
# ============================================================

st.set_page_config(
    page_title="Generador informe Calculadora Energética",
    layout="wide",
)

st.title("Generador de informe - Calculadora Energética")

st.write(
    "Introduce los enlaces de IDAE y la tabla de precios eléctricos. "
    "La app generará el PDF con el formato fijo de la plataforma."
)

st.subheader("1. Enlaces")

url_tarifas = st.text_input(
    "PDF IDAE - Tarifas Reguladas",
    value="https://www.idae.es/sites/default/files/estudios_informes_y_estadisticas/Tarifas_Reguladas_ene_2026.pdf",
)

url_combustibles = st.text_input(
    "PDF IDAE - Combustibles y carburantes",
    value="https://www.idae.es/sites/default/files/estudios_informes_y_estadisticas/Combustibles_y_carburantes_abr2026.pdf",
)

st.subheader("2. Tabla de precios eléctricos")

tabla_precios = st.text_area(
    "Pega aquí la tabla Valle / Llano / Punta",
    value="Valle\t0,102184318\nLlano\t0,111051511\nPunta\t0,178221335",
    height=120,
)

st.subheader("3. Generar informe")
st.subheader("Depuración")

mostrar_debug = st.checkbox("Mostrar tablas extraídas de los PDFs")

if st.button("Generar informe PDF"):
    try:
        with st.spinner("Leyendo PDFs, extrayendo datos y generando informe..."):
            datos = construir_datos(url_tarifas, url_combustibles, tabla_precios)
            if mostrar_debug:
    pdf_tarifas_debug = descargar_pdf(url_tarifas)
    texto_tarifas_debug, tablas_tarifas_debug = leer_pdf(pdf_tarifas_debug)

    pdf_combustibles_debug = descargar_pdf(url_combustibles)
    texto_combustibles_debug, tablas_combustibles_debug = leer_pdf(pdf_combustibles_debug)

    st.markdown("### Tablas detectadas en Tarifas Reguladas")
    for i, tabla in enumerate(tablas_tarifas_debug):
        st.write(f"Tabla {i + 1}")
        st.dataframe(tabla)

    st.markdown("### Tablas detectadas en Combustibles")
    for i, tabla in enumerate(tablas_combustibles_debug):
        st.write(f"Tabla {i + 1}")
        st.dataframe(tabla)
            faltantes = detectar_faltantes(datos)
            pdf = generar_pdf(datos)

        st.success("Informe generado correctamente.")

        if faltantes:
            st.warning("Algunos valores no se han encontrado. El formato del PDF se mantiene, pero revisa estos campos:")
            for item in faltantes:
                st.write(f"- {item}")

        st.download_button(
            label="Descargar informe PDF",
            data=pdf,
            file_name="informe_calculadora_energetica.pdf",
            mime="application/pdf",
        )

        st.subheader("Vista previa")

        for bloque, filas in datos.items():
            st.markdown(f"### {bloque}")
            st.dataframe(
                [{"Campo": campo, "Valor": valor, "Unidad": unidad} for campo, valor, unidad in filas],
                use_container_width=True,
                hide_index=True,
            )

    except Exception as error:
        st.error("No se pudo generar el informe.")
        st.exception(error)
