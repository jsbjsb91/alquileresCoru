"""
Generador de dataset sintético realista para el mercado de alquiler de vivienda en A Coruña.
Utiliza la configuración geográfica y de precios de config/barrios_coruna.json.
"""

import json
import math
import random
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd


class CorunaRentalSyntheticGenerator:
    """Generador sintético de ofertas de alquiler para A Coruña con correlaciones realistas."""

    TITLES_BY_TYPE = {
        "estudio": [
            "Acogedor estudio reformado cerca de {landmark}",
            "Estudio luminoso y moderno en {barrio}",
            "Estudio funcional ideal para persona sola o pareja en {barrio}",
            "Coqueto estudio con diseño abierto en {barrio}",
        ],
        "apartamento": [
            "Apartamento con encanto junto a {landmark}",
            "Moderno apartamento totalmente equipado en {barrio}",
            "Apartamento soleado y listo para entrar a vivir en {barrio}",
            "Céntrico apartamento reformado a pasos de {landmark}",
            "Apartamento exterior muy luminoso en {barrio}",
        ],
        "piso": [
            "Espacioso piso familiar en {barrio}",
            "Luminoso piso exterior con vistas en {barrio}",
            "Amplio piso reformado junto a {landmark}",
            "Excelente piso señorial en {barrio}",
            "Magnífico piso amueblado con terraza en {barrio}",
            "Piso alto y soleado en excelente ubicación de {barrio}",
            "Gran piso con plaza de garaje incluida en {barrio}",
            "Piso completamente amueblado a estrenar en {barrio}",
        ],
        "atico": [
            "Exclusivo ático con gran terraza en {barrio}",
            "Espectacular ático con vistas al mar en {landmark}",
            "Ático de ensueño reformado con vistas panorámicas en {barrio}",
            "Luminoso ático con techos abuhardillados en {barrio}",
        ],
        "duplex": [
            "Singular dúplex de diseño en {barrio}",
            "Amplio dúplex familiar con garaje en {barrio}",
            "Dúplex luminoso con acabados de primera calidad en {barrio}",
        ],
    }

    LANDMARKS = {
        "ciudad_vieja": ["la Plaza de Azcárraga", "la Colegiata de Santa María", "el Jardín de San Carlos", "la Plaza de María Pita"],
        "monte_alto": ["la Torre de Hércules", "la Playa de las Lapas", "el Paseo Marítimo", "el Mercado de Monte Alto"],
        "pescaderia_ensanche": ["la Plaza de Lugo", "la Calle Real", "los Cantones", "la Plaza de Pontevedra"],
        "riazor_ciudad_jardin": ["la Playa de Riazor", "el Estadio de Riazor", "Ciudad Jardín", "el Paseo de Ronda"],
        "cuatro_caminos": ["la Fábrica de Tabacos", "Nuevos Ministerios", "la Fuente de Cuatro Caminos", "el Parque Europa"],
        "los_mallos": ["la Estación de Tren", "la Ronda de Outeiro", "la Plaza de la Concordia", "el Parque de Vioño"],
        "agragra_orzan": ["la Plaza del Comercio", "la Calle Barcelona", "la Ronda de Nelle", "el Parque de San Pedro"],
        "matogrande_someso": ["el Hotel Attica21", "Expocoruña", "el Campus de Elviña", "el Parque de Eirís"],
        "castros_castrillon": ["el Mirador de San Diego", "el Parque de Oza", "la Avenida del Ejército", "el Castrillón"],
        "mesoiro_pocomaco": ["la Avenida Novo Mesoiro", "el Polígono de Pocomaco", "el Parque Infantil de Mesoiro"],
    }

    # Pesos de distribución de inmuebles en alquiler según densidad y oferta típica de la ciudad
    NEIGHBORHOOD_WEIGHTS = {
        "pescaderia_ensanche": 0.16,
        "cuatro_caminos": 0.14,
        "monte_alto": 0.13,
        "agragra_orzan": 0.13,
        "riazor_ciudad_jardin": 0.12,
        "los_mallos": 0.10,
        "matogrande_someso": 0.08,
        "castros_castrillon": 0.06,
        "mesoiro_pocomaco": 0.05,
        "ciudad_vieja": 0.03,
    }

    # Probabilidad base de garaje según antigüedad/modernidad del barrio
    PARKING_PROBABILITY = {
        "matogrande_someso": 0.85,
        "mesoiro_pocomaco": 0.88,
        "cuatro_caminos": 0.35,
        "pescaderia_ensanche": 0.28,
        "riazor_ciudad_jardin": 0.32,
        "monte_alto": 0.24,
        "castros_castrillon": 0.30,
        "los_mallos": 0.18,
        "agragra_orzan": 0.14,
        "ciudad_vieja": 0.06,
    }

    # Probabilidad de ascensor según características del parque residencial del barrio
    ELEVATOR_PROBABILITY_MODERNITY = {
        "matogrande_someso": 0.98,
        "mesoiro_pocomaco": 0.99,
        "pescaderia_ensanche": 0.82,
        "cuatro_caminos": 0.86,
        "riazor_ciudad_jardin": 0.80,
        "monte_alto": 0.72,
        "castros_castrillon": 0.75,
        "los_mallos": 0.65,
        "agragra_orzan": 0.60,
        "ciudad_vieja": 0.40,
    }

    def __init__(self, config_path: str = "config/barrios_coruna.json", seed: int = 42):
        self.config_path = Path(config_path)
        self.seed = seed
        random.seed(seed)
        np.random.seed(seed)
        self.config = self._load_config()
        self.neighborhoods = {b["id"]: b for b in self.config["neighborhoods"]}

    def _load_config(self) -> Dict[str, Any]:
        with open(self.config_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _generate_sqm_and_rooms(self) -> tuple[int, int, int, str]:
        """Genera superficie y habitaciones/baños de forma coherente."""
        # Categorías de vivienda
        r = random.random()
        if r < 0.12:  # Estudio / Pequeño (35 - 50 m²)
            sqm = random.randint(35, 50)
            rooms = 1
            bathrooms = 1
            prop_type = "estudio" if random.random() < 0.55 else "apartamento"
        elif r < 0.45:  # Apartamento 1-2 hab (51 - 75 m²)
            sqm = random.randint(51, 75)
            rooms = random.choices([1, 2], weights=[0.25, 0.75])[0]
            bathrooms = 1
            prop_type = "apartamento" if rooms == 1 else "piso"
        elif r < 0.82:  # Piso estándar 2-3 hab (76 - 110 m²)
            sqm = random.randint(76, 110)
            rooms = random.choices([2, 3], weights=[0.35, 0.65])[0]
            bathrooms = random.choices([1, 2], weights=[0.30, 0.70])[0]
            prop_type = "piso"
        elif r < 0.94:  # Piso grande 3-4 hab (111 - 150 m²)
            sqm = random.randint(111, 150)
            rooms = random.choices([3, 4], weights=[0.55, 0.45])[0]
            bathrooms = random.choices([2, 3], weights=[0.75, 0.25])[0]
            prop_type = "duplex" if random.random() < 0.15 else "piso"
        else:  # Gran vivienda / Ático / Exclusivo (151 - 220 m²)
            sqm = random.randint(151, 220)
            rooms = random.choices([4, 5], weights=[0.60, 0.40])[0]
            bathrooms = random.choices([2, 3], weights=[0.40, 0.60])[0]
            prop_type = "atico" if random.random() < 0.40 else ("duplex" if random.random() < 0.30 else "piso")

        return sqm, rooms, bathrooms, prop_type

    def _generate_floor(self, prop_type: str) -> str:
        """Determina la planta del inmueble."""
        if prop_type == "atico":
            return random.choice(["7", "8", "9", "10", "Ático"])
        floors = ["Bajo"] + [str(i) for i in range(1, 11)]
        weights = [0.06, 0.15, 0.18, 0.18, 0.15, 0.10, 0.08, 0.05, 0.03, 0.015, 0.005]
        return random.choices(floors, weights=weights)[0]

    def _generate_price(
        self,
        sqm: int,
        neighborhood_id: str,
        has_elevator: bool,
        has_parking: bool,
        is_exterior: bool,
        furnished: bool,
        floor: str,
        prop_type: str,
    ) -> tuple[float, float, bool]:
        """Calcula el precio mensual y el precio/m² con varianza, economía de escala y outliers."""
        n_info = self.neighborhoods[neighborhood_id]
        min_sqm_p = n_info["typical_price_sqm_min"]
        max_sqm_p = n_info["typical_price_sqm_max"]

        # Base price per sqm dentro del rango típico con distribución beta sesgada al centro
        base_price_sqm = min_sqm_p + (max_sqm_p - min_sqm_p) * random.betavariate(2.2, 2.2)

        # Efecto de escala: pisos muy pequeños tienen mayor €/m², pisos grandes menor €/m²
        if sqm < 50:
            scale_mult = 1.15
        elif sqm < 75:
            scale_mult = 1.05
        elif sqm > 140:
            scale_mult = 0.90
        elif sqm > 180:
            scale_mult = 0.85
        else:
            scale_mult = 1.0

        # Modificadores por comodidades
        premium = 1.0
        if has_elevator:
            premium += 0.06
        elif floor not in ["Bajo", "1"]:
            # Penalización severa por pisos altos sin ascensor
            penalty = 0.05 * (int(floor) if floor.isdigit() else 4)
            premium -= min(0.25, penalty)

        if has_parking:
            premium += 0.10
        if is_exterior:
            premium += 0.05
        else:
            premium -= 0.08
        if furnished:
            premium += 0.05
        if prop_type == "atico":
            premium += 0.12

        # Ruido gaussiano aleatorio de mercado (~5% desviación)
        noise = random.gauss(0, 0.05)
        price_sqm = base_price_sqm * scale_mult * premium * (1.0 + noise)

        is_outlier = False
        outlier_roll = random.random()
        # ~2.5% Outliers de lujo / vista despejada mar
        if outlier_roll < 0.025 and neighborhood_id in ["pescaderia_ensanche", "riazor_ciudad_jardin", "ciudad_vieja"]:
            price_sqm *= random.uniform(1.35, 1.65)
            is_outlier = True
        # ~2.5% Outliers de oportunidad / vivienda antigua no renovada
        elif outlier_roll > 0.975 and neighborhood_id in ["los_mallos", "agragra_orzan", "castros_castrillon", "mesoiro_pocomaco"]:
            price_sqm *= random.uniform(0.65, 0.78)
            is_outlier = True

        raw_price_month = price_sqm * sqm

        # Redondear a valores comunes del mercado español (múltiplos de 10 o 25 €)
        price_month = round(raw_price_month / 10.0) * 10
        # Mínimo de mercado realista para A Coruña
        price_month = max(380, price_month)
        final_price_sqm = round(price_month / sqm, 2)

        return float(price_month), final_price_sqm, is_outlier

    def _generate_coordinates(self, neighborhood_id: str) -> tuple[float, float]:
        """Añade jitter gaussiano acotado a las coordenadas del barrio."""
        n_info = self.neighborhoods[neighborhood_id]
        lat_center = n_info["lat"]
        lon_center = n_info["lon"]

        # 1 grado aprox 111 km. 0.0035 grados ≈ 380 metros de radio
        lat_jitter = random.gauss(0, 0.0022)
        lon_jitter = random.gauss(0, 0.0030)

        # Clamping para evitar que caigan en el mar o fuera de la península coruñesa
        lat = round(lat_center + lat_jitter, 6)
        lon = round(lon_center + lon_jitter, 6)
        return lat, lon

    def _generate_title(self, prop_type: str, neighborhood_id: str, neighborhood_name: str) -> str:
        templates = self.TITLES_BY_TYPE.get(prop_type, self.TITLES_BY_TYPE["piso"])
        template = random.choice(templates)
        landmarks = self.LANDMARKS.get(neighborhood_id, ["el centro"])
        landmark = random.choice(landmarks)
        clean_name = neighborhood_name.split(" - ")[0]
        return template.format(barrio=clean_name, landmark=landmark)

    def generate_listing(self, item_index: int) -> Dict[str, Any]:
        """Genera un registro individual de alquiler."""
        # Seleccionar barrio según pesos
        neighborhood_ids = list(self.NEIGHBORHOOD_WEIGHTS.keys())
        weights = [self.NEIGHBORHOOD_WEIGHTS[nid] for nid in neighborhood_ids]
        nid = random.choices(neighborhood_ids, weights=weights)[0]
        n_info = self.neighborhoods[nid]

        sqm, rooms, bathrooms, prop_type = self._generate_sqm_and_rooms()
        floor = self._generate_floor(prop_type)

        # Probabilidad de ascensor
        base_elev_prob = self.ELEVATOR_PROBABILITY_MODERNITY[nid]
        if floor in ["Bajo", "1"]:
            # En bajos y 1º da menos prioridad al ascensor aunque exista
            has_elevator = random.random() < (base_elev_prob * 0.85)
        elif floor in ["6", "7", "8", "9", "10", "Ático"]:
            # En plantas altas casi obligatorio tener ascensor
            has_elevator = random.random() < 0.96
        else:
            has_elevator = random.random() < base_elev_prob

        # Probabilidad de garaje
        has_parking = random.random() < self.PARKING_PROBABILITY[nid]

        # Exterior / Interior
        is_exterior = random.random() < 0.83

        # Amueblado
        furnished = random.random() < 0.65

        # Coordenadas
        lat, lon = self._generate_coordinates(nid)

        # Precio
        price_month, price_sqm, is_outlier = self._generate_price(
            sqm=sqm,
            neighborhood_id=nid,
            has_elevator=has_elevator,
            has_parking=has_parking,
            is_exterior=is_exterior,
            furnished=furnished,
            floor=floor,
            prop_type=prop_type,
        )

        # Título
        title = self._generate_title(prop_type, nid, n_info["name"])

        # Fecha reciente (últimos 45 días)
        days_ago = random.randint(0, 45)
        hours_ago = random.randint(0, 23)
        minutes_ago = random.randint(0, 59)
        base_now = datetime.now(timezone.utc)
        created_at = (base_now - timedelta(days=days_ago, hours=hours_ago, minutes=minutes_ago)).isoformat()

        # ID único reproducible y claro
        unique_id = f"coruna-alq-{item_index:04d}-{uuid.uuid4().hex[:6]}"

        return {
            "id": unique_id,
            "title": title,
            "neighborhood": n_info["name"],
            "neighborhood_id": nid,
            "price_month": int(price_month),
            "sqm": sqm,
            "rooms": rooms,
            "bathrooms": bathrooms,
            "floor": floor,
            "has_elevator": has_elevator,
            "is_exterior": is_exterior,
            "furnished": furnished,
            "has_parking": has_parking,
            "lat": lat,
            "lon": lon,
            "price_sqm": price_sqm,
            "is_outlier": is_outlier,
            "property_type": prop_type,
            "created_at": created_at,
        }

    def generate_dataset(self, n_samples: int = 850) -> pd.DataFrame:
        """Genera un dataset completo de n_samples registros."""
        records = [self.generate_listing(i + 1) for i in range(n_samples)]
        df = pd.DataFrame(records)
        return df

    def save_dataset(
        self,
        df: pd.DataFrame,
        csv_path: str = "data/processed/alquileres_coruna.csv",
        parquet_path: str = "data/processed/alquileres_coruna.parquet",
        dictionary_path: str = "data/processed/data_dictionary.json",
    ) -> None:
        """Guarda el dataset en CSV, Parquet y genera el diccionario de datos."""
        Path(csv_path).parent.mkdir(parents=True, exist_ok=True)

        # Guardar CSV
        df.to_csv(csv_path, index=False, encoding="utf-8")
        print(f"CSV guardado en: {csv_path} ({len(df)} registros)")

        # Guardar Parquet
        df.to_parquet(parquet_path, index=False, engine="pyarrow")
        print(f"Parquet guardado en: {parquet_path}")

        # Generar Diccionario de Datos
        data_dictionary = {
            "dataset_name": "alquileres_coruna",
            "city": "A Coruña",
            "country": "Spain",
            "total_records": len(df),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "description": "Dataset de oferta de alquiler de viviendas en la ciudad de A Coruña con correlaciones realistas de mercado, precios/m², comodidades y localización.",
            "fields": {
                "id": {
                    "type": "string",
                    "description": "Identificador único de la oferta (UUID con prefijo coruna-alq-)",
                    "example": df["id"].iloc[0],
                },
                "title": {
                    "type": "string",
                    "description": "Título descriptivo y comercial del inmueble",
                    "example": df["title"].iloc[0],
                },
                "neighborhood": {
                    "type": "string",
                    "description": "Nombre oficial/habitual del barrio o zona",
                    "example": df["neighborhood"].iloc[0],
                },
                "neighborhood_id": {
                    "type": "string",
                    "description": "Clave única identificadora del barrio (slug)",
                    "example": df["neighborhood_id"].iloc[0],
                },
                "price_month": {
                    "type": "integer",
                    "unit": "EUR/mes",
                    "description": "Renta mensual de alquiler en euros",
                    "range": [int(df["price_month"].min()), int(df["price_month"].max())],
                },
                "sqm": {
                    "type": "integer",
                    "unit": "m²",
                    "description": "Superficie construida/útil de la vivienda",
                    "range": [int(df["sqm"].min()), int(df["sqm"].max())],
                },
                "rooms": {
                    "type": "integer",
                    "description": "Número de dormitorios / habitaciones",
                    "range": [int(df["rooms"].min()), int(df["rooms"].max())],
                },
                "bathrooms": {
                    "type": "integer",
                    "description": "Número de cuartos de baño completos o aseos",
                    "range": [int(df["bathrooms"].min()), int(df["bathrooms"].max())],
                },
                "floor": {
                    "type": "string",
                    "description": "Planta en la que se encuentra la vivienda ('Bajo', '1'-'10', 'Ático')",
                    "example": "3",
                },
                "has_elevator": {
                    "type": "boolean",
                    "description": "Indica si el edificio dispone de ascensor",
                    "example": True,
                },
                "is_exterior": {
                    "type": "boolean",
                    "description": "Indica si la vivienda da al exterior o a patio de manzana/luces",
                    "example": True,
                },
                "furnished": {
                    "type": "boolean",
                    "description": "Indica si la vivienda se alquila amueblada",
                    "example": True,
                },
                "has_parking": {
                    "type": "boolean",
                    "description": "Indica si incluye plaza de garaje en el precio",
                    "example": False,
                },
                "lat": {
                    "type": "float",
                    "unit": "degrees",
                    "description": "Latitud geográfica WGS84 del inmueble (con dispersión gaussiana)",
                    "range": [float(df["lat"].min()), float(df["lat"].max())],
                },
                "lon": {
                    "type": "float",
                    "unit": "degrees",
                    "description": "Longitud geográfica WGS84 del inmueble (con dispersión gaussiana)",
                    "range": [float(df["lon"].min()), float(df["lon"].max())],
                },
                "price_sqm": {
                    "type": "float",
                    "unit": "EUR/m²",
                    "description": "Precio unitario por metro cuadrado calculado (price_month / sqm)",
                    "range": [float(df["price_sqm"].min()), float(df["price_sqm"].max())],
                },
                "is_outlier": {
                    "type": "boolean",
                    "description": "Bandera que indica si el registro simula una anomalía o inmueble singular de mercado",
                    "example": False,
                },
                "property_type": {
                    "type": "string",
                    "description": "Tipología de vivienda (estudio, apartamento, piso, duplex, atico)",
                    "example": "piso",
                },
                "created_at": {
                    "type": "string (ISO 8601)",
                    "description": "Fecha y hora de publicación de la oferta",
                    "example": df["created_at"].iloc[0],
                },
            },
        }

        with open(dictionary_path, "w", encoding="utf-8") as f:
            json.dump(data_dictionary, f, ensure_ascii=False, indent=2)
        print(f"Diccionario de datos guardado en: {dictionary_path}")


if __name__ == "__main__":
    generator = CorunaRentalSyntheticGenerator(config_path="config/barrios_coruna.json", seed=2026)
    dataset = generator.generate_dataset(n_samples=850)
    generator.save_dataset(dataset)
    print("Generación completada con éxito!")
