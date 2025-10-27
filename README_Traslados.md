
# Registro de Traslados — Papudo ↔ La Ligua (Streamlit)

App para registrar quién conduce y a quién transporta en cada tramo (Ida/Vuelta), con cálculo automático
de montos diarios, mensuales, acumulados y saldos por persona.

## Ejecutar localmente
1. Crea y activa un entorno:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Windows: .venv\Scripts\activate
   pip install streamlit pandas gspread google-auth
   ```
2. Ejecuta:
   ```bash
   streamlit run streamlit_app.py
   ```
3. Por defecto, la app guarda en `trips.csv` (en la misma carpeta).

## Usar Google Sheets (recomendado para varios usuarios)
1. Crea una **Hoja de Cálculo** en Google Drive y copia su **ID** (lo que aparece en la URL entre `/d/` y `/edit`).
2. Crea una **cuenta de servicio** en Google Cloud y descarga el JSON de credenciales.
3. En **Streamlit Cloud** (o `~/.streamlit/secrets.toml` local), define `st.secrets` así:
   ```toml
   # secrets.toml
   sheet_id = "<TU_SHEET_ID>"
   # Pega el JSON de la cuenta de servicio en formato TOML (claves y strings)
   # Si ejecutas en Streamlit Cloud, pega el JSON en el editor de secrets (se guarda como dict).
   ```
   En Streamlit Cloud puedes pegar el JSON directamente como estructura en `gcp_service_account`.

### Ejemplo de `st.secrets` (Streamlit Cloud)
En el editor de secretos pega algo como:
```json
{
  "sheet_id": "1ABCDEFtuIdDeHojaXYZ",
  "gcp_service_account": {
    "type": "service_account",
    "project_id": "tu-proyecto",
    "private_key_id": "xxxxxxxxxxxxxxxxxxxxxxxxxxxx",
    "private_key": "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n",
    "client_email": "nombre@tu-proyecto.iam.gserviceaccount.com",
    "client_id": "1234567890",
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
    "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/nombre%40tu-proyecto.iam.gserviceaccount.com"
  }
}
```
4. Comparte la Google Sheet con el **client_email** de la cuenta de servicio (permiso Editor).
5. Al iniciar, la app creará/actualizará la hoja **trips** con columnas: `date, leg, driver, passengers, car, notes`.

## Lógica de cobros
- Costo por **tramo (Ida o Vuelta) por persona**: por defecto **$1.250** (ajustable en la barra lateral).
- Cada pasajero **debe** ese monto al conductor del tramo; el conductor **cobra** la suma de sus pasajeros.
- Los reportes muestran totales **hoy**, **mes actual** y **acumulado**, además de una matriz *Pasajero → Conductor* y el **balance neto**.

## Personalización rápida
- Edita en la barra lateral la lista de **Conductores** y **Personas**.
- Agrega notas por tramo (campo *notes*).

---
Hecho para Wilson y equipo. 🚗
