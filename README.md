# YouTube AI-utomizer

Conecta **Claude Code** con **tu canal de YouTube** desde tu PC. Claude puede ver tus
estadísticas e ingresos, buscar nichos, preparar y subir vídeos (en privado) y publicarlos
cuando tú lo apruebes, respetando las normas de YouTube sobre IA.

## Instalación en PC (Windows)

1. Descarga este repositorio: botón verde **Code → Download ZIP**. Descomprímelo donde quieras.
2. Haz **doble clic en `instalar.bat`**.
   - Si no tienes Python, se abre la página de descarga. Instálalo marcando
     **"Add python.exe to PATH"** y vuelve a hacer doble clic.
3. Sigue los 4 pasos que salen en la ventana. Te abre cada página de Google, tú solo pulsas los
   botones que te dice:
   1. Crear el proyecto y activar las APIs de YouTube.
   2. Pantalla de permisos (nombre y correo) → **Publicar app**.
   3. Crear la clave (*App de escritorio*) → **Descargar JSON**. La ventana la encuentra sola en Descargas.
   4. Elegir tu cuenta de YouTube. Si Google avisa de "app no verificada", es normal: es tu propia app.
      Pulsa *Configuración avanzada → Ir a yt-automizer*.
4. Abre Claude Code y escribe: *"Haz la revisión semanal de mi canal"*.

El servidor queda registrado en Claude Code para **cualquier carpeta**, así que no hace falta
abrir Claude Code dentro de este proyecto.

**macOS / Linux:** `bash instalar.sh`. Los pasos son los mismos.

### Si algo falla
- Haz doble clic en `instalar.bat` otra vez, o ejecuta `.venv\Scripts\python -m yt_automizer doctor`.
  Te dice qué falta y cómo arreglarlo.
- Si la sesión de Google caduca, Claude Code abre el navegador solo para que vuelvas a entrar.
- Si no tienes Claude Code instalado cuando haces la instalación, se crea un `.mcp.json` en esta
  carpeta. Abre Claude Code aquí y acepta el servidor `youtube`.

## Qué puede hacer Claude

| Área | Herramientas |
|---|---|
| Estadísticas | `channel_overview`, `list_recent_videos`, `performance_summary` (visitas, tiempo de visualización, retención, Shorts frente a largos, fuentes de tráfico), `analytics_query` (cualquier consulta de YouTube Analytics) |
| Dinero | `revenue_report`: ingresos estimados, CPM, RPM, día a día. Solo con el canal en YPP. |
| Investigación | `search_youtube`, `research_niches`: puntuación de 0 a 100 según demanda y canales pequeños que triunfan, con vídeos de ejemplo |
| Publicar | `compliance_check`, `upload_video` (siempre **privado**), `publish_video` (necesita tu aprobación; también puede programar), `update_video_metadata` |
| Comunidad | `list_comments`, `reply_to_comment` |
| Seguridad | `quota_status`, `audit_log` (todo lo que se cambia, con los valores antiguos para deshacer) |
| Atajos | `weekly_review`, `find_niche` |

Opcional: copia `docs/claude-settings.example.json` a `.claude/settings.json` (o a
`~/.claude/settings.json`). Así las consultas de solo lectura van sin preguntas, y subir,
publicar, editar o responder siempre te pide confirmación.

## Normas de YouTube integradas (`src/yt_automizer/compliance.py`)
- **Contenido alterado o sintético:** cada subida declara `containsSyntheticMedia`, el campo de la
  API desde octubre de 2024. Avisa si usas herramientas como clonación de voz o vídeo con IA y no lo declaras.
- **Contenido "inauthentic" (YPP):** bloquea si no describes tu aportación humana, si el vídeo es
  casi igual a uno reciente, o si se superan 3 subidas en 24 horas.
- **Temas delicados** (salud, finanzas, noticias, elecciones) con IA: pide contrastar datos y citar fuentes.
- **COPPA:** hay que indicar siempre si el vídeo es para niños.
- **Límites de la API:** título hasta 100 caracteres, descripción hasta 5000 bytes, etiquetas hasta 500, Shorts hasta 3 minutos.

Los umbrales se cambian en `~/.yt-automizer/settings.json`. Ahí se guardan también la sesión,
el registro y la cuota, siempre en tu PC.

## A tener en cuenta
- YouTube puede dejar en privado los vídeos subidos por la API desde un proyecto sin auditar.
  Pide la [auditoría de la API](https://support.google.com/youtube/contact/yt_api_form) pronto;
  mientras tanto, sube con la herramienta y publica desde YouTube Studio.
- Cuota de 10.000 unidades al día: investigar una palabra clave gasta unas 100 y subir un vídeo unas 1.600.

## Desarrollo
```bash
python -m venv .venv && .venv/bin/pip install -e '.[dev]' && .venv/bin/pytest -q
```
