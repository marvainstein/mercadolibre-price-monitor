"""
Mercadolibre Price Monitor - Production Ready
Monitors product prices and sends email alerts when prices change.
Uses Playwright for realistic headless browsing.
"""

import asyncio
import json
import smtplib
import schedule
import time
import sys
from datetime import datetime
from pathlib import Path
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from playwright.async_api import async_playwright
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
    
    async def extract_price_from_page(self, page):
        """Extract 'Mejor precio en cuotas' price from Mercadolibre page."""
        try:
            await page.wait_for_load_state('networkidle', timeout=self.config.get('TIMEOUT', 30000))
            await asyncio.sleep(2)
            
            # Method 1: Extract installment price
            price_data = await self._extract_installment_price(page)
            
            # Method 2: Fallback to alternative methods
            if not price_data:
                logger.warning("Installment price not found, trying alternative methods...")
                price_data = await self._extract_alternative_price(page)
            
            if price_data:
                price_data['timestamp'] = datetime.now().isoformat()
            
            return price_data
            
        except Exception as e:
            logger.error(f"Error extracting price: {e}")
            return {}
    
    async def _extract_installment_price(self, page):
        """Extract price from 'Mejor precio en cuotas' section."""
        try:
            price_info = await page.evaluate("""
                () => {
                    const elements = Array.from(document.querySelectorAll('*'));
                    const cuotasElement = elements.find(el => 
                        el.textContent.includes('Mejor precio en cuotas')
                    );
                    
                    if (cuotasElement) {
                        const text = cuotasElement.textContent;
                        const match = text.match(/\$[\d.,]+/);
                        
                        if (match) {
                            return {
                                price: match[0],
                                full_text: text,
                                found: true
                            };
                        }
                    }
                    
                    return { found: false };
                }
            """)
            
            if price_info.get('found'):
                price_str = price_info['price'].replace('$', '').replace('.', '').replace(',', '.')
                try:
                    return {
                        'price': float(price_str),
                        'currency': 'ARS',
                        'raw_text': price_info.get('full_text', ''),
                        'source': 'installments'
                    }
                except ValueError:
                    logger.error(f"Could not parse price: {price_str}")
                    return {}
            
            return {}
            
        except Exception as e:
            logger.error(f"Error in installment price extraction: {e}")
            return {}
    
    async def _extract_alternative_price(self, page):
        """Extract price using alternative selectors."""
        try:
            price_info = await page.evaluate("""
                () => {
                    let price = null;
                    let found = false;
                    
                    // Try multiple selector strategies
                    const selectors = [
                        'span[class*="price"]',
                        'div[class*="price"]',
                        '[data-testid*="PRICE"]',
                        '[class*="ui-pdp-price"]'
                    ];
                    
                    for (let selector of selectors) {
                        const elements = document.querySelectorAll(selector);
                        for (let el of elements) {
                            const text = el.textContent;
                            const match = text.match(/\$[\d.,]+/);
                            if (match) {
                                price = match[0];
                                found = true;
                                break;
                            }
                        }
                        if (found) break;
                    }
                    
                    // Try meta tags
                    if (!found) {
                        const metaPrice = document.querySelector('meta[itemprop="price"]');
                        if (metaPrice) {
                            price = metaPrice.getAttribute('content');
                            found = true;
                        }
                    }
                    
                    return { price, found };
                }
            """)
            
            if price_info['found'] and price_info['price']:
                price_str = price_info['price'].replace('$', '').replace('.', '').replace(',', '.')
                try:
                    return {
                        'price': float(price_str),
                        'currency': 'ARS',
                        'source': 'alternative'
                    }
                except ValueError:
                    return {}
            
            return {}
            
        except Exception as e:
            logger.error(f"Error in alternative price extraction: {e}")
            return {}
    
    async def fetch_current_price(self):
        """Fetch current price using Playwright with realistic user simulation."""
        async with async_playwright() as p:
            try:
                browser = await p.chromium.launch(
                    headless=self.config.get('HEADLESS', True),
                    args=[
                        '--disable-blink-features=AutomationControlled',
                    ]
                )
                
                context = await browser.new_context(
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
                    locale='es-AR',
                    timezone_id='America/Argentina/Buenos_Aires',
                    viewport={'width': 1920, 'height': 1080}
                )
                
                page = await context.new_page()
                
                # Set realistic headers
                await page.set_extra_http_headers({
                    'Accept-Language': 'es-AR,es;q=0.9',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Referer': 'https://www.mercadolibre.com.ar'
                })
                
                logger.info(f"🌐 Fetching: {self.config['PRODUCT_URL'][:80]}...")
                
                try:
                    await page.goto(self.config['PRODUCT_URL'], wait_until='networkidle', timeout=60000)
                    price_data = await self.extract_price_from_page(page)
                except asyncio.TimeoutError:
                    logger.warning("Page load timeout, extracting available data...")
                    price_data = await self.extract_price_from_page(page)
                finally:
                    await context.close()
                    await browser.close()
                
                return price_data
                
            except Exception as e:
                logger.error(f"❌ Error fetching price: {e}")
                raise
    
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
    
    async def check_price(self):
        """Check current price and send alert if changed."""
        try:
            logger.info("=" * 60)
            logger.info("🔍 INICIANDO VERIFICACIÓN DE PRECIO")
            logger.info("=" * 60)
            
            current_price_data = await self.fetch_current_price()
            
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
        
        schedule.every(interval_hours).hours.do(
            lambda: asyncio.run(self.check_price())
        )
        
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
        asyncio.run(monitor.check_price())
        
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
