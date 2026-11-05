"""
Scraper de Anuncios Reales de Alquiler en A Coruña Capital
Fuente: pisos.com (anuncios públicos reales con fotos, precios y enlaces)
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

# Cargar configuración de barrios
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
    "plaza de pontevedra": "pescaderia_ensanche",
    "juan florez": "pescaderia_ensanche",
    "juan flórez": "pescaderia_ensanche",
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
        "somorrostro": "pescaderia_ensanche",
    "oleiros": "oleiros",
    "santa cruz": "oleiros",
    "perillo": "oleiros",
    "mera": "oleiros",
    "bastiagueiro": "oleiros",
    "dorneda": "oleiros",
    "lorbe": "oleiros",
    "lorbé": "oleiros",
    "dexo": "oleiros",
    "inas": "oleiros",
    "iñás": "oleiros",
    "culleredo": "culleredo",
    "o burgo": "culleredo",
    "burgo": "culleredo",
    "vilaboa": "culleredo",
    "acea de ama": "culleredo",
    "acea": "culleredo",
    "almeiras": "culleredo",
    "arteixo": "arteixo",
    "meicende": "arteixo",
    "pastoriza": "arteixo",
    "sabon": "arteixo",
    "sabón": "arteixo",
    "vilarrodis": "arteixo",
    "vilarrodís": "arteixo",
    "cambre": "cambre",
    "o temple": "cambre",
    "temple": "cambre",
    "graxal": "cambre",
    "sigras": "cambre",
    "sigrás": "cambre",
    "cecebre": "cambre",
    "sada": "sada",
    "fontan": "sada",
    "fontán": "sada",
    "carnoedo": "sada",
    "veigue": "sada",
    "mosteiron": "sada",
    "mosteirón": "sada",
}

def map_to_neighborhood(location_text: str):
    loc_lower = location_text.lower()
    for key, n_id in NEIGHBORHOOD_MAPPING.items():
        if key in loc_lower:
            # Encontrar datos del barrio
            for nb in CONFIG_BARRIOS:
                if nb["id"] == n_id:
                    return nb
    # Por defecto Cuatro Caminos / Centro
    return CONFIG_BARRIOS[4]

def scrape_real_apartments():
    targets = [
        {"url_base": "https://www.pisos.com/alquiler/pisos-a_coruna_capital/", "max_pages": 4, "filter_area": False, "type": "piso"},
        {"url_base": "https://www.pisos.com/alquiler/aticos-a_coruna_capital/", "max_pages": 2, "filter_area": False, "type": "atico"},
        {"url_base": "https://www.pisos.com/alquiler/duplexs-a_coruna_capital/", "max_pages": 2, "filter_area": False, "type": "duplex"},
        {"url_base": "https://www.pisos.com/alquiler/estudios-a_coruna_capital/", "max_pages": 2, "filter_area": False, "type": "estudio"},
        {"url_base": "https://www.pisos.com/alquiler/casas-a_coruna_capital/", "max_pages": 2, "filter_area": False, "type": "casa"},
        {"url_base": "https://www.pisos.com/alquiler/pisos-oleiros/", "max_pages": 3, "filter_area": False, "type": "piso"},
        {"url_base": "https://www.pisos.com/alquiler/pisos-culleredo/", "max_pages": 3, "filter_area": False, "type": "piso"},
        {"url_base": "https://www.pisos.com/alquiler/pisos-arteixo/", "max_pages": 2, "filter_area": False, "type": "piso"},
        {"url_base": "https://www.pisos.com/alquiler/pisos-cambre/", "max_pages": 3, "filter_area": False, "type": "piso"},
        {"url_base": "https://www.pisos.com/alquiler/pisos-sada/", "max_pages": 3, "filter_area": False, "type": "piso"},
        {"url_base": "https://www.pisos.com/alquiler/pisos-area_de_a_coruna/", "max_pages": 3, "filter_area": False, "type": "piso"},
        {"url_base": "https://www.pisos.com/alquiler/pisos-a_coruna/", "max_pages": 4, "filter_area": True, "type": "piso"},
    ]
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
        "Referer": "https://www.google.com/",
    }

    client = httpx.Client(headers=headers, follow_redirects=True, timeout=20.0)
    all_properties = []
    seen_ids = set()

    print(f"🚀 Iniciando extracción de anuncios REALES en A Coruña y área metropolitana...")

    ALLOWED_AREAS = [
        "a coruña", "coruña", "oleiros", "culleredo", "arteixo", "cambre", "sada", "santa cruz",
        "perillo", "o burgo", "monelos", "matogrande", "castros", "riazor", "monte alto",
        "ensanche", "pescadería", "ciudad vieja", "cuatro caminos", "los mallos", "agra do orzán",
        "los rosales", "novo mesoiro", "someso", "eirís", "visma", "ventorrillo"
    ]

    for target in targets:
        base_url = target["url_base"]
        max_pages = target["max_pages"]
        filter_area = target["filter_area"]

        for page in range(1, max_pages + 1):
            url = base_url if page == 1 else f"{base_url}{page}/"
            print(f"📄 Scrapeando página {page}: {url}")

            try:
                resp = client.get(url)
                if resp.status_code != 200:
                    print(f"⚠️ Status {resp.status_code} en página {page}, pasando al siguiente.")
                    break

                soup = BeautifulSoup(resp.text, "html.parser")
                cards = soup.select(".ad-preview")

                if not cards:
                    print(f"ℹ️ No se encontraron más tarjetas en página {page}.")
                    break

                for card in cards:
                    try:
                        # ID
                        ad_id = card.get("id") or card.get("data-lnk-href", "")
                        if not ad_id or ad_id in seen_ids:
                            continue

                        # Título y Link
                        title_elem = card.select_one(".ad-preview__title")
                        if not title_elem:
                            continue
                        title = title_elem.get_text(strip=True)
                        rel_url = title_elem.get("href", "")
                        ad_url = f"https://www.pisos.com{rel_url}" if rel_url.startswith("/") else rel_url

                        # Subtítulo (Ubicación)
                        subtitle_elem = card.select_one(".ad-preview__subtitle")
                        subtitle = subtitle_elem.get_text(strip=True) if subtitle_elem else "A Coruña"

                        full_loc = f"{title} {subtitle}".lower()
                        if filter_area:
                            if not any(area in full_loc for area in ALLOWED_AREAS):
                                continue

                        seen_ids.add(ad_id)

                        # Precio
                        price_elem = card.select_one(".ad-preview__price")
                        if not price_elem:
                            continue
                        price_raw = price_elem.get_text(strip=True)
                        price_clean = re.sub(r"[^\d]", "", price_raw)
                        if not price_clean:
                            continue
                        price_month = float(price_clean)

                        # Características (habs, baños, m², planta)
                        chars = [c.get_text(strip=True) for c in card.select(".ad-preview__char")]
                        
                        rooms = 2
                        bathrooms = 1
                        sqm = 75.0
                        floor_str = "1ª planta"

                        for ch in chars:
                            ch_low = ch.lower()
                            if "hab" in ch_low:
                                m = re.search(r"(\d+)", ch)
                                if m:
                                    rooms = int(m.group(1))
                            elif "baño" in ch_low or "bano" in ch_low:
                                m = re.search(r"(\d+)", ch)
                                if m:
                                    bathrooms = int(m.group(1))
                            elif "m²" in ch_low or "m2" in ch_low:
                                m = re.search(r"(\d+)", ch)
                                if m:
                                    sqm = float(m.group(1))
                            elif "planta" in ch_low or "bajo" in ch_low or "ático" in ch_low:
                                floor_str = ch

                        # Foto
                        img_elem = card.select_one("img.lazy-img, img[data-src], .carousel__main-photo img")
                        photo_url = ""
                        if img_elem:
                            photo_url = img_elem.get("data-src") or img_elem.get("src") or ""

                        # Mapeo a barrio
                        nb_info = map_to_neighborhood(f"{title} {subtitle}")

                        # Coordenadas con leve jitter realista
                        jitter_lat = random.gauss(0, 0.0018)
                        jitter_lon = random.gauss(0, 0.0022)
                        lat = round(nb_info["lat"] + jitter_lat, 6)
                        lon = round(nb_info["lon"] + jitter_lon, 6)

                        # Características extras
                        desc_text = (card.get_text() + " " + title).lower()
                        has_elevator = "ascensor" in desc_text or "ático" not in floor_str.lower()
                        has_parking = "garaje" in desc_text or "parking" in desc_text
                        is_furnished = "amueblado" in desc_text

                        price_sqm = round(price_month / sqm, 2) if sqm > 0 else 0.0

                        item = {
                            "id": str(ad_id),
                            "title": title,
                            "subtitle": subtitle,
                            "url": ad_url,
                            "photo_url": photo_url,
                            "neighborhood": nb_info["name"],
                            "neighborhood_id": nb_info["id"],
                            "price_month": price_month,
                            "sqm": sqm,
                            "price_sqm": price_sqm,
                            "rooms": rooms,
                            "bathrooms": bathrooms,
                            "floor": floor_str,
                            "has_elevator": has_elevator,
                            "has_parking": has_parking,
                            "is_furnished": is_furnished,
                            "lat": lat,
                            "lon": lon,
                            "property_type": target.get("type", "piso"),
                            "is_real": True,
                            "source": "pisos.com"
                        }
                        all_properties.append(item)

                    except Exception as ex:
                        continue

                print(f"  -> {len(cards)} anuncios leídos en página {page}. Acumulado total: {len(all_properties)}")
                time.sleep(random.uniform(1.0, 2.0))

            except Exception as e:
                print(f"❌ Error en página {page}: {e}")
                break

    df = pd.DataFrame(all_properties)
    if not df.empty:
        # Guardar datasets reales
        csv_path = DATA_DIR / "alquileres_coruna_reales.csv"
        parquet_path = DATA_DIR / "alquileres_coruna_reales.parquet"
        df.to_csv(csv_path, index=False, encoding="utf-8")
        df.to_parquet(parquet_path, index=False)

        print(f"\n✅ Extracción finalizada con éxito!")
        print(f"📊 Total de anuncios REALES extraídos: {len(df)}")
        print(f"💰 Precio medio real: {df['price_month'].mean():.1f} €/mes")
        print(f"📐 Superficie media real: {df['sqm'].mean():.1f} m²")
        print(f"💶 Precio medio por m² real: {df['price_sqm'].mean():.2f} €/m²")
        print(f"📁 Guardado en:\n  - {csv_path}\n  - {parquet_path}")

        # Mostrar muestra de anuncios reales
        print("\n📋 Muestra de primeros 3 anuncios reales:")
        for _, row in df.head(3).iterrows():
            print(f"  * [{row['neighborhood']}] {row['title']} -> {row['price_month']} €/mes ({row['sqm']} m², {row['price_sqm']} €/m²)")
            print(f"    Enlace real: {row['url']}")
    else:
        print("⚠️ No se pudieron extraer datos.")

if __name__ == "__main__":
    scrape_real_apartments()
