import streamlit as st
import pandas as pd
from influxdb import InfluxDBClient
import plotly.express as px
import plotly.graph_objects as go
import numpy as np
import datetime
from weasyprint import HTML
import os
import json

# --- CONFIGURACIÓN DE LA PÁGINA ---
st.set_page_config(page_title="TFM - Gestión de Demanda", layout="wide")

# --- 2. CONTROL DE SESIÓN (LOGIN DEMO) ---
if 'login_completed' not in st.session_state:
    st.session_state['login_completed'] = False
if 'username' not in st.session_state:
    st.session_state['username'] = "alejandro"
if 'vista_actual' not in st.session_state:
    st.session_state['vista_actual'] = "menu"  # Puede ser "menu" o "dashboard"
if 'pestaña_activa' not in st.session_state:
    st.session_state['pestaña_activa'] = 0  # Índice de la pestaña seleccionada (0 a 3)

# --- Guía de estilos para la app
st.markdown("""
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        /* Ocultar la barra superior de Streamlit */
        header {visibility: hidden;}
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        
        /* Ajustar el padding para que no quede espacio arriba */
        .block-container {
            padding-top: 1rem;
            padding-bottom: 1rem;
            padding-left: 1rem;
            padding-right: 1rem;
        }
        /* Estilo premium para el formulario nativo */
        [data-testid="stForm"] {
            border: 1px solid var(--border-color) !important;
            border-radius: 16px !important;
            padding: 30px !important;
            box-shadow: 0 10px 25px rgba(0,0,0,0.15) !important;
            background-color: var(--secondary-background-color) !important;
            color: var(--text-color) !important;
            border-top: 5px solid #3b82f6 !important;
        }
        
        /* Configuración de Flexbox vinculada a las llaves nativas de Streamlit */
        div.st-key-btn_mon button, 
        div.st-key-btn_ene button, 
        div.st-key-btn_rec button, 
        div.st-key-btn_per button, 
        div.st-key-btn_res button {
            display: flex !important;
            align-items: center !important;
            justify-content: space-between !important;
            text-align: left !important;
            padding-left: 20px !important;
            padding-right: 25px !important;
            height: 120px !important; 
            font-weight: bold !important; 
            font-size: 16px !important; 
            border-radius: 12px !important;
            color: white !important;
        }

        /* Colores de fondo aplicados mediante selectores de clave */
        div.st-key-btn_mon button { background-color: #ef4444 !important; }
        div.st-key-btn_ene button { background-color: #f97316 !important; }
        div.st-key-btn_rec button { background-color: #10b981 !important; }
        div.st-key-btn_per button { background-color: #3b82f6 !important; }
        div.st-key-btn_res button { background-color: #8b5cf6 !important; }

        /* Inyección de iconos Font Awesome en el lado derecho mediante pseudoelementos */
        div.st-key-btn_mon button::after {
            content: "\f017" !important; /* Clock */
            font-family: "Font Awesome 6 Free" !important;
            font-weight: 900 !important;
            font-size: 26px !important;
        }
        div.st-key-btn_ene button::after {
            content: "\f080" !important; /* Chart Bar */
            font-family: "Font Awesome 6 Free" !important;
            font-weight: 900 !important;
            font-size: 26px !important;
        }
        div.st-key-btn_rec button::after {
            content: "\f0eb" !important; /* Lightbulb */
            font-family: "Font Awesome 6 Free" !important;
            font-weight: 900 !important;
            font-size: 26px !important;
        }
        div.st-key-btn_per button::after {
            content: "\f007" !important; /* User */
            font-family: "Font Awesome 6 Free" !important;
            font-weight: 900 !important;
            font-size: 26px !important;
        }
        div.st-key-btn_res button::after {
            content: "\f15c" !important; /* File Lines */
            font-family: "Font Awesome 6 Free" !important;
            font-weight: 900 !important;
            font-size: 26px !important;
        }
    </style>
    """, unsafe_allow_html=True)

# --- PARÁMETROS ---
PRECIO_KWH = 0.147653  # Coste de la energía según útlima factura eléctrica 
PRECIO_EXC = 0.050000 # Compensación de excedentes a 0,05€/kWh, basado en tarifa de contador virutal de Endesa
FACTOR_SOLAR = 0.4  # De 5kWp (CSV) a 2kWp (Tu parte de comunidad)
CSV_SOLAR = 'Timeseries_28.482_-16.306_SA3_5kWp_crystSi_14_26deg_-1deg_2023_2023.csv'

# --- CONEXIÓN A INFLUXDB ---
client = InfluxDBClient(host='influx_db', port=8086)
db_name = 'tfm_energia'
ahora_canarias = pd.Timestamp.now(tz='Atlantic/Canary')
@st.cache_data
def load_solar_pvgis():
    """Carga y procesa el CSV de PVGIS con gestión de zona horaria."""
    if not os.path.exists(CSV_SOLAR):
        return None
    try:
        df = pd.read_csv(CSV_SOLAR, skiprows=10, skipfooter=10, engine='python')
        df['time'] = pd.to_datetime(df['time'], format='%Y%m%d:%H%M')
        
        # PASO CRUCIAL: Localizar en UTC y convertir a Canarias (gestiona el horario de verano)
        df['time'] = df['time'].dt.tz_localize('UTC').dt.tz_convert('Atlantic/Canary')
        
        df['P_solar'] = df['P'] * FACTOR_SOLAR
        return df
    except:
        return None

def get_real_data():
    try:
        query = 'SELECT last("value") FROM "potencia_activa_w" WHERE "canal"=\'0\''
        result = client.query(query, database=db_name)
        points = list(result.get_points())
        return points[0]['last'] if points else 0.0
    except:
        return 0.0

def get_max_24h():
    try:
        query = 'SELECT MAX("value") FROM "potencia_activa_w" WHERE "canal"=\'0\' AND time > now() - 24h'
        result = client.query(query, database=db_name)
        points = list(result.get_points())
        return points[0]['max'] if points else 0.0
    except: return 0.0

def get_user_profile(usuario):
    try:
        # La query ahora busca el usuario exacto que ha iniciado sesión
        query = f'SELECT * FROM "perfiles_usuario" WHERE "usuario"=\'{usuario}\' ORDER BY time DESC LIMIT 1'
        result = client.query(query, database=db_name)
        points = list(result.get_points())
        return points[0] if points else None
    except: 
        return None

def save_user_profile(datos):
    json_body = [{"measurement": "perfiles_usuario", "tags": {"usuario": datos['nombre'], "patron": datos['patron']},
                  "fields": {"tiene_ve": bool(datos['tiene_ve']), "tiene_clima": bool(datos['tiene_clima']),
                             "pot_contratada": float(datos['pot_contratada']), "gasto_medio": float(datos['gasto_medio'])}}]
    client.write_points(json_body, database=db_name)

def get_periodo_tarifario(dt):
    """
    Algoritmo de clasificación según la matriz estacional de tarifas de 2026.
    Tipos A, B, B.1, C (L-V) y Tipo D (S-D y Festivos)
    """
    dia_semana = dt.weekday() # 0=Lunes, 6=Domingo
    mes = dt.month
    hora = dt.hour

    # --- TIPO D: Sábados, Domingos y Festivos Nacionales de control ---
    # Nota: Puedes añadir aquí los días festivos fijos si lo requieres para la demo
    festivos_nacionales = [(1, 1), (6, 1), (1, 5), (15, 8), (12, 10), (1, 11), (6, 12), (8, 12), (25, 12)]
    if dia_semana >= 5 or (mes, dt.day) in festivos_nacionales:
        return "P6"

    # --- TRAMOS HORARIOS LABORALES DE LUNES A VIERNES ---
    # Tipo A: Temporada Alta (Julio, Agosto, Septiembre, Octubre)
    if mes in [7, 8, 9, 10]:
        if 10 <= hora < 15 or 18 <= hora < 22: return "P1"
        if 8 <= hora < 10 or 15 <= hora < 18 or 22 <= hora < 24: return "P3"
        return "P6"

    # Tipo B: Temporada Media Alta (Noviembre, Diciembre)
    elif mes in [11, 12]:
        if 10 <= hora < 15 or 18 <= hora < 22: return "P2"
        if 8 <= hora < 10 or 15 <= hora < 18 or 22 <= hora < 24: return "P3"
        return "P6"

    # Tipo B.1: Temporada Media (Enero, Febrero, Marzo)
    elif mes in [1, 2, 3]:
        if 10 <= hora < 15 or 18 <= hora < 22: return "P3"
        if 8 <= hora < 10 or 15 <= hora < 18 or 22 <= hora < 24: return "P4"
        return "P6"

    # Tipo C: Temporada Baja (Abril, Mayo, Junio)
    elif mes in [4, 5, 6]:
        if 10 <= hora < 15 or 18 <= hora < 22: return "P4"
        if 8 <= hora < 10 or 15 <= hora < 18 or 22 <= hora < 24: return "P5"
        return "P6"
        
    return "P6"
def generar_pdf_auditoria(nombre_mes, anio_mes, total_consumido_kwh, total_sc_kwh, total_imp_kwh, total_exp_kwh, factor_ajuste, d_max, v_max_kwh, d_min, v_min_kwh, d_aprov, v_aprov, df_tramos_datos):
    """ Compila los resultados reales expresados en kWh en un PDF estructurado para la memoria """
    tabla_rows_html = ""
    mapa_nombres = {
        "P1": "P1 (Punta Alta)", "P2": "P2 (Punta Media-Alta)", 
        "P3": "P3 (Llano / Punta Media)", "P4": "P4 (Punta Baja / Valle Medio)",
        "P5": "P5 (Llano Bajo)", "P6": "P6 (Valle Continuo / S-D)"
    }
    for _, fila in df_tramos_datos.iterrows():
        nombre_format = mapa_nombres.get(fila['tramo'], fila['tramo'])
        tabla_rows_html += f"<tr><td><strong>{nombre_format}</strong></td><td>{fila['consumo_kwh']:.2f} kWh</td><td>{fila['porcentaje']:.1f} %</td></tr>"

    html_template = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
            @page {{ size: A4; margin: 20mm 15mm; @bottom-right {{ content: "Página " counter(page) " de " counter(pages); font-family: Arial; font-size: 9pt; color: #64748b; }} }}
            body {{ font-family: Arial, sans-serif; color: #1e293b; line-height: 1.5; }}
            .header {{ border-bottom: 3px solid #0284c7; padding-bottom: 10px; margin-bottom: 20px; }}
            .title-box {{ background-color: #f8fafc; border-left: 5px solid #0c4a6e; padding: 15px; margin-bottom: 25px; border: 1px solid #e2e8f0; }}
            .metrics-table {{ width: 100%; display: table; margin-bottom: 25px; }}
            .metric-card {{ display: table-cell; width: 24%; background-color: #f8fafc; border: 1px solid #e2e8f0; padding: 12px; text-align: center; border-radius: 4px; }}
            .metric-label {{ font-size: 8pt; color: #64748b; font-weight: bold; text-transform: uppercase; }}
            .metric-value {{ font-size: 15pt; font-weight: bold; color: #0f172a; margin-top: 5px; }}
            .ext-table {{ width: 100%; display: table; margin-bottom: 25px; }}
            .ext-box {{ display: table-cell; width: 32%; border: 1px solid #e2e8f0; padding: 10px; background-color: #ffffff; border-radius: 4px; }}
            table.data-table {{ width: 100%; border-collapse: collapse; margin-bottom: 20px; }}
            table.data-table th {{ background-color: #0f172a; color: white; padding: 8px; font-size: 9.5pt; text-align: left; }}
            table.data-table td {{ padding: 8px; font-size: 10pt; border-bottom: 1px solid #e2e8f0; }}
            .note {{ background-color: #f0fdf4; border: 1px solid #bbf7d0; padding: 12px; border-radius: 4px; font-size: 9pt; color: #166534; margin-top: 30px; }}
        </style>
    </head>
    <body>
        <div class="header">
            <table style="width:100%;">
                <tr>
                    <td><h2 style="margin:0; color:#0c4a6e;">Comunidad Energética ULL</h2><p style="margin:0; color:#0284c7; font-size:9pt; text-transform:uppercase;">Gestión Activa de la Demanda</p></td>
                    <td style="text-align:right; font-size:9pt; color:#475569;"><strong>Ref:</strong> AUD-REAL-KWH<br><strong>Localización:</strong> La Laguna, Tenerife</td>
                </tr>
            </table>
        </div>
        <div class="title-box">
            <h3 style="margin:0; color:#0c4a6e; font-size:11pt;">INFORME DE AUDITORÍA ENERGÉTICA MENSUAL</h3>
            <p style="margin:5px 0 0 0; font-size:9.5pt;">Periodo analizado: <strong>{nombre_mes} de {anio_mes}</strong></p>
        </div>
        <div class="metrics-table">
            <div class="metric-card" style="border-top: 4px solid #0284c7;"><div class="metric-label">Demanda Total</div><div class="metric-value">{total_consumido_kwh:.2f} kWh</div></div>
            <div style="display:table-cell; width:1%;"></div>
            <div class="metric-card" style="border-top: 4px solid #10b981;"><div class="metric-label">Autoconsumo</div><div class="metric-value">{total_sc_kwh:.2f} kWh</div></div>
            <div style="display:table-cell; width:1%;"></div>
            <div class="metric-card" style="border-top: 4px solid #f97316;"><div class="metric-label">Importado Red</div><div class="metric-value">{total_imp_kwh:.2f} kWh</div></div>
            <div style="display:table-cell; width:1%;"></div>
            <div class="metric-card" style="border-top: 4px solid #8b5cf6;"><div class="metric-label">Ajuste Solar</div><div class="metric-value">{factor_ajuste:.1f} %</div></div>
        </div>
        <h4 style="color:#0c4a6e; border-bottom:1px solid #e2e8f0; padding-bottom:3px;">⚖️ Extremos de Demanda y Eficiencia Colectiva</h4>
        <div class="ext-table">
            <div class="ext-box" style="border-left: 4px solid #ef4444;"><span style="font-size:8.5pt; color:#64748b; font-weight:bold;">🔥 MÁXIMO DIARIO</span><div style="font-size:12pt; font-weight:bold;">{v_max_kwh:.2f} kWh</div><div style="font-size:8pt; color:#64748b;">{d_max}</div></div>
            <div style="display:table-cell; width:1%;"></div>
            <div class="ext-box" style="border-left: 4px solid #3b82f6;"><span style="font-size:8.5pt; color:#64748b; font-weight:bold;">❄️ MÍNIMO DIARIO</span><div style="font-size:12pt; font-weight:bold;">{v_min_kwh:.2f} kWh</div><div style="font-size:8pt; color:#64748b;">{d_min}</div></div>
            <div style="display:table-cell; width:1%;"></div>
            <div class="ext-box" style="border-left: 4px solid #10b981;"><span style="font-size:8.5pt; color:#64748b; font-weight:bold;">⭐ MEJOR APROVECHAMIENTO</span><div style="font-size:12pt; font-weight:bold;">{v_aprov:.1f} %</div><div style="font-size:8pt; color:#64748b;">{d_aprov}</div></div>
        </div>
        <h4 style="color:#0c4a6e; border-bottom:1px solid #e2e8f0; padding-bottom:3px; margin-top:20px;">⏱️ Desglose por Tramos Horarios Consolidados</h4>
        <table class="data-table"><thead><tr><th>Periodo Tarifario</th><th>Energía Absoluta</th><th>Porcentaje</th></tr></thead><tbody>{tabla_rows_html}</tbody></table>
    </body>
    </html>
    """
    return HTML(string=html_template).write_pdf()
# --- CARGA DE LA BASE DE DATOS NILM (TAREA 1) ---
try:
    with open("database_aparatos_nilm.json", "r", encoding="utf-8") as f:
        db_aparatos = json.load(f)
except FileNotFoundError:
    # Fallback de seguridad por si el archivo no estuviera en el servidor de Azure
    db_aparatos = {
        "Horno Eléctrico": {"potencia_w": 2000, "duracion_min": 60, "energia_kwh": 2.0},
        "Lavavajillas": {"potencia_w": 1200, "duracion_min": 60, "energia_kwh": 1.2},
        "Lavadora": {"potencia_w": 600, "duracion_min": 60, "energia_kwh": 0.6}
    }

# --- 4. RENDERIZADO DEL POP-UP DE ACCESO (MOCK) ---
if not st.session_state['login_completed']:
    # Usamos columnas nativas balanceadas para centrar perfectamente el login sin romper el DOM
    col_space_left, col_login_card, col_space_right = st.columns([1, 1.3, 1])
    
    with col_login_card:
        st.write("") # Espaciado vertical superior
        st.write("")
        st.write("")
        
        # Logo institucional centrado
        st.markdown(
            '<div style="text-align: center; margin-bottom: 20px;">'
            '<img src="https://sede.fg.ull.es/assets/images/brands/icono-ull-original.svg" width="220">'
            '</div>', 
            unsafe_allow_html=True
        )
        
        st.markdown('<h3 style="color: #1e3a8a; font-family: sans-serif; margin-bottom: 5px; text-align: center;">Acceso a la App de la Comunidad Energética de la Universidad de La Laguna</h3>', unsafe_allow_html=True)
        st.markdown('<p style="color: #64748b; font-size: 13px; margin-bottom: 25px; text-align: center;">Introduce las credenciales para acceder al sistema.</p>', unsafe_allow_html=True)
        
        # El formulario nativo hereda la clase CSS premium definida en el estilo global
        with st.form("demo_login_form"):
            u_input = st.text_input("Usuario de ejemplo", value="alejandro", placeholder="Introduce tu usuario")
            p_input = st.text_input("Contraseña", type="password", value="tfm2026", placeholder="••••••••")
            btn_entrar = st.form_submit_button("Entrar al Panel", use_container_width=True)
            
            if btn_entrar:
                st.session_state['login_completed'] = True
                st.session_state['username'] = u_input.strip().lower() if u_input else "alejandro"
                st.success(f"¡Acceso concedido! Bienvenido, {st.session_state['username'].capitalize()}.")
                st.rerun()
                
    st.stop() # Detiene la ejecución aquí para que no se muestre el dashboard detrás antes de loguearse

# --- CONTROL DE VISTAS PRINCIPALES ---
if st.session_state['vista_actual'] == "menu":
    
    st.markdown("<h2 style='text-align: center; color: #1e3a8a;'>Menú principal</h2>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: #64748b;'>Bienvenido, Alejandro, pincha un botón para empezar a gestionar tu energía!</p>", unsafe_allow_html=True)
    st.write("")
    
    # Creamos 4 columnas balanceadas
    b_col1, b_col2, b_col3, b_col4, b_col5 = st.columns(5)
    
    # --- SECCIÓN DE BOTONES COMPACTA (Sin wrappers manuales) ---
    with b_col1:
        if st.button("Monitor\nTiempo Real", use_container_width=True, key="btn_mon"):
            st.session_state['pestaña_activa'] = 0
            st.session_state['vista_actual'] = "dashboard"
            st.rerun()
            
    with b_col2:
        if st.button("Análisis\nHistórico", use_container_width=True, key="btn_ene"):
            st.session_state['pestaña_activa'] = 1
            st.session_state['vista_actual'] = "dashboard"
            st.rerun()
            
    with b_col3:
        if st.button("Consejos\nInteligentes", use_container_width=True, key="btn_rec"):
            st.session_state['pestaña_activa'] = 2
            st.session_state['vista_actual'] = "dashboard"
            st.rerun()
            
    with b_col4:
        if st.button("Configurar\nPerfil", use_container_width=True, key="btn_per"):
            st.session_state['pestaña_activa'] = 3
            st.session_state['vista_actual'] = "dashboard"
            st.rerun()

    with b_col5:
        if st.button("Resumen\nMensual", use_container_width=True, key="btn_res"):
            st.session_state['pestaña_activa'] = 4
            st.session_state['vista_actual'] = "dashboard"
            st.rerun()

else:
    # --- CARGA DE DATOS ---
    df_solar_db = load_solar_pvgis()
    
    # 🚀 REUBICACIÓN: Cálculos en tiempo real globales (Margen del bloque else)
    potencia_actual = get_real_data()  # Shelly Canal 0 (W)
    ahora_canarias = pd.Timestamp.now(tz='Atlantic/Canary')
    potencia_actual = get_real_data()
    pico_24h = get_max_24h() 
    # Pegamos aquí el bloque de interpolación solar continua de PVGIS
    gen_solar_ahora_w = 0.0
    if df_solar_db is not None:
        df_hoy = df_solar_db[(df_solar_db['time'].dt.month == ahora_canarias.month) & 
                             (df_solar_db['time'].dt.day == ahora_canarias.day)].copy()
        
        if not df_hoy.empty:
            df_hoy['time_interp'] = df_hoy['time'].apply(lambda x: x.replace(year=ahora_canarias.year))
            x_puntos = df_hoy['time_interp'].values.astype(np.int64) // 10**9
            y_puntos = df_hoy['P_solar'].values
            x_objetivo = ahora_canarias.timestamp()
            
            # INTERPOLACIÓN GLOBAL: Disponible para cualquier pestaña
            gen_solar_ahora_w = np.interp(x_objetivo, x_puntos, y_puntos)
            
    # Barra superior con información del usuario logueado de ejemplo y botón de reinicio
    col_title, col_logout = st.columns([8, 2])
    with col_title:
        now_local = pd.Timestamp.now(tz='Atlantic/Canary').strftime('%Y-%m-%d %H:%M:%S')
        st.title("⚡ Comunidad energética ULL")
        st.markdown(f"**Ubicación:** Tenerife (28.482, -16.306) | **Datos Solares:** PVGIS-SARAH3")
        st.markdown(f"**Hora local:** {now_local}")
    with col_logout:
        st.write("")
        if st.button("🚪 Salir de Demo", use_container_width=True):
            st.session_state['login_completed'] = False
            st.session_state['username'] = "alejandro"
            st.rerun()


    # --- SISTEMA DE PESTAÑAS ---
    # Botón discreto para regresar al menú principal en la barra superior
    with col_logout:
        if st.button("⬅️ Volver al Menú", use_container_width=True):
            st.session_state['vista_actual'] = "menu"
            st.rerun()

    # --- PESTAÑA 1: MONITOR REAL-TIME ---
    if st.session_state['pestaña_activa'] == 0:
        
        col1, col2 = st.columns([1, 2])

        with col1:
            st.metric(label="Consumo real (potencia instantánea)", value=f"{potencia_actual:.1f} W")
            # Ahora el valor numérico es exacto para el minuto actual
            st.metric(label="Generación solar estimada (potencia instantánea)", value=f"{gen_solar_ahora_w:.1f} W")
            st.metric(label="Pico de Demanda (24h)", value=f"{pico_24h:.1f} W", 
                    help="Máxima potencia registrada en el último día.")
            
            excedente_w = gen_solar_ahora_w - potencia_actual
            if excedente_w > 100:
                st.success(f"✅ EXCEDENTE: {excedente_w:.1f} W. ¡Es momento de consumir!")
            elif excedente_w > -100:
                st.warning("⚖️ BALANCE CERO: Generación igual a consumo.")
            else:
                st.error(f"⚠️ DÉFICIT: Importando {abs(excedente_w):.1f} W de la red.")

        with col2:
            st.subheader("📊 Balance neto de energía (Wh)")
            intervalo_r = st.selectbox("Rango rápido", options=["Última hora", "Últimas 24 horas"], index=1)
            map_t = {"Última hora": "1h", "Últimas 24 horas": "24h"}
            
            try:
                # 1. Consulta a InfluxDB (Solo Canal 0 necesario para el balance general de energía)
                q_p = f'SELECT "value" FROM "potencia_activa_w" WHERE "canal"=\'0\' AND time > now() - {map_t[intervalo_r]} ORDER BY time ASC'
                df_raw = pd.DataFrame(list(client.query(q_p, database=db_name).get_points()))
                
                if not df_raw.empty:
                    df_raw['time'] = pd.to_datetime(df_raw['time'], format='ISO8601').dt.tz_convert('Atlantic/Canary')
                    df_p = df_raw.rename(columns={'value': 'value'}).fillna(0.0)

                    frecuencia = st.radio("Ver balance por:", ["15 Minutos", "1 Hora"], horizontal=True)

                    # 2. Sincronización e Interpolación de la Generación Solar Instantánea
                    df_p['ts'] = df_p['time'].astype(np.int64) // 10**9
                    x_solar = df_hoy['time_interp'].astype(np.int64) // 10**9
                    y_solar = df_hoy['P_solar'].values
                    df_p['gen_w'] = np.interp(df_p['ts'], x_solar, y_solar, left=0, right=0)
                    
                    # Convertimos las potencias instantáneas (W) a muestras de energía base minuto (Wh) antes de agrupar
                    # Como tu base de datos toma muestras muy seguidas, promediamos a intervalos base de 1 minuto
                    df_min = df_p.resample('1min', on='time').mean().reset_index()
                    df_min['dem_wh'] = df_min['value'] / 60
                    df_min['gen_wh'] = df_min['gen_w'] / 60

                    # 3. IMPLEMENTACIÓN DEL BALANCE NETO DENTRO DEL INTERVALO SELECCIONADO
                    # Primero agrupamos (sumamos) toda la energía del bloque (15min o 1H) independientemente de los picos puntuales
                    f_resample = '1H' if frecuencia == "1 Hora" else '15min'
                    df_plot = df_min.resample(f_resample, on='time').sum().reset_index()
                    
                    # Ahora calculamos el Neto sobre el total acumulado del bloque energético
                    # Si en 1 hora has generado más de lo que has consumido en total, hay autoconsumo completo e importación cero.
                    df_plot['sc_wh'] = np.minimum(df_plot['dem_wh'], df_plot['gen_wh'])
                    df_plot['imp_wh'] = np.maximum(df_plot['dem_wh'] - df_plot['gen_wh'], 0)
                    df_plot['exp_wh'] = np.maximum(df_plot['gen_wh'] - df_plot['dem_wh'], 0)

                    # Configuración de etiquetas del eje Y
                    y_label = 'Energía (Wh por hora)' if frecuencia == "1 Hora" else 'Energía (Wh por 15 minutos)'

                    # 4. Construcción Gráfica Exclusiva de Energía
                    fig_energy = go.Figure()
                    
                    # Barras apiladas del balance neto
                    fig_energy.add_trace(go.Bar(x=df_plot['time'], y=df_plot['sc_wh'], name='Autoconsumo Solar', marker_color='#10b981'))
                    fig_energy.add_trace(go.Bar(x=df_plot['time'], y=df_plot['exp_wh'], name='Exportado Red', marker_color='#3b82f6'))
                    fig_energy.add_trace(go.Bar(x=df_plot['time'], y=df_plot['imp_wh'], name='Importado Red', marker_color='#f97316'))

                    # Líneas continuas de referencia suavizadas (Splines)
                    fig_energy.add_trace(go.Scatter(x=df_plot['time'], y=df_plot['dem_wh'], name='Demanda Total', 
                                                    mode='lines', line=dict(color="#6B2222", width=2, shape='spline')))
                    fig_energy.add_trace(go.Scatter(x=df_plot['time'], y=df_plot['gen_wh'], name='Generación Total', 
                                                    mode='lines', line=dict(color='#fbbf24', width=2, shape='spline')))

                    fig_energy.update_layout(
                        barmode='stack', height=400,
                        xaxis=dict(title=None, type='date'),
                        yaxis=dict(title=y_label),
                        margin=dict(l=0, r=0, t=10, b=0),
                        legend=dict(orientation='h', yanchor='bottom', y=-0.4, xanchor='center', x=0.5)
                    )
                    st.plotly_chart(fig_energy, use_container_width=True)
                    
            except Exception as e:
                st.error(f"Error en balance de energía: {e}")

    # --- PESTAÑA 2: ANÁLISIS DE ENERGÍA Y COSTE ---
    if st.session_state['pestaña_activa'] == 1:
        st.header("Análisis de consumo histórico")
        col_d1, col_d2, col_d3 = st.columns([2, 2, 1])
        with col_d1: fecha_inicio = st.date_input("Desde", ahora_canarias.date() - datetime.timedelta(days=7))
        with col_d2: fecha_fin = st.date_input("Hasta", ahora_canarias.date())
        with col_d3:
            st.write(" ")
            if st.button("Ver Hoy"): st.rerun()

        # InfluxDB trabaja internamente en UTC, adaptamos los rangos locales seleccionados
        start_iso = f"{fecha_inicio}T00:00:00Z"
        end_iso = f"{fecha_fin}T23:59:59Z"

        try:
            # 1. Obtener los puntos de potencia del Canal 0 (General) para el rango completo
            q_hist = f'SELECT "value" FROM "potencia_activa_w" WHERE "canal"=\'0\' AND time >= \'{start_iso}\' AND time <= \'{end_iso}\' ORDER BY time ASC'
            df_h = pd.DataFrame(list(client.query(q_h_query := q_hist, database=db_name).get_points()))
            
            if not df_h.empty:
                df_h['time'] = pd.to_datetime(df_h['time'], format='ISO8601').dt.tz_convert('Atlantic/Canary')
                
                # 2. Reconstruir la generación solar para CADA punto del histórico
                df_h['ts'] = df_h['time'].astype(np.int64) // 10**9
                df_h['gen_w'] = 0.0
                
                if df_solar_db is not None:
                    # Extraemos los meses y días únicos presentes en el rango consultado
                    dias_sol_h = df_h['time'].dt.strftime('%m-%d').unique()
                    sol_list_h = []
                    for d_str in dias_sol_h:
                        m, d = map(int, d_str.split('-'))
                        df_dia_s = df_solar_db[(df_solar_db['time'].dt.month == m) & (df_solar_db['time'].dt.day == d)].copy()
                        mask_h = df_h['time'].dt.strftime('%m-%d') == d_str
                        if any(mask_h):
                            y_h = df_h[mask_h]['time'].dt.year.iloc[0]
                            df_dia_s['time_plot'] = df_dia_s['time'].apply(lambda x: x.replace(year=y_h))
                            sol_list_h.append(df_dia_s)
                    
                    if sol_list_h:
                        df_sol_consolidado = pd.concat(sol_list_h).sort_values('time_plot')
                        x_s_h = df_sol_consolidado['time_plot'].astype(np.int64) // 10**9
                        y_s_h = df_sol_consolidado['P_solar'].values
                        # Interpolamos de forma continua sobre la línea de tiempo del histórico
                        df_h['gen_w'] = np.interp(df_h['ts'], x_s_h, y_s_h, left=0, right=0)
                freq_h = st.radio("Frecuencia del gráfico y balance:", ["Día", "Hora"], index=0, horizontal=True, key="hist_freq")
                # 3. Integración inicial de muestras de potencia (W) a energía base de 1 Minuto (Wh)
                df_h_res = df_h.resample('1min', on='time').mean().reset_index()
                df_h_res['dem_wh'] = df_h_res['value'] / 60
                df_h_res['gen_wh'] = df_h_res['gen_w'] / 60

                # 4. CÁLCULO DEL BALANCE NETO HORARIO OBLIGATORIO (Base de la facturación)
                # Agrupamos primero por hora para eliminar picos instantáneos
                df_horario = df_h_res.resample('1H', on='time').sum().reset_index()
                
                # Aplicamos las condiciones de neteo sobre los bloques de 1 hora
                df_horario['sc_wh'] = np.minimum(df_horario['dem_wh'], df_horario['gen_wh'])
                df_horario['imp_wh'] = np.maximum(df_horario['dem_wh'] - df_horario['gen_wh'], 0)
                df_horario['exp_wh'] = np.maximum(df_horario['gen_wh'] - df_horario['dem_wh'], 0)

                # 5. CONSTRUCCIÓN DEL DATAFRAME FINAL PARA EL GRÁFICO (df_hist_plot)
                # Si se elige "Hora", usamos el neteo horario directo.
                # Si se elige "Día", hacemos el SUMATORIO de los valores horarios netos de ese día.
                if freq_h == "Hora":
                    df_hist_plot = df_horario.copy()
                else:
                    df_hist_plot = df_horario.resample('1D', on='time').sum().reset_index()
                
                # 6. Cálculo de Totales Absolutos para las Métricas basado en el DataFrame procesado
                total_imp_kwh = df_hist_plot['imp_wh'].sum() / 1000
                total_sc_kwh = df_hist_plot['sc_wh'].sum() / 1000
                total_exp_kwh = df_hist_plot['exp_wh'].sum() / 1000
                total_kwh = total_imp_kwh + total_sc_kwh
                
                # ✨ NUEVA MÉTRICA DE INGENIERÍA: Factor de Ajuste al Autoconsumo
                total_gen_solar = total_sc_kwh + total_exp_kwh
                factor_autoconsumo = (total_sc_kwh / total_kwh * 100) if total_gen_solar > 0 else 0.0

                coste_red = total_imp_kwh * PRECIO_KWH
                ahorro_sc = total_sc_kwh * PRECIO_KWH
                abono_exc = total_exp_kwh * PRECIO_EXC
                factura_estimada = max(0, coste_red - abono_exc)

                # --- RENDERIZADO DE LAS MÉTRICAS DE LA ECUACIÓN ENERGÉTICA ---
                # Ampliamos la matriz de columnas para albergar de forma asimétrica la nueva tarjeta al final
                c_t, c_e1, c_i, c_e2, c_s, c_sep, c_x, c_sep2, c_f = st.columns([2, 0.4, 2, 0.4, 2, 0.4, 2, 0.4, 2])

                with c_t: st.markdown(f'<div class="eq-card" style="border-top-color: #374151;"><p class="eq-label">Demanda Total</p><p class="eq-val" style="color: #374151;">{total_kwh:.2f} <small>kWh</small></p></div>', unsafe_allow_html=True)
                with c_e1: st.markdown('<div class="eq-symbol">=</div>', unsafe_allow_html=True)
                with c_i: st.markdown(f'<div class="eq-card" style="border-top-color: #f97316;"><p class="eq-label">Importado Red</p><p class="eq-val" style="color: #f97316;">{total_imp_kwh:.2f} <small>kWh</small></p></div>', unsafe_allow_html=True)
                with c_e2: st.markdown('<div class="eq-symbol">+</div>', unsafe_allow_html=True)
                with c_s: st.markdown(f'<div class="eq-card" style="border-top-color: #10b981;"><p class="eq-label">Autoconsumo</p><p class="eq-val" style="color: #10b981;">{total_sc_kwh:.2f} <small>kWh</small></p></div>', unsafe_allow_html=True)
                with c_sep: st.markdown('<div class="eq-symbol" style="color:#e2e8f0">|</div>', unsafe_allow_html=True)
                with c_x: st.markdown(f'<div class="eq-card" style="border-top-color: #3b82f6;"><p class="eq-label">Excedentes</p><p class="eq-val" style="color: #3b82f6;">{total_exp_kwh:.2f} <small>kWh</small></p></div>', unsafe_allow_html=True)
               
                with c_sep2: st.markdown('<div class="eq-symbol" style="color:#e2e8f0">|</div>', unsafe_allow_html=True)
                with c_f: st.markdown(f'<div class="eq-card" style="border-top-color: #8b5cf6;"><p class="eq-label">Ajuste Autoconsumo</p><p class="eq-val" style="color: #8b5cf6;">{factor_autoconsumo:.1f} <small>%</small></p></div>', unsafe_allow_html=True)
                
                st.subheader("💰 Resumen Económico")
                mc1, mc2, mc3, mc4 = st.columns(4)
                mc1.metric("Gasto Red", f"{coste_red:.2f} €", help="Coste de la energía comprada.")
                mc2.metric("Ahorro Autoconsumo", f"{ahorro_sc:.2f} €", help="Dinero ahorrado gracias a la generación solar.")
                mc3.metric("Abono Excedentes", f"{abono_exc:.2f} €", help=f"Compensación de excedentes.")
                mc4.metric("Factura Estimada", f"{factura_estimada:.2f} €", delta=f"-{abono_exc:.2f} €", delta_color="normal")

                st.divider()

                # Selector de frecuencia para agrupar e implementar el Balance Neto Horario o Diario
                st.subheader("📊 Histórico de Energía (Wh)")
                
                f_map = {"Día": "1D", "Hora": "1H"}

                # 5. DIBUJAR LA GRÁFICA DE ENERGÍA HISTÓRICA ASOCIADA
                fig_h_stack = go.Figure()
                # Bloques apilados idénticos a la pestaña 1
                fig_h_stack.add_trace(go.Bar(x=df_hist_plot['time'], y=df_hist_plot['sc_wh'], name='Autoconsumo Solar', marker_color='#10b981'))
                fig_h_stack.add_trace(go.Bar(x=df_hist_plot['time'], y=df_hist_plot['exp_wh'], name='Exportado Red', marker_color='#3b82f6'))
                fig_h_stack.add_trace(go.Bar(x=df_hist_plot['time'], y=df_hist_plot['imp_wh'], name='Importado Red', marker_color='#f97316'))
                
                # Líneas continuas de referencia suavizadas (Splines)
                fig_h_stack.add_trace(go.Scatter(x=df_hist_plot['time'], y=df_hist_plot['dem_wh'], name='Demanda Total', mode='lines', line=dict(color="#374151", width=2, shape='spline')))
                fig_h_stack.add_trace(go.Scatter(x=df_hist_plot['time'], y=df_hist_plot['gen_wh'], name='Generación Total', mode='lines', line=dict(color='#fbbf24', width=2, shape='spline')))

                y_label_h = "Energía (Wh por día)" if freq_h == "Día" else "Energía (Wh por hora)"
                fig_h_stack.update_layout(
                    barmode='stack', height=400, yaxis=dict(title=y_label_h), xaxis=dict(title=None, type='date'),
                    margin=dict(l=0, r=0, t=10, b=0), legend=dict(orientation='h', yanchor='bottom', y=-0.4, xanchor='center', x=0.5)
                )
                st.plotly_chart(fig_h_stack, use_container_width=True)

        except Exception as e: 
            st.error(f"Error en análisis histórico: {e}")

    if st.session_state['pestaña_activa'] == 3:
        st.header("👤 Mi Perfil Energético")
        st.write("Configura tus hábitos de consumo y electrodomésticos para personalizar el motor de recomendaciones.")

        # 1. CARGA DE ARCHIVOS BASE (Creados en la Tarea 1)
        try:
            df_curvas = pd.read_csv('perfil_consumo_predeterminado.csv')
            opciones_perfiles = [col for col in df_curvas.columns if col != 'hora']
        except FileNotFoundError:
            st.error("⚠️ No se encuentra 'perfil_consumo_predeterminado.csv'. Ejecuta el script de generación de perfiles.")
            opciones_perfiles = ["Piso Compartido (3-4 estudiantes)"]
            df_curvas = pd.DataFrame({'hora': list(range(24)), "Piso Compartido (3-4 estudiantes)": [200]*24})

        try:
            with open("database_aparatos_nilm.json", "r", encoding="utf-8") as f:
                db_aparatos = json.load(f)
            lista_electrodomesticos = list(db_aparatos.keys())
        except FileNotFoundError:
            lista_electrodomesticos = ["Horno Eléctrico", "Lavavajillas", "Lavadora", "Secadora", "Frigorífico"]

        # 2. FORMULARIO DE CONFIGURACIÓN DEL PERFIL
        with st.form("perfil_v9_dinamico"):
            n = st.text_input("Nombre Completo / Identificador", value="Usuario_Demo")
            
            c1, c2 = st.columns(2)
            with c1:
                # Selector con las 5 nuevas plantillas sociodemográficas adaptadas a la universidad
                patron_elegido = st.selectbox(
                    "📅 Patrón de uso y rutina horaria (Plantilla SolarEdge/IEA)", 
                    options=opciones_perfiles
                )
                pot = st.number_input("⚡ Potencia Contratada (kW)", 1.0, 10.0, 4.6, step=0.1)

            st.divider()
            
            # 3. CHECKBOXES DINÁMICAS DE ELECTRODOMÉSTICOS (Basadas en las firmas del dataset)
            st.subheader("🔌 Electrodomésticos en la vivienda")
            st.write("Selecciona los dispositivos que tienes:")
            
            # Distribuimos los checkboxes en 3 columnas limpias
            col_app1, col_app2, col_app3 = st.columns(3)
            dict_checks = {}
            
            for idx, el_name in enumerate(lista_electrodomesticos):
                # Determinamos en qué columna renderizar de forma equilibrada
                if idx % 3 == 0:
                    with col_app1: dict_checks[el_name] = st.checkbox(el_name, value=True)
                elif idx % 3 == 1:
                    with col_app2: dict_checks[el_name] = st.checkbox(el_name, value=True)
                else:
                    with col_app3: dict_checks[el_name] = st.checkbox(el_name, value=True)

            # Botón de envío del formulario
            submit_perfil = st.form_submit_button("💾 Guardar y Actualizar Perfil Técnico")
            
            if submit_perfil:
                # Filtramos la lista de electrodomésticos que el usuario ha marcado como "True"
                aparatos_activos = [key for key, val in dict_checks.items() if val]
                
                # Guardamos la configuración completa en la base de datos/estado del aplicativo
                datos_perfil = {
                    "nombre": n,
                    "tiene_ve": False,
                    "tiene_clima": False,
                    "patron": patron_elegido,
                    "pot_contratada": pot,
                    "gasto_medio": 60,
                    "electrodomesticos": aparatos_activos
                }
                
                # Guardamos en tu backend
                save_user_profile(datos_perfil)
                
                # Almacenamos la curva horaria específica elegida en el session_state para que el gráfico de la pestaña 2 la lea de inmediato
                st.session_state['perfil_consumo_usuario'] = df_curvas[['hora', patron_elegido]].rename(columns={patron_elegido: 'consumo_wh'})
                st.session_state['electrodomesticos_usuario'] = aparatos_activos
                
                st.success(f"¡Perfil de **{n}** actualizado con éxito! Se ha cargado la curva patrón de: *{patron_elegido}*.")

        # 4. VISUALIZACIÓN INTERACTIVA DE LA CURVA ELEGIDA
        # Fuera del formulario para que responda dinámicamente si el usuario cambia el selectbox y pulsa guardar
        perfil_actual_nombre = patron_elegido if 'perfil_consumo_usuario' not in st.session_state else st.session_state.get('datos_perfil', {}).get('patron', patron_elegido)
        
        st.divider()
        st.subheader(f"📈 Curva de Demanda Asignada: {perfil_actual_nombre}")
        st.write("Esta serie temporal horaria simula tu consumo base en la Comunidad Energética:")

        fig_perfil = px.line(
            df_curvas, 
            x='hora', 
            y=patron_elegido, 
            labels={'hora': 'Hora del Día (0-23)', patron_elegido: 'Demanda Estimada Promedio (Wh)'},
            template='plotly_white'
        )
        # Estilo técnico de la línea: color verde ingeniería sostenible
        fig_perfil.update_traces(line_color='#2E7D32', line_width=3, mode='lines+markers')
        fig_perfil.update_layout(
            hovermode="x unified",
            margin=dict(l=20, r=20, t=20, b=20),
            height=300
        )
        st.plotly_chart(fig_perfil, use_container_width=True)

    # --- PESTAÑA 4: RECOMENDACIONES ---
    if st.session_state['pestaña_activa'] == 2:
        # Inyectamos estilos CSS personalizados para los botones interactivos de la Columna A
        st.markdown("""
            <style>
            /* 🟢 Estilo para los botones seleccionados (activos) */
            div[data-testid="stButton"] button:has(div:contains("🟢")) {
                background-color: #e8f5e9 !important;
                color: #1b5e20 !important;
                border: 2px solid #2e7d32 !important;
                font-weight: bold !important;
            }
            /* 🔴 Estilo para botones deshabilitados (bloqueados por sobrecarga) */
            div[data-testid="stButton"] button:disabled {
                background-color: #ffebee !important;
                color: #b71c1c !important;
                border: 1px solid #ef9a9a !important;
                opacity: 0.6;
                cursor: not-allowed !important;
            }
            </style>
        """, unsafe_allow_html=True)

        # =========================================================================
        # 1. PREPARACIÓN Y FILTRADO DE ELECTRODOMÉSTICOS (NILM)
        # =========================================================================
        # Recuperamos el patrón del usuario
        patron_actual = st.session_state.get('perfil_consumo_usuario', pd.DataFrame()).columns
        patron_actual = patron_actual[1] if len(patron_actual) > 1 else "Piso Compartido (3-4 estudiantes)"
        
        aparatos_perfil = st.session_state.get('electrodomesticos_usuario', [])
        
        # Fallback de seguridad ordenado con los nombres exactos de tu JSON ("Coche", "Aire Acondicionado")
        if not aparatos_perfil:
            aparatos_perfil = ["Horno Eléctrico", "Lavavajillas", "Lavadora", "Secadora", "Aire Acondicionado", "Coche"]

        # 🚨 FILTRADO: Excluimos por completo el Frigorífico del panel de control manual
        aparatos_usuario = [ap for ap in aparatos_perfil if "frigor" not in ap.lower() and "frigo" not in ap.lower()]

        # Aseguramos que la máquina de estados de los botones de la Columna A esté inicializada
        if 'sim_toggles' not in st.session_state:
            st.session_state['sim_toggles'] = {}
        for ap in aparatos_usuario:
            if ap not in st.session_state['sim_toggles']:
                st.session_state['sim_toggles'][ap] = False

        # Carga de la curva de demanda base horaria
        try:
            df_curvas_base = pd.read_csv('perfil_consumo_predeterminado.csv')
            curva_demanda_base = df_curvas_base[patron_actual].values
        except:
            curva_demanda_base = [200] * 24

        # =========================================================================
        # 🏛️ INTERFAZ ASIMÉTRICA EN DOS COLUMNAS
        # =========================================================================
        col_a, col_b = st.columns([2, 3])

        # -------------------------------------------------------------------------
        # 📅 COLUMNA A: ¿Qué electrodomésticos necesitas usar ahora? (Tiempo Real)
        # -------------------------------------------------------------------------
        with col_a:
            st.subheader("📅 ¿Qué deseas usar ahora?")
            st.write("Gestiona la demanda instantánea combinando tus equipos activos:")

            # Cálculos de holguras dinámicas para la simulación viva
            excedente_inicial = gen_solar_ahora_w - potencia_actual
            potencia_seleccionada_sim = 0
            for ap in aparatos_usuario:
                if st.session_state['sim_toggles'].get(ap, False) and ap in db_aparatos:
                    potencia_seleccionada_sim += db_aparatos[ap]["potencia_w"]

            holgura_restante_sim = excedente_inicial - potencia_seleccionada_sim

            # Indicador visual superior del balance neto de potencia
            if holgura_restante_sim > 0:
                st.markdown(f'<div style="background-color: #e8f5e9; border-left: 5px solid #2e7d32; padding: 10px; border-radius: 6px; margin-bottom: 15px;"><h4 style="margin:0; color:#2e7d32;">Sobrante Solar: +{holgura_restante_sim:.0f} W</h4></div>', unsafe_allow_html=True)
            else:
                st.markdown(f'<div style="background-color: #ffebee; border-left: 5px solid #c62828; padding: 10px; border-radius: 6px; margin-bottom: 15px;"><h4 style="margin:0; color:#c62828;">Déficit de Red: {holgura_restante_sim:.0f} W</h4></div>', unsafe_allow_html=True)

            # Generación de la botonera combinatoria en tiempo real
            for aparato in aparatos_usuario:
                if aparato in db_aparatos:
                    pot_w = db_aparatos[aparato]["potencia_w"]
                    is_active = st.session_state['sim_toggles'][aparato]
                    
                    if is_active:
                        if st.button(f"🟢 {aparato} (+{pot_w} W) [ON]", key=f"now_{aparato}", use_container_width=True):
                            st.session_state['sim_toggles'][aparato] = False
                            st.rerun()
                    else:
                        if pot_w <= holgura_restante_sim:
                            if st.button(f"⚪ {aparato} ({pot_w} W) [OFF]", key=f"now_{aparato}", use_container_width=True):
                                st.session_state['sim_toggles'][aparato] = True
                                st.rerun()
                        else:
                            st.button(f"🔴 {aparato} ({pot_w} W) — Sobrecarga", key=f"now_{aparato}", disabled=True, use_container_width=True)

            # 🚨 AVISO CRÍTICO DE AHORRO SOLAR (Solicitado)
            if excedente_inicial <= 50: # Si apenas hay excedente o es negativo
                st.markdown(
                    f'<div style="background-color: #fff3e0; border-left: 5px solid #f57c00; padding: 12px; border-radius: 6px; margin-top: 20px;">'
                    f'<p style="margin:0; color:#e65100; font-size:13px; font-weight:500;">⚠️ <b>Aviso de eficiencia:</b> '
                    f'En este momento la generación de la comunidad solar es insuficiente para cubrir cargas adicionales. '
                    f'Cualquier aparato que utilices ahora se alimentará de la red general y <b>no estaría aprovechando el ahorro solar</b>.</p>'
                    f'</div>', unsafe_allow_html=True
                )

            if potencia_seleccionada_sim > 0:
                st.write(" ")
                if st.button("🔌 Apagar todos los simuladores", use_container_width=True):
                    for ap in aparatos_usuario: st.session_state['sim_toggles'][ap] = False
                    st.rerun()

        # -------------------------------------------------------------------------
        # 🔮 COLUMNA B: ¿Qué electrodomésticos necesitas usar mañana? (Bloques Horarios)
        # -------------------------------------------------------------------------
        with col_b:
            st.subheader("🔮 Planificador Horario de Excedentes")
            
            # Algoritmo de detección horaria de recurso solar remanente
            ahora_canarias = pd.Timestamp.now(tz='Atlantic/Canary')
            hora_actual = ahora_canarias.hour
            
            df_solar_db['hora_pvgis'] = df_solar_db['time'].dt.hour
            df_solar_hoy = df_solar_db[(df_solar_db['time'].dt.month == ahora_canarias.month) & (df_solar_db['time'].dt.day == ahora_canarias.day)]
            curva_solar_hoy = df_solar_hoy.groupby('hora_pvgis')['P_solar'].mean().reindex(range(24), fill_value=0.0).values
            
            energia_solar_restante_hoy = sum(curva_solar_hoy[hora_actual:])
            
            if hora_actual >= 18 or energia_solar_restante_hoy < 600:
                dia_planificacion = "MAÑANA"
                fecha_objetivo = ahora_canarias + datetime.timedelta(days=1)
                st.warning(f"🌙 **Previsión para {dia_planificacion} ({fecha_objetivo.strftime('%d/%m')}):** No queda suficiente recurso solar hoy.")
            else:
                dia_planificacion = "HOY"
                fecha_objetivo = ahora_canarias
                st.success(f"☀️ **Previsión para {dia_planificacion} ({fecha_objetivo.strftime('%d/%m')}):** Optimizando las horas de luz restantes.")

            # Descarga de la curva de producción de la fecha destino
            df_solar_objetivo = df_solar_db[(df_solar_db['time'].dt.month == fecha_objetivo.month) & (df_solar_db['time'].dt.day == fecha_objetivo.day)]
            curva_solar_predicha = df_solar_objetivo.groupby('hora_pvgis')['P_solar'].mean().reindex(range(24), fill_value=0.0).values

            st.write("Selecciona qué tareas deseas programar a lo largo del día:")
            
            # Checkboxes horizontales de planificación (Excluido el frigo)
            cols_plan = st.columns(3)
            aparatos_planificar = []
            for idx, ap in enumerate(aparatos_usuario):
                with cols_plan[idx % 3]:
                    if st.checkbox(f"📅 {ap.split(' (')[0]}", key=f"chk_plan_{ap}", value=(idx==0)):
                        aparatos_planificar.append(ap)

            # Matriz de asignación óptima (Greedy Displacements)
            matriz_planificacion_w = {'Carga Base Perfil': list(curva_demanda_base)}
            for ap in aparatos_planificar:
                matriz_planificacion_w[ap] = [0.0] * 24

            excedentes_teoricos_hora = curva_solar_predicha - curva_demanda_base
            horas_diurnas_validas = [h for h in np.argsort(excedentes_teoricos_hora)[::-1] if 9 <= h <= 17]

            cronograma_textos = []
            if horas_diurnas_validas and aparatos_planificar:
                aparatos_ordenados = sorted(aparatos_planificar, key=lambda x: db_aparatos.get(x, {}).get('potencia_w', 0), reverse=True)
                for idx, ap_sel in enumerate(aparatos_ordenados):
                    if ap_sel in db_aparatos:
                        pot_w = db_aparatos[ap_sel]["potencia_w"]
                        hora_asignada = horas_diurnas_validas[idx % len(horas_diurnas_validas)]
                        matriz_planificacion_w[ap_sel][hora_asignada] = pot_w
                        cronograma_textos.append(f"⏱️ **{ap_sel}**: Programar de **{hora_asignada}:00 a {hora_asignada+1}:00h**.")

            # =========================================================================
            # 📊 CONSTRUCCIÓN DEL GRÁFICO DUO-BARRA APILADA (OFFSETGROUP)
            # =========================================================================
            st.subheader(f"📈 Cronograma Predictivo en Bloques Horarios ({dia_planificacion.lower()})")
            
            fig_plan = go.Figure()
            horas_eje_x = [f"{h}:00h" for h in range(24)]
            
            color_map = {
                'Carga Base Perfil': '#cbd5e1',
                'Horno Eléctrico': '#3b82f6',
                'Lavavajillas': '#b91c1c',
                'Lavadora': '#10b981',
                'Secadora': '#f97316',
                'Aire Acondicionado': '#06b6d4',
                'Coche': '#8b5cf6'
            }

            # 1. Grupo de Barras de Demanda (offsetgroup='demanda')
            for componente, valores_24h in matriz_planificacion_w.items():
                fig_plan.add_trace(go.Bar(
                    x=horas_eje_x, y=valores_24h, name=componente,
                    marker_color=color_map.get(componente, '#64748b'),
                    offsetgroup='demanda',
                    hovertemplate=f'<b>{componente}</b><br>Potencia: %{{y:.0f}} Wh<extra></extra>'
                ))

            # 2. Grupo de Barra de Generación Solar en Bloques Horarios (offsetgroup='solar')
            # Al usar go.Bar con un offsetgroup diferente, Plotly las dibuja una al lado de la otra por cada hora
            fig_plan.add_trace(go.Bar(
                x=horas_eje_x, y=curva_solar_predicha, 
                name="Energía Solar Disponible (PVGIS)",
                marker_color='#eab308',
                marker_line_color='#ca8a04',
                marker_line_width=1,
                opacity=0.85,
                offsetgroup='solar',
                hovertemplate='<b>Bloque Fotovoltaico</b><br>Energía prevista: %{y:.0f} Wh<extra></extra>'
            ))

            fig_plan.update_layout(
                barmode='stack', template='plotly_white', height=360,
                margin=dict(l=0, r=0, t=10, b=0),
                xaxis=dict(title=None), yaxis=dict(title="Energía por Hora (Wh)"),
                legend=dict(orientation='h', yanchor='bottom', y=-0.35, xanchor='center', x=0.5)
            )
            st.plotly_chart(fig_plan, use_container_width=True)

            # Directivas resumidas
            if cronograma_textos:
                st.markdown("##### 📋 Sugerencias de Desplazamiento de Carga:")
                for txt in cronograma_textos:
                    st.markdown(txt)
        # =========================================================================
        # 📚 RECURSOS EXTERNOS: OBSERVATORIO DE LA POBREZA ENERGÉTICA DE TENERIFE
        # =========================================================================
        st.divider()
        st.markdown("### 📚 Recursos de Apoyo y Formación Energética")
        st.write("Para mejorar tu cultura energética y auditar tus costes, consulta las guías oficiales del **Observatorio de la Pobreza Energética de Tenerife (OCCET)**:")

        col_ref1, col_ref2 = st.columns(2)
        
        with col_ref1:
            st.markdown(
                """
                <div style="background-color: #f8fafc; padding: 15px; border-radius: 8px; border: 1px solid #e2e8f0; height: 100%;">
                    <h5 style="margin-top:0; color:#1e293b;">📑 Entiende tu factura de la luz</h5>
                    <p style="font-size: 13px; color: #475569;">Desglosa los términos de potencia y energía de tu contrato para optimizar tu tarifa contratada.</p>
                    <a href="https://occet.es/observatorio-pobreza-energetica/la-factura-de-la-luz/" target="_blank" style="color:#3b82f6; font-weight:bold; text-decoration:none;">💻 Acceder al apartado →</a>
                </div>
                """, 
                unsafe_allow_html=True
            )
            
        with col_ref2:
            st.markdown(
                """
                <div style="background-color: #f8fafc; padding: 15px; border-radius: 8px; border: 1px solid #e2e8f0; height: 100%;">
                    <h5 style="margin-top:0; color:#1e293b;">💡 Consejos de Eficiencia Energética</h5>
                    <p style="font-size: 13px; color: #475569;">Recomendaciones prácticas y hábitos estructurales para minimizar el desperdicio energético en el hogar.</p>
                    <a href="https://occet.es/observatorio-pobreza-energetica/la-eficiencia-energetica-del-hogar/" target="_blank" style="color:#10b981; font-weight:bold; text-decoration:none;">💻 Ver consejos de eficiencia →</a>
                </div>
                """, 
                unsafe_allow_html=True
            )            
    # --- PESTAÑA 5: RECOMENDACIONES ---
    if st.session_state['pestaña_activa'] == 4:
        st.header("📊 Auditoría Energética Mensual Automática")
        st.write("Cálculo de balances netos reales consolidados utilizando la metodología de paso de muestra a bloque de energía horaria.")

        # =========================================================================
        # 1. DETERMINACIÓN DEL RANGO DEL ÚLTIMO MES NATURAL COMPLETO
        # =========================================================================
        hoy = datetime.date.today()
        primero_este_mes = hoy.replace(day=1)
        ultimo_dia_mes_pasado = primero_este_mes - datetime.timedelta(days=1)
        primero_mes_pasado = ultimo_dia_mes_pasado.replace(day=1)

        nombre_mes = primero_mes_pasado.strftime('%B').capitalize()
        anio_mes = primero_mes_pasado.year

        st.subheader(f"📅 Periodo Auditado Real: {nombre_mes} de {anio_mes}")

        # 🗺️ CORRECCIÓN CRÍTICA: Convertimos el inicio/fin local a UTC antes de consultar a InfluxDB
        start_local = pd.Timestamp(f"{primero_mes_pasado} 00:00:00", tz='Atlantic/Canary')
        end_local = pd.Timestamp(f"{ultimo_dia_mes_pasado} 23:59:59", tz='Atlantic/Canary')

        start_utc_str = start_local.tz_convert('UTC').strftime('%Y-%m-%d %H:%M:%S')
        end_utc_str = end_local.tz_convert('UTC').strftime('%Y-%m-%d %H:%M:%S')

        # =========================================================================
        # 2. EXTRACCIÓN Y TRATAMIENTO DE DATOS REALES INTERPOLADOS CON PVGIS
        # =========================================================================
        # La consulta ahora pide a InfluxDB el bloque UTC exacto que equivale al mes local
        q_p = f'SELECT "value" FROM "potencia_activa_w" WHERE "canal"=\'0\' AND time >= \'{start_utc_str}\' AND time <= \'{end_utc_str}\' ORDER BY time ASC'
        
        df_raw = pd.DataFrame(list(client.query(q_p, database=db_name).get_points()))
        # Tratamiento de marcas de tiempo e indexación temporal idéntica a tu primera pestaña
        df_raw['time'] = pd.to_datetime(df_raw['time'], format='ISO8601').dt.tz_convert('Atlantic/Canary')
        df_p = df_raw.rename(columns={'value': 'value'}).fillna(0.0)
        df_p['ts'] = df_p['time'].astype(np.int64) // 10**9
        df_p['gen_w'] = 0.0

        # ☀️ LÓGICA DE DETECCIÓN Y REDISTRIBUCIÓN SOLAR POR DÍAS ÚNICOS (MÉTODO PESTAÑA 1)
        if df_solar_db is not None:
            if df_solar_db['time'].dt.tz is None:
                df_solar_db['time'] = df_solar_db['time'].dt.tz_localize('UTC').dt.tz_convert('Atlantic/Canary')
            
            dias_sol_h = df_p['time'].dt.strftime('%m-%d').unique()
            sol_list_h = []
            for d_str in dias_sol_h:
                m, d = map(int, d_str.split('-'))
                df_dia_s = df_solar_db[(df_solar_db['time'].dt.month == m) & (df_solar_db['time'].dt.day == d)].copy()
                mask_h = df_p['time'].dt.strftime('%m-%d') == d_str
                if any(mask_h):
                    y_h = df_p[mask_h]['time'].dt.year.iloc[0]
                    df_dia_s['time_plot'] = df_dia_s['time'].apply(lambda x: x.replace(year=y_h))
                    sol_list_h.append(df_dia_s)
            
            if sol_list_h:
                df_sol_consolidado = pd.concat(sol_list_h).sort_values('time_plot')
                x_s_h = df_sol_consolidado['time_plot'].astype(np.int64) // 10**9
                y_s_h = df_sol_consolidado['P_solar'].values
                # Interpolación exacta sobre el timeline continuo de InfluxDB
                df_p['gen_w'] = np.interp(df_p['ts'], x_s_h, y_s_h, left=0, right=0)

        # Integración inicial de muestras de potencia (W) a energía base de 1 Minuto (Wh)
        df_min = df_p.resample('1min', on='time').mean().reset_index()
        df_min['dem_wh'] = df_min['value'] / 60
        df_min['gen_wh'] = df_min['gen_w'] / 60

        # Agrupación final en bloques cerrados de 1 Hora ('1H') para aplicar el Balance Neto Horario
        df_plot = df_min.resample('1H', on='time').sum().reset_index()
        
        df_plot['sc_wh'] = np.minimum(df_plot['dem_wh'], df_plot['gen_wh'])
        df_plot['imp_wh'] = np.maximum(df_plot['dem_wh'] - df_plot['gen_wh'], 0)
        df_plot['exp_wh'] = np.maximum(df_plot['gen_wh'] - df_plot['dem_wh'], 0)
        df_plot['consumo_total_wh'] = df_plot['imp_wh'] + df_plot['sc_wh']
        df_plot['fecha'] = df_plot['time'].dt.date

        # =========================================================================
        # 3. CÁLCULO DE TOTALES ABSOLUTOS EN KWH (CORREGIDO)
        # =========================================================================
        total_imp_kwh = df_plot['imp_wh'].sum() / 1000
        total_sc_kwh = df_plot['sc_wh'].sum() / 1000
        total_exp_kwh = df_plot['exp_wh'].sum() / 1000
        total_consumido_kwh = total_imp_kwh + total_sc_kwh

        col_m1, col_m2 = st.columns([2, 3])

        with col_m1:
            st.markdown(
                f'<div style="background-color: #f8fafc; border-left: 5px solid #0c4a6e; padding: 20px; border-radius: 8px; margin-top:15px;">'
                f'<p style="margin:0; font-size:14px; color:#64748b; font-weight:bold; text-transform:uppercase;">Energía Total Consumida Real</p>'
                f'<h1 style="margin:0; color:#1e293b; font-size:42px;">{total_consumido_kwh:.2f} <small style="font-size:20px;">kWh</small></h1>'
                f'</div>', unsafe_allow_html=True
            )
            st.write(" ")
            st.write("📋 **Flujos Integrados del Mes:**")
            st.write(f"🔹 **Autoconsumo Solar Directo:** {total_sc_kwh:.2f} kWh")
            st.write(f"🔹 **Importación desde Red:** {total_imp_kwh:.2f} kWh")
            st.write(f"🔹 **Sobrantes Inyectados:** {total_exp_kwh:.2f} kWh")

        with col_m2:
            # Gráfico dinámico alimentado por las variables reales neteadas
            fig_pie = go.Figure(data=[go.Pie(
                labels=['Autoconsumo Directo', 'Importado de Red', 'Sobrantes'],
                values=[total_sc_kwh, total_imp_kwh, total_exp_kwh],
                hole=.3,
                marker=dict(colors=['#10b981', '#f97316', '#3b82f6'])
            )])
            fig_pie.update_layout(
                margin=dict(l=0, r=0, t=10, b=0), height=240,
                legend=dict(orientation="h", yanchor="bottom", y=-0.1, xanchor="center", x=0.5)
            )
            st.plotly_chart(fig_pie, use_container_width=True)

        st.divider()

        # =========================================================================
        # 4. ANÁLISIS DE EXTREMOS DIARIOS REALES EN KWH (CORREGIDO)
        # =========================================================================
        st.subheader("⚖️ Extremos de Demanda y Eficiencia")

        df_diario = df_plot.groupby('fecha').agg({
            'consumo_total_wh': 'sum',
            'sc_wh': 'sum',
            'exp_wh': 'sum'
        }).reset_index()

        df_diario['consumo_kwh'] = df_diario['consumo_total_wh'] / 1000
        df_diario['total_solar_wh'] = df_diario['sc_wh'] + df_diario['exp_wh']
        df_diario['aprovechamiento_pct'] = (df_diario['sc_wh'] / df_diario['total_solar_wh'] * 100).fillna(0)

        idx_max_cons = df_diario['consumo_kwh'].idxmax()
        idx_min_cons = df_diario['consumo_kwh'].idxmin()
        idx_max_aprov = df_diario['aprovechamiento_pct'].idxmax()

        c_ext1, c_ext2, c_ext3 = st.columns(3)
        with c_ext1:
            st.metric(label="🔥 Día de Mayor Consumo", value=f"{df_diario.loc[idx_max_cons, 'consumo_kwh']:.2f} kWh", delta=df_diario.loc[idx_max_cons, 'fecha'].strftime('%d/%m'))
        with c_ext2:
            st.metric(label="❄️ Día de Menor Consumo", value=f"{df_diario.loc[idx_min_cons, 'consumo_kwh']:.2f} kWh", delta=df_diario.loc[idx_min_cons, 'fecha'].strftime('%d/%m'), delta_color="inverse")
        with c_ext3:
            st.metric(label="⭐ Máximo Aprovechamiento Solar", value=f"{df_diario.loc[idx_max_aprov, 'aprovechamiento_pct']:.1f} %", delta=df_diario.loc[idx_max_aprov, 'fecha'].strftime('%d/%m'))

        st.divider()

        # =========================================================================
        # 5. BALANCE POR TRAMOS HORARIOS REGULADOS 2026
        # =========================================================================
        st.subheader("⏱️ Distribución por Tramos Horarios")
        
        df_plot['tramo'] = df_plot['time'].apply(get_periodo_tarifario)
        df_tramos = df_plot.groupby('tramo')['consumo_total_wh'].sum().reset_index()
        df_tramos['consumo_kwh'] = df_tramos['consumo_total_wh'] / 1000 
        df_tramos['porcentaje'] = (df_tramos['consumo_total_wh'] / df_plot['consumo_total_wh'].sum()) * 100

        cols_tabla = st.columns([3, 2])
        with cols_tabla[0]:
            mapa_nombres = {
                "P1": "P1 (Punta Alta)", "P2": "P2 (Punta Media-Alta)", 
                "P3": "P3 (Llano / Punta Media)", "P4": "P4 (Punta Baja / Valle Medio)",
                "P5": "P5 (Llano Bajo)", "P6": "P6 (Valle Continuo / S-D)"
            }
            df_tramos['Periodo Tarifario'] = df_tramos['tramo'].map(mapa_nombres)
            st.dataframe(
                df_tramos[['Periodo Tarifario', 'consumo_kwh', 'porcentaje']].style.format({
                    'consumo_kwh': '{:.2f} kWh', 'porcentaje': '{:.1f} %'
                }), use_container_width=True, hide_index=True
            )
        with cols_tabla[1]:
            st.markdown("📋 **Nota de clasificación:** El algoritmo agrupa de forma dinámica las muestras analizando si el sello de tiempo corresponde a fin de semana/festivo (P6) o discrimina el tramo estacional según la matriz regulada.")

        st.divider()

        # =========================================================================
        # 6. HISTOGRAMA APILADO DEL DÍA ÓPTIMO REAL
        # =========================================================================
        fecha_mejor_dia = df_diario.loc[idx_max_aprov, 'fecha']
        st.subheader(f"📈 Perfil de Carga Horario del Día Óptimo Real ({fecha_mejor_dia.strftime('%d/%m/%Y')})")

        df_mejor_dia = df_plot[df_plot['fecha'] == fecha_mejor_dia].sort_values('time')
        horas_x = [f"{h}:00h" for h in df_mejor_dia['time'].dt.hour]

        fig_mejor_dia = go.Figure()
        fig_mejor_dia.add_trace(go.Bar(x=horas_x, y=df_mejor_dia['sc_wh'], name="Autoconsumo Directo", marker_color='#10b981'))
        fig_mejor_dia.add_trace(go.Bar(x=horas_x, y=df_mejor_dia['imp_wh'], name="Importación de Red", marker_color='#f97316'))
        fig_mejor_dia.add_trace(go.Bar(x=horas_x, y=df_mejor_dia['exp_wh'], name="Excedentes Vertidos", marker_color='#3b82f6'))

        fig_mejor_dia.update_layout(
            barmode='stack', template='plotly_white', height=360, margin=dict(l=0, r=0, t=10, b=0),
            xaxis=dict(title="Franja Horaria"), yaxis=dict(title="Energía Real (Wh)"),
            legend=dict(orientation='h', yanchor='bottom', y=-0.3, xanchor='center', x=0.5)
        )
        st.plotly_chart(fig_mejor_dia, use_container_width=True)

        # =========================================================================
        # 7. GENERACIÓN DEL BOTÓN DE DESCARGA PDF DEL REPORTE REAL
        # =========================================================================
        try:
            pdf_bytes = generar_pdf_auditoria(
                nombre_mes=nombre_mes, anio_mes=anio_mes,
                total_consumido_kwh=total_consumido_kwh, total_sc_kwh=total_sc_kwh,
                total_imp_kwh=total_imp_kwh, total_exp_kwh=total_exp_kwh,
                factor_ajuste=df_diario.loc[idx_max_aprov, 'aprovechamiento_pct'],
                d_max=df_diario.loc[idx_max_cons, 'fecha'].strftime('%d/%m/%Y'), v_max_kwh=df_diario.loc[idx_max_cons, 'consumo_kwh'],
                d_min=df_diario.loc[idx_min_cons, 'fecha'].strftime('%d/%m/%Y'), v_min_kwh=df_diario.loc[idx_min_cons, 'consumo_kwh'],
                d_aprov=df_diario.loc[idx_max_aprov, 'fecha'].strftime('%d/%m/%Y'), v_aprov=df_diario.loc[idx_max_aprov, 'aprovechamiento_pct'],
                df_tramos_datos=df_tramos
            )
            st.write(" ")
            st.download_button(
                label="📥 Descargar Informe de Auditoría Real en PDF",
                data=pdf_bytes,
                file_name=f"Auditoria_Real_{nombre_mes}_{anio_mes}.pdf",
                mime="application/pdf",
                use_container_width=True,
                key="btn_descarga_pdf_real"  
            )
        except Exception as e:
            st.error(f"⚠️ No se pudo precompilar el reporte PDF: {e}")

    st.divider()
    if st.button('🔄 Refrescar'): st.rerun()
