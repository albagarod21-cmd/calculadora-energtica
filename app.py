import io
from datetime import datetime

import streamlit as st
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet


# ============================================================
# FORMATO FIJO DEL INFORME
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
# FUNCIONES
# ============================================================

def parsear_precios_electricidad(texto):
    """
    Lee la tabla pegada por el usuario:
    Valle 0,102184318
    Llano 0,111051511
    Punta 0,178221335
    """
    precios = {
        "Precio energía PUNTA": "",
        "Precio energía LLANO": "",
        "Precio energía VALLE": "",
    }

    for linea in texto.splitlines():
        partes = linea.replace("\t", " ").split()
        if len(partes) < 2:
            continue

        nombre = partes[0].strip().lower()
        valor = partes[-1].strip().replace(",", ".")

        if "punta" in nombre:
            precios["Precio energía PUNTA"] = valor
        elif "llano" in nombre:
            precios["Precio energía LLANO"] = valor
        elif "valle" in nombre:
            precios["Precio energía VALLE"] = valor

    return precios


def actualizar_tabla(tabla_base, valores):
    tabla_final = []

    for campo, valor, unidad in tabla_base:
        nuevo_valor = valores.get(campo, valor)
        tabla_final.append((campo, nuevo_valor, unidad))

    return tabla_final


def crear_tabla_pdf(titulo, filas):
    styles = getSampleStyleSheet()

    elementos = [
        Paragraph(titulo, styles["Heading2"]),
        Spacer(1, 0.15 * cm),
    ]

    data = [["Campo", "Valor", "Unidad"]]
    for campo, valor, unidad in filas:
        data.append([campo, valor, unidad])

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


# ============================================================
# APP STREAMLIT
# ============================================================

st.set_page_config(
    page_title="Calculadora Energética",
    layout="wide",
)

st.title("Generador de informe - Calculadora Energética")

st.write(
    "Esta primera versión genera el PDF con la estructura fija. "
    "De momento introducimos manualmente los valores variables para comprobar que el formato es correcto."
)

st.subheader("Electricidad")

precio_potencia_punta = st.text_input("Precio potencia PUNTA", value="27.704413")
precio_potencia_valle = st.text_input("Precio potencia VALLE", value="0.725423")
precio_alquiler_contadores = st.text_input("Precio alquiler contadores", value="0.81")

tabla_precios = st.text_area(
    "Precios energía eléctrica",
    value="Valle\t0,102184318\nLlano\t0,111051511\nPunta\t0,178221335",
    height=120,
)

st.subheader("Gas")

tur1_fijo = st.text_input("TUR 1 término fijo", value="3.93")
tur2_fijo = st.text_input("TUR 2 término fijo", value="8.11")
tur1_variable = st.text_input("TUR 1 término variable", value="3.822924")
tur2_variable = st.text_input("TUR 2 término variable", value="3.613034")
alquiler_gas = st.text_input("TUR 1 y TUR 2 alquiler equipos", value="0.58")

st.subheader("Gasóleo")

precio_gasoleo = st.text_input("Precio medio nacional", value="11.69")

if st.button("Generar informe PDF"):
    precios_energia = parsear_precios_electricidad(tabla_precios)

    valores_electricidad = {
        "Precio potencia PUNTA": precio_potencia_punta,
        "Precio potencia VALLE": precio_potencia_valle,
        "Precio energía PUNTA": precios_energia["Precio energía PUNTA"],
        "Precio energía LLANO": precios_energia["Precio energía LLANO"],
        "Precio energía VALLE": precios_energia["Precio energía VALLE"],
        "Precio alquiler contadores": precio_alquiler_contadores,
    }

    valores_gas = {
        "TUR 1 término fijo": tur1_fijo,
        "TUR 2 término fijo": tur2_fijo,
        "TUR 1 término variable": tur1_variable,
        "TUR 2 término variable": tur2_variable,
        "TUR 1 alquiler equipos": alquiler_gas,
        "TUR 2 alquiler equipos": alquiler_gas,
    }

    valores_gasoleo = {
        "Precio medio nacional": precio_gasoleo,
    }

    datos = {
        "Electricidad": actualizar_tabla(ELECTRICIDAD, valores_electricidad),
        "Gas": actualizar_tabla(GAS, valores_gas),
        "Gasóleo": actualizar_tabla(GASOLEO, valores_gasoleo),
    }

    pdf = generar_pdf(datos)

    st.success("Informe generado correctamente.")

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
