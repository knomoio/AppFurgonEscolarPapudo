# streamlit_app.py — Registro de Traslados Papudo ↔ La Ligua
# Autor: Asistente de Wilson — 2025-11-17 (edición, eliminación, Excel y Google Sheets con autoguardado)
# Características:
# - Ingresar viajes (Ida, Vuelta, Ida y Vuelta) con conductor y pasajeros
# - Tarifa configurable por tramo y opción de incluir al conductor en el prorrateo
# - Historial con filtros por fecha y conductor
# - Editar y eliminar filas con IDs autoincrementales
# - Resúmenes: total por conductor, total adeudado por persona y matriz Pasajero→Conductor
# - Importar/Exportar CSV y exportar Excel con hojas de datos y resúmenes (openpyxl o XlsxWriter)
# - Sincronización manual y autoguardado con Google Sheets (gspread + google-auth)

import io
from datetime import date
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

# ---------------------------- Helpers (definidos antes de su uso) ----------------------------

def _clean_df(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    # Asegurar columnas
    for c in COLS:
        if c not in df.columns:
            df[c] = None
    # Tipos
    df["id"] = pd.to_numeric(df["id"], errors="coerce").astype("Int64")
    df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce").dt.date
    df["tarifa_por_tramo"] = pd.to_numeric(df["tarifa_por_tramo"], errors="coerce").fillna(0).astype(int)
    df["n_pasajeros"] = pd.to_numeric(df["n_pasajeros"], errors="coerce").fillna(0).astype(int)
    df["monto_al_conductor"] = pd.to_numeric(df["monto_al_conductor"], errors="coerce").fillna(0).astype(int)
    # Orden columnas
    return df[COLS]


def _explode_pasajeros(df: pd.DataFrame) -> pd.DataFrame:
    """Fila por pasajero por tramo, con columna 'monto' (= tarifa_por_tramo)."""
    if df is None or df.empty:
        return pd.DataFrame(columns=["fecha", "conductor", "tramo", "pasajero", "monto"])
    e = df.copy()
    e["pasajeros_list"] = e["pasajeros"].fillna("").apply(lambda s: [p for p in str(s).split(";") if p])
    e = e.explode("pasajeros_list").rename(columns={"pasajeros_list": "pasajero"})
    if e.empty:
        return pd.DataFrame(columns=["fecha", "conductor", "tramo", "pasajero", "monto"])
    e["monto"] = e["tarifa_por_tramo"].astype(int)
    return e[["fecha", "conductor", "tramo", "pasajero", "monto"]]


def _pivot_pasajero_conductor(expl: pd.DataFrame) -> pd.DataFrame:
    if expl is None or expl.empty:
        return pd.DataFrame(index=PARTICIPANTES, columns=CONDUCTORES).fillna(0).astype(int)
    pvt = expl.pivot_table(index="pasajero", columns="conductor", values="monto", aggfunc="sum", fill_value=0)
    pvt = pvt.reindex(index=PARTICIPANTES, fill_value=0)
    pvt = pvt.reindex(columns=CONDUCTORES, fill_value=0)
    return pvt.astype(int)


def _append_rows(rows: List[dict]):
    if not rows:
        return
    # Asignar IDs autoincrementales
    for r in rows:
        r["id"] = int(st.session_state.next_id)
        st.session_state.next_id += 1
    df_new = pd.DataFrame(rows)
    st.session_state.data = pd.concat([st.session_state.data, df_new], ignore_index=True)
    st.session_state.dirty = True  # marcar cambios para autoguardado


def _init_state():
    if "data" not in st.session_state:
        st.session_state.data = pd.DataFrame(columns=COLS)
    if "next_id" not in st.session_state:
        if not st.session_state.data.empty and "id" in st.session_state.data.columns:
            max_id = pd.to_numeric(st.session_state.data["id"], errors="coerce").fillna(0).max()
            st.session_state.next_id = int(max_id) + 1
        else:
            st.session_state.next_id = 1
    if "cfg_tarifa" not in st.session_state:
        st.session_state.cfg_tarifa = 1250
    if "cfg_incluir_conductor" not in st.session_state:
        st.session_state.cfg_incluir_conductor = False
    if "dirty" not in st.session_state:
        st.session_state.dirty = False

# ---------------------------- Sidebar (configuración, archivos y cloud) ----------------------------
_init_state()
st.sidebar.header("⚙️ Configuración")
colA, colB = st.sidebar.columns(2)
with colA:
    tarifa_default = st.number_input(
        "Tarifa por tramo (CLP)",
        min_value=0,
        step=50,
        value=int(st.session_state.cfg_tarifa),
        help="Monto que paga cada pasajero por cada tramo (Ida o Vuelta).",
    )
with colB:
    incluir_conductor = st.checkbox(
        "Incluir conductor en prorrateo",
        value=bool(st.session_state.cfg_incluir_conductor),
        help="Si está activado, el conductor también paga su propio cupo.",
    )

# Persistir configuración
st.session_state.cfg_tarifa = int(tarifa_default)
st.session_state.cfg_incluir_conductor = bool(incluir_conductor)

st.sidebar.divider()
st.sidebar.subheader("📁 Importar / Exportar")
# ⬇️ Importación controlada por botón para evitar que el uploader reescriba el estado en cada rerun
up = st.sidebar.file_uploader(
    "Importar CSV de viajes",
    type=["csv"],
    help="Seleccione el archivo y luego presione 'Cargar CSV en memoria' para aplicar.",
    key="u_csv",
)
if "csv_loaded_once" not in st.session_state:
    st.session_state.csv_loaded_once = False

if up is not None:
    st.sidebar.info(f"Archivo seleccionado: {up.name}")
    if st.sidebar.button("Cargar CSV en memoria", key="btn_load_csv"):
        try:
            df_up = pd.read_csv(up)
            df_up = _clean_df(df_up)
            # IDs coherentes
            if df_up["id"].isna().all():
                if "id" in df_up.columns:
                    df_up = df_up.drop(columns=["id"])
                df_up.insert(0, "id", range(st.session_state.next_id, st.session_state.next_id + len(df_up)))
                st.session_state.next_id += len(df_up)
            else:
                max_id = int(pd.to_numeric(df_up["id"], errors="coerce").fillna(0).max())
                st.session_state.next_id = max(st.session_state.next_id, max_id + 1)
            st.session_state.data = _clean_df(df_up)
            st.session_state.csv_loaded_once = True
            st.session_state.dirty = True
            st.sidebar.success("Archivo cargado en memoria correctamente.")
            st.rerun()
        except Exception as e:
            st.sidebar.error(f"No se pudo importar el CSV: {e}")

# Descargar CSV actual
_df_export = _clean_df(st.session_state.data).copy()
if not _df_export.empty:
    _df_export["id"] = pd.to_numeric(_df_export["id"], errors="coerce").fillna(0).astype(int)
csv_bytes = _df_export.to_csv(index=False).encode("utf-8")
st.sidebar.download_button(
    label="💾 Descargar CSV",
    data=csv_bytes,
    file_name="traslados_papudo_laligua.csv",
    mime="text/csv",
    key="btn_dl_csv",
)

st.sidebar.caption("*El CSV incluye la columna* `id` *para poder editar/eliminar con seguridad.*")

# ---------------------------- Exportar Excel (Datos + Resúmenes) ----------------------------
# Detección de motor Excel (openpyxl o xlsxwriter)
_engine_excel = None
_excel_hint = None
try:
    import openpyxl  # type: ignore
    _engine_excel = "openpyxl"
except Exception:
    try:
        import xlsxwriter  # type: ignore
        _engine_excel = "xlsxwriter"
    except Exception:
        _engine_excel = None
        _excel_hint = "Instala uno de estos: pip install openpyxl  —o—  pip install XlsxWriter"

if _engine_excel is None:
    st.sidebar.error("Para exportar a Excel instala una librería de Excel. " + (_excel_hint or ""))
else:
    st.sidebar.success(f"Motor Excel disponible: {_engine_excel}")

if st.sidebar.button("⬇️ Exportar Excel (con resúmenes)"):
    if _engine_excel is None:
        st.sidebar.warning("Instala openpyxl o XlsxWriter y vuelve a intentar.")
    else:
        try:
            df = _clean_df(st.session_state.data)
            if not df.empty:
                df["id"] = pd.to_numeric(df["id"], errors="coerce").fillna(0).astype(int)
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine=_engine_excel) as writer:
                df.to_excel(writer, index=False, sheet_name="Datos")
                if not df.empty:
                    df_sum_conductor = df.groupby("conductor", as_index=False)["monto_al_conductor"].sum().rename(
                        columns={"monto_al_conductor": "Total a cobrar"}
                    )
                    expl = _explode_pasajeros(df)
                    df_sum_persona = expl.groupby("pasajero", as_index=False)["monto"].sum().rename(
                        columns={"monto": "Total adeudado"}
                    )
                    matriz = _pivot_pasajero_conductor(expl)
                    df_sum_conductor.to_excel(writer, index=False, sheet_name="Resumen Conductor")
                    df_sum_persona.to_excel(writer, index=False, sheet_name="Resumen Persona")
                    matriz.to_excel(writer, sheet_name="Matriz Pasajero→Conductor")
            st.sidebar.download_button(
                label="Descargar Excel",
                data=output.getvalue(),
                file_name="traslados_papudo_laligua.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="dl_xlsx",
            )
        except Exception as e:
            st.sidebar.error(f"No se pudo generar el Excel: {e}")

# ---------------------------- Google Sheets (sincronización y autoguardado) ----------------------------
# Requisitos en requirements.txt: gspread, google-auth
# Secrets esperados en Streamlit (Manage app → Settings → Secrets):
# [gcp_service_account]
# type = "service_account"
# private_key = "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
# client_email = "<service-account>@<project>.iam.gserviceaccount.com"
# token_uri = "https://oauth2.googleapis.com/token"
# [gsheets]
# SPREADSHEET_ID = "<ID del Google Sheet>"

try:
    from google.oauth2.service_account import Credentials  # type: ignore
    import gspread  # type: ignore
    _has_gsheets_libs = True
except Exception:
    _has_gsheets_libs = False

st.sidebar.divider()
st.sidebar.subheader("☁️ Google Sheets")

# ID por defecto desde secrets o el provisto por el usuario
_default_sheet_id = None
try:
    _default_sheet_id = st.secrets.get("gsheets", {}).get("SPREADSHEET_ID")
except Exception:
    _default_sheet_id = None

# Valor por defecto: el ID que nos compartiste
default_from_user = "1NFu3KET3AcR_B4jlnrbJnle0LkkDOV3UOEiK0xEnaFY"
spreadsheet_id = st.sidebar.text_input(
    "Spreadsheet ID",
    value=_default_sheet_id or default_from_user,
    placeholder="Ej: 1NFu3KET3AcR_B4jlnrbJnle0LkkDOV3UOEiK0xEnaFY",
    help="Pega el ID del Google Sheet (entre /d/ y /edit) y comparte la hoja con el service account.",
)
ws_name = st.sidebar.text_input("Hoja (worksheet)", value=st.session_state.get("ws_name", "Datos"))
st.session_state.ws_name = ws_name

auto_save = st.sidebar.checkbox("Auto-guardar en Sheets", value=st.session_state.get("auto_save", False))
st.session_state.auto_save = auto_save

_gsheets_ready = _has_gsheets_libs and bool(spreadsheet_id)
if not _has_gsheets_libs:
    st.sidebar.info("Para sincronizar: agrega a requirements.txt → gspread, google-auth")
elif not spreadsheet_id:
    st.sidebar.warning("Ingresa el Spreadsheet ID para habilitar la sincronización.")

if _gsheets_ready:
    def _gsheets_client():
        scope = ["https://www.googleapis.com/auth/spreadsheets"]
        creds = Credentials.from_service_account_info(dict(st.secrets["gcp_service_account"]), scopes=scope)
        return gspread.authorize(creds)

    def _gsheets_open(ws_title: str):
        gc = _gsheets_client()
        sh = gc.open_by_key(spreadsheet_id)
        try:
            ws = sh.worksheet(ws_title)
        except gspread.exceptions.WorksheetNotFound:
            ws = sh.add_worksheet(title=ws_title, rows="1000", cols=str(len(COLS)))
            ws.update("A1", [COLS])
        return ws

    def _to_sheet_values(df: pd.DataFrame) -> list:
        d = _clean_df(df).copy()
        if not d.empty:
            d["id"] = pd.to_numeric(d["id"], errors="coerce").fillna(0).astype(int)
            d["fecha"] = pd.to_datetime(d["fecha"], errors="coerce").dt.strftime("%Y-%m-%d")
        return [COLS] + d.astype(object).where(pd.notna(d), "").values.tolist()

    def _from_sheet_values(values: list) -> pd.DataFrame:
        if not values:
            return pd.DataFrame(columns=COLS)
        header, rows = values[0], values[1:]
        df = pd.DataFrame(rows, columns=header)
        return _clean_df(df)

    def _save_to_sheets():
        try:
            ws = _gsheets_open(ws_name)
            ws.clear()
            ws.update("A1", _to_sheet_values(st.session_state.data))
            return True, None
        except Exception as e:
            return False, str(e)

    # 🔍 Probar conexión
    if st.sidebar.button("🔍 Probar conexión", key="btn_test_gs"):
        try:
            gc = _gsheets_client()
            sh = gc.open_by_key(spreadsheet_id)
            ws_titles = [w.title for w in sh.worksheets()]
            st.sidebar.success(
                "Conexión OK.\n"
                f"Spreadsheet: {sh.title}\n"
                f"Worksheets: {', '.join(ws_titles)}"
            )
        except Exception as e:
            st.sidebar.error(f"No se pudo conectar a Google Sheets: {e}")

    col_g1, col_g2 = st.sidebar.columns(2)
    with col_g1:
        if st.button("⬆️ Guardar en Sheets", use_container_width=True, key="btn_save_gs"):
            ok, err = _save_to_sheets()
            st.sidebar.success("Sincronizado a Google Sheets.") if ok else st.sidebar.error(
                f"No se pudo guardar: {err}"
            )
    with col_g2:
        if st.button("⬇️ Cargar desde Sheets", use_container_width=True, key="btn_load_gs"):
            try:
                ws = _gsheets_open(ws_name)
                values = ws.get_all_values()
                df_new = _from_sheet_values(values)
                st.session_state.data = _clean_df(df_new)
                if not st.session_state.data.empty:
                    st.session_state.data["id"] = pd.to_numeric(
                        st.session_state.data["id"], errors="coerce"
                    ).fillna(0).astype(int)
                    st.session_state.next_id = int(st.session_state.data["id"].max()) + 1
                else:
                    st.session_state.next_id = 1
                st.sidebar.success("Datos cargados desde Google Sheets.")
                st.rerun()
            except Exception as e:
                st.sidebar.error(f"No se pudo cargar: {e}")

    # Auto-guardado si hubo cambios
    if st.session_state.get("dirty", False) and st.session_state.auto_save:
        ok, err = _save_to_sheets()
        if ok:
            st.session_state.dirty = False
            st.sidebar.info("Auto-guardado en Sheets.")
        else:
            st.sidebar.error(f"Auto-guardado falló: {err}")

# ---------------------------- Ingreso de viajes ----------------------------
st.title("🚗 Registro de Traslados — Papudo ↔ La Ligua")
st.caption("Versión con edición, eliminación, Excel y Google Sheets (auto-guardado opcional).")

with st.expander("➕ Agregar viaje", expanded=True):
    c1, c2, c3, c4 = st.columns([1, 1, 1, 2])
    with c1:
        fecha = st.date_input("Fecha", value=date.today(), format="DD/MM/YYYY")
    with c2:
        conductor = st.selectbox("Conductor", CONDUCTORES)
    with c3:
        tipo = st.selectbox("Tipo de viaje", ["Ida", "Vuelta", "Ida y Vuelta"], index=2)
    with c4:
        tarifa = st.number_input("Tarifa por tramo (CLP)", min_value=0, step=50, value=int(st.session_state.cfg_tarifa))

    # Pasajeros (si el conductor no participa del prorrateo, no se sugiere por defecto)
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
            st.success(f"Se registró {tipo} — Conductor: {conductor} — Pasajeros: {', '.join(pasajeros)}")

# ---------------------------- Historial + Filtros ----------------------------
st.subheader("📜 Historial de viajes")

f0, f1, f2, f3 = st.columns([0.8, 1, 1, 1.2])
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
# Asegurar tipo int para comparaciones seguras
if not st.session_state.data.empty:
    st.session_state.data["id"] = pd.to_numeric(st.session_state.data["id"], errors="coerce").fillna(0).astype(int)

ids_disp = _df["id"].dropna().astype(int).tolist()
sel_del = st.multiselect("Selecciona IDs a eliminar", ids_disp, placeholder="IDs…")
if st.button("Eliminar seleccionadas") and sel_del:
    before = len(st.session_state.data)
    st.session_state.data = st.session_state.data[~st.session_state.data["id"].isin(sel_del)].reset_index(drop=True)
    st.session_state.dirty = True
    st.success(f"Eliminadas {before - len(st.session_state.data)} filas (por ID).")
    st.rerun()

st.markdown("### ✏️ Editar fila")
edit_id = st.selectbox("ID a editar", ids_disp, placeholder="Elige un ID") if ids_disp else None
if edit_id is not None:
    row = st.session_state.data.loc[st.session_state.data["id"] == edit_id].iloc[0]

    c1, c2, c3, c4 = st.columns([1, 1, 1, 2])
    with c1:
        e_fecha = st.date_input(
            "Fecha (edición)",
            value=pd.to_datetime(row["fecha"]).date() if pd.notna(row["fecha"]) else date.today(),
            format="DD/MM/YYYY",
            key=f"e_fecha_{edit_id}",
        )
    with c2:
        e_conductor = st.selectbox(
            "Conductor (edición)",
            CONDUCTORES,
            index=CONDUCTORES.index(row["conductor"]) if row["conductor"] in CONDUCTORES else 0,
            key=f"e_cond_{edit_id}",
        )
    with c3:
        e_tramo = st.selectbox(
            "Tramo (edición)",
            ["Ida", "Vuelta"],
            index=0 if row["tramo"] == "Ida" else 1,
            key=f"e_tramo_{edit_id}",
        )
    with c4:
        e_tarifa = st.number_input(
            "Tarifa por tramo (edición)",
            min_value=0,
            step=50,
            value=int(row["tarifa_por_tramo"]) if pd.notna(row["tarifa_por_tramo"]) else int(st.session_state.cfg_tarifa),
            key=f"e_tarifa_{edit_id}",
        )

    actuales = [p for p in str(row["pasajeros"]).split(";") if p]
    opciones_pas = [p for p in PARTICIPANTES if (st.session_state.cfg_incluir_conductor or p != e_conductor)]
    e_pasajeros = st.multiselect(
        "Pasajeros (edición)",
        opciones_pas,
        default=[p for p in actuales if p in opciones_pas],
        key=f"e_pas_{edit_id}",
    )

    if st.button("Guardar cambios", key=f"save_{edit_id}"):
        n_p = len(e_pasajeros)
        monto = int(e_tarifa) * n_p
        idx = st.session_state.data.index[st.session_state.data["id"] == edit_id][0]
        st.session_state.data.loc[idx, [
            "fecha",
            "conductor",
            "tramo",
            "pasajeros",
            "tarifa_por_tramo",
            "n_pasajeros",
            "monto_al_conductor",
        ]] = [
            e_fecha,
            e_conductor,
            e_tramo,
            ";".join(e_pasajeros),
            int(e_tarifa),
            n_p,
            monto,
        ]
        st.session_state.dirty = True
        st.success(f"Fila ID {edit_id} actualizada.")
        st.rerun()

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
        sum_p = sum_p.set_index("pasajero").reindex(PARTICIPANTES, fill_value=0).reset_index()
        st.dataframe(sum_p, use_container_width=True)

    st.markdown("**Matriz Pasajero → Conductor (CLP)**")
    matriz = _pivot_pasajero_conductor(_explode_pasajeros(_df))
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
    - *Google Sheets:* comparte la hoja con el *service account* y activa el *Auto-guardar* si quieres persistencia automática.
    """
)
