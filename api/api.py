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
MLP_MODEL_PATH = BASE_DIR / "modelo_mlp_final.pkl"
XGBOOST_MODEL_PATH = BASE_DIR / "xgboost_lastmile_model.pkl"

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


def _load_mlp_artifact() -> dict[str, Any]:
    if not MLP_MODEL_PATH.exists():
        raise RuntimeError(f"Modelo MLP não encontrado em {MLP_MODEL_PATH.name}.")
    with MLP_MODEL_PATH.open("rb") as file:
        artifact = pickle.load(file)

    required = {
        "model",
        "threshold",
        "features",
        "scaler",
        "encoding_maps",
        "global_delay_rate",
        "schema_version",
        "model_type",
    }
    missing = required.difference(artifact) if isinstance(artifact, dict) else required
    if missing:
        raise RuntimeError(
            "Artefato do MLP incompatível. Gere o arquivo pelo notebook atualizado. "
            f"Campos ausentes: {', '.join(sorted(missing))}."
        )
    if artifact["schema_version"] != 3:
        raise RuntimeError("Versão do artefato não suportada pela API atual.")
    if artifact["model_type"] != "MLPClassifier":
        raise RuntimeError("O artefato informado não contém um modelo MLPClassifier.")
    if not hasattr(artifact["model"], "predict_proba"):
        raise RuntimeError("O modelo MLP não suporta cálculo de probabilidades.")
    return artifact


def _load_xgboost_artifact() -> dict[str, Any]:
    if not XGBOOST_MODEL_PATH.exists():
        raise RuntimeError(
            f"Modelo XGBoost não encontrado em {XGBOOST_MODEL_PATH.name}."
        )
    with XGBOOST_MODEL_PATH.open("rb") as file:
        artifact = pickle.load(file)

    required = {"modelo", "limiar", "feature_names", "scaler", "schema_version"}
    missing = required.difference(artifact) if isinstance(artifact, dict) else required
    if missing:
        raise RuntimeError(
            "Artefato do XGBoost incompatível. "
            f"Campos ausentes: {', '.join(sorted(missing))}."
        )
    if not hasattr(artifact["modelo"], "predict_proba"):
        raise RuntimeError("O modelo XGBoost não suporta cálculo de probabilidades.")
    return artifact


try:
    ARTEFATO = _load_mlp_artifact()
    ARTEFATO_XGBOOST = _load_xgboost_artifact()
    if ARTEFATO["features"] != ARTEFATO_XGBOOST["feature_names"]:
        raise RuntimeError("MLP e XGBoost possuem variáveis de entrada incompatíveis.")

    MODELO = ARTEFATO["model"]
    MODELO_XGBOOST = ARTEFATO_XGBOOST["modelo"]
    LIMIAR_ATRASO = float(ARTEFATO["threshold"])
    LIMIAR_XGBOOST = float(ARTEFATO_XGBOOST["limiar"])
    MODEL_NAME = str(ARTEFATO.get("model_name", "MLP (Rede Neural)"))
    XGBOOST_MODEL_NAME = "XGBoost"
    LOAD_ERROR = None
except Exception as exc:  # Mantém /health disponível para facilitar diagnóstico.
    ARTEFATO = None
    ARTEFATO_XGBOOST = None
    MODELO = None
    MODELO_XGBOOST = None
    LIMIAR_ATRASO = 0.30
    LIMIAR_XGBOOST = 0.20
    MODEL_NAME = "MLP (Rede Neural)"
    XGBOOST_MODEL_NAME = "XGBoost"
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
    if (
        MODELO is None
        or MODELO_XGBOOST is None
        or ARTEFATO is None
        or ARTEFATO_XGBOOST is None
    ):
        raise HTTPException(status_code=503, detail=f"Modelos indisponíveis: {LOAD_ERROR}")


def _risk_level(probability: float) -> str:
    """Faixas exibidas na interface para o XGBoost, modelo principal."""
    if probability < LIMIAR_XGBOOST:
        return "Baixo"
    if probability < 0.30:
        return "Atenção"
    if probability < 0.61:
        return "Moderado"
    if probability < 0.81:
        return "Alto"
    return "Muito alto"


def _format_factors(
    feature_names: list[str],
    contributions: list[float] | Any,
) -> list[dict[str, Any]]:
    """Normaliza as contribuições para as barras de explicabilidade."""
    impacts = [
        (name, float(contribution))
        for name, contribution in zip(feature_names, contributions)
    ]
    top = sorted(impacts, key=lambda item: abs(item[1]), reverse=True)[:5]
    largest_impact = max((abs(value) for _, value in top), default=0.0)
    if largest_impact == 0:
        return []

    return [
        {
            "name": FEATURE_LABELS.get(name, name),
            "impact": round(abs(value) / largest_impact * 100),
            "direction": (
                "Aumenta o risco"
                if value > 0
                else "Reduz o risco"
                if value < 0
                else "Impacto neutro"
            ),
        }
        for name, value in top
    ]


def _xgboost_local_factors(
    feature_row: pd.DataFrame,
) -> tuple[list[dict[str, Any]], str]:
    """Obtém as contribuições locais nativas do XGBoost para o pedido."""
    try:
        import xgboost as xgb

        booster = MODELO_XGBOOST.get_booster()
        feature_names = list(feature_row.columns)
        matrix = xgb.DMatrix(feature_row, feature_names=feature_names)
        contributions = booster.predict(matrix, pred_contribs=True)[0][:-1]
        return (
            _format_factors(feature_names, contributions),
            "Contribuições locais calculadas pelo XGBoost para este pedido.",
        )
    except Exception:
        # Mantém uma explicação útil caso a versão instalada do XGBoost não
        # suporte contribuições locais. O texto deixa claro que é global.
        try:
            importances = MODELO_XGBOOST.feature_importances_
            return (
                _format_factors(list(feature_row.columns), importances),
                "Importância global do XGBoost (contribuição local indisponível).",
            )
        except Exception:
            return [], "Não foi possível calcular os fatores do XGBoost para este pedido."


def _mlp_local_factors(
    feature_row: pd.DataFrame,
    base_probability: float,
) -> tuple[list[dict[str, Any]], str]:
    """Mede a sensibilidade local do MLP ao neutralizar uma variável por vez.

    As features chegam padronizadas; portanto, o valor zero representa a média
    de treino. A variação da probabilidade mede o efeito local do valor real do
    pedido em comparação com esse valor típico.
    """
    try:
        feature_names = list(feature_row.columns)
        variants = pd.concat([feature_row] * len(feature_names), ignore_index=True)
        for position, feature_name in enumerate(feature_names):
            variants.loc[position, feature_name] = 0.0

        neutralized_probabilities = MODELO.predict_proba(variants)[:, 1]
        contributions = [
            float(base_probability - probability)
            for probability in neutralized_probabilities
        ]
        return (
            _format_factors(feature_names, contributions),
            "Sensibilidade local do MLP: cada variável é comparada ao valor médio de treino.",
        )
    except Exception:
        return [], "Não foi possível calcular os fatores do MLP para este pedido."


def _model_factor_groups(
    feature_row: pd.DataFrame,
    mlp_probability: float,
) -> list[dict[str, Any]]:
    xgboost_factors, xgboost_method = _xgboost_local_factors(feature_row)
    mlp_factors, mlp_method = _mlp_local_factors(feature_row, mlp_probability)
    return [
        {
            "name": XGBOOST_MODEL_NAME,
            "method": xgboost_method,
            "factors": xgboost_factors,
        },
        {
            "name": MODEL_NAME,
            "method": mlp_method,
            "factors": mlp_factors,
        },
    ]


def _to_json_value(value: Any) -> Any:
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        return value.item()
    return value


def _build_result(
    mlp_probability: float,
    xgboost_probability: float,
    feature_row: pd.DataFrame,
    raw_row: dict[str, Any],
    pedido_id: int | None = None,
    resultado_real: int | None = None,
) -> dict[str, Any]:
    # O XGBoost é a fonte oficial da decisão apresentada no sistema. O MLP
    # permanece no retorno apenas para comparação transparente no frontend.
    delayed = xgboost_probability >= LIMIAR_XGBOOST
    mlp_delayed = mlp_probability >= LIMIAR_ATRASO
    factors_by_model = _model_factor_groups(feature_row, mlp_probability)
    result = {
        "previsao_atraso": delayed,
        "prediction": int(delayed),
        "probabilidade": xgboost_probability,
        "probability": xgboost_probability,
        "risk_level": _risk_level(xgboost_probability),
        "decision_threshold": LIMIAR_XGBOOST,
        "main_model": XGBOOST_MODEL_NAME,
        "models": [
            {
                "name": XGBOOST_MODEL_NAME,
                "probability": xgboost_probability,
                "prediction": int(xgboost_probability >= LIMIAR_XGBOOST),
                "decision_threshold": LIMIAR_XGBOOST,
            },
            {
                "name": MODEL_NAME,
                "probability": mlp_probability,
                "prediction": int(mlp_delayed),
                "decision_threshold": LIMIAR_ATRASO,
            },
        ],
        # Mantém "factors" para compatibilidade com versões anteriores do
        # frontend e fornece os dois grupos para a nova visualização.
        "factors": factors_by_model[0]["factors"],
        "factors_by_model": factors_by_model,
        "factors_available": any(group["factors"] for group in factors_by_model),
        "factors_message": "Os fatores são exibidos separadamente para cada modelo.",
        "input": {key: _to_json_value(value) for key, value in raw_row.items()},
    }
    if pedido_id is not None:
        result["pedido_id"] = pedido_id
    if resultado_real is not None:
        result["resultado_real"] = resultado_real
    return result


def _predict_raw_dataframe(
    raw_df: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, list[float], list[float]]:
    _require_model()
    try:
        clean_raw, features = transform_raw_dataframe(raw_df, ARTEFATO)
    except InputValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    mlp_probabilities = MODELO.predict_proba(features)[:, 1].astype(float).tolist()
    xgboost_probabilities = MODELO_XGBOOST.predict_proba(features)[:, 1].astype(float).tolist()
    return clean_raw, features, mlp_probabilities, xgboost_probabilities


@app.get("/health")
def health_check():
    return {
        "status": "ok" if LOAD_ERROR is None else "error",
        "model_loaded": LOAD_ERROR is None,
        "inference_moment": "carrier_collection",
        "model_name": XGBOOST_MODEL_NAME,
        "model_type": "XGBClassifier",
        "models": [
            {"name": XGBOOST_MODEL_NAME, "type": "XGBClassifier", "threshold": LIMIAR_XGBOOST},
            {"name": MODEL_NAME, "type": "MLPClassifier", "threshold": LIMIAR_ATRASO},
        ],
        "raw_columns": RAW_COLUMNS,
        "threshold": LIMIAR_XGBOOST,
        "detail": LOAD_ERROR,
    }


@app.post("/predict")
def prever_atraso_individual(dados: DadosEntrega):
    payload = dados.model_dump() if hasattr(dados, "model_dump") else dados.dict()
    clean_raw, features, mlp_probabilities, xgboost_probabilities = _predict_raw_dataframe(
        pd.DataFrame([payload])
    )
    result = _build_result(
        mlp_probabilities[0],
        xgboost_probabilities[0],
        features.iloc[[0]],
        clean_raw.iloc[0].to_dict(),
    )
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

    clean_raw, features, mlp_probabilities, xgboost_probabilities = _predict_raw_dataframe(raw_df)
    resultados = []
    for position, mlp_probability in enumerate(mlp_probabilities):
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
                mlp_probability,
                xgboost_probabilities[position],
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
        "decision_threshold": LIMIAR_XGBOOST,
        "resultados": resultados,
        "demo_mode": False,
    }


frontend_dir = BASE_DIR / "frontend"
if frontend_dir.is_dir():
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
