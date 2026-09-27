from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import pandas as pd
import pickle
import io
import json
import os
from urllib.request import Request, urlopen
from datetime import date, datetime, timedelta
from typing import Optional

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
    # Campos do formulário individual e do CSV
    purchase_date: Optional[str] = None
    purchase_time: Optional[str] = None
    price: float
    height_cm: Optional[float] = None
    width_cm: Optional[float] = None
    length_cm: Optional[float] = None

    # Também aceita o formato já pré-processado, caso o form.js envie assim.
    holiday_at_purchase: Optional[int] = None
    is_holiday_in_7_days: Optional[int] = None
    is_holiday_in_14_days: Optional[int] = None
    had_holiday_7_days_ago: Optional[int] = None
    purchase_hour: Optional[int] = None
    purchase_day_of_week: Optional[int] = None
    is_weekend: Optional[int] = None
    freight_value: Optional[float] = None
    product_weight_g: Optional[float] = None
    volume_cm3: Optional[float] = None
    distance_km: Optional[float] = None
    same_city: Optional[int] = None
    prazo_transportadora_dias: Optional[int] = None

modelo = None
limiar_atraso = 0.50
CAMINHO_MODELO = os.path.join(os.path.dirname(__file__), 'modelo_treinado_xgboost.pkl')
if os.path.exists(CAMINHO_MODELO):
    with open(CAMINHO_MODELO, 'rb') as f:
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
    if modelo is None:
        raise HTTPException(
            status_code=503,
            detail="Modelo de previsão não encontrado. Verifique o arquivo modelo_treinado_xgboost.pkl.",
        )

    dados_dict = {feat: dados_dict.get(feat, 0) for feat in FEATURES}
    input_df = pd.DataFrame([dados_dict], columns=FEATURES)

    probabilidade = float(modelo.predict_proba(input_df)[0][1])
    atraso = bool(probabilidade >= limiar_atraso)

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


def gerar_resultado_pedido(dados_dict, pedido_id=None, resultado_real=None):
    """Gera a mesma estrutura de previsão para um pedido individual ou do lote."""
    resultado = calcular_risco_motor(dados_dict)
    resultado["features"] = resultado["input"].copy()

    if pedido_id is not None:
        resultado["pedido_id"] = pedido_id
    if resultado_real is not None:
        resultado["resultado_real"] = resultado_real

    return resultado

def _pascoa(ano: int) -> date:
    """Calcula a data da Páscoa pelo algoritmo de Meeus/Jones/Butcher."""
    a = ano % 19
    b, c = divmod(ano, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mes = (h + l - 7 * m + 114) // 31
    dia = ((h + l - 7 * m + 114) % 31) + 1
    return date(ano, mes, dia)


FERIADOS_NAGER_URL = "https://date.nager.at/api/v3/publicholidays/{ano}/BR"
_feriados_cache = {}


def _feriados_fallback(ano: int):
    """Fallback local para manter a análise disponível sem conexão externa."""
    pascoa = _pascoa(ano)
    return {
        date(ano, 1, 1),
        pascoa - timedelta(days=48),  # segunda de carnaval
        pascoa - timedelta(days=47),  # terça de carnaval
        pascoa - timedelta(days=2),   # sexta-feira santa
        date(ano, 4, 21),
        date(ano, 5, 1),
        pascoa + timedelta(days=60),  # corpus christi
        date(ano, 7, 9),              # revolução constitucionalista - SP
        date(ano, 9, 7),
        date(ano, 10, 12),
        date(ano, 11, 2),
        date(ano, 11, 15),
        date(ano, 11, 20),
        date(ano, 12, 25),
    }


def _feriados(ano: int):
    """Busca feriados na Nager.Date e mantém o resultado em cache por ano."""
    if ano in _feriados_cache:
        return _feriados_cache[ano]

    try:
        request = Request(
            FERIADOS_NAGER_URL.format(ano=ano),
            headers={"User-Agent": "PredictDelivery-TCC/1.0"},
        )
        with urlopen(request, timeout=3) as response:
            feriados = json.load(response)

        datas = {
            date.fromisoformat(item["date"])
            for item in feriados
            if item.get("global") or "BR-SP" in (item.get("counties") or [])
        }
        if not datas:
            raise ValueError("A Nager.Date não retornou feriados compatíveis")
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        datas = _feriados_fallback(ano)

    _feriados_cache[ano] = datas
    return datas


def _tem_feriado(data_compra: date, inicio: int, fim: int) -> int:
    for deslocamento in range(inicio, fim + 1):
        d = data_compra + timedelta(days=deslocamento)
        if d in _feriados(d.year):
            return 1
    return 0


def preparar_dados_individual(dados: DadosEntrega):
    """Converte os campos amigáveis do index.html nas FEATURES usadas pelo XGBoost."""
    bruto = dados.model_dump() if hasattr(dados, "model_dump") else dados.dict()

    # Se o frontend já enviou a feature, preserva-a; caso contrário, deriva do formulário.
    data_compra = None
    if bruto.get("purchase_date"):
        try:
            data_compra = datetime.strptime(bruto["purchase_date"], "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="purchase_date deve estar no formato YYYY-MM-DD")

    hora = bruto.get("purchase_hour")
    if hora is None and bruto.get("purchase_time"):
        try:
            hora = int(bruto["purchase_time"].split(":")[0])
        except (ValueError, IndexError):
            raise HTTPException(status_code=400, detail="purchase_time deve estar no formato HH:MM")

    peso = bruto.get("product_weight_g")

    volume = bruto.get("volume_cm3")
    if volume is None:
        dimensoes = [bruto.get("height_cm"), bruto.get("width_cm"), bruto.get("length_cm")]
        if all(v is not None for v in dimensoes):
            volume = float(dimensoes[0]) * float(dimensoes[1]) * float(dimensoes[2])

    distancia = bruto.get("distance_km")

    mesma_cidade = bruto.get("same_city")

    frete = bruto.get("freight_value")

    prazo = bruto.get("prazo_transportadora_dias")
    # O index atual não possui esse campo. Mantemos 0 para não quebrar a chamada;
    # idealmente, adicione o prazo ao formulário se ele foi usado no treinamento.
    if prazo is None:
        prazo = 0

    processado = {
        "holiday_at_purchase": bruto.get("holiday_at_purchase"),
        "is_holiday_in_7_days": bruto.get("is_holiday_in_7_days"),
        "is_holiday_in_14_days": bruto.get("is_holiday_in_14_days"),
        "had_holiday_7_days_ago": bruto.get("had_holiday_7_days_ago"),
        "purchase_hour": hora,
        "purchase_day_of_week": bruto.get("purchase_day_of_week"),
        "is_weekend": bruto.get("is_weekend"),
        "price": bruto.get("price"),
        "freight_value": frete,
        "product_weight_g": peso,
        "volume_cm3": volume,
        "distance_km": distancia,
        "same_city": mesma_cidade,
        "prazo_transportadora_dias": prazo,
    }

    if data_compra:
        processado["holiday_at_purchase"] = processado["holiday_at_purchase"] if processado["holiday_at_purchase"] is not None else int(data_compra in _feriados(data_compra.year))
        processado["is_holiday_in_7_days"] = processado["is_holiday_in_7_days"] if processado["is_holiday_in_7_days"] is not None else _tem_feriado(data_compra, 1, 7)
        processado["is_holiday_in_14_days"] = processado["is_holiday_in_14_days"] if processado["is_holiday_in_14_days"] is not None else _tem_feriado(data_compra, 1, 14)
        processado["had_holiday_7_days_ago"] = processado["had_holiday_7_days_ago"] if processado["had_holiday_7_days_ago"] is not None else _tem_feriado(data_compra, -7, -1)
        processado["purchase_day_of_week"] = processado["purchase_day_of_week"] if processado["purchase_day_of_week"] is not None else data_compra.weekday()
        processado["is_weekend"] = processado["is_weekend"] if processado["is_weekend"] is not None else int(data_compra.weekday() >= 5)

    faltantes = [f for f in FEATURES if processado.get(f) is None]
    if faltantes:
        raise HTTPException(status_code=400, detail=f"Não foi possível calcular/preencher: {', '.join(faltantes)}")

    return processado


@app.post("/predict")
def prever_atraso_individual(dados: DadosEntrega):
    try:
        dados_processados = preparar_dados_individual(dados)
        resultado = gerar_resultado_pedido(dados_processados)

        # Campos esperados por resultado.js.
        resultado["analysis_id"] = f"IND-{pd.Timestamp.now().strftime('%Y%m%d%H%M%S')}"
        resultado["demo_mode"] = False
        resultado["input"] = {
            "purchase_date": dados.purchase_date,
            "purchase_time": dados.purchase_time,
            "price": dados.price,
            "freight_value": dados_processados["freight_value"],
            "product_weight_g": dados_processados["product_weight_g"],
            "distance_km": dados_processados["distance_km"],
            "same_city": dados_processados["same_city"],
        }
        return resultado
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao processar pedido: {str(e)}")

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
            resultado_real = None
            if 'resultado_real_atraso' in df.columns and pd.notna(row.get('resultado_real_atraso')):
                resultado_real = int(row['resultado_real_atraso'])
            resultado = gerar_resultado_pedido(
                dados_dict,
                pedido_id=index + 1,
                resultado_real=resultado_real,
            )
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
