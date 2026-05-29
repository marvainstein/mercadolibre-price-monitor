"""
Mercadolibre Price Monitor - Simplified Version
Uses requests + BeautifulSoup instead of Playwright for better macOS compatibility
"""

import json
import smtplib
import schedule
import time
import sys
from datetime import datetime
from pathlib import Path
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import requests
from bs4 import BeautifulSoup
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('price_monitor.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class PriceMonitor:
    """Monitors Mercadolibre product prices and sends email alerts."""
    
    def __init__(self, config_file='config.json'):
        """Initialize the price monitor with configuration."""
        self.config = self._load_config(config_file)
        self.price_history = self._load_price_history()
        self._validate_config()
    
    def _load_config(self, config_file):
        """Load configuration from JSON file."""
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            logger.error(f"Configuration file '{config_file}' not found.")
            raise
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON in '{config_file}'")
            raise
    
    def _validate_config(self):
        """Validate configuration has required fields."""
        required = ['PRODUCT_URL', 'EMAIL_SENDER', 'EMAIL_PASSWORD', 'EMAIL_RECIPIENT']
        missing = [field for field in required if field not in self.config]
        
        if missing:
            raise ValueError(f"Missing config fields: {', '.join(missing)}")
        
        if self.config['EMAIL_SENDER'] == 'your_email@gmail.com':
            logger.warning("⚠️  EMAIL_SENDER not configured. Email alerts will be skipped.")
    
    def _load_price_history(self):
        """Load price history from JSON file."""
        history_file = Path(self.config.get('PRICE_HISTORY_FILE', 'price_history.json'))
        if history_file.exists():
            try:
                with open(history_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"Could not load price history: {e}. Starting fresh.")
                return []
        return []
    
    def _save_price_history(self):
        """Save price history to JSON file."""
        history_file = Path(self.config.get('PRICE_HISTORY_FILE', 'price_history.json'))
        try:
            with open(history_file, 'w', encoding='utf-8') as f:
                json.dump(self.price_history, f, indent=2, ensure_ascii=False)
        except IOError as e:
            logger.error(f"Could not save price history: {e}")
    
    def fetch_current_price(self):
        """Fetch current price using requests + BeautifulSoup (more reliable on macOS)."""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'es-AR,es;q=0.9',
                'Referer': 'https://www.mercadolibre.com.ar'
            }
            
            logger.info(f"🌐 Fetching: {self.config['PRODUCT_URL'][:80]}...")
            
            # Add timeout
            timeout = self.config.get('TIMEOUT', 30000) / 1000  # Convert ms to seconds
            response = requests.get(self.config['PRODUCT_URL'], headers=headers, timeout=timeout)
            response.raise_for_status()
            
            # Parse HTML
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Try to extract price from "Mejor precio en cuotas"
            price_data = self._extract_price_from_html(soup)
            
            if price_data:
                price_data['timestamp'] = datetime.now().isoformat()
                return price_data
            else:
                logger.warning("❌ Could not extract price from HTML")
                return {}
            
        except requests.Timeout:
            logger.error(f"❌ Request timeout after {timeout} seconds")
            return {}
        except requests.ConnectionError as e:
            logger.error(f"❌ Connection error: {e}")
            return {}
        except Exception as e:
            logger.error(f"❌ Error fetching price: {e}")
            return {}
    
    def _extract_price_from_html(self, soup):
        """Extract price from HTML."""
        try:
            # Method 1: Look for text containing "Mejor precio en cuotas"
            text_content = soup.get_text()
            
            if 'Mejor precio en cuotas' in text_content:
                # Find price near this text
                lines = text_content.split('\n')
                for i, line in enumerate(lines):
                    if 'Mejor precio en cuotas' in line:
                        # Look at next lines for price
                        for j in range(i, min(i+10, len(lines))):
                            price_str = self._extract_price_string(lines[j])
                            if price_str:
                                try:
                                    price = float(price_str)
                                    return {
                                        'price': price,
                                        'currency': 'ARS',
                                        'source': 'installments'
                                    }
                                except ValueError:
                                    continue
            
            # Method 2: Look for price patterns in the entire page
            import re
            price_pattern = r'\$[\s]*[\d.,]+'
            matches = re.findall(price_pattern, text_content)
            
            if matches:
                # Get the first significant price (likely the product price)
                for match in matches:
                    price_str = self._extract_price_string(match)
                    if price_str and float(price_str) > 10000:  # Reasonable product price
                        try:
                            price = float(price_str)
                            return {
                                'price': price,
                                'currency': 'ARS',
                                'source': 'alternative'
                            }
                        except ValueError:
                            continue
            
            return {}
        
        except Exception as e:
            logger.error(f"Error extracting price from HTML: {e}")
            return {}
    
    def _extract_price_string(self, text):
        """Extract numeric price from text."""
        import re
        # Remove $ and spaces, replace dots with nothing, comma with dot
        text = text.replace('$', '').strip()
        # Match digits with optional thousands separator
        match = re.search(r'[\d.]+(?:,\d+)?', text)
        if match:
            price_str = match.group()
            # Handle both European (1.000,50) and US (1,000.50) formats
            if ',' in price_str and '.' in price_str:
                if price_str.index(',') > price_str.index('.'):
                    # US format: 1,000.50
                    price_str = price_str.replace(',', '')
                else:
                    # European format: 1.000,50
                    price_str = price_str.replace('.', '').replace(',', '.')
            elif ',' in price_str:
                # Could be thousands or decimal
                if price_str.count(',') == 1 and len(price_str.split(',')[1]) == 2:
                    # Likely decimal: 1000,50
                    price_str = price_str.replace(',', '.')
                else:
                    # Likely thousands: remove it
                    price_str = price_str.replace(',', '')
            
            try:
                return str(float(price_str))
            except ValueError:
                return None
        return None
    
    def send_email_alert(self, previous_price, current_price, change_type):
        """Send email alert about price change."""
        try:
            if self.config['EMAIL_SENDER'] == 'your_email@gmail.com':
                logger.warning("Email configuration incomplete. Skipping email.")
                return False
            
            price_change = current_price - previous_price
            percentage_change = (price_change / previous_price) * 100 if previous_price else 0
            
            arrow = "📉" if change_type == 'down' else "📈"
            subject = f"{arrow} Alerta de Precio - Mercadolibre: ${current_price:,.0f}"
            
            html_content = f"""
            <html>
                <body style="font-family: 'Segoe UI', Arial, sans-serif; line-height: 1.6; color: #333; background-color: #f5f5f5;">
                    <div style="max-width: 600px; margin: 0 auto; background-color: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                        <h2 style="color: #FFB100; margin-top: 0;">⚠️ Alerta de Cambio de Precio</h2>
                        
                        <p><strong>Producto:</strong> Smartwatch Forerunner 165 Garmin AMOLED</p>
                        
                        <div style="background-color: #f9f9f9; padding: 15px; border-left: 4px solid #FFB100; margin: 15px 0; border-radius: 4px;">
                            <p style="margin: 5px 0;"><strong>Precio anterior:</strong> <span style="color: #666;">💰 ${previous_price:,.0f} ARS</span></p>
                            <p style="margin: 5px 0;"><strong>Precio actual:</strong> <span style="font-size: 1.2em; color: #FFB100; font-weight: bold;">${current_price:,.0f} ARS</span></p>
                            <p style="margin: 5px 0;"><strong>Cambio:</strong> 
                                <span style="color: {'#27ae60' if change_type == 'down' else '#e74c3c'}; font-weight: bold; font-size: 1.1em;">
                                    {arrow} ${abs(price_change):,.0f} ({percentage_change:+.1f}%)
                                </span>
                            </p>
                        </div>
                        
                        <hr style="border: none; border-top: 1px solid #eee; margin: 20px 0;">
                        
                        <p style="font-size: 0.9em; color: #666;">
                            <strong>Tipo de Precio:</strong> Mejor precio en cuotas<br>
                            <strong>Fecha y Hora:</strong> {datetime.now().strftime('%d/%m/%Y a las %H:%M:%S')}<br>
                            <strong>Zona horaria:</strong> Argentina (ART)
                        </p>
                        
                        <div style="margin-top: 20px; padding-top: 15px; border-top: 1px solid #eee;">
                            <a href="{self.config['PRODUCT_URL']}" style="display: inline-block; background-color: #FFB100; color: white; padding: 10px 20px; text-decoration: none; border-radius: 4px; font-weight: bold;">
                                Ver producto en Mercadolibre →
                            </a>
                        </div>
                        
                        <p style="font-size: 0.8em; color: #999; margin-top: 20px;">
                            Este es un email automático del monitor de precios de Mercadolibre.
                        </p>
                    </div>
                </body>
            </html>
            """
            
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = self.config['EMAIL_SENDER']
            msg['To'] = self.config['EMAIL_RECIPIENT']
            
            msg.attach(MIMEText(html_content, 'html'))
            
            logger.info(f"📧 Sending email to {self.config['EMAIL_RECIPIENT']}...")
            
            with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
                server.login(self.config['EMAIL_SENDER'], self.config['EMAIL_PASSWORD'])
                server.send_message(msg)
            
            logger.info("✅ Email sent successfully!")
            return True
            
        except smtplib.SMTPAuthenticationError:
            logger.error("❌ Email authentication failed. Check your email and app password.")
            return False
        except Exception as e:
            logger.error(f"❌ Error sending email: {e}")
            return False
    
    def check_price(self):
        """Check current price and send alert if changed."""
        try:
            logger.info("=" * 60)
            logger.info("🔍 INICIANDO VERIFICACIÓN DE PRECIO")
            logger.info("=" * 60)
            
            current_price_data = self.fetch_current_price()
            
            if not current_price_data or not current_price_data.get('price'):
                logger.error("❌ No se pudo extraer el precio de la página")
                return
            
            current_price = current_price_data['price']
            logger.info(f"✅ Precio obtenido: ${current_price:,.0f} ARS")
            
            if self.price_history:
                last_entry = self.price_history[-1]
                last_price = last_entry['price']
                
                if current_price != last_price:
                    change_type = 'down' if current_price < last_price else 'up'
                    price_diff = abs(current_price - last_price)
                    pct_change = (price_diff / last_price) * 100
                    
                    emoji = "📉" if change_type == 'down' else "📈"
                    logger.warning(f"{emoji} ¡PRECIO CAMBIÓ! {change_type.upper()}: ${last_price:,.0f} → ${current_price:,.0f} ({pct_change:+.1f}%)")
                    
                    self.send_email_alert(last_price, current_price, change_type)
                else:
                    logger.info("✅ Precio sin cambios")
            else:
                logger.info("ℹ️  Primera verificación - sin datos previos para comparar")
            
            # Add to history
            self.price_history.append({
                'price': current_price,
                'timestamp': datetime.now().isoformat(),
                'currency': current_price_data.get('currency', 'ARS'),
                'source': current_price_data.get('source', 'unknown')
            })
            
            # Keep only last 365 entries
            if len(self.price_history) > 365:
                self.price_history = self.price_history[-365:]
            
            self._save_price_history()
            logger.info(f"💾 Historial guardado ({len(self.price_history)} registros)")
            
        except Exception as e:
            logger.error(f"❌ Error en verificación de precio: {e}", exc_info=True)
    
    def start_scheduler(self):
        """Start the price monitoring scheduler."""
        interval_hours = self.config.get('SCAN_INTERVAL', 4)
        
        schedule.every(interval_hours).hours.do(self.check_price)
        
        logger.info("\n" + "=" * 60)
        logger.info("🚀 MONITOR DE PRECIOS INICIADO")
        logger.info("=" * 60)
        logger.info(f"⏱️  Intervalo: Cada {interval_hours} horas")
        logger.info(f"🔗 Producto: {self.config['PRODUCT_URL'][:70]}...")
        logger.info(f"📧 Email: {self.config['EMAIL_RECIPIENT']}")
        logger.info("=" * 60 + "\n")
        
        while True:
            schedule.run_pending()
            time.sleep(60)


def main():
    """Main entry point."""
    try:
        monitor = PriceMonitor('config.json')
        
        # Run first check immediately
        logger.info("\n🔄 Ejecutando verificación inicial...\n")
        monitor.check_price()
        
        # Start scheduler
        monitor.start_scheduler()
        
    except KeyboardInterrupt:
        logger.info("\n⏹️  Monitor detenido por el usuario.")
        sys.exit(0)
    except Exception as e:
        logger.error(f"❌ Error fatal: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
