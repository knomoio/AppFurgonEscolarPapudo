# streamlit_app.py — Registro de Traslados (CSV local únicamente)
import os
from datetime import date
import pandas as pd
import streamlit as st

# ---------------------------- Config ----------------------------
st.set_page_config(page_title="Registro de Traslados — CSV local", layout="wide")

# ---------------------------- Constantes / Defaults ----------------------------
DEFAULT_DRIVERS = ["Wilson", "Valentina"]
DEFAULT_PEOPLE  = ["Wilson", "Valentina", "Jp", "Gerard", "Paula"]
DEFAULT_FARE_CLP = 1250  # costo por tramo (Ida o Vuelta) por persona

LOCAL_CSV = "trips.csv"  # archivo local

# ---------------------------- Helpers: CSV Storage ----------------------------
def load_csv(path: str) -> pd.DataFrame:
    if os.path.exists(path):
        try:
            df = pd.read_csv(path, dtype=str).fillna("")
        except Exception:
            df = pd.DataFrame(columns=["row_id","date","leg","driver","passengers","car","notes"])
    else:
        df = pd.DataFrame(columns=["row_id","date","leg","driver","passengers","car","notes"])
    # Asegurar columnas
    for c in ["row_id","date","leg","driver","passengers","car","notes"]:
        if c not in df.columns:
            df[c] = ""
    # Forzar row_id numérico si existe
    if not df.empty:
        df["row_id"] = pd.to_numeric(df["row_id"], errors="coerce").fillna(0).astype(int)
    return df

def save_csv(df: pd.DataFrame, path: str):
    base_cols = ["row_id","date","leg","driver","passengers","car","notes"]
    for c in base_cols:
        if c not in df.columns:
            df[c] = ""
    df = df[base_cols].copy()
    df.to_csv(path, index=False, encoding="utf-8")

# ---------------------------- State & Sidebar ----------------------------
if "fare" not in st.session_state:
    st.session_state.fare = DEFAULT_FARE_CLP

with st.sidebar:
    st.header("⚙️ Configuración")
    fare = st.number_input("Costo por tramo (CLP/persona)", min_value=0, value=st.session_state.fare, step=50)
    st.session_state.fare = int(fare)
    drivers = st.multiselect("Conductores", DEFAULT_DRIVERS, default=DEFAULT_DRIVERS)
    people  = st.multiselect("Personas", DEFAULT_PEOPLE, default=DEFAULT_PEOPLE)
    st.caption("💾 Almacenamiento: CSV local")
    st.caption(f"Archivo: {LOCAL_CSV}")
    st.markdown("---")
    st.write("**Ayuda rápida**")
    st.caption("• Un *tramo* es Ida **o** Vuelta.\n• Selecciona conductor/a y pasajeros transportados en ese tramo.")

df = load_csv(LOCAL_CSV)

# Garantizar columna identificadora estable para poder borrar/editar filas
if df.empty:
    next_id = 1
else:
    next_id = int(pd.to_numeric(df["row_id"], errors="coerce").fillna(0).max()) + 1

# ---------------------------- UI: Alta de Viajes ----------------------------
st.title("🚗 Registro de Traslados — CSV local")
st.write("Registra cada **tramo (Ida/Vuelta)** indicando **quién conduce** y **a quién transporta**.")

with st.expander("➕ Agregar tramo (Ida/Vuelta)", expanded=True):
    col1, col2, col3 = st.columns(3)
    with col1:
        ddate = st.date_input("Fecha", value=date.today())
        leg = st.selectbox("Tramo", options=["Ida","Vuelta"])
    with col2:
        driver = st.selectbox("Conductor/a", options=drivers)
        car = driver  # auto asociado al conductor
    with col3:
        passengers = st.multiselect("Pasajeros transportados", options=[p for p in people if p != driver])
        notes = st.text_input("Notas (opcional)", value="")

    add_btn = st.button("Guardar tramo", type="primary", use_container_width=True)
    if add_btn:
        if len(passengers) == 0:
            st.warning("Debes seleccionar al menos un pasajero.")
        else:
            new_row = {
                "row_id": next_id,
                "date": pd.to_datetime(ddate).strftime("%Y-%m-%d"),
                "leg": leg,
                "driver": driver,
                "passengers": ",".join(passengers),
                "car": car,
                "notes": notes.strip()
            }
            df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
            save_csv(df, LOCAL_CSV)
            st.success("Tramo guardado.")
            st.experimental_rerun()

# ---------------------------- Registro histórico (Editar/Eliminar) ----------------------------
st.subheader("📋 Registro histórico")
hist = df.sort_values(["date","leg","driver"], ascending=[True, True, True]).copy()
if "Eliminar" not in hist.columns:
    hist["Eliminar"] = False

display_cols = ["Eliminar","date","leg","driver","passengers","car","notes","row_id"]
display_cols = [c for c in display_cols if c in hist.columns]

# Column config
try:
    col_config = {
        "leg": st.column_config.SelectboxColumn("Tramo", options=["Ida","Vuelta"]),
        "driver": st.column_config.SelectboxColumn("Conductor/a", options=drivers),
        "passengers": st.column_config.TextColumn("Pasajeros (separa por coma)"),
        "date": st.column_config.TextColumn("Fecha (YYYY-MM-DD)"),
        "notes": st.column_config.TextColumn("Notas"),
        "car": st.column_config.TextColumn("Auto"),
        "row_id": st.column_config.NumberColumn("ID", disabled=True),
        "Eliminar": st.column_config.CheckboxColumn("Eliminar")
    }
except Exception:
    col_config = {}

edited = st.data_editor(
    hist[display_cols],
    use_container_width=True,
    num_rows="fixed",
    key="editor_hist",
    column_config=col_config
)

col_left, col_right = st.columns([1,1])
with col_left:
    save_btn = st.button("💾 Guardar cambios", type="primary", use_container_width=True)
with col_right:
    del_btn = st.button("🗑️ Eliminar seleccionados", type="secondary", use_container_width=True)

# Guardar cambios editados
if save_btn:
    updated = edited.copy()
    # Validaciones y normalizaciones
    if "date" in updated.columns:
        updated["date"] = pd.to_datetime(updated["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    # Auto por defecto = driver si viene vacío
    if "car" in updated.columns and "driver" in updated.columns:
        updated["car"] = updated.apply(lambda r: r["car"] if isinstance(r["car"], str) and r["car"].strip() else r["driver"], axis=1)
    # Aplicar cambios por row_id
    if "row_id" in updated.columns and "row_id" in df.columns:
        cols_to_update = [c for c in ["date","leg","driver","passengers","car","notes"] if c in updated.columns and c in df.columns]
        df = df.set_index("row_id")
        upd = updated.set_index("row_id")
        # Solo actualizar ids que existan
        inter = df.index.intersection(upd.index)
        df.loc[inter, cols_to_update] = upd.loc[inter, cols_to_update]
        df = df.reset_index()
        save_csv(df, LOCAL_CSV)
        st.success("Cambios guardados en CSV.")
        st.experimental_rerun()
    else:
        st.error("No se encontró 'row_id' para aplicar cambios.")

# Eliminar registros seleccionados
if del_btn:
    to_delete_ids = edited.loc[edited.get("Eliminar", False) == True, "row_id"].tolist() if "row_id" in edited.columns else []
    if to_delete_ids:
        new_df = df[~df["row_id"].isin(to_delete_ids)].copy()
        save_csv(new_df, LOCAL_CSV)
        st.success(f"Se eliminaron {len(to_delete_ids)} registro(s).")
        st.experimental_rerun()
    else:
        st.info("No hay registros marcados para eliminar.")

st.markdown("---")

# ---------------------------- Cálculos y Resúmenes ----------------------------
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
    pay_df["date"] = pd.to_datetime(pay_df["date"], errors="coerce")
    pay_df = pay_df.dropna(subset=["date"])
    pay_df["date"] = pay_df["date"].dt.normalize()
    pay_df["month"] = pay_df["date"].dt.to_period("M").astype(str)

colA, colB, colC = st.columns(3)
with colA:
    st.markdown("### 📅 Hoy")
    if pay_df.empty:
        st.info("Sin registros hoy.")
    else:
        today_ts = pd.Timestamp.today().normalize()
        today_df = pay_df[pay_df["date"] == today_ts]
        if today_df.empty:
            st.info("Sin registros hoy.")
        else:
            st.metric("Total cobrado por conductores (hoy)", f"$ {int(today_df['fare'].sum()):,}".replace(",", "."))
            st.dataframe(today_df.groupby("driver")["fare"].sum().reset_index(name="cobro_hoy (CLP)"), use_container_width=True)

with colB:
    st.markdown("### 🗓️ Mes actual")
    if pay_df.empty:
        st.info("Sin registros este mes.")
    else:
        month_key = pd.Timestamp.today().strftime("%Y-%m")
        month_df = pay_df[pay_df["month"] == month_key]
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
st.subheader("💰 Saldos por persona")
if pay_df.empty:
    st.info("Agrega tramos para ver saldos.")
else:
    owed = pay_df.groupby(["passenger","driver"])["fare"].sum().reset_index(name="monto (CLP)")
    pivot = owed.pivot_table(index="passenger", columns="driver", values="monto (CLP)", aggfunc="sum", fill_value=0)
    st.write("**Matriz Pasajero → Conductor (monto a pagar):**")
    st.dataframe(pivot, use_container_width=True)

    deuda_por_pasajero = pay_df.groupby("passenger")["fare"].sum().reset_index(name="debe_total (CLP)")
    cobro_por_conductor = pay_df.groupby("driver")["fare"].sum().reset_index(name="cobra_total (CLP)")

    col1, col2 = st.columns(2)
    with col1:
        st.write("**Deuda total por pasajero:**")
        st.dataframe(deuda_por_pasajero.sort_values("debe_total (CLP)", ascending=False), use_container_width=True)
    with col2:
        st.write("**Cobro total por conductor:**")
        st.dataframe(cobro_por_conductor.sort_values("cobra_total (CLP)", ascending=False), use_container_width=True)

    # Balance neto por persona
    personas = sorted(set(DEFAULT_PEOPLE + list(pivot.index) + list(pivot.columns)))
    balance = {p: 0 for p in personas}
    for _, r in owed.iterrows():
        balance[r["passenger"]] -= r["monto (CLP)"]
        balance[r["driver"]]    += r["monto (CLP)"]
    bal_df = pd.DataFrame([{"persona": k, "balance_neto (CLP)": v} for k, v in balance.items() if k != ""])
    st.write("**Balance neto por persona (positivo = recibir, negativo = pagar):**")
    st.dataframe(bal_df.sort_values("balance_neto (CLP)", ascending=False), use_container_width=True)

st.markdown("---")
st.subheader("⬇️ Exportar")
if not df.empty:
    raw_csv = df.to_csv(index=False).encode("utf-8")
    st.download_button("Descargar CSV (tramos)", raw_csv, file_name="trips.csv", mime="text/csv", use_container_width=True)
    if not pay_df.empty:
        pay_csv = pay_df.to_csv(index=False).encode("utf-8")
        st.download_button("Descargar CSV (pagos)", pay_csv, file_name="pagos.csv", mime="text/csv", use_container_width=True)
else:
    st.caption("No hay datos para exportar aún.")
