# streamlit_app.py — Registro de Traslados Papudo ↔ La Ligua
# Autor: Asistente de Wilson — 2025-10-28 (fix: define helpers antes de usarlos + filtros de fecha seguros)
# Descripción:
# App para registrar viajes diarios entre Papudo y La Ligua usando 2 autos (Wilson y Valentina)
# con 5 personas participantes: JP, Gerard, Paula, Wilson y Valentina. Permite:
# - Ingresar viajes (ida, vuelta o ida y vuelta), conductor y pasajeros
# - Configurar tarifa por tramo (por persona) y si el conductor participa del prorrateo
# - Ver el historial y filtros por fecha/conductor
# - Resúmenes: totales por conductor, totales adeudados por persona, y matriz Pasajero→Conductor
# - Exportar/Importar CSV; Exportar a Excel con hojas de datos y resúmenes

import io
from datetime import date, datetime
from typing import List

import pandas as pd
import streamlit as st

# ---------------------------- Config ----------------------------
st.set_page_config(
    page_title="Registro Traslados Papudo – La Ligua",
    page_icon="🚗",
    layout="wide",
)

PARTICIPANTES: List[str] = ["JP", "Gerard", "Paula", "Wilson", "Valentina"]
CONDUCTORES: List[str] = ["Wilson", "Valentina"]

# Columnas y claves
COLS = [
    "id",               # int autoincremental
    "fecha",            # yyyy-mm-dd
    "conductor",        # Wilson | Valentina
    "tramo",            # Ida | Vuelta
    "pasajeros",        # lista separada por ; (sin el conductor)
    "tarifa_por_tramo", # CLP por persona por tramo
    "n_pasajeros",      # int
    "monto_al_conductor"# CLP (tarifa * n_pasajeros)
]


# ---------------------------- Helpers (definidos antes de ser usados) ----------------------------

def _clean_df(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    # Tipos
    if "fecha" in df.columns:
        df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce").dt.date
    if "tarifa_por_tramo" in df.columns:
        df["tarifa_por_tramo"] = pd.to_numeric(df["tarifa_por_tramo"], errors="coerce").fillna(0).astype(int)
    if "n_pasajeros" in df.columns:
        df["n_pasajeros"] = pd.to_numeric(df["n_pasajeros"], errors="coerce").fillna(0).astype(int)
    if "monto_al_conductor" in df.columns:
        df["monto_al_conductor"] = pd.to_numeric(df["monto_al_conductor"], errors="coerce").fillna(0).astype(int)
    return df


def _explode_pasajeros(df: pd.DataFrame) -> pd.DataFrame:
    """Devuelve un DataFrame con una fila por pasajero por tramo, y la columna 'monto'."""
    if df.empty:
        return pd.DataFrame(columns=["fecha", "conductor", "tramo", "pasajero", "monto"])  
    e = df.copy()
    e["pasajeros_list"] = e["pasajeros"].fillna("").apply(lambda s: [p for p in s.split(";") if p])
    e = e.explode("pasajeros_list").rename(columns={"pasajeros_list": "pasajero"})
    e["monto"] = e["tarifa_por_tramo"].astype(int)
    return e[["fecha", "conductor", "tramo", "pasajero", "monto"]]


def _pivot_pasajero_conductor(expl: pd.DataFrame) -> pd.DataFrame:
    if expl is None or expl.empty:
        return pd.DataFrame(index=PARTICIPANTES, columns=CONDUCTORES).fillna(0).astype(int)
    pvt = expl.pivot_table(index="pasajero", columns="conductor", values="monto", aggfunc="sum", fill_value=0)
    # Reordenar filas/columnas para consistencia
    pvt = pvt.reindex(index=PARTICIPANTES, fill_value=0)
    pvt = pvt.reindex(columns=CONDUCTORES, fill_value=0)
    return pvt.astype(int)


def _append_rows(rows: List[dict]):
    if not rows:
        return
    # Asignar IDs autoincrementales
    for r in rows:
        r["id"] = st.session_state.next_id
        st.session_state.next_id += 1
    df_new = pd.DataFrame(rows)
    st.session_state.data = pd.concat([st.session_state.data, df_new], ignore_index=True)


def _init_state():
    if "data" not in st.session_state:
        st.session_state.data = pd.DataFrame(columns=COLS)
    # IDs
    if "next_id" not in st.session_state:
        if "id" in st.session_state.data.columns and not st.session_state.data.empty:
            st.session_state.next_id = int(pd.to_numeric(st.session_state.data["id"], errors="coerce").fillna(0).max()) + 1
        else:
            st.session_state.next_id = 1
    if "cfg_tarifa" not in st.session_state:
        st.session_state.cfg_tarifa = 1250  # CLP por persona por tramo
    if "cfg_incluir_conductor" not in st.session_state:
        st.session_state.cfg_incluir_conductor = False  # por defecto, el conductor NO paga

# Persistimos configuración
st.session_state.cfg_tarifa = tarifa_default
st.session_state.cfg_incluir_conductor = incluir_conductor

st.sidebar.divider()
st.sidebar.subheader("📁 Importar / Exportar")
up = st.sidebar.file_uploader("Importar CSV de viajes", type=["csv"], help="Debe contener las columnas del dataset de esta app.")
if up is not None:
    try:
        df_up = pd.read_csv(up)
        df_up = _clean_df(df_up)
        # Asegurar columnas e IDs
        for c in COLS:
            if c not in df_up.columns:
                df_up[c] = None
        # Si no hay id, generar
        if df_up["id"].isna().all() or (df_up["id"].astype(str) == "").all():
            if "id" in df_up.columns:
                df_up = df_up.drop(columns=["id"])
            df_up.insert(0, "id", range(st.session_state.next_id, st.session_state.next_id + len(df_up)))
            st.session_state.next_id += len(df_up)
        else:
            # Mantener next_id coherente
            max_id = int(pd.to_numeric(df_up["id"], errors="coerce").fillna(0).max())
            st.session_state.next_id = max(st.session_state.next_id, max_id + 1)
        st.session_state.data = df_up[COLS]
        st.sidebar.success("Archivo cargado correctamente.")("Archivo cargado correctamente.")
    except Exception as e:
        st.sidebar.error(f"No se pudo importar el CSV: {e}")

# Botón descargar CSV actual
csv_bytes = st.session_state.data.to_csv(index=False).encode("utf-8")
st.sidebar.download_button(
    label="💾 Descargar CSV",
    data=csv_bytes,
    file_name="traslados_papudo_laligua.csv",
    mime="text/csv",
)

st.sidebar.caption("*El CSV incluye la columna* `id` *para poder editar/eliminar con seguridad.*")

# Exportar a Excel con hojas (Datos, Resumen por Conductor, Resumen por Persona, Matriz)
if st.sidebar.button("⬇️ Exportar Excel (con resúmenes)"):
    try:
        df = _clean_df(st.session_state.data)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Datos")
            # Resúmenes
            if not df.empty:
                df_sum_conductor = df.groupby("conductor", as_index=False)["monto_al_conductor"].sum().rename(columns={"monto_al_conductor":"Total a cobrar"})
                expl = _explode_pasajeros(df)
                df_sum_persona = expl.groupby("pasajero", as_index=False)["monto"].sum().rename(columns={"monto":"Total adeudado"})
                matriz = _pivot_pasajero_conductor(expl)
                df_sum_conductor.to_excel(writer, index=False, sheet_name="Resumen Conductor")
                df_sum_persona.to_excel(writer, index=False, sheet_name="Resumen Persona")
                matriz.to_excel(writer, sheet_name="Matriz Pasajero→Conductor")
        st.sidebar.download_button(
            label="Descargar Excel",
            data=output.getvalue(),
            file_name="traslados_papudo_laligua.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    except Exception as e:
        st.sidebar.error(f"No se pudo generar el Excel: {e}")

# ---------------------------- Ingreso de viajes ----------------------------
st.title("🚗 Registro de Traslados — Papudo ↔ La Ligua")
st.caption("Versión con correcciones: helpers definidos antes de su uso y filtros de fecha opcionales.")

with st.expander("➕ Agregar viaje", expanded=True):
    c1, c2, c3, c4 = st.columns([1,1,1,2])
    with c1:
        fecha = st.date_input("Fecha", value=date.today(), format="DD/MM/YYYY")
    with c2:
        conductor = st.selectbox("Conductor", CONDUCTORES)
    with c3:
        tipo = st.selectbox("Tipo de viaje", ["Ida", "Vuelta", "Ida y Vuelta"], index=2)
    with c4:
        tarifa = st.number_input("Tarifa por tramo (CLP)", min_value=0, step=50, value=st.session_state.cfg_tarifa)

    opciones_pasajeros = [p for p in PARTICIPANTES if (st.session_state.cfg_incluir_conductor or p != conductor)]
    default_pasajeros = [p for p in opciones_pasajeros if p != conductor]
    pasajeros = st.multiselect("Pasajeros que viajaron en este auto", opciones_pasajeros, default=default_pasajeros)

    if st.button("Agregar al registro"):
        if len(pasajeros) == 0:
            st.warning("Debes seleccionar al menos 1 pasajero (aparte del conductor) o activar 'Incluir conductor'.")
        else:
            rows = []
            legs = ["Ida", "Vuelta"] if tipo == "Ida y Vuelta" else [tipo]
            for leg in legs:
                n_p = len(pasajeros)
                monto = int(tarifa) * n_p
                rows.append({
                    "fecha": fecha,
                    "conductor": conductor,
                    "tramo": leg,
                    "pasajeros": ";".join(pasajeros),
                    "tarifa_por_tramo": int(tarifa),
                    "n_pasajeros": n_p,
                    "monto_al_conductor": monto,
                })
            _append_rows(rows)
            st.success(f"Se registró {tipo} — Conductor: {conductor} — Pasajeros: {', '.join(pasajeros)}")}")

# ---------------------------- Historial + Filtros ----------------------------
st.subheader("📜 Historial de viajes")

f0, f1, f2, f3 = st.columns([0.8,1,1,1.2])
with f0:
    usar_filtros = st.checkbox("Activar filtros de fecha", value=False)
with f1:
    desde = st.date_input("Desde", value=date.today()) if usar_filtros else None
with f2:
    hasta = st.date_input("Hasta", value=date.today()) if usar_filtros else None
with f3:
    filtro_conductor = st.multiselect("Conductor", CONDUCTORES, default=CONDUCTORES)

_df = _clean_df(st.session_state.data)
if usar_filtros and desde:
    _df = _df[_df["fecha"] >= desde]
if usar_filtros and hasta:
    _df = _df[_df["fecha"] <= hasta]
if filtro_conductor:
    _df = _df[_df["conductor"].isin(filtro_conductor)]

_df = _df.sort_values(["fecha", "conductor", "tramo"]).reset_index(drop=True)
st.dataframe(_df, use_container_width=True)

# -------- Acciones: Eliminar y Editar --------
st.markdown("### 🗑️ Eliminar filas")
ids_disp = _df["id"].tolist()
sel_del = st.multiselect("Selecciona IDs a eliminar", ids_disp, placeholder="IDs…")
if st.button("Eliminar seleccionadas") and sel_del:
    before = len(st.session_state.data)
    st.session_state.data = st.session_state.data[~st.session_state.data["id"].isin(sel_del)].reset_index(drop=True)
    st.success(f"Eliminadas {before - len(st.session_state.data)} filas (por ID).")

st.markdown("### ✏️ Editar fila")
edit_id = st.selectbox("ID a editar", ids_disp, placeholder="Elige un ID") if ids_disp else None
if edit_id is not None:
    row = st.session_state.data.loc[st.session_state.data["id"] == edit_id].iloc[0]
    c1,c2,c3,c4 = st.columns([1,1,1,2])
    with c1:
        e_fecha = st.date_input("Fecha (edición)", value=pd.to_datetime(row["fecha"]).date() if pd.notna(row["fecha"]) else date.today(), format="DD/MM/YYYY", key=f"e_fecha_{edit_id}")
    with c2:
        e_conductor = st.selectbox("Conductor (edición)", CONDUCTORES, index=CONDUCTORES.index(row["conductor"]) if row["conductor"] in CONDUCTORES else 0, key=f"e_cond_{edit_id}")
    with c3:
        e_tramo = st.selectbox("Tramo (edición)", ["Ida", "Vuelta"], index=0 if row["tramo"]=="Ida" else 1, key=f"e_tramo_{edit_id}")
    with c4:
        e_tarifa = st.number_input("Tarifa por tramo (edición)", min_value=0, step=50, value=int(row["tarifa_por_tramo"]) if pd.notna(row["tarifa_por_tramo"]) else st.session_state.cfg_tarifa, key=f"e_tarifa_{edit_id}")

    actuales = [p for p in str(row["pasajeros"]).split(";") if p]
    opciones_pas = [p for p in PARTICIPANTES if (st.session_state.cfg_incluir_conductor or p != e_conductor)]
    e_pasajeros = st.multiselect("Pasajeros (edición)", opciones_pas, default=[p for p in actuales if p in opciones_pas], key=f"e_pas_{edit_id}")

    if st.button("Guardar cambios", key=f"save_{edit_id}"):
        n_p = len(e_pasajeros)
        monto = int(e_tarifa) * n_p
        idx = st.session_state.data.index[st.session_state.data["id"] == edit_id][0]
        st.session_state.data.loc[idx, ["fecha","conductor","tramo","pasajeros","tarifa_por_tramo","n_pasajeros","monto_al_conductor"]] = [
            e_fecha,
            e_conductor,
            e_tramo,
            ";".join(e_pasajeros),
            int(e_tarifa),
            n_p,
            monto,
        ]
        st.success(f"Fila ID {edit_id} actualizada.").reset_index(drop=True), use_container_width=True)

# ---------------------------- Resúmenes ----------------------------
st.subheader("📈 Resúmenes")

if _df.empty:
    st.info("Aún no hay datos para resumir.")
else:
    colr1, colr2 = st.columns(2)

    with colr1:
        st.markdown("**Total a cobrar por conductor (CLP)**")
        sum_c = _df.groupby("conductor", as_index=False)["monto_al_conductor"].sum()
        st.dataframe(sum_c, use_container_width=True)

    with colr2:
        st.markdown("**Total adeudado por persona (CLP)**")
        expl = _explode_pasajeros(_df)
        sum_p = expl.groupby("pasajero", as_index=False)["monto"].sum()
        # Asegurar que todas las personas aparezcan aunque no tengan deuda
        sum_p = sum_p.set_index("pasajero").reindex(PARTICIPANTES, fill_value=0).reset_index()
        st.dataframe(sum_p, use_container_width=True)

    st.markdown("**Matriz Pasajero → Conductor (cuánto le debe cada persona a cada conductor, CLP)**")
    matriz = _pivot_pasajero_conductor(expl)
    st.dataframe(matriz, use_container_width=True)

    st.markdown("**Conteo de tramos por conductor**")
    cnt = _df.groupby(["conductor", "tramo"]).size().reset_index(name="tramos")
    st.dataframe(cnt, use_container_width=True)

# ---------------------------- Notas de uso ----------------------------
st.markdown(
    """
    ---
    **Notas**
    - *Tarifa:* por defecto es CLP 1.250 por **tramo** (Ida o Vuelta) por **pasajero**. Cambia esto en la barra lateral.
    - *Prorrateo:* por defecto el **conductor no paga** su propio cupo. Puedes cambiar esa regla en la barra lateral.
    - *Edición/Corrección:* descarga el CSV, edítalo y vuelve a importarlo si necesitas ajustes masivos.
    - *Exportación:* usa el botón de la barra lateral para generar un Excel con hojas de datos y resúmenes.
    """
)
