# streamlit_app.py — Registro de Traslados Papudo ↔ La Ligua
import os, io, json
from datetime import datetime, date
import pandas as pd
import streamlit as st

# ---------------------------- Config ----------------------------
st.set_page_config(page_title="Registro de Traslados — Papudo ↔ La Ligua", layout="wide")

# ---------------------------- Constantes / Defaults ----------------------------
DEFAULT_DRIVERS = ["Wilson", "Valentina"]
DEFAULT_PEOPLE  = ["Wilson", "Valentina", "Jp", "Gerard", "Paula"]
DEFAULT_FARE_CLP = 1250  # costo por tramo (Ida o Vuelta) por persona

LOCAL_CSV = "trips.csv"  # respaldo local si no hay Google Sheets

# ---------------------------- Helpers: Storage Backend ----------------------------
@st.cache_resource(show_spinner=False)
def get_storage():
    """Devuelve un dict con funciones save(df) y load() usando Google Sheets si hay secretos, 
    sino CSV local como fallback."""
    use_gsheets = False
    gsheets_ready = False
    try:
        secrets = st.secrets
        # Esperamos dos parámetros: gcp_service_account (json) y sheet_id (string)
        if "gcp_service_account" in secrets and "sheet_id" in secrets:
            import gspread
            from google.oauth2.service_account import Credentials
            info = secrets["gcp_service_account"]
            scopes = ["https://www.googleapis.com/auth/spreadsheets"]
            creds = Credentials.from_service_account_info(info, scopes=scopes)
            client = gspread.authorize(creds)
            sh = client.open_by_key(secrets["sheet_id"])
            try:
                ws = sh.worksheet("trips")
            except Exception:
                ws = sh.add_worksheet(title="trips", rows=1000, cols=20)
                # set headers
                ws.update("A1:F1", [["date","leg","driver","passengers","car","notes"]])
            gsheets_ready = True
            use_gsheets = True
    except Exception as e:
        gsheets_ready = False
        use_gsheets = False

    def load():
        if use_gsheets and gsheets_ready:
            import gspread
            try:
                ws = gspread.authorize(
                    __import__("google.oauth2.service_account", fromlist=['Credentials']).service_account.Credentials.from_service_account_info(
                        st.secrets["gcp_service_account"],
                        scopes=["https://www.googleapis.com/auth/spreadsheets"]
                    )
                ).open_by_key(st.secrets["sheet_id"]).worksheet("trips")
                values = ws.get_all_records()
                df = pd.DataFrame(values)
            except Exception:
                df = pd.DataFrame(columns=["date","leg","driver","passengers","car","notes"])
        else:
            if os.path.exists(LOCAL_CSV):
                df = pd.read_csv(LOCAL_CSV, dtype=str).fillna("")
            else:
                df = pd.DataFrame(columns=["date","leg","driver","passengers","car","notes"])
        # Sanear tipos
        if "date" in df.columns:
            # Normalizar a ISO yyyy-mm-dd
            try:
                df["date"] = pd.to_datetime(df["date"]).dt.date.astype(str)
            except Exception:
                pass
        for col in ["leg","driver","passengers","car","notes"]:
            if col in df.columns:
                df[col] = df[col].astype(str)
        return df

    def save(df: pd.DataFrame):
        df = df.copy()
        # Asegurar columnas
        base_cols = ["date","leg","driver","passengers","car","notes"]
        for c in base_cols:
            if c not in df.columns:
                df[c] = ""
        df = df[base_cols]
        if use_gsheets and gsheets_ready:
            import gspread
            client = gspread.authorize(
                __import__("google.oauth2.service_account", fromlist=['Credentials']).service_account.Credentials.from_service_account_info(
                    st.secrets["gcp_service_account"],
                    scopes=["https://www.googleapis.com/auth/spreadsheets"]
                )
            )
            sh = client.open_by_key(st.secrets["sheet_id"])
            try:
                ws = sh.worksheet("trips")
            except Exception:
                ws = sh.add_worksheet(title="trips", rows=len(df)+10, cols=len(df.columns)+2)
            # Limpiar y subir todo (simple y robusto para planillas pequeñas)
            ws.clear()
            ws.update("A1:F1", [df.columns.tolist()])
            if not df.empty:
                ws.update(f"A2:F{len(df)+1}", df.values.tolist())
        else:
            df.to_csv(LOCAL_CSV, index=False, encoding="utf-8")

    return {"load": load, "save": save, "use_gsheets": use_gsheets and gsheets_ready}

storage = get_storage()

# ---------------------------- State & Sidebar ----------------------------
if "fare" not in st.session_state:
    st.session_state.fare = DEFAULT_FARE_CLP

with st.sidebar:
    st.header("⚙️ Configuración")
    fare = st.number_input("Costo por tramo (CLP/persona)", min_value=0, value=st.session_state.fare, step=50)
    st.session_state.fare = int(fare)
    drivers = st.multiselect("Conductores", DEFAULT_DRIVERS, default=DEFAULT_DRIVERS)
    people  = st.multiselect("Personas", DEFAULT_PEOPLE, default=DEFAULT_PEOPLE)
    st.caption("💾 Almacenamiento: " + ("Google Sheets" if storage["use_gsheets"] else "CSV local"))
    st.markdown("---")
    st.write("**Ayuda rápida**")
    st.caption("• Un *tramo* es Ida **o** Vuelta.\n• Selecciona conductor/a y pasajeros transportados en ese tramo.")

df = storage["load"]()

# ---------------------------- UI: Alta de Viajes ----------------------------
st.title("🚗 Registro de Traslados — Papudo ↔ La Ligua")
st.write("Registra cada **tramo (Ida/Vuelta)** indicando **quién conduce** y **a quién transporta**.")

with st.expander("➕ Agregar tramo (Ida/Vuelta)", expanded=True):
    col1, col2, col3 = st.columns(3)
    with col1:
        ddate = st.date_input("Fecha", value=date.today())
        leg = st.selectbox("Tramo", options=["Ida","Vuelta"])
    with col2:
        driver = st.selectbox("Conductor/a", options=drivers)
        car = driver  # auto asociado al conductor (Wilson o Valentina)
    with col3:
        passengers = st.multiselect("Pasajeros transportados", options=[p for p in people if p != driver])
        notes = st.text_input("Notas (opcional)", value="")

    add_btn = st.button("Guardar tramo", type="primary", use_container_width=True)
    if add_btn:
        # Construir fila
        new_row = {
            "date": ddate.strftime("%Y-%m-%d"),
            "leg": leg,
            "driver": driver,
            "passengers": ",".join(passengers),
            "car": car,
            "notes": notes.strip()
        }
        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
        storage["save"](df)
        st.success("Tramo guardado.")

# ---------------------------- Tablas y Resúmenes ----------------------------
st.subheader("📋 Registro histórico")
st.dataframe(df.sort_values(["date","leg","driver"], ascending=[True, True, True]), use_container_width=True)

# Procesar montos por persona
def explode_passengers(df_in: pd.DataFrame) -> pd.DataFrame:
    if df_in.empty:
        return pd.DataFrame(columns=["date","leg","driver","passenger","fare"])
    rows = []
    for _, r in df_in.iterrows():
        plist = [p.strip() for p in str(r.get("passengers","")).split(",") if p.strip()]
        for p in plist:
            rows.append({
                "date": r["date"],
                "leg": r["leg"],
                "driver": r["driver"],
                "passenger": p,
                "fare": st.session_state.fare
            })
    return pd.DataFrame(rows)

pay_df = explode_passengers(df)
# Totales por día / mes / acumulado
if not pay_df.empty:
    pay_df["date"] = pd.to_datetime(pay_df["date"]).dt.date
    pay_df["month"] = pd.to_datetime(pay_df["date"]).to_period("M").astype(str)

colA, colB, colC = st.columns(3)
with colA:
    st.markdown("### 📅 Hoy")
    today = date.today()
    today_df = pay_df[pay_df["date"] == today] if not pay_df.empty else pd.DataFrame(columns=pay_df.columns if not pay_df.empty else [])
    if today_df.empty:
        st.info("Sin registros hoy.")
    else:
        st.metric("Total cobrado por conductores (hoy)", f"$ {int(today_df['fare'].sum()):,}".replace(",", "."))
        st.dataframe(today_df.groupby("driver")["fare"].sum().reset_index(name="cobro_hoy (CLP)"), use_container_width=True)

with colB:
    st.markdown("### 🗓️ Mes actual")
    if not pay_df.empty:
        month_key = date.today().strftime("%Y-%m")
        month_df = pay_df[pay_df["month"] == month_key]
    else:
        month_df = pd.DataFrame(columns=pay_df.columns if not pay_df.empty else [])
    if month_df.empty:
        st.info("Sin registros este mes.")
    else:
        st.metric("Total cobrado (mes)", f"$ {int(month_df['fare'].sum()):,}".replace(",", "."))
        st.dataframe(month_df.groupby("driver")["fare"].sum().reset_index(name="cobro_mes (CLP)"), use_container_width=True)

with colC:
    st.markdown("### 🧮 Acumulado")
    if pay_df.empty:
        st.info("Sin registros.")
    else:
        st.metric("Total acumulado", f"$ {int(pay_df['fare'].sum()):,}".replace(",", "."))
        st.dataframe(pay_df.groupby("driver")["fare"].sum().reset_index(name="cobro_total (CLP)"), use_container_width=True)

st.markdown("---")

# Saldos por persona (quién debe a quién)
st.subheader("💰 Saldos por persona")
if pay_df.empty:
    st.info("Agrega tramos para ver saldos.")
else:
    # Lo que cada pasajero debe a cada conductor
    owed = pay_df.groupby(["passenger","driver"])["fare"].sum().reset_index(name="monto (CLP)")

    # Totales por pasajero (deuda total) y por conductor (cobro total)
    deuda_por_pasajero = pay_df.groupby("passenger")["fare"].sum().reset_index(name="debe_total (CLP)")
    cobro_por_conductor = pay_df.groupby("driver")["fare"].sum().reset_index(name="cobra_total (CLP)")

    st.write("**Matriz Pasajero → Conductor (monto a pagar):**")
    pivot = owed.pivot_table(index="passenger", columns="driver", values="monto (CLP)", aggfunc="sum", fill_value=0)
    st.dataframe(pivot, use_container_width=True)

    col1, col2 = st.columns(2)
    with col1:
        st.write("**Deuda total por pasajero:**")
        st.dataframe(deuda_por_pasajero.sort_values("debe_total (CLP)", ascending=False), use_container_width=True)
    with col2:
        st.write("**Cobro total por conductor:**")
        st.dataframe(cobro_por_conductor.sort_values("cobra_total (CLP)", ascending=False), use_container_width=True)

    # Balance neto por persona (positivos = recibe, negativos = debe)
    personas = sorted(set(DEFAULT_PEOPLE + list(pivot.index) + list(pivot.columns)))
    balance = {p: 0 for p in personas}
    # Pasajeros pagan (negativo), conductores cobran (positivo)
    for _, r in owed.iterrows():
        balance[r["passenger"]] -= r["monto (CLP)"]
        balance[r["driver"]]    += r["monto (CLP)"]
    bal_df = pd.DataFrame([{"persona": k, "balance_neto (CLP)": v} for k, v in balance.items() if k != ""])
    st.write("**Balance neto por persona (positivo = recibir, negativo = pagar):**")
    st.dataframe(bal_df.sort_values("balance_neto (CLP)", ascending=False), use_container_width=True)

st.markdown("---")
st.subheader("⬇️ Exportar")
if not df.empty:
    # Exportar datos crudos y pagos
    raw_csv = df.to_csv(index=False).encode("utf-8")
    st.download_button("Descargar CSV (tramos)", raw_csv, file_name="trips.csv", mime="text/csv", use_container_width=True)
    if not pay_df.empty:
        pay_csv = pay_df.to_csv(index=False).encode("utf-8")
        st.download_button("Descargar CSV (pagos)", pay_csv, file_name="pagos.csv", mime="text/csv", use_container_width=True)
else:
    st.caption("No hay datos para exportar aún.")

st.markdown("---")
with st.expander("ℹ️ Cómo funciona el cálculo", expanded=False):
    st.write("""
    - Cada **tramo (Ida o Vuelta)** tiene un costo fijo **por persona** (por defecto $1.250 CLP).
    - Por cada pasajero registrado en un tramo:
      - Ese pasajero **debe** el monto del tramo (aparece en *Deuda total por pasajero*).
      - El **conductor** correspondiente **cobra** ese monto (aparece en *Cobro total por conductor*).
    - El **balance neto** combina ambos efectos para cada persona (cobros menos deudas).
    - Puedes ajustar el costo por tramo en la barra lateral.
    """)
