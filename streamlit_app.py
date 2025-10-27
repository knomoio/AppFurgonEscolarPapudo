# streamlit_app.py — Registro de Traslados (CSV local con enlace directo)
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

# ---------------------------- Helpers ----------------------------
def load_csv(path: str) -> pd.DataFrame:
    if os.path.exists(path):
        try:
            df = pd.read_csv(path, dtype=str).fillna("")
        except Exception:
            df = pd.DataFrame(columns=["row_id","date","leg","driver","passengers","car","notes"])
    else:
        df = pd.DataFrame(columns=["row_id","date","leg","driver","passengers","car","notes"])
    for c in ["row_id","date","leg","driver","passengers","car","notes"]:
        if c not in df.columns:
            df[c] = ""
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

def do_rerun():
    try:
        st.rerun()
    except Exception:
        if hasattr(st, "experimental_rerun"):
            st.experimental_rerun()

# ---------------------------- Sidebar ----------------------------

with st.sidebar:
    st.header("⚙️ Configuración")

    fare = st.number_input("Costo por tramo (CLP/persona)", min_value=0, value=DEFAULT_FARE_CLP, step=50)
    st.session_state.fare = int(fare)
    drivers = st.multiselect("Conductores", DEFAULT_DRIVERS, default=DEFAULT_DRIVERS)
    people  = st.multiselect("Personas", DEFAULT_PEOPLE, default=DEFAULT_PEOPLE)

    st.markdown("---")

    abs_path = os.path.abspath(LOCAL_CSV)
    st.markdown("💾 **Almacenamiento:** CSV local")
    if os.path.exists(LOCAL_CSV):
        # Ofrecer descarga directa (más confiable que file:// en la nube)
        try:
            csv_bytes = open(LOCAL_CSV, "rb").read()
            # Descarga del archivo actual
            st.download_button("⬇️ Descargar trips.csv (actual)", data=csv_bytes, file_name="trips.csv", mime="text/csv", use_container_width=True)
            # Copia de seguridad con fecha
            from datetime import datetime
            stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
            st.download_button("🧭 Copia de seguridad (con fecha)", data=csv_bytes, file_name=f"trips_{stamp}.csv", mime="text/csv", use_container_width=True)
        except Exception:
            st.caption("No se pudo leer el archivo para descarga.")
        st.caption(f"Ruta completa:\n`{abs_path}`")
        # --- Restaurar desde CSV de respaldo ---
        st.markdown("#### Restaurar desde respaldo")
        up = st.file_uploader("Selecciona un CSV de respaldo", type=["csv"], accept_multiple_files=False, key="restore_csv")
        if up is not None:
            st.caption("El archivo se validará y reemplazará el dataset actual.")
            confirm = st.checkbox("Confirmo que deseo **reemplazar** los datos actuales con este respaldo.", key="restore_confirm")
            if confirm and st.button("🔁 Restaurar ahora", type="secondary", use_container_width=True):
                try:
                    import pandas as pd
                    tmp = pd.read_csv(up, dtype=str).fillna("")
                    # Validación y normalización de columnas
                    required = ["row_id","date","leg","driver","passengers","car","notes"]
                    for c in required:
                        if c not in tmp.columns:
                            tmp[c] = ""
                    # Normalizar tipos
                    tmp["row_id"] = pd.to_numeric(tmp["row_id"], errors="coerce").fillna(0).astype(int)
                    if (tmp["row_id"] == 0).any():
                        # Reasignar IDs si faltan o vienen inválidos
                        tmp = tmp.drop(columns=["row_id"])
                        tmp.insert(0, "row_id", range(1, len(tmp)+1))
                    # Fechas a ISO
                    tmp["date"] = pd.to_datetime(tmp["date"], errors="coerce").dt.strftime("%Y-%m-%d")
                    # Auto por defecto = driver si está vacío
                    tmp["car"] = tmp.apply(lambda r: r["car"] if isinstance(r["car"], str) and r["car"].strip() else r["driver"], axis=1)
                    # Orden de columnas
                    tmp = tmp[required]
                    # Guardar y recargar
                    save_csv(tmp, LOCAL_CSV)
                    st.success("Respaldo restaurado correctamente.")
                    do_rerun()
                except Exception as e:
                    st.error(f"No se pudo restaurar el CSV: {e}")

    else:
        st.caption("📁 El archivo se creará automáticamente cuando guardes el **primer tramo**.")
        st.caption(f"Ruta prevista:\n`{abs_path}`")

    st.markdown("---")
    st.write("**Ayuda rápida**")
    st.caption("• Un *tramo* es Ida **o** Vuelta.\n• Selecciona conductor/a y pasajeros transportados en ese tramo.")
