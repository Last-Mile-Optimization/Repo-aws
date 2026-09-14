from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import pickle
import os

app = FastAPI(title="API Previsão de Atrasos - TCC")

# 1. Estrutura de dados esperada pelo frontend (features do seu modelo)
class DadosEntrega(BaseModel):
    distancia_km: float
    tempo_estimado_min: float
    clima_severo: int  # 0 para clima limpo, 1 para chuva/condição adversa

# 2. Tenta carregar o modelo real. Se não achar o arquivo, segue sem ele.
modelo = None
if os.path.exists('modelo_treinado.pkl'):
    with open('modelo_treinado.pkl', 'rb') as f:
        modelo = pickle.load(f)

# 3. Rota para fazer a previsão
@app.post("/predict")
def prever_atraso(dados: DadosEntrega):
    if modelo is not None:
        # Aqui entra a chamada real para o seu modelo quando ele existir
        # input_features = [[dados.distancia_km, dados.tempo_estimado_min, dados.clima_severo]]
        # previsao = modelo.predict(input_features)[0]
        # prob = modelo.predict_proba(input_features)[0][1]
        pass
    else:
        # SIMULAÇÃO: Lógica simples para testar o frontend agora mesmo
        probabilidade = 0.85 if dados.clima_severo == 1 else 0.15
        if dados.distancia_km > 50:
            probabilidade += 0.1
        
        atraso = probabilidade >= 0.5
        
        return {
            "previsao_atraso": atraso,
            "probabilidade": min(probabilidade, 0.99) # Trava em 99% max
        }

# 4. Serve a pasta do frontend. IMPORTANTE: Deve ser a última linha!
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")