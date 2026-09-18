const batchResult = JSON.parse(sessionStorage.getItem("batchPredictionResult") || "null");
if (!batchResult) window.location.href = "index.html";

const results = batchResult?.results || batchResult?.items || batchResult?.predictions || [];
const delayed = batchResult?.delayed_count ?? results.filter(item => item.prediction === 1).length;
const total = batchResult?.total ?? results.length;
const onTime = batchResult?.on_time_count ?? total - delayed;

document.getElementById("batchAnalysisId").textContent = batchResult?.analysis_id || "—";
document.getElementById("batchModeTag").textContent = batchResult?.demo_mode ? "Modo teste" : "API";
document.getElementById("batchDescription").textContent = `${total} pedidos foram analisados${batchResult?.demo_mode ? " localmente" : ""}.`;

const summary = [["Pedidos analisados", total], ["Com risco de atraso", delayed], ["Dentro do prazo", onTime]];
document.getElementById("batchSummary").innerHTML = summary.map(([label, value]) => `<div class="batch-stat"><span>${label}</span><strong>${value}</strong></div>`).join("");

document.getElementById("batchResults").innerHTML = results.map((result, index) => {
    const input = result.input || result;
    const delayedOrder = result.prediction === 1;
    return `<tr><td>#${index + 1}</td><td>${result.risk_level || "—"}</td><td>${Math.round((result.probability || 0) * 100)}%</td><td>${Number(input.distance_km || 0).toLocaleString("pt-BR")} km</td><td>R$ ${Number(input.freight_value || 0).toLocaleString("pt-BR", { minimumFractionDigits: 2 })}</td><td><span class="batch-result-tag ${delayedOrder ? "delay" : "ontime"}">${delayedOrder ? "RISCO DE ATRASO" : "DENTRO DO PRAZO"}</span></td></tr>`;
}).join("");
