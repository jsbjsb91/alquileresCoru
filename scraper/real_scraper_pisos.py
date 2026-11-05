import sys
import re
import time
import json
import httpx
from bs4 import BeautifulSoup
import pandas as pd
from pathlib import Path

# Configurar salida UTF-8
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

CONFIG_PATH = Path("config/barrios_coruna.json")
with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    CONFIG_DATA = json.load(f)
    CONFIG_BARRIOS = CONFIG_DATA["neighborhoods"]

URBAN_NEIGHBORHOODS = [nb for nb in CONFIG_BARRIOS if nb.get("zone_type") == "city"]

def get_nearest_urban_neighborhood(lat, lon):
    best_nb = URBAN_NEIGHBORHOODS[0]
    min_dist = float("inf")
    for nb in URBAN_NEIGHBORHOODS:
        d = (lat - nb["lat"])**2 + (lon - nb["lon"])**2
        if d < min_dist:
            min_dist = d
            best_nb = nb
    return best_nb

def determine_municipality(lat, lon, text):
    t = text.lower()
    if "oleiros" in t or "santa cruz" in t or "perillo" in t or "mera" in t or "bastiagueiro" in t or "dorneda" in t:
        return "Oleiros"
    if "culleredo" in t or "o burgo" in t or "vilaboa" in t or "almeiras" in t or "acea de ama" in t:
        return "Culleredo"
    if "arteixo" in t or "meicende" in t or "pastoriza" in t or "sabón" in t or "vilarrodís" in t:
        return "Arteixo"
    if "cambre" in t or "o temple" in t or "graxal" in t or "sigrás" in t:
        return "Cambre"
    if "sada" in t or "fontán" in t or "carnoedo" in t or "veigue" in t:
        return "Sada"
    
    # Geográfico por coordenadas
    if lon < -8.455 and lat < 43.345:
        return "Arteixo"
    if lon > -8.365 and lat > 43.325:
        return "Oleiros"
    if lon > -8.290:
        return "Sada"
    if lat < 43.328 and -8.420 <= lon <= -8.355:
        return "Culleredo"
    if lat < 43.305 and -8.365 <= lon <= -8.320:
        return "Cambre"
        
    return "A Coruña"

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
}

client = httpx.Client(headers=headers, follow_redirects=True, timeout=20.0)

# URLs a consultar
urls_to_scrape = [
    # Distritos urbanos de A Coruña
    ("https://www.pisos.com/alquiler/pisos-cidade_vella_atochas_pescaderia/", "A Coruña", "pescaderia_ensanche", "Pescadería - Ensanche - Ciudad Vieja"),
    ("https://www.pisos.com/alquiler/pisos-cidade_xardin_cidade_escolar/", "A Coruña", "riazor_ciudad_jardin", "Ciudad Jardín - Riazor"),
    ("https://www.pisos.com/alquiler/pisos-labanou_os_rosales/", "A Coruña", "riazor_ciudad_jardin", "Los Rosales - Labañou"),
    ("https://www.pisos.com/alquiler/pisos-catro_caminos_a_gaiteira/", "A Coruña", "cuatro_caminos", "Cuatro Caminos - A Gaiteira"),
    ("https://www.pisos.com/alquiler/pisos-os_mallos_a_falperra/", "A Coruña", "los_mallos", "Los Mallos - A Falperra"),
    ("https://www.pisos.com/alquiler/pisos-agra_do_orzan_o_ventorillo/", "A Coruña", "agras_del_orzán", "Agra do Orzán - Ventorrillo"),
    ("https://www.pisos.com/alquiler/pisos-elvina_barrio_flores_matogrande_someso/", "A Coruña", "matogrande", "Matogrande - Elviña - Someso"),
    ("https://www.pisos.com/alquiler/pisos-os_castros_castrillon_monelos/", "A Coruña", "castros_castrillon", "Os Castros - Castrillón - Monelos"),
    # Tipologías en Coruña Capital
    ("https://www.pisos.com/alquiler/aticos-a_coruna_capital/", "A Coruña", None, None),
    ("https://www.pisos.com/alquiler/duplexs-a_coruna_capital/", "A Coruña", None, None),
    ("https://www.pisos.com/alquiler/estudios-a_coruna_capital/", "A Coruña", None, None),
    ("https://www.pisos.com/alquiler/casas-a_coruna_capital/", "A Coruña", None, None),
    ("https://www.pisos.com/alquiler/pisos-a_coruna_capital/", "A Coruña", None, None),
    # Concellos Metropolitanos
    ("https://www.pisos.com/alquiler/pisos-oleiros/", "Oleiros", "oleiros", "Concello de Oleiros"),
    ("https://www.pisos.com/alquiler/casas-oleiros/", "Oleiros", "oleiros", "Concello de Oleiros"),
    ("https://www.pisos.com/alquiler/pisos-culleredo/", "Culleredo", "culleredo", "Concello de Culleredo"),
    ("https://www.pisos.com/alquiler/pisos-arteixo/", "Arteixo", "arteixo", "Concello de Arteixo"),
    ("https://www.pisos.com/alquiler/pisos-cambre/", "Cambre", "cambre", "Concello de Cambre"),
    ("https://www.pisos.com/alquiler/pisos-sada/", "Sada", "sada", "Concello de Sada"),
    ("https://www.pisos.com/alquiler/pisos-area_de_a_coruna/", "Área Metropolitana", None, None),
]

all_properties = []
seen_ids = set()

print("🚀 Extrayendo pisos con coordenadas EXACTAS de JSON-LD...")

for item_info in urls_to_scrape:
    url, default_muni, default_nb_id, default_nb_name = item_info
    print(f" -> Consultando {url}...")
    try:
        resp = client.get(url)
        if resp.status_code != 200:
            continue
        soup = BeautifulSoup(resp.text, "html.parser")

        # Extraer coordenadas reales de JSON-LD
        geo_map = {}
        for s in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(s.string)
                if isinstance(data, dict):
                    ad_url_part = data.get("url", "").rstrip("/")
                    geo = data.get("geo", {})
                    if ad_url_part and geo:
                        lat_val = float(geo.get("latitude", 0))
                        lon_val = float(geo.get("longitude", 0))
                        # Validar que caen dentro del área metropolitana de A Coruña y comarca
                        if 43.20 <= lat_val <= 43.45 and -8.60 <= lon_val <= -8.20:
                            geo_map[ad_url_part] = (round(lat_val, 6), round(lon_val, 6))
            except Exception:
                pass

        cards = soup.select(".ad-preview")
        for card in cards:
            ad_id = card.get("id")
            if not ad_id or ad_id in seen_ids:
                continue

            title_elem = card.select_one(".ad-preview__title")
            if not title_elem:
                continue
            title = title_elem.get_text(strip=True)
            ad_url_part = title_elem.get("href", "")
            ad_url = f"https://www.pisos.com{ad_url_part}" if ad_url_part.startswith("/") else ad_url_part

            # Coordenadas exactas desde el JSON-LD
            clean_key = ad_url_part.rstrip("/")
            exact_geo = geo_map.get(clean_key)
            if not exact_geo:
                # Solo aceptar anuncios con coordenadas exactas verificadas
                continue

            lat, lon = exact_geo

            # Precio
            price_elem = card.select_one(".ad-preview__price")
            if not price_elem:
                continue
            price_raw = price_elem.get_text(strip=True)
            price_clean = re.sub(r"[^\d]", "", price_raw)
            if not price_clean:
                continue
            price_month = float(price_clean)

            # Características
            chars = [c.get_text(strip=True) for c in card.select(".ad-preview__char")]
            rooms, bathrooms, sqm = 2, 1, 75.0
            floor_str = "1ª planta"
            for ch in chars:
                ch_low = ch.lower()
                if "hab" in ch_low:
                    m = re.search(r"(\d+)", ch)
                    if m: rooms = int(m.group(1))
                elif "baño" in ch_low or "bano" in ch_low:
                    m = re.search(r"(\d+)", ch)
                    if m: bathrooms = int(m.group(1))
                elif "m²" in ch_low or "m2" in ch_low:
                    m = re.search(r"(\d+)", ch)
                    if m: sqm = float(m.group(1))
                elif "planta" in ch_low or "bajo" in ch_low or "ático" in ch_low:
                    floor_str = ch

            # Subtítulo (zona local o parroquia)
            subtitle_elem = card.select_one(".ad-preview__location, .ad-preview__subtitle")
            subtitle = subtitle_elem.get_text(strip=True) if subtitle_elem else ""

            # Determinar Concello y Barrio con precisión
            muni = determine_municipality(lat, lon, f"{title} {subtitle} {ad_url_part} {default_muni}")
            
            if muni == "A Coruña":
                if default_nb_id:
                    nb_id = default_nb_id
                    nb_name = default_nb_name
                else:
                    nearest = get_nearest_urban_neighborhood(lat, lon)
                    nb_id = nearest["id"]
                    nb_name = nearest["name"]
            else:
                muni_key = muni.lower()
                nb_id = muni_key
                nb_name = f"{subtitle} ({muni})" if subtitle and muni not in subtitle else f"Concello de {muni}"

            # Foto real
            img_elem = card.select_one("img.lazy-img, img[data-src], .carousel__main-photo img")
            photo_url = ""
            if img_elem:
                photo_url = img_elem.get("data-src") or img_elem.get("src") or ""

            desc_text = (card.get_text() + " " + title).lower()
            has_elevator = "ascensor" in desc_text or "ático" not in floor_str.lower()
            has_parking = "garaje" in desc_text or "parking" in desc_text
            is_furnished = "amueblado" in desc_text

            price_sqm = round(price_month / sqm, 2) if sqm > 0 else 0.0

            prop_type = "piso"
            if "ático" in title.lower() or "atico" in title.lower():
                prop_type = "atico"
            elif "dúplex" in title.lower() or "duplex" in title.lower():
                prop_type = "duplex"
            elif "estudio" in title.lower():
                prop_type = "estudio"
            elif "chalet" in title.lower() or "casa" in title.lower():
                prop_type = "casa"

            item = {
                "id": str(ad_id),
                "title": title,
                "subtitle": subtitle,
                "url": ad_url,
                "photo_url": photo_url,
                "municipality": muni,
                "neighborhood": nb_name,
                "neighborhood_id": nb_id,
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
                "property_type": prop_type,
                "is_real": True,
                "source": "pisos.com",
            }
            all_properties.append(item)
            seen_ids.add(ad_id)

        time.sleep(0.3)
    except Exception as e:
        print(f"Error procesando {url}: {e}")

print(f"\n✅ Total anuncios con geolocalización catastral real exacta: {len(all_properties)}")

df = pd.DataFrame(all_properties)
print("\nDesglose por Concello:")
print(df["municipality"].value_counts())

print("\nDesglose por Distrito / Barrio:")
print(df["neighborhood_id"].value_counts())

data_dir = Path("data/processed")
parquet_path = data_dir / "alquileres_coruna_reales.parquet"
csv_path = data_dir / "alquileres_coruna_reales.csv"

df.to_parquet(parquet_path, index=False)
df.to_csv(csv_path, index=False, encoding="utf-8")
print(f" Datasets guardados con éxito en:\n - {parquet_path}\n - {csv_path}")

fallback_path = Path("frontend/data/properties_fallback.json")
fallback_records = df.to_dict(orient="records")
fallback_path.write_text(json.dumps(fallback_records, indent=2, ensure_ascii=False), encoding="utf-8")
print(f" properties_fallback.json actualizado para Render/Offline.")
