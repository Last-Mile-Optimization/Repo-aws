from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware # 1. IMPORTAR O CORS
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import pandas as pd
import pickle
import io
import os

app = FastAPI(title="API Previsão de Atrasos - TCC")

# ADICIONAR O MIDDLEWARE DE CORS (Permite requisições do front local)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Permite acesso de qualquer origem
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# CRIAR A ROTA DE HEALTH CHECK ESPERADA PELO FRONTEND
@app.get("/health")
def health_check():
    return {"status": "ok", "message": "API Online"}

# 1. Estrutura com as 14 variáveis exatas do modelo
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

# 2. Carregamento do dicionário (Modelo + Limiar Otimizado)
modelo = None
limiar_atraso = 0.50 # Fallback de segurança

if os.path.exists('modelo_treinado_xgboost.pkl'):
    with open('modelo_treinado_xgboost.pkl', 'rb') as f:
        dados_exportacao = pickle.load(f)
        modelo = dados_exportacao['modelo']
        limiar_atraso = dados_exportacao['limiar']

# ==========================================
# MOTOR CENTRAL DE PREDIÇÃO
# ==========================================
def calcular_risco_motor(dados_dict):
    """
    Função central que roda o modelo XGBoost.
    Recebe um dicionário com os dados de um pedido.
    """
    if modelo is not None:
        # Transforma o dicionário em um DataFrame de 1 linha.
        # Isso garante que o XGBoost receba os nomes das colunas na ordem correta.
        input_df = pd.DataFrame([dados_dict])
        
        # Pega a probabilidade da classe 1 (Atraso)
        probabilidade = float(modelo.predict_proba(input_df)[0][1])
        
        # Aplica o limiar otimizado do Optuna (ex: 0.17)
        atraso = bool(probabilidade >= limiar_atraso)
    else:
        # SIMULAÇÃO (Caso o arquivo .pkl não seja encontrado)
        probabilidade = 0.85 if dados_dict.get('is_weekend') == 1 else 0.15
        if dados_dict.get('distance_km', 0) > 50:
            probabilidade += 0.1
            
        probabilidade = min(probabilidade, 0.99)
        atraso = probabilidade >= limiar_atraso

    return {
        "previsao_atraso": atraso,
        "probabilidade": probabilidade
    }

# ==========================================
# ENDPOINT 1: PREDIÇÃO INDIVIDUAL (JSON)
# ==========================================
@app.post("/predict")
def prever_atraso_individual(dados: DadosEntrega):
    # dados.dict() converte o objeto Pydantic em um dicionário do Python
    return calcular_risco_motor(dados.dict())


# ==========================================
# ENDPOINT 2: PREDIÇÃO EM LOTE (CSV)
# ==========================================
@app.post("/predict-batch")
async def prever_atraso_lote(file: UploadFile = File(...)):
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="O arquivo deve ser um .csv")

    try:
        # Lê o CSV enviado pelo usuário na tela
        conteudo = await file.read()
        df = pd.read_csv(io.StringIO(conteudo.decode('utf-8')))
        
        resultados_lote = []
        
        # Colunas obrigatórias que o modelo precisa
        features_necessarias = [
            'holiday_at_purchase', 'is_holiday_in_7_days', 'is_holiday_in_14_days',
            'had_holiday_7_days_ago', 'purchase_hour', 'purchase_day_of_week',
            'is_weekend', 'price', 'freight_value', 'product_weight_g',
            'volume_cm3', 'distance_km', 'same_city', 'prazo_transportadora_dias'
        ]
        
        # Itera linha a linha no CSV
        for index, row in df.iterrows():
            # Extrai apenas as variáveis que o modelo conhece e converte para dicionário
            dados_dict = {feat: row.get(feat, 0) for feat in features_necessarias}
            
            # Chama o motor
            resultado = calcular_risco_motor(dados_dict)
            
            # Insere dados de apoio para exibir na tabela do frontend
            resultado['pedido_id'] = index + 1
            resultado['distance_km'] = dados_dict['distance_km']
            resultado['freight_value'] = dados_dict['freight_value']
            
            # Mantém a variável de resultado_real_atraso (se existir no CSV) para você validar
            if 'resultado_real_atraso' in row:
                resultado['resultado_real'] = int(row['resultado_real_atraso'])
                
            resultados_lote.append(resultado)
            
        return {"resultados": resultados_lote}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao processar CSV: {str(e)}")

# 4. Serve a pasta do frontend
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")