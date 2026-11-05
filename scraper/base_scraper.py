"""
Módulo base estructurado y extensible para Web Scraping de portales inmobiliarios.
Construido sobre httpx y BeautifulSoup4 con soporte para:
- Rotación de User-Agents y cabeceras realistas
- Rate-limiting adaptativo y delays aleatorios
- Reintentos exponenciales ante códigos de estado transitorios (429, 5xx)
- Normalización y parsing robusto de campos inmobiliarios
- Persistencia estructurada (JSON, CSV, Parquet)
"""

import abc
import dataclasses
import json
import logging
import random
import re
import time
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Tuple, Union

import bs4
from bs4 import BeautifulSoup
import httpx
import pandas as pd

# Configuración de logging estructurado
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("BaseRealEstateScraper")


@dataclasses.dataclass
class ScraperConfig:
    """Configuración para el cliente de scraping."""
    min_delay: float = 1.8
    max_delay: float = 3.5
    timeout: float = 15.0
    max_retries: int = 3
    backoff_factor: float = 2.0
    proxies: Optional[Dict[str, str]] = None
    verify_ssl: bool = True
    output_dir: str = "data/raw"


class RealEstateDataCleaner:
    """Utilidades estáticas para normalizar y limpiar datos brutos de portales inmobiliarios."""

    @staticmethod
    def clean_price(text: Optional[str]) -> Optional[int]:
        """Extrae el precio numérico mensual en euros."""
        if not text:
            return None
        # Eliminar separadores de miles y caracteres no numéricos
        cleaned = re.sub(r"[^\d]", "", text)
        return int(cleaned) if cleaned else None

    @staticmethod
    def clean_sqm(text: Optional[str]) -> Optional[int]:
        """Extrae los metros cuadrados (m²)."""
        if not text:
            return None
        match = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:m²|m2|metros)", text, re.IGNORECASE)
        if match:
            val_str = match.group(1).replace(",", ".")
            return int(round(float(val_str)))
        # Si sólo viene un número
        cleaned = re.sub(r"[^\d]", "", text)
        return int(cleaned) if cleaned else None

    @staticmethod
    def clean_rooms(text: Optional[str]) -> Optional[int]:
        """Extrae el número de habitaciones."""
        if not text:
            return None
        match = re.search(r"(\d+)\s*(?:hab|dorm|habitaci|bedroom)", text, re.IGNORECASE)
        if match:
            return int(match.group(1))
        cleaned = re.sub(r"[^\d]", "", text)
        return int(cleaned) if cleaned else None

    @staticmethod
    def clean_bathrooms(text: Optional[str]) -> Optional[int]:
        """Extrae el número de baños."""
        if not text:
            return None
        match = re.search(r"(\d+)\s*(?:baño|bano|aseo|bath)", text, re.IGNORECASE)
        if match:
            return int(match.group(1))
        cleaned = re.sub(r"[^\d]", "", text)
        return int(cleaned) if cleaned else None

    @staticmethod
    def clean_floor(text: Optional[str]) -> Optional[str]:
        """Normaliza la planta (Bajo, Entreplanta, 1..N, Ático)."""
        if not text:
            return None
        text_lower = text.lower()
        if "ático" in text_lower or "atico" in text_lower:
            return "Ático"
        if "bajo" in text_lower:
            return "Bajo"
        if "entreplanta" in text_lower or "entresuelo" in text_lower:
            return "Entreplanta"
        match = re.search(r"(\d+)\s*ª|\b(\d+)\b", text)
        if match:
            return match.group(1) or match.group(2)
        return text.strip()


class BaseRealEstateScraper(abc.ABC):
    """Clase abstracta base para la creación de scrapers robustos."""

    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    ]

    BASE_HEADERS = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
    }

    def __init__(self, config: Optional[ScraperConfig] = None):
        self.config = config or ScraperConfig()
        self.cleaner = RealEstateDataCleaner()
        self.session: Optional[httpx.Client] = None
        Path(self.config.output_dir).mkdir(parents=True, exist_ok=True)

    def _get_random_headers(self) -> Dict[str, str]:
        headers = self.BASE_HEADERS.copy()
        headers["User-Agent"] = random.choice(self.USER_AGENTS)
        return headers

    def __enter__(self):
        self.session = httpx.Client(
            headers=self._get_random_headers(),
            timeout=self.config.timeout,
            follow_redirects=True,
            verify=self.config.verify_ssl,
        )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            self.session.close()

    def _rate_limit(self) -> None:
        """Aplica un retraso aleatorio entre peticiones para simular comportamiento humano."""
        delay = random.uniform(self.config.min_delay, self.config.max_delay)
        logger.debug(f"Pausa de rate-limiting: {delay:.2f}s")
        time.sleep(delay)

    def fetch_html(self, url: str, params: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """Realiza una petición GET con reintentos y backoff exponencial."""
        if not self.session:
            raise RuntimeError("El scraper debe usarse dentro de un bloque 'with' de contexto.")

        retries = 0
        backoff = self.config.backoff_factor

        while retries <= self.config.max_retries:
            try:
                self._rate_limit()
                # Rotar User-Agent periódicamente
                self.session.headers["User-Agent"] = random.choice(self.USER_AGENTS)

                logger.info(f"Descargando URL ({retries}/{self.config.max_retries}): {url}")
                response = self.session.get(url, params=params)

                if response.status_code == 200:
                    return response.text

                if response.status_code in (429, 500, 502, 503, 504):
                    wait_time = backoff * (2 ** retries) + random.uniform(0.5, 1.5)
                    logger.warning(
                        f"Código {response.status_code} recibido en {url}. Reintentando en {wait_time:.1f}s..."
                    )
                    time.sleep(wait_time)
                    retries += 1
                    continue

                logger.error(f"Error no recuperable {response.status_code} al solicitar {url}")
                return None

            except (httpx.RequestError, httpx.TimeoutException) as exc:
                retries += 1
                wait_time = backoff * (2 ** retries)
                logger.warning(f"Excepción de red en {url}: {exc}. Reintento {retries} en {wait_time:.1f}s")
                time.sleep(wait_time)

        logger.error(f"Superado el número máximo de reintentos para: {url}")
        return None

    def make_soup(self, html: str) -> BeautifulSoup:
        """Crea un objeto BeautifulSoup utilizando el parser lxml o html.parser."""
        return BeautifulSoup(html, "html.parser")

    @abc.abstractmethod
    def parse_listing_page(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """Extrae la lista de inmuebles o URLs de detalle desde una página de catálogo."""
        pass

    @abc.abstractmethod
    def parse_detail_page(self, soup: BeautifulSoup, url: str) -> Dict[str, Any]:
        """Extrae la información detallada de una ficha de inmueble."""
        pass

    def export_dataset(
        self,
        items: List[Dict[str, Any]],
        filename_prefix: str = "scraped_alquileres",
        export_formats: Optional[List[str]] = None,
    ) -> Dict[str, str]:
        """Exporta los datos extraídos en CSV, Parquet o JSON."""
        if not items:
            logger.warning("No hay datos para exportar.")
            return {}

        formats = export_formats or ["csv", "parquet", "json"]
        df = pd.DataFrame(items)
        saved_files = {}

        if "csv" in formats:
            csv_path = Path(self.config.output_dir) / f"{filename_prefix}.csv"
            df.to_csv(csv_path, index=False, encoding="utf-8")
            saved_files["csv"] = str(csv_path)

        if "parquet" in formats:
            parquet_path = Path(self.config.output_dir) / f"{filename_prefix}.parquet"
            df.to_parquet(parquet_path, index=False, engine="pyarrow")
            saved_files["parquet"] = str(parquet_path)

        if "json" in formats:
            json_path = Path(self.config.output_dir) / f"{filename_prefix}.json"
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(items, f, ensure_ascii=False, indent=2)
            saved_files["json"] = str(json_path)

        logger.info(f"Exportación completada ({len(items)} registros): {saved_files}")
        return saved_files


class MockRealEstatePortalScraper(BaseRealEstateScraper):
    """Implementación de ejemplo demostrativa para tests locales y CI."""

    def parse_listing_page(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        listings = []
        for card in soup.select("div.property-card, article.item"):
            title_tag = card.select_one(".title, h2, h3")
            price_tag = card.select_one(".price, .item-price")
            url_tag = card.select_one("a[href]")

            listings.append({
                "title": title_tag.get_text(strip=True) if title_tag else "Sin título",
                "price_raw": price_tag.get_text(strip=True) if price_tag else None,
                "url": url_tag["href"] if url_tag else None,
            })
        return listings

    def parse_detail_page(self, soup: BeautifulSoup, url: str) -> Dict[str, Any]:
        title = soup.select_one("h1").get_text(strip=True) if soup.select_one("h1") else ""
        price_text = soup.select_one(".price").get_text(strip=True) if soup.select_one(".price") else ""
        features = [f.get_text(strip=True) for f in soup.select(".features li, .details span")]
        
        sqm_text = next((f for f in features if "m²" in f or "m2" in f), None)
        rooms_text = next((f for f in features if "hab" in f.lower()), None)
        baths_text = next((f for f in features if "baño" in f.lower() or "bano" in f.lower()), None)

        return {
            "title": title,
            "url": url,
            "price_month": self.cleaner.clean_price(price_text),
            "sqm": self.cleaner.clean_sqm(sqm_text),
            "rooms": self.cleaner.clean_rooms(rooms_text),
            "bathrooms": self.cleaner.clean_bathrooms(baths_text),
        }


if __name__ == "__main__":
    # Test básico de las utilidades de limpieza
    cleaner = RealEstateDataCleaner()
    assert cleaner.clean_price("1.250 €/mes") == 1250
    assert cleaner.clean_sqm("85 m² construidos") == 85
    assert cleaner.clean_rooms("3 hab.") == 3
    assert cleaner.clean_bathrooms("2 baños") == 2
    assert cleaner.clean_floor("Planta 4ª exterior") == "4"
    assert cleaner.clean_floor("Ático con ascensor") == "Ático"
    print("Test unitario de RealEstateDataCleaner: ¡OK!")
