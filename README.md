# Mercadolibre Price Monitor 🚀

Monitor de precios automático para productos de Mercadolibre con alertas por email.

## Características

✅ **Navegación Realista**: Simula un usuario real con Playwright  
✅ **Extracción de Precios**: Obtiene automáticamente "Mejor precio en cuotas"  
✅ **Historial de Precios**: Mantiene registro de los últimos 365 cambios  
✅ **Alertas por Email**: Notificaciones HTML formateadas  
✅ **Intervalos Configurables**: Por defecto cada 4 horas  
✅ **Logging Completo**: Registra todas las acciones en archivo y consola  
✅ **Manejo de Errores**: Recuperación automática ante fallos  

## Instalación

### 1. Clonar el repositorio

```bash
git clone https://github.com/marvainstein/mercadolibre-price-monitor.git
cd mercadolibre-price-monitor
```

### 2. Instalar dependencias

```bash
pip install -r requirements.txt
playwright install chromium
```

### 3. Configurar email (Gmail)

1. Activa 2FA en tu cuenta de Gmail: https://myaccount.google.com/security
2. Genera una [Contraseña de Aplicación](https://myaccount.google.com/apppasswords)
3. Edita `config.json`:

```json
{
  "EMAIL_SENDER": "tu_email@gmail.com",
  "EMAIL_PASSWORD": "tu_contrasena_de_aplicacion_16_caracteres"
}
```

> ⚠️ **IMPORTANTE**: Usa la contraseña de aplicación, NO tu contraseña regular de Gmail

### 4. (Opcional) Cambiar producto

Reemplaza `PRODUCT_URL` en `config.json` con otro producto de Mercadolibre.

## Uso

```bash
python mercadolibre_monitor.py
```

### Primera ejecución:
- Realiza una verificación inmediata
- Guarda el precio en el historial
- Se programa para verificaciones futuras cada 4 horas

### Verificaciones posteriores:
- Compara con el precio anterior
- Si hay cambio, envía un email
- Actualiza el historial

## Archivos generados

- **price_history.json**: Historial de precios (último cambio)
- **price_monitor.log**: Registro de eventos y errores

## Ejemplo de salida

```
2026-05-29 14:30:45 - INFO - ============================================================
2026-05-29 14:30:45 - INFO - 🚀 MONITOR DE PRECIOS INICIADO
2026-05-29 14:30:45 - INFO - ============================================================
2026-05-29 14:30:45 - INFO - ⏱️  Intervalo: Cada 4 horas
2026-05-29 14:30:45 - INFO - 🔗 Producto: https://www.mercadolibre.com.ar/smartwatch...
2026-05-29 14:30:45 - INFO - 📧 Email: martinvainstein@outlook.com
2026-05-29 14:30:45 - INFO - ============================================================

2026-05-29 14:30:46 - INFO - 🔍 INICIANDO VERIFICACIÓN DE PRECIO
2026-05-29 14:30:46 - INFO - 🌐 Fetching: https://www.mercadolibre.com.ar/smartwatch...
2026-05-29 14:31:02 - INFO - ✅ Precio obtenido: $850,000 ARS
2026-05-29 14:31:02 - INFO - ℹ️  Primera verificación - sin datos previos para comparar
2026-05-29 14:31:02 - INFO - 💾 Historial guardado (1 registros)
```

## Solución de problemas

### "Email authentication failed"
- Verifica que usaste una contraseña de aplicación (16 caracteres)
- No uses tu contraseña regular de Gmail
- Genera una nueva en https://myaccount.google.com/apppasswords

### "No se pudo extraer el precio"
- Mercadolibre puede haber cambiado su estructura HTML
- El script tiene métodos alternativos que se activan automáticamente
- Revisa el archivo `price_monitor.log` para más detalles

### Timeout en la carga de página
- El script maneja timeouts automáticamente
- Intenta extraer los datos disponibles hasta el momento
- Aumenta `TIMEOUT` en config.json si es necesario

## Configuración avanzada

### Cambiar intervalo de escaneo

En `config.json`:
```json
"SCAN_INTERVAL": 6
```

Opciones: 1, 2, 3, 4, 6, 8, 12, 24 horas

### Deshabilitar modo headless

Para ver el navegador en acción:
```json
"HEADLESS": false
```

### Aumentar timeout

Si la página es lenta:
```json
"TIMEOUT": 60000
```

Tiempo en milisegundos.

## Ejecutar como servicio (Linux/Mac)

### Crear archivo systemd

```bash
sudo nano /etc/systemd/system/price-monitor.service
```

```ini
[Unit]
Description=Mercadolibre Price Monitor
After=network.target

[Service]
Type=simple
User=tu_usuario
WorkingDirectory=/ruta/a/mercadolibre-price-monitor
ExecStart=/usr/bin/python3 mercadolibre_monitor.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Activar:
```bash
sudo systemctl enable price-monitor
sudo systemctl start price-monitor
```

Ver logs:
```bash
sudo journalctl -u price-monitor -f
```

## Ejecutar como tarea programada (Windows)

1. Abre **Programador de tareas**
2. Crea una nueva tarea básica
3. Nombre: `Mercadolibre Price Monitor`
4. Trigger: Repetir cada 4 horas
5. Acción: Programa = `python.exe` | Argumentos = `ruta\mercadolibre_monitor.py`
6. Configuración: Ejecutar si el usuario está conectado

## Contribuciones

¿Mejoras? Pull requests bienvenidos.

## Licencia

MIT

## Autor

Creado para monitorear precios en Mercadolibre Argentina.

---

⭐ Si te fue útil, dale una estrella al proyecto
