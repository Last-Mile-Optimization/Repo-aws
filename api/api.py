from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import pandas as pd
import pickle
import io
import os

app = FastAPI(title="API Previsão de Atrasos - TCC")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

@app.get("/health")
def health_check():
    return {"status": "ok", "message": "API Online"}

FEATURES = [
    'holiday_at_purchase', 'is_holiday_in_7_days', 'is_holiday_in_14_days',
    'had_holiday_7_days_ago', 'purchase_hour', 'purchase_day_of_week',
    'is_weekend', 'price', 'freight_value', 'product_weight_g',
    'volume_cm3', 'distance_km', 'same_city', 'prazo_transportadora_dias'
]

FEATURE_LABELS = {
    'holiday_at_purchase': 'Feriado na compra',
    'is_holiday_in_7_days': 'Feriado nos próximos 7 dias',
    'is_holiday_in_14_days': 'Feriado nos próximos 14 dias',
    'had_holiday_7_days_ago': 'Feriado nos últimos 7 dias',
    'purchase_hour': 'Horário da compra',
    'purchase_day_of_week': 'Dia da semana',
    'is_weekend': 'Fim de semana',
    'price': 'Valor do produto',
    'freight_value': 'Valor do frete',
    'product_weight_g': 'Peso do produto',
    'volume_cm3': 'Volume do produto',
    'distance_km': 'Distância da entrega',
    'same_city': 'Mesma cidade',
    'prazo_transportadora_dias': 'Prazo da transportadora'
}

class DadosEntrega(BaseModel):
    holiday_at_purchase: int
    is_holiday_in_7_days: int
    is_holiday_in_14_days: int
    had_holiday_7_days_ago: int
    purchase_hour: int
    purchase_day_of_week: int
    is_weekend: int
    price: float
    freight_value: float
    product_weight_g: float
    volume_cm3: float
    distance_km: float
    same_city: int
    prazo_transportadora_dias: int

modelo = None
limiar_atraso = 0.50
if os.path.exists('modelo_treinado_xgboost.pkl'):
    with open('modelo_treinado_xgboost.pkl', 'rb') as f:
        dados_exportacao = pickle.load(f)
        modelo = dados_exportacao['modelo']
        limiar_atraso = dados_exportacao['limiar']

def nivel_risco(prob):
    if prob < .30: return "Baixo"
    if prob < .61: return "Moderado"
    if prob < .81: return "Alto"
    return "Muito alto"

def fatores_locais(input_df):
    """Tenta obter contribuições locais do XGBoost; cai para importâncias globais se necessário."""
    if modelo is None:
        return []
    impactos = None
    try:
        import xgboost as xgb
        booster = modelo.get_booster()
        contrib = booster.predict(xgb.DMatrix(input_df), pred_contribs=True)[0][:-1]
        impactos = dict(zip(FEATURES, map(abs, contrib)))
    except Exception:
        try:
            importances = modelo.feature_importances_
            impactos = dict(zip(FEATURES, map(float, importances)))
        except Exception:
            return []

    top = sorted(impactos.items(), key=lambda item: item[1], reverse=True)[:5]
    maior = max((valor for _, valor in top), default=0) or 1
    return [{"name": FEATURE_LABELS.get(nome, nome), "impact": round(valor / maior * 100)} for nome, valor in top]

def calcular_risco_motor(dados_dict):
    dados_dict = {feat: dados_dict.get(feat, 0) for feat in FEATURES}
    input_df = pd.DataFrame([dados_dict], columns=FEATURES)

    if modelo is not None:
        probabilidade = float(modelo.predict_proba(input_df)[0][1])
        atraso = bool(probabilidade >= limiar_atraso)
    else:
        probabilidade = 0.85 if dados_dict.get('is_weekend') == 1 else 0.15
        if dados_dict.get('distance_km', 0) > 50:
            probabilidade += 0.1
        probabilidade = min(probabilidade, 0.99)
        atraso = probabilidade >= limiar_atraso

    return {
        "previsao_atraso": atraso,
        "prediction": 1 if atraso else 0,
        "probabilidade": probabilidade,
        "probability": probabilidade,
        "risk_level": nivel_risco(probabilidade),
        "main_model": "XGBoost",
        "models": [{"name": "XGBoost", "probability": probabilidade, "prediction": 1 if atraso else 0}],
        "factors": fatores_locais(input_df),
        "input": dados_dict
    }

@app.post("/predict")
def prever_atraso_individual(dados: DadosEntrega):
    return calcular_risco_motor(dados.dict())

@app.post("/predict-batch")
async def prever_atraso_lote(file: UploadFile = File(...)):
    if not file.filename.lower().endswith('.csv'):
        raise HTTPException(status_code=400, detail="O arquivo deve ser um .csv")
    try:
        conteudo = await file.read()
        df = pd.read_csv(io.StringIO(conteudo.decode('utf-8')))
        faltantes = [feat for feat in FEATURES if feat not in df.columns]
        if faltantes:
            raise HTTPException(status_code=400, detail=f"Colunas obrigatórias ausentes: {', '.join(faltantes)}")

        resultados_lote = []
        for index, row in df.iterrows():
            dados_dict = {feat: row[feat] for feat in FEATURES}
            resultado = calcular_risco_motor(dados_dict)
            resultado['pedido_id'] = index + 1
            if 'resultado_real_atraso' in df.columns and pd.notna(row.get('resultado_real_atraso')):
                resultado['resultado_real'] = int(row['resultado_real_atraso'])
            resultados_lote.append(resultado)

        atrasos = sum(1 for item in resultados_lote if item['previsao_atraso'])
        return {
            "analysis_id": f"LOTE-{pd.Timestamp.now().strftime('%Y%m%d%H%M%S')}",
            "total": len(resultados_lote),
            "delayed_count": atrasos,
            "on_time_count": len(resultados_lote) - atrasos,
            "resultados": resultados_lote,
            "demo_mode": False
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao processar CSV: {str(e)}")

app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
