const batchResult = JSON.parse(sessionStorage.getItem("batchPredictionResult") || "null");
if (!batchResult) window.location.href = "index.html";

// 1. Adicionado o suporte para ler a chave "resultados" da API
const results = batchResult?.resultados || batchResult?.results || batchResult?.items || batchResult?.predictions || [];

// 2. Ajustado para ler "item.previsao_atraso === true"
const delayed = batchResult?.delayed_count ?? results.filter(item => item.previsao_atraso === true || item.prediction === 1).length;
const total = batchResult?.total ?? results.length;
const onTime = batchResult?.on_time_count ?? total - delayed;

document.getElementById("batchAnalysisId").textContent = batchResult?.analysis_id || "—";
document.getElementById("batchModeTag").textContent = batchResult?.demo_mode ? "Modo teste" : "API";
document.getElementById("batchDescription").textContent = `${total} pedidos foram analisados${batchResult?.demo_mode ? " localmente" : ""}.`;

const summary = [["Pedidos analisados", total], ["Com risco de atraso", delayed], ["Dentro do prazo", onTime]];
document.getElementById("batchSummary").innerHTML = summary.map(([label, value]) => `<div class="batch-stat"><span>${label}</span><strong>${value}</strong></div>`).join("");

document.getElementById("batchResults").innerHTML = results.map((result, index) => {
    const input = result.input || result;
    
    // 3. Lê corretamente as variáveis do Python
    const delayedOrder = result.previsao_atraso === true || result.prediction === 1;
    const probabilidade = result.probabilidade !== undefined ? result.probabilidade : (result.probability || 0);
    
    // 4. Calcula o nível de risco automaticamente se a API não o enviar
    let riskLevel = result.risk_level || "—";
    if (!result.risk_level) {
        if (probabilidade < 0.3) riskLevel = "Baixo";
        else if (probabilidade < 0.6) riskLevel = "Moderado";
        else if (probabilidade < 0.8) riskLevel = "Alto";
        else riskLevel = "Muito alto";
    }

    return `<tr>
        <td>#${index + 1}</td>
        <td>${riskLevel}</td>
        <td>${Math.round(probabilidade * 100)}%</td>
        <td>${Number(input.distance_km || 0).toLocaleString("pt-BR")} km</td>
        <td>R$ ${Number(input.freight_value || 0).toLocaleString("pt-BR", { minimumFractionDigits: 2 })}</td>
        <td><span class="batch-result-tag ${delayedOrder ? "delay" : "ontime"}">${delayedOrder ? "RISCO DE ATRASO" : "DENTRO DO PRAZO"}</span></td>
    </tr>`;
}).join("");