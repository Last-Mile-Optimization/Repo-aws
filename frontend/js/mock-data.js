function buildMockPrediction(payload, index = 0) {
    const volume = payload.height_cm * payload.width_cm * payload.length_cm;
    const date = new Date(`${payload.purchase_date}T${payload.purchase_time}:00`);
    const hour = date.getHours();
    const weekend = [0, 6].includes(date.getDay()) ? 1 : 0;

    let probability = 0.16;
    probability += Math.min(payload.distance_km / 1500, 1) * 0.28;
    probability += Math.min(payload.freight_value / Math.max(payload.price, 1), .5) * .18;
    probability += Math.min(payload.product_weight_g / 12000, 1) * .10;
    probability += Math.min(volume / 120000, 1) * .08;
    probability += weekend * .08;
    probability += payload.same_city ? -.06 : .08;
    probability += hour >= 18 ? .03 : 0;
    probability = Math.max(.05, Math.min(.96, probability));

    const riskLevel = probability < .30 ? "Baixo" : probability < .61 ? "Moderado" : probability < .81 ? "Alto" : "Muito alto";
    const modelProbability = delta => Math.max(.03, Math.min(.97, probability + delta));

    return {
        analysis_id: `TESTE-${String(index + 1).padStart(3, "0")}`,
        prediction: probability >= .5 ? 1 : 0,
        probability,
        main_model: "Mock Deep Learning",
        risk_level: riskLevel,
        models: [
            ["Deep Learning", 0], ["Random Forest", .05], ["XGBoost", .08],
            ["Árvore de Decisão", -.04], ["KNN", -.12]
        ].map(([name, delta]) => ({ name, probability: modelProbability(delta), prediction: modelProbability(delta) >= .5 ? 1 : 0 })),
        factors: [
            ["Distância da entrega", Math.min(100, Math.round(payload.distance_km / 9))],
            ["Valor do frete", Math.min(100, Math.round((payload.freight_value / Math.max(payload.price, 1)) * 170))],
            ["Peso do produto", Math.min(100, Math.round(payload.product_weight_g / 50))],
            ["Volume do produto", Math.min(100, Math.round(volume / 700))],
            ["Fim de semana", weekend ? 62 : 18]
        ].sort((a, b) => b[1] - a[1]).map(([name, impact]) => ({ name, impact })),
        cluster: payload.distance_km > 500
            ? { name: "Pedidos de longa distância", description: "Entregas com maior deslocamento entre vendedor e cliente.", stats: [["Distância média", "684 km"], ["Frete médio", "R$ 52,40"], ["Atrasos no grupo", "37%"]] }
            : { name: "Pedidos urbanos e leves", description: "Entregas de menor porte e menor deslocamento.", stats: [["Distância média", "96 km"], ["Frete médio", "R$ 24,10"], ["Atrasos no grupo", "14%"]] },
        dbscan: { is_outlier: payload.distance_km > 1200 || payload.product_weight_g > 12000, text: "Resultado gerado localmente no modo teste." },
        features: { purchase_hour: hour, purchase_day_of_week: date.getDay(), is_weekend: weekend, volume_cm3: volume },
        input: payload,
        demo_mode: true
    };
}

function parseCsv(text) {
    const rows = [];
    let row = [], value = "", quoted = false;
    for (let i = 0; i < text.length; i += 1) {
        const char = text[i];
        if (char === '"' && text[i + 1] === '"') { value += char; i += 1; }
        else if (char === '"') quoted = !quoted;
        else if (char === ',' && !quoted) { row.push(value.trim()); value = ""; }
        else if ((char === '\n' || char === '\r') && !quoted) {
            if (char === '\r' && text[i + 1] === '\n') i += 1;
            row.push(value.trim());
            if (row.some(cell => cell)) rows.push(row);
            row = []; value = "";
        } else value += char;
    }
    row.push(value.trim());
    if (row.some(cell => cell)) rows.push(row);
    return rows;
}

function mockBatchFromCsv(text) {
    const [headers, ...rows] = parseCsv(text);
    const required = ["purchase_date", "purchase_time", "price", "freight_value", "product_weight_g", "height_cm", "width_cm", "length_cm", "distance_km", "same_city"];
    const missing = required.filter(header => !headers?.includes(header));
    if (missing.length) throw new Error(`O CSV não possui as colunas: ${missing.join(", ")}.`);
    if (!rows.length) throw new Error("O CSV não possui pedidos para analisar.");

    const results = rows.map((row, index) => {
        const raw = Object.fromEntries(headers.map((header, column) => [header, row[column] || ""]));
        const payload = {
            purchase_date: raw.purchase_date, purchase_time: raw.purchase_time,
            price: Number(raw.price), freight_value: Number(raw.freight_value),
            product_weight_g: Number(raw.product_weight_g), height_cm: Number(raw.height_cm),
            width_cm: Number(raw.width_cm), length_cm: Number(raw.length_cm),
            distance_km: Number(raw.distance_km), same_city: Number(raw.same_city)
        };
        if (Object.values(payload).some(value => value === "" || Number.isNaN(value))) throw new Error(`Há dados inválidos no pedido ${index + 1}.`);
        return buildMockPrediction(payload, index);
    });
    const delayedCount = results.filter(result => result.prediction === 1).length;
    return { analysis_id: `LOTE-TESTE-${Date.now().toString().slice(-6)}`, total: results.length, delayed_count: delayedCount, on_time_count: results.length - delayedCount, results, demo_mode: true };
}

window.MockPredictions = { single: buildMockPrediction, batchFromCsv: mockBatchFromCsv };
