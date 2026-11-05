"""
Machine Learning Module for A Coruña Rental Property Valuation.
Provides training, evaluation, persistence and inference pipelines.
"""

import os
from pathlib import Path
from typing import Dict, Any, Optional, Union
from datetime import datetime, timezone

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import OneHotEncoder

# Base directories
BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DATA_PARQUET = BASE_DIR / "data" / "processed" / "alquileres_coruna.parquet"
DEFAULT_DATA_CSV = BASE_DIR / "data" / "processed" / "alquileres_coruna.csv"
DEFAULT_MODEL_PATH = BASE_DIR / "backend" / "models" / "rental_valuation_model.joblib"

# Feature configuration
CATEGORICAL_FEATURES = ["neighborhood_id", "property_type"]
NUMERICAL_FEATURES = [
    "sqm",
    "rooms",
    "bathrooms",
    "has_elevator",
    "has_parking",
    "furnished",
    "is_exterior",
]
ALL_FEATURES = CATEGORICAL_FEATURES + NUMERICAL_FEATURES
TARGET_COL = "price_month"

# Global memory cache
_MODEL_BUNDLE: Optional[Dict[str, Any]] = None


def load_dataset(parquet_path: Optional[Path] = None, csv_path: Optional[Path] = None) -> pd.DataFrame:
    """Load dataset from parquet if available, otherwise from CSV."""
    p_path = parquet_path or DEFAULT_DATA_PARQUET
    c_path = csv_path or DEFAULT_DATA_CSV

    if p_path.exists():
        df = pd.read_parquet(p_path)
    elif c_path.exists():
        df = pd.read_csv(c_path)
    else:
        raise FileNotFoundError(f"Could not find dataset at {p_path} or {c_path}")

    return df


def build_pipeline() -> Any:
    """Build scikit-learn ColumnTransformer and GradientBoostingRegressor pipeline."""
    from sklearn.pipeline import Pipeline

    preprocessor = ColumnTransformer(
        transformers=[
            (
                "cat",
                OneHotEncoder(handle_unknown="ignore", sparse_output=False),
                CATEGORICAL_FEATURES,
            ),
            (
                "num",
                "passthrough",
                NUMERICAL_FEATURES,
            ),
        ]
    )

    # GradientBoosting offers strong non-linear fit and robustness on tabular real-estate data
    model = GradientBoostingRegressor(
        n_estimators=180,
        learning_rate=0.07,
        max_depth=4,
        subsample=0.85,
        random_state=42,
    )

    return Pipeline([("preprocessor", preprocessor), ("regressor", model)])


def train_and_save_model(
    data_path: Optional[Union[str, Path]] = None,
    model_path: Optional[Union[str, Path]] = None,
    exclude_outliers: bool = True,
) -> Dict[str, Any]:
    """
    Train valuation regression model on rental dataset, evaluate metrics and persist to disk.
    """
    m_path = Path(model_path) if model_path else DEFAULT_MODEL_PATH
    m_path.parent.mkdir(parents=True, exist_ok=True)

    df = load_dataset(parquet_path=Path(data_path) if data_path else None)

    # Exclude synthetic extreme outliers to train a robust baseline market valuation
    if exclude_outliers and "is_outlier" in df.columns:
        train_df = df[~df["is_outlier"]].copy()
    else:
        train_df = df.copy()

    X = train_df[ALL_FEATURES].copy()
    y = train_df[TARGET_COL].copy()

    # Ensure boolean columns are integers
    for col in ["has_elevator", "has_parking", "furnished", "is_exterior"]:
        X[col] = X[col].astype(int)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.20, random_state=42
    )

    pipeline = build_pipeline()
    pipeline.fit(X_train, y_train)

    y_pred = pipeline.predict(X_test)

    mae = float(mean_absolute_error(y_test, y_pred))
    rmse = float(np.sqrt(mean_squared_error(y_test, y_pred)))
    r2 = float(r2_score(y_test, y_pred))

    bundle = {
        "pipeline": pipeline,
        "feature_names": ALL_FEATURES,
        "metrics": {
            "r2": round(r2, 4),
            "mae": round(mae, 2),
            "rmse": round(rmse, 2),
            "train_samples": len(X_train),
            "test_samples": len(X_test),
            "total_samples": len(train_df),
            "model_type": "GradientBoostingRegressor (scikit-learn)",
        },
        "neighborhoods": sorted(train_df["neighborhood_id"].unique().tolist()),
        "property_types": sorted(train_df["property_type"].unique().tolist()),
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "version": "1.0.0",
    }

    joblib.dump(bundle, m_path)

    global _MODEL_BUNDLE
    _MODEL_BUNDLE = bundle

    print("==================================================")
    print(" [ML Training] A Coruña Rental Valuation Model")
    print(f" -> Output file: {m_path}")
    print(f" -> Samples: {len(train_df)} (Train: {len(X_train)}, Test: {len(X_test)})")
    print(f" -> R² Score: {r2:.4f}")
    print(f" -> MAE:     {mae:.2f} €/mes")
    print(f" -> RMSE:    {rmse:.2f} €/mes")
    print("==================================================")

    return bundle


def load_model(model_path: Optional[Union[str, Path]] = None) -> Dict[str, Any]:
    """
    Load model bundle from disk or train if missing. Caches in memory.
    """
    global _MODEL_BUNDLE
    if _MODEL_BUNDLE is not None:
        return _MODEL_BUNDLE

    m_path = Path(model_path) if model_path else DEFAULT_MODEL_PATH
    if not m_path.exists():
        print(f"Model file not found at {m_path}. Training new model...")
        return train_and_save_model(model_path=m_path)

    bundle = joblib.load(m_path)
    _MODEL_BUNDLE = bundle
    return bundle


def predict_valuation(
    features: Union[Dict[str, Any], Any],
    offered_price: Optional[float] = None,
    model_path: Optional[Union[str, Path]] = None,
) -> Dict[str, Any]:
    """
    Predict fair market rental price and compute evaluation verdict.

    Parameters:
    - features: dict or Pydantic object with keys:
        sqm, rooms, bathrooms, neighborhood_id, has_elevator, has_parking,
        furnished, is_exterior, property_type
    - offered_price: optional real or asking monthly price to benchmark.

    Returns:
    - dict with keys:
        predicted_price, price_range_min, price_range_max,
        predicted_price_sqm, market_verdict, deviation_pct,
        offered_price, neighborhood_id, sqm, model_version
    """
    bundle = load_model(model_path)
    pipeline = bundle["pipeline"]

    # Normalize input features into a clean dictionary
    if hasattr(features, "model_dump"):
        raw_dict = features.model_dump()
    elif hasattr(features, "dict"):
        raw_dict = features.dict()
    elif isinstance(features, dict):
        raw_dict = dict(features)
    else:
        raise ValueError(f"Unsupported features type: {type(features)}")

    # Check for offered_price in parameters or in raw_dict
    price_to_eval = offered_price
    if price_to_eval is None and "offered_price" in raw_dict:
        price_to_eval = raw_dict["offered_price"]
    elif price_to_eval is None and "price_month" in raw_dict:
        price_to_eval = float(raw_dict["price_month"])

    sqm = float(raw_dict.get("sqm", 75.0))
    rooms = int(raw_dict.get("rooms", 2))
    bathrooms = int(raw_dict.get("bathrooms", 1))
    neighborhood_id = str(raw_dict.get("neighborhood_id", "pescaderia_ensanche"))
    property_type = str(raw_dict.get("property_type", "piso"))
    has_elevator = int(bool(raw_dict.get("has_elevator", True)))
    has_parking = int(bool(raw_dict.get("has_parking", False)))
    furnished = int(bool(raw_dict.get("furnished", False)))
    is_exterior = int(bool(raw_dict.get("is_exterior", True)))

    input_df = pd.DataFrame(
        [
            {
                "neighborhood_id": neighborhood_id,
                "property_type": property_type,
                "sqm": sqm,
                "rooms": rooms,
                "bathrooms": bathrooms,
                "has_elevator": has_elevator,
                "has_parking": has_parking,
                "furnished": furnished,
                "is_exterior": is_exterior,
            }
        ]
    )

    pred_val = float(pipeline.predict(input_df)[0])
    predicted_price = round(pred_val, 2)
    # Market range ±10%
    price_range_min = round(predicted_price * 0.90, 2)
    price_range_max = round(predicted_price * 1.10, 2)
    predicted_price_sqm = round(predicted_price / max(sqm, 1.0), 2)

    # Market Verdict calculation
    deviation_pct: Optional[float] = None
    if price_to_eval is not None and price_to_eval > 0:
        deviation_pct = round(((price_to_eval - predicted_price) / predicted_price) * 100, 2)
        if deviation_pct < -12.0:
            market_verdict = "Oportunidad / Muy buen precio"
        elif deviation_pct > 12.0:
            market_verdict = "Sobreprecio"
        else:
            market_verdict = "Precio de mercado"
    else:
        market_verdict = "Precio de mercado"

    return {
        "predicted_price": predicted_price,
        "price_range_min": price_range_min,
        "price_range_max": price_range_max,
        "predicted_price_sqm": predicted_price_sqm,
        "market_verdict": market_verdict,
        "deviation_pct": deviation_pct,
        "offered_price": price_to_eval,
        "neighborhood_id": neighborhood_id,
        "sqm": sqm,
        "model_version": bundle.get("version", "1.0.0"),
    }


if __name__ == "__main__":
    train_and_save_model()
