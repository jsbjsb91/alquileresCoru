"""
FastAPI REST API for A Coruña Rental Housing Market & Machine Learning Valuation.
"""

from typing import List, Optional, Dict, Any, Annotated
from pathlib import Path
from contextlib import asynccontextmanager

import pandas as pd
import numpy as np
from fastapi import FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.schemas import (
    HealthResponse,
    ValuationRequest,
    ValuationResponse,
    PropertyResponse,
    PropertyDetailResponse,
    PaginatedPropertiesResponse,
    NeighborhoodStats,
    MarketSummaryResponse,
)
from backend.ml_model import (
    load_model,
    predict_valuation,
    load_dataset,
    DEFAULT_DATA_PARQUET,
    DEFAULT_DATA_CSV,
    ALL_FEATURES,
)

# Global dataset caches
_DF_PROPERTIES: Optional[pd.DataFrame] = None
_PROPERTIES_BY_ID: Dict[str, Dict[str, Any]] = {}


REAL_DATA_PARQUET = Path(__file__).resolve().parent.parent / "data" / "processed" / "alquileres_coruna_reales.parquet"

def get_properties_df() -> pd.DataFrame:
    """Return in-memory cached properties DataFrame combining real & benchmark data."""
    global _DF_PROPERTIES, _PROPERTIES_BY_ID
    if _DF_PROPERTIES is None:
        df_bench = load_dataset(DEFAULT_DATA_PARQUET, DEFAULT_DATA_CSV).copy()
        df_bench["created_at"] = df_bench["created_at"].astype(str)
        if "is_real" not in df_bench.columns:
            df_bench["is_real"] = False
        if "url" not in df_bench.columns:
            df_bench["url"] = None
        if "photo_url" not in df_bench.columns:
            df_bench["photo_url"] = None
        if "source" not in df_bench.columns:
            df_bench["source"] = "synthetic"

        if REAL_DATA_PARQUET.exists():
            df_real = pd.read_parquet(REAL_DATA_PARQUET).copy()
            df_real["created_at"] = ""
            df_real["is_outlier"] = False
            df_real["property_type"] = "piso"
            df_real["is_exterior"] = df_real["is_exterior"].fillna(True).astype(bool) if "is_exterior" in df_real.columns else True
            df_real["furnished"] = df_real["is_furnished"].fillna(False).astype(bool) if "is_furnished" in df_real.columns else False
            df_real["has_parking"] = df_real["has_parking"].fillna(False).astype(bool) if "has_parking" in df_real.columns else False
            df_real["has_elevator"] = df_real["has_elevator"].fillna(True).astype(bool) if "has_elevator" in df_real.columns else True
            df_real["is_real"] = True
            df = pd.concat([df_real, df_bench], ignore_index=True)
        else:
            df = df_bench

        # Compute ML Valuation and Market Verdicts for all listings
        try:
            bundle = load_model()
            pipeline = bundle["pipeline"]
            # Fill any missing feature defaults safely
            feat_df = df[ALL_FEATURES].copy()
            feat_df["has_elevator"] = feat_df["has_elevator"].astype(int)
            feat_df["has_parking"] = feat_df["has_parking"].astype(int)
            feat_df["furnished"] = feat_df["furnished"].astype(int)
            feat_df["is_exterior"] = feat_df["is_exterior"].astype(int)
            pred_prices = np.round(pipeline.predict(feat_df), 2)
            df["predicted_price"] = pred_prices
            df["deviation_pct"] = np.round(((df["price_month"] - df["predicted_price"]) / df["predicted_price"]) * 100, 2)
            def _verdict(d):
                if d < -12.0:
                    return "Oportunidad / Muy buen precio"
                elif d > 12.0:
                    return "Sobreprecio"
                return "Precio de mercado"
            df["market_verdict"] = df["deviation_pct"].apply(_verdict)
        except Exception as e:
            print(f"Warning: Could not precalculate valuations: {e}")
            df["predicted_price"] = None
            df["deviation_pct"] = None
            df["market_verdict"] = None

        _DF_PROPERTIES = df
        _PROPERTIES_BY_ID = {
            str(row["id"]): row for row in df.to_dict(orient="records")
        }
    return _DF_PROPERTIES


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle handler."""
    # Pre-load dataset and ML model on startup
    print("Pre-loading dataset and ML valuation model...")
    get_properties_df()
    load_model()
    print("Startup complete: dataset & model loaded in memory.")
    yield


app = FastAPI(
    title="A Coruña Real Estate & Rental Valuation API",
    description=(
        "API analítica y predictiva del mercado del alquiler en la ciudad de A Coruña. "
        "Permite consultar ofertas reales/sintetizadas, estadísticas por barrio, resumen de mercado "
        "y simulación de precios con algoritmos de Machine Learning."
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Enable CORS for frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get(
    "/api/v1/health",
    response_model=HealthResponse,
    tags=["System"],
    summary="Estado de salud de la API y versión del modelo",
)
def health_check() -> HealthResponse:
    df = get_properties_df()
    try:
        model_bundle = load_model()
        metrics = model_bundle.get("metrics")
        model_loaded = True
    except Exception:
        metrics = None
        model_loaded = False

    return HealthResponse(
        status="ok",
        app_name="A Coruña Rental Market Intelligence API",
        version="1.0.0",
        total_listings=len(df),
        model_loaded=model_loaded,
        model_metrics=metrics,
    )


@app.get(
    "/api/v1/neighborhoods",
    response_model=List[Dict[str, str]],
    tags=["Metadata"],
    summary="Listado de barrios disponibles con su slug y nombre",
)
def list_neighborhoods() -> List[Dict[str, str]]:
    df = get_properties_df()
    unique_n = (
        df[["neighborhood_id", "neighborhood"]]
        .drop_duplicates()
        .sort_values("neighborhood")
        .to_dict(orient="records")
    )
    return unique_n


@app.get(
    "/api/v1/properties",
    response_model=PaginatedPropertiesResponse,
    tags=["Properties"],
    summary="Consulta de listado de viviendas con filtrado y paginación",
)
def get_properties(
    neighborhood_id: Annotated[Optional[str], Query(description="Filtrar por slug de barrio")] = None,
    min_price: Annotated[Optional[int], Query(ge=0, description="Precio mínimo mensual (€)")] = None,
    max_price: Annotated[Optional[int], Query(ge=0, description="Precio máximo mensual (€)")] = None,
    min_sqm: Annotated[Optional[int], Query(ge=10, description="Superficie mínima en m²")] = None,
    max_sqm: Annotated[Optional[int], Query(ge=10, description="Superficie máxima en m²")] = None,
    rooms: Annotated[Optional[int], Query(ge=1, le=10, description="Número exacto de habitaciones")] = None,
    min_rooms: Annotated[Optional[int], Query(ge=1, le=10, description="Mínimo de habitaciones")] = None,
    bathrooms: Annotated[Optional[int], Query(ge=1, description="Mínimo de baños")] = None,
    has_elevator: Annotated[Optional[bool], Query(description="Dispone de ascensor")] = None,
    has_parking: Annotated[Optional[bool], Query(description="Dispone de plaza de garaje")] = None,
    furnished: Annotated[Optional[bool], Query(description="Amueblado")] = None,
    property_type: Annotated[Optional[str], Query(description="Tipo de inmueble (piso, apartamento, duplex, atico, estudio)")] = None,
    is_real: Annotated[Optional[bool], Query(description="Filtrar exclusivamente anuncios 100% reales de portales")] = None,
    market_verdict: Annotated[Optional[str], Query(description="Filtrar por veredicto ML ('Oportunidad / Muy buen precio', 'Precio de mercado', 'Sobreprecio')")] = None,
    sort_by: Annotated[
        Optional[str],
        Query(description="Criterio de orden: opportunity, best_deals, price_asc, price_desc, sqm_asc, sqm_desc, price_sqm_asc, price_sqm_desc, newest")
    ] = "price_asc",
    page: Annotated[int, Query(ge=1, description="Número de página (1-indexed)")] = 1,
    page_size: Annotated[int, Query(ge=1, le=1000, description="Elementos por página")] = 20,
) -> PaginatedPropertiesResponse:
    df = get_properties_df().copy()

    # Apply filters
    if neighborhood_id:
        df = df[df["neighborhood_id"] == neighborhood_id]
    if min_price is not None:
        df = df[df["price_month"] >= min_price]
    if max_price is not None:
        df = df[df["price_month"] <= max_price]
    if min_sqm is not None:
        df = df[df["sqm"] >= min_sqm]
    if max_sqm is not None:
        df = df[df["sqm"] <= max_sqm]
    if rooms is not None:
        df = df[df["rooms"] == rooms]
    if min_rooms is not None:
        df = df[df["rooms"] >= min_rooms]
    if bathrooms is not None:
        df = df[df["bathrooms"] >= bathrooms]
    if has_elevator is not None:
        df = df[df["has_elevator"] == has_elevator]
    if has_parking is not None:
        df = df[df["has_parking"] == has_parking]
    if furnished is not None:
        df = df[df["furnished"] == furnished]
    if property_type:
        df = df[df["property_type"].str.lower() == property_type.lower()]
    if is_real is not None:
        df = df[df["is_real"] == is_real]
    if market_verdict:
        df = df[df["market_verdict"] == market_verdict]

    # Sorting
    sort_map = {
        "opportunity": ("deviation_pct", True),
        "best_deals": ("deviation_pct", True),
        "worst_deals": ("deviation_pct", False),
        "price_asc": ("price_month", True),
        "price_desc": ("price_month", False),
        "sqm_asc": ("sqm", True),
        "sqm_desc": ("sqm", False),
        "price_sqm_asc": ("price_sqm", True),
        "price_sqm_desc": ("price_sqm", False),
        "newest": ("created_at", False),
    }

    if sort_by in sort_map:
        col, ascending = sort_map[sort_by]
        df = df.sort_values(by=col, ascending=ascending)

    total = len(df)
    total_pages = max(1, int(np.ceil(total / page_size)))
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size

    sliced = df.iloc[start_idx:end_idx]
    items = sliced.to_dict(orient="records")

    return PaginatedPropertiesResponse(
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        items=[PropertyResponse(**item) for item in items],
    )


@app.get(
    "/api/v1/properties/{property_id}",
    response_model=PropertyDetailResponse,
    tags=["Properties"],
    summary="Detalle completo de una vivienda con su tasación por Machine Learning",
)
def get_property_by_id(property_id: str) -> PropertyDetailResponse:
    get_properties_df()
    prop_dict = _PROPERTIES_BY_ID.get(property_id)
    if not prop_dict:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Inmueble con ID '{property_id}' no encontrado",
        )

    # Compute ML Valuation with market verdict
    valuation_res = predict_valuation(prop_dict, offered_price=float(prop_dict["price_month"]))
    valuation_obj = ValuationResponse(**valuation_res)

    return PropertyDetailResponse(**prop_dict, valuation=valuation_obj)


@app.get(
    "/api/v1/stats/neighborhoods",
    response_model=List[NeighborhoodStats],
    tags=["Analytics"],
    summary="Métricas agregadas y dispersión de precios por barrio",
)
def get_neighborhood_stats() -> List[NeighborhoodStats]:
    df = get_properties_df()

    stats_list: List[NeighborhoodStats] = []
    grouped = df.groupby(["neighborhood_id", "neighborhood"])

    for (n_id, n_name), grp in grouped:
        stats_list.append(
            NeighborhoodStats(
                neighborhood_id=n_id,
                neighborhood=n_name,
                count=int(len(grp)),
                avg_price=round(float(grp["price_month"].mean()), 2),
                median_price=round(float(grp["price_month"].median()), 2),
                min_price=round(float(grp["price_month"].min()), 2),
                max_price=round(float(grp["price_month"].max()), 2),
                avg_price_sqm=round(float(grp["price_sqm"].mean()), 2),
                median_price_sqm=round(float(grp["price_sqm"].median()), 2),
                std_price=round(float(grp["price_month"].std()), 2) if len(grp) > 1 else 0.0,
                avg_sqm=round(float(grp["sqm"].mean()), 2),
            )
        )

    # Sort by avg_price_sqm descending
    stats_list.sort(key=lambda x: x.avg_price_sqm, reverse=True)
    return stats_list


@app.get(
    "/api/v1/stats/market-summary",
    response_model=MarketSummaryResponse,
    tags=["Analytics"],
    summary="Resumen global del mercado inmobiliario en A Coruña",
)
def get_market_summary() -> MarketSummaryResponse:
    df = get_properties_df()
    n_stats = get_neighborhood_stats()

    # Most expensive and cheapest neighborhoods by €/m²
    most_expensive = n_stats[:3]
    cheapest = list(reversed(n_stats[-3:]))

    # Distribution of property types
    type_counts = df["property_type"].value_counts().to_dict()

    # Amenities percentages
    total = len(df)
    amenities = {
        "pct_elevator": round((df["has_elevator"].sum() / total) * 100, 2),
        "pct_parking": round((df["has_parking"].sum() / total) * 100, 2),
        "pct_furnished": round((df["furnished"].sum() / total) * 100, 2),
        "pct_exterior": round((df["is_exterior"].sum() / total) * 100, 2),
    }

    try:
        model_bundle = load_model()
        model_metrics = model_bundle.get("metrics")
    except Exception:
        model_metrics = None

    return MarketSummaryResponse(
        total_properties=total,
        avg_price=round(float(df["price_month"].mean()), 2),
        median_price=round(float(df["price_month"].median()), 2),
        min_price=round(float(df["price_month"].min()), 2),
        max_price=round(float(df["price_month"].max()), 2),
        avg_price_sqm=round(float(df["price_sqm"].mean()), 2),
        median_price_sqm=round(float(df["price_sqm"].median()), 2),
        most_expensive_neighborhoods=most_expensive,
        cheapest_neighborhoods=cheapest,
        property_type_distribution=type_counts,
        amenities_pct=amenities,
        model_metrics=model_metrics,
    )


@app.post(
    "/api/v1/valuation/predict",
    response_model=ValuationResponse,
    tags=["Valuation"],
    summary="Simulador interactivo de tasación de alquiler con veredicto de oportunidad",
)
def predict_rental_price(request: ValuationRequest) -> ValuationResponse:
    try:
        result = predict_valuation(request, offered_price=request.offered_price)
        return ValuationResponse(**result)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error al calcular la tasación: {str(e)}",
        )


# Mount static files for frontend SPA
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")

