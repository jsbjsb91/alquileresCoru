"""
Pydantic schemas for the A Coruña Rental Market Backend API.
"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, ConfigDict


class HealthResponse(BaseModel):
    status: str = Field(default="ok", description="API operational status")
    app_name: str = Field(default="A Coruña Rental Market Intelligence API")
    version: str = Field(default="1.0.0")
    total_listings: int = Field(description="Number of processed rental records available")
    model_loaded: bool = Field(description="Flag indicating if the ML valuation model is loaded")
    model_metrics: Optional[Dict[str, Any]] = Field(default=None, description="Evaluation metrics of the loaded ML model")


class ValuationRequest(BaseModel):
    sqm: float = Field(..., gt=10, le=500, description="Superficie construida/útil de la vivienda en m²", examples=[85.0])
    rooms: int = Field(default=2, ge=1, le=10, description="Número de dormitorios / habitaciones", examples=[2])
    bathrooms: int = Field(default=1, ge=1, le=6, description="Número de cuartos de baño", examples=[1])
    neighborhood_id: str = Field(
        ...,
        description="Identificador del barrio en A Coruña (slug, ej. 'pescaderia_ensanche', 'monte_alto', 'cuatro_caminos')",
        examples=["pescaderia_ensanche"]
    )
    has_elevator: bool = Field(default=True, description="Dispone de ascensor", examples=[True])
    has_parking: bool = Field(default=False, description="Dispone de plaza de garaje incluida", examples=[False])
    furnished: bool = Field(default=False, description="Se alquila amueblado", examples=[False])
    is_exterior: bool = Field(default=True, description="Vivienda exterior con luz natural", examples=[True])
    property_type: str = Field(
        default="piso",
        description="Tipología ('piso', 'apartamento', 'estudio', 'duplex', 'atico')",
        examples=["piso"]
    )
    offered_price: Optional[float] = Field(
        default=None,
        gt=0,
        description="Precio mensual de oferta a evaluar (€/mes). Si se proporciona, se calcula veredicto y desviación.",
        examples=[950.0]
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "sqm": 85.0,
                "rooms": 2,
                "bathrooms": 1,
                "neighborhood_id": "pescaderia_ensanche",
                "has_elevator": True,
                "has_parking": False,
                "furnished": True,
                "is_exterior": True,
                "property_type": "piso",
                "offered_price": 950.0
            }
        }
    )


class ValuationResponse(BaseModel):
    predicted_price: float = Field(..., description="Precio estimado de mercado mensual en EUR (€/mes)")
    price_range_min: float = Field(..., description="Límite inferior del rango de confianza estimado (-10%)")
    price_range_max: float = Field(..., description="Límite superior del rango de confianza estimado (+10%)")
    predicted_price_sqm: float = Field(..., description="Precio estimado por metro cuadrado (€/m²)")
    market_verdict: str = Field(
        ...,
        description="Diagnóstico comparativo: 'Oportunidad / Muy buen precio', 'Precio de mercado', o 'Sobreprecio'"
    )
    deviation_pct: Optional[float] = Field(
        default=None,
        description="Porcentaje de desviación del precio ofertado respecto al valor de mercado estimado"
    )
    offered_price: Optional[float] = Field(
        default=None,
        description="Precio ofertado evaluado (€/mes)"
    )
    neighborhood_id: str = Field(..., description="Barrio tasado")
    sqm: float = Field(..., description="Metros cuadrados tasados")
    model_version: str = Field(default="1.0.0", description="Versión del pipeline de tasación")


class PropertyResponse(BaseModel):
    id: str = Field(..., description="ID único del inmueble")
    title: str = Field(..., description="Título de la publicación")
    neighborhood: str = Field(..., description="Nombre del barrio")
    neighborhood_id: str = Field(..., description="Identificador slug del barrio")
    municipality: str = Field(default="A Coruña", description="Concello o municipio de la vivienda")
    price_month: float = Field(..., description="Precio mensual en euros (€/mes)")
    sqm: float = Field(..., description="Superficie en m²")
    rooms: int = Field(..., description="Número de habitaciones")
    bathrooms: int = Field(..., description="Número de baños")
    floor: str = Field(..., description="Planta del inmueble")
    has_elevator: bool = Field(..., description="Tiene ascensor")
    is_exterior: bool = Field(default=True, description="Es exterior")
    furnished: bool = Field(default=False, description="Amueblado")
    has_parking: bool = Field(default=False, description="Tiene plaza de garaje")
    lat: float = Field(..., description="Latitud")
    lon: float = Field(..., description="Longitud")
    price_sqm: float = Field(..., description="Precio por m² (€/m²)")
    property_type: str = Field(default="piso", description="Tipo de propiedad")
    is_outlier: bool = Field(default=False, description="Indica si es un valor atípico")
    created_at: str = Field(default="", description="Fecha de publicación ISO 8601")
    url: Optional[str] = Field(default=None, description="Enlace directo al anuncio real en el portal")
    photo_url: Optional[str] = Field(default=None, description="URL de fotografía real del inmueble")
    is_real: bool = Field(default=False, description="Indica si es un anuncio 100% real de mercado")
    source: Optional[str] = Field(default="synthetic", description="Portal o fuente del anuncio")
    predicted_price: Optional[float] = Field(default=None, description="Precio estimado por modelo ML")
    deviation_pct: Optional[float] = Field(default=None, description="Desviación porcentual respecto a tasación ML")
    market_verdict: Optional[str] = Field(default=None, description="Veredicto de mercado ML")

    model_config = ConfigDict(from_attributes=True)


class PropertyDetailResponse(PropertyResponse):
    valuation: Optional[ValuationResponse] = Field(
        default=None,
        description="Tasación y veredicto de mercado calculados automáticamente por el modelo ML"
    )


class PaginatedPropertiesResponse(BaseModel):
    total: int = Field(..., description="Total de propiedades que coinciden con los filtros")
    page: int = Field(..., description="Página actual (1-indexed)")
    page_size: int = Field(..., description="Elementos por página")
    total_pages: int = Field(..., description="Total de páginas disponibles")
    items: List[PropertyResponse] = Field(..., description="Listado de inmuebles de la página")


class NeighborhoodStats(BaseModel):
    neighborhood_id: str = Field(..., description="Identificador slug del barrio")
    neighborhood: str = Field(..., description="Nombre descriptivo del barrio")
    count: int = Field(..., description="Número de ofertas registradas en este barrio")
    avg_price: float = Field(..., description="Precio mensual medio en euros")
    median_price: float = Field(..., description="Mediana del precio mensual")
    min_price: float = Field(..., description="Precio mensual mínimo")
    max_price: float = Field(..., description="Precio mensual máximo")
    avg_price_sqm: float = Field(..., description="Precio medio por metro cuadrado (€/m²)")
    median_price_sqm: float = Field(..., description="Mediana del precio por metro cuadrado (€/m²)")
    std_price: float = Field(..., description="Desviación típica del precio (dispersión)")
    avg_sqm: float = Field(..., description="Superficie media en m²")


class MarketSummaryResponse(BaseModel):
    total_properties: int = Field(..., description="Total de inmuebles en la muestra")
    avg_price: float = Field(..., description="Precio medio global de alquiler mensual")
    median_price: float = Field(..., description="Precio mediano global de alquiler mensual")
    min_price: float = Field(..., description="Precio mínimo registrado")
    max_price: float = Field(..., description="Precio máximo registrado")
    avg_price_sqm: float = Field(..., description="Precio medio global por metro cuadrado (€/m²)")
    median_price_sqm: float = Field(..., description="Precio mediano global por metro cuadrado (€/m²)")
    most_expensive_neighborhoods: List[NeighborhoodStats] = Field(..., description="Top 3 barrios con mayor €/m²")
    cheapest_neighborhoods: List[NeighborhoodStats] = Field(..., description="Top 3 barrios con menor €/m²")
    property_type_distribution: Dict[str, int] = Field(..., description="Distribución por tipología de vivienda")
    amenities_pct: Dict[str, float] = Field(..., description="Porcentajes de comodidades (% ascensor, parking, etc.)")
    model_metrics: Optional[Dict[str, Any]] = Field(default=None, description="Métricas del modelo de tasación ML")
