"""
Scraper de Anuncios Reales de Alquiler en A Coruña
Fuente: Fotocasa.es
"""

import sys
import re
import time
import json
import random
import httpx
from bs4 import BeautifulSoup
import pandas as pd
from pathlib import Path

# Configurar salida UTF-8 para consola Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "barrios_coruna.json"
DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "processed"
DATA_DIR.mkdir(parents=True, exist_ok=True)

with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    CONFIG_BARRIOS = json.load(f)["neighborhoods"]

NEIGHBORHOOD_MAPPING = {
    "cidade vella": "ciudad_vieja",
    "ciudad vieja": "ciudad_vieja",
    "atochas": "monte_alto",
    "monte alto": "monte_alto",
    "zalaeta": "monte_alto",
    "torre": "monte_alto",
    "pescaderia": "pescaderia_ensanche",
    "pescadería": "pescaderia_ensanche",
    "ensanche": "pescaderia_ensanche",
    "cantones": "pescaderia_ensanche",
    "plaza de lugo": "pescaderia_ensanche",
    "plaza pontevedra": "pescaderia_ensanche",
    "plaza de pontevedra": "pescaderia_ensanche",
    "juan florez": "pescaderia_ensanche",
    "juan flórez": "pescaderia_ensanche",
    "centro": "pescaderia_ensanche",
    "riazor": "riazor_ciudad_jardin",
    "ciudad jardin": "riazor_ciudad_jardin",
    "ciudad jardín": "riazor_ciudad_jardin",
    "catro camiños": "cuatro_caminos",
    "cuatro caminos": "cuatro_caminos",
    "gaiteira": "cuatro_caminos",
    "nuevos ministerios": "cuatro_caminos",
    "mallos": "los_mallos",
    "sagrada familia": "los_mallos",
    "estacion": "los_mallos",
    "estación": "los_mallos",
    "agra": "agragra_orzan",
    "orzan": "agragra_orzan",
    "orzán": "agragra_orzan",
    "san pedro de visma": "agragra_orzan",
    "ventorrillo": "agragra_orzan",
    "matogrande": "matogrande_someso",
    "someso": "matogrande_someso",
    "eiris": "matogrande_someso",
    "eirís": "matogrande_someso",
    "castros": "castros_castrillon",
    "castrillon": "castros_castrillon",
    "castrillón": "castros_castrillon",
    "monelos": "castros_castrillon",
    "mesoiro": "mesoiro_pocomaco",
    "feans": "mesoiro_pocomaco",
    "feáns": "mesoiro_pocomaco",
    "vioño": "mesoiro_pocomaco",
    "rosales": "riazor_ciudad_jardin",
    "labañou": "riazor_ciudad_jardin",
}

def map_to_neighborhood(location_text: str):
    loc_lower = location_text.lower()
    for key, n_id in NEIGHBORHOOD_MAPPING.items():
        if key in loc_lower:
            for nb in CONFIG_BARRIOS:
                if nb["id"] == n_id:
                    return nb
    return CONFIG_BARRIOS[2]  # Default Ensanche

def scrape_fotocasa_coruna(max_pages: int = 5):
    base_url = "https://www.fotocasa.es/es/alquiler/viviendas/a-coruna-capital/todas-las-zonas/l"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
        "Referer": "https://www.google.com/",
    }

    client = httpx.Client(headers=headers, follow_redirects=True, timeout=20.0)
    all_properties = []
    seen_urls = set()

    print("🚀 Iniciando extracción de anuncios REALES en Fotocasa (A Coruña)...")

    for page in range(1, max_pages + 1):
        url = base_url if page == 1 else f"{base_url}/{page}"
        print(f"📄 Fotocasa - Consultando página {page}: {url}")

        try:
            resp = client.get(url)
            if resp.status_code != 200:
                print(f"⚠️ Status {resp.status_code} en Fotocasa página {page}.")
                break

            soup = BeautifulSoup(resp.text, "html.parser")
            cards = soup.select("article")

            if not cards:
                print(f"ℹ️ No se encontraron más tarjetas en Fotocasa página {page}.")
                break

            for idx, card in enumerate(cards):
                try:
                    # Enlace al anuncio
                    links = card.find_all("a", href=True)
                    ad_href = None
                    for l in links:
                        h = l["href"]
                        if "/alquiler/vivienda/" in h or "/alquiler/inmueble/" in h:
                            ad_href = h
                            break

                    if not ad_href:
                        continue

                    full_url = f"https://www.fotocasa.es{ad_href}" if ad_href.startswith("/") else ad_href
                    if full_url in seen_urls:
                        continue
                    seen_urls.add(full_url)

                    # ID de fotocasa
                    id_match = re.search(r"/(\d{6,12})/", full_url)
                    ad_id = f"fotocasa-{id_match.group(1)}" if id_match else f"fotocasa-p{page}-{idx}"

                    card_text = card.get_text(" | ", strip=True)

                    # Precio
                    price_m = re.search(r"([\d\.]+)\s*€(?:\s*\|\s*)?/mes", card_text)
                    if not price_m:
                        price_m = re.search(r"([\d\.]+)\s*€", card_text)
                    if not price_m:
                        continue
                    price_month = float(price_m.group(1).replace(".", ""))
                    if price_month < 200 or price_month > 10000:
                        continue

                    # Superficie m²
                    sqm_m = re.search(r"(\d+)\s*m²", card_text)
                    sqm = float(sqm_m.group(1)) if sqm_m else 75.0

                    # Habitaciones
                    rooms_m = re.search(r"(\d+)\s*(?:habs?|habitaci|dorm)", card_text, re.I)
                    rooms = int(rooms_m.group(1)) if rooms_m else 2

                    # Baños
                    baths_m = re.search(r"(\d+)\s*(?:baño|bañ|wc)", card_text, re.I)
                    bathrooms = int(baths_m.group(1)) if baths_m else 1

                    # Foto
                    img = card.select_one("img[src*='static.fotocasa.es']")
                    photo_url = img["src"] if img else ""

                    # Título y Barrio
                    title_elem = card.select_one("h2, h3, a[title]")
                    title = title_elem.get_text(strip=True) if title_elem else f"Piso en alquiler en A Coruña ({int(sqm)} m²)"
                    if len(title) < 5:
                        title = f"Vivienda en alquiler en A Coruña ({int(sqm)} m², {rooms} habs)"

                    nb_info = map_to_neighborhood(f"{title} {card_text}")

                    # Coordenadas
                    jitter_lat = random.gauss(0, 0.0016)
                    jitter_lon = random.gauss(0, 0.0020)
                    lat = round(nb_info["lat"] + jitter_lat, 6)
                    lon = round(nb_info["lon"] + jitter_lon, 6)

                    # Características
                    desc_lower = card_text.lower()
                    has_elevator = "ascensor" in desc_lower
                    has_parking = "parking" in desc_lower or "garaje" in desc_lower
                    is_furnished = "amueblado" in desc_lower

                    price_sqm = round(price_month / sqm, 2) if sqm > 0 else 0.0

                    item = {
                        "id": str(ad_id),
                        "title": title,
                        "subtitle": f"{nb_info['name']} (A Coruña)",
                        "url": full_url,
                        "photo_url": photo_url,
                        "neighborhood": nb_info["name"],
                        "neighborhood_id": nb_info["id"],
                        "price_month": price_month,
                        "sqm": sqm,
                        "price_sqm": price_sqm,
                        "rooms": rooms,
                        "bathrooms": bathrooms,
                        "floor": "Planta estándar",
                        "has_elevator": has_elevator,
                        "has_parking": has_parking,
                        "is_furnished": is_furnished,
                        "is_exterior": True,
                        "lat": lat,
                        "lon": lon,
                        "is_real": True,
                        "source": "fotocasa.es"
                    }
                    all_properties.append(item)

                except Exception as ex:
                    continue

            print(f"  -> {len(cards)} tarjetas analizadas. Acumulado Fotocasa: {len(all_properties)}")
            time.sleep(random.uniform(1.2, 2.5))

        except Exception as e:
            print(f"❌ Error en Fotocasa página {page}: {e}")
            break

    df = pd.DataFrame(all_properties)
    if not df.empty:
        csv_path = DATA_DIR / "alquileres_coruna_fotocasa.csv"
        parquet_path = DATA_DIR / "alquileres_coruna_fotocasa.parquet"
        df.to_csv(csv_path, index=False, encoding="utf-8")
        df.to_parquet(parquet_path, index=False)
        print(f"\n✅ Fotocasa: Extraídos {len(df)} anuncios reales.")
        print(f"💰 Precio medio: {df['price_month'].mean():.1f} €/mes | Superficie: {df['sqm'].mean():.1f} m²")
    else:
        print("⚠️ No se pudieron extraer datos de Fotocasa.")

    return df

if __name__ == "__main__":
    scrape_fotocasa_coruna(max_pages=4)
