from __future__ import annotations

import io
import pickle
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .feature_pipeline import (
    InputValidationError,
    RAW_COLUMNS,
    transform_raw_dataframe,
)

BASE_DIR = Path(__file__).resolve().parent
MODEL_PATH = BASE_DIR / "xgboost_lastmile_model.pkl"

app = FastAPI(title="API Previsão de Atrasos - TCC")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class DadosEntrega(BaseModel):
    """Dados disponíveis no momento da coleta pela transportadora."""

    purchase_date: str
    purchase_time: str
    carrier_datetime: str
    estimated_delivery_datetime: str
    price: float
    freight_value: float
    product_weight_g: float
    height_cm: float
    width_cm: float
    length_cm: float
    distance_km: float
    same_city: int
    customer_city: str
    seller_city: str
    category_name: str


def _load_artifact() -> dict[str, Any]:
    if not MODEL_PATH.exists():
        raise RuntimeError(f"Modelo não encontrado em {MODEL_PATH.name}.")
    with MODEL_PATH.open("rb") as file:
        artifact = pickle.load(file)

    required = {
        "modelo",
        "limiar",
        "feature_names",
        "scaler",
        "encoding_maps",
        "global_delay_rate",
        "schema_version",
    }
    missing = required.difference(artifact) if isinstance(artifact, dict) else required
    if missing:
        raise RuntimeError(
            "Artefato do modelo incompatível. Gere o arquivo pelo notebook atualizado. "
            f"Campos ausentes: {', '.join(sorted(missing))}."
        )
    if artifact["schema_version"] != 2:
        raise RuntimeError("Versão do artefato não suportada pela API atual.")
    return artifact


try:
    ARTEFATO = _load_artifact()
    MODELO = ARTEFATO["modelo"]
    LIMIAR_ATRASO = float(ARTEFATO["limiar"])
    LOAD_ERROR = None
except Exception as exc:  # Mantém /health disponível para facilitar diagnóstico.
    ARTEFATO = None
    MODELO = None
    LIMIAR_ATRASO = 0.20
    LOAD_ERROR = str(exc)


FEATURE_LABELS = {
    "holiday_at_carrier": "Feriado na coleta",
    "days_since_last_holiday": "Dias desde o último feriado",
    "days_until_next_holiday": "Dias até o próximo feriado",
    "ecommerce_event_at_carrier": "Evento de e-commerce na coleta",
    "days_since_last_ecommerce_event": "Dias desde o último evento de e-commerce",
    "days_until_next_ecommerce_event": "Dias até o próximo evento de e-commerce",
    "is_ecommerce_event_in_7_days": "Evento de e-commerce nos próximos 7 dias",
    "is_ecommerce_event_in_14_days": "Evento de e-commerce nos próximos 14 dias",
    "had_ecommerce_event_7_days_ago": "Evento de e-commerce nos últimos 7 dias",
    "had_ecommerce_event_14_days_ago": "Evento de e-commerce nos últimos 14 dias",
    "purchase_hour": "Horário da compra",
    "purchase_day_of_week": "Dia da semana da compra",
    "price": "Valor do produto",
    "freight_value": "Valor do frete",
    "product_weight_g": "Peso do produto",
    "volume_cm3": "Volume do produto",
    "distance_km": "Distância da entrega",
    "same_city": "Mesma cidade",
    "prazo_transportadora_dias": "Prazo restante da transportadora",
    "purchase_month": "Mês da compra",
    "prazo_por_km": "Prazo por quilômetro",
    "frete_por_kg": "Frete por quilograma",
    "densidade_produto": "Densidade do produto",
    "customer_city_encoded": "Histórico da cidade do cliente",
    "seller_city_encoded": "Histórico da cidade do vendedor",
    "category_name_encoded": "Histórico da categoria",
}


def _require_model() -> None:
    if MODELO is None or ARTEFATO is None:
        raise HTTPException(status_code=503, detail=f"Modelo indisponível: {LOAD_ERROR}")


def _risk_level(probability: float) -> str:
    if probability < LIMIAR_ATRASO:
        return "Baixo"
    if probability < 0.30:
        return "Atenção"
    if probability < 0.61:
        return "Moderado"
    if probability < 0.81:
        return "Alto"
    return "Muito alto"


def _local_factors(feature_row: pd.DataFrame) -> list[dict[str, Any]]:
    """Calcula contribuições locais do XGBoost; sem trocar a previsão se falhar."""
    try:
        import xgboost as xgb

        booster = MODELO.get_booster()
        contributions = booster.predict(xgb.DMatrix(feature_row), pred_contribs=True)[0][:-1]
        impacts = dict(zip(feature_row.columns, map(abs, contributions)))
    except Exception:
        importances = getattr(MODELO, "feature_importances_", None)
        if importances is None:
            return []
        impacts = dict(zip(feature_row.columns, map(float, importances)))

    top = sorted(impacts.items(), key=lambda item: item[1], reverse=True)[:5]
    highest = max((impact for _, impact in top), default=0) or 1
    return [
        {"name": FEATURE_LABELS.get(name, name), "impact": round(impact / highest * 100)}
        for name, impact in top
    ]


def _to_json_value(value: Any) -> Any:
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        return value.item()
    return value


def _build_result(
    probability: float,
    feature_row: pd.DataFrame,
    raw_row: dict[str, Any],
    pedido_id: int | None = None,
    resultado_real: int | None = None,
) -> dict[str, Any]:
    delayed = probability >= LIMIAR_ATRASO
    result = {
        "previsao_atraso": delayed,
        "prediction": int(delayed),
        "probabilidade": probability,
        "probability": probability,
        "risk_level": _risk_level(probability),
        "decision_threshold": LIMIAR_ATRASO,
        "main_model": "XGBoost",
        "models": [{"name": "XGBoost", "probability": probability, "prediction": int(delayed)}],
        "factors": _local_factors(feature_row),
        "input": {key: _to_json_value(value) for key, value in raw_row.items()},
    }
    if pedido_id is not None:
        result["pedido_id"] = pedido_id
    if resultado_real is not None:
        result["resultado_real"] = resultado_real
    return result


def _predict_raw_dataframe(raw_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, list[float]]:
    _require_model()
    try:
        clean_raw, features = transform_raw_dataframe(raw_df, ARTEFATO)
    except InputValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    probabilities = MODELO.predict_proba(features)[:, 1].astype(float).tolist()
    return clean_raw, features, probabilities


@app.get("/health")
def health_check():
    return {
        "status": "ok" if LOAD_ERROR is None else "error",
        "model_loaded": LOAD_ERROR is None,
        "inference_moment": "carrier_collection",
        "raw_columns": RAW_COLUMNS,
        "threshold": LIMIAR_ATRASO,
        "detail": LOAD_ERROR,
    }


@app.post("/predict")
def prever_atraso_individual(dados: DadosEntrega):
    payload = dados.model_dump() if hasattr(dados, "model_dump") else dados.dict()
    clean_raw, features, probabilities = _predict_raw_dataframe(pd.DataFrame([payload]))
    result = _build_result(probabilities[0], features.iloc[[0]], clean_raw.iloc[0].to_dict())
    result["analysis_id"] = f"IND-{pd.Timestamp.now().strftime('%Y%m%d%H%M%S')}"
    result["demo_mode"] = False
    return result


@app.post("/predict-batch")
async def prever_atraso_lote(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="O arquivo deve ser um CSV.")

    content = await file.read()
    try:
        raw_df = pd.read_csv(io.StringIO(content.decode("utf-8-sig")))
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="O CSV deve estar codificado em UTF-8.") from exc
    except pd.errors.EmptyDataError as exc:
        raise HTTPException(status_code=400, detail="O CSV está vazio.") from exc
    except pd.errors.ParserError as exc:
        raise HTTPException(status_code=400, detail=f"CSV inválido: {exc}") from exc

    clean_raw, features, probabilities = _predict_raw_dataframe(raw_df)
    resultados = []
    for position, probability in enumerate(probabilities):
        actual = raw_df.iloc[position].get("target_real_atraso")
        if pd.notna(actual):
            try:
                actual = int(float(actual))
            except (TypeError, ValueError) as exc:
                raise HTTPException(
                    status_code=400,
                    detail=f"Linha {position + 2}: 'target_real_atraso' deve ser 0 ou 1.",
                ) from exc
            if actual not in (0, 1):
                raise HTTPException(
                    status_code=400,
                    detail=f"Linha {position + 2}: 'target_real_atraso' deve ser 0 ou 1.",
                )
        else:
            actual = None
        resultados.append(
            _build_result(
                probability,
                features.iloc[[position]],
                clean_raw.iloc[position].to_dict(),
                pedido_id=position + 1,
                resultado_real=actual,
            )
        )

    delayed_count = sum(result["prediction"] for result in resultados)
    return {
        "analysis_id": f"LOTE-{pd.Timestamp.now().strftime('%Y%m%d%H%M%S')}",
        "total": len(resultados),
        "delayed_count": delayed_count,
        "on_time_count": len(resultados) - delayed_count,
        "decision_threshold": LIMIAR_ATRASO,
        "resultados": resultados,
        "demo_mode": False,
    }


frontend_dir = BASE_DIR / "frontend"
if frontend_dir.is_dir():
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
