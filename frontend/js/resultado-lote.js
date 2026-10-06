/* =========================================================
   RECUPERA RESULTADO DO LOTE
   ========================================================= */

const batchResult = JSON.parse(
    sessionStorage.getItem(
        "batchPredictionResult"
    ) || "null"
);


if (!batchResult) {

    window.location.href =
        "index.html";

}


/* =========================================================
   NORMALIZA RESULTADOS

   Compatível tanto com:
   - API Python
   - modo teste
   ========================================================= */

const results =

    batchResult?.resultados ||

    batchResult?.results ||

    batchResult?.items ||

    batchResult?.predictions ||

    [];


/* =========================================================
   FUNÇÕES AUXILIARES
   ========================================================= */

function isDelayed(result) {

    return (

        result.previsao_atraso === true ||

        result.prediction === 1 ||

        result.prediction === true

    );

}


function getProbability(result) {

    return Number(

        result.probabilidade ??

        result.probability ??

        0

    );

}


function percentage(value) {

    return Math.round(
        Number(value || 0) * 100
    );

}


function getRiskLevel(
    probability,
    suppliedLevel
) {

    if (suppliedLevel) {

        return suppliedLevel;

    }


    if (probability < 0.30) {

        return "Baixo";

    }


    if (probability < 0.61) {

        return "Moderado";

    }


    if (probability < 0.81) {

        return "Alto";

    }


    return "Muito alto";

}


function escapeHtml(value) {

    return String(value ?? "")
        .replace(

            /[&<>'"]/g,

            char => ({

                "&": "&amp;",

                "<": "&lt;",

                ">": "&gt;",

                "'": "&#39;",

                '"': "&quot;"

            })[char]

        );

}


/* =========================================================
   RECOMENDAÇÃO
   MESMA LÓGICA DO RESULTADO INDIVIDUAL
   ========================================================= */

function getRecommendation(
    probability
) {

    const probabilityPct =
        percentage(probability);


    if (probabilityPct >= 81) {

        return {

            title:
                "Prioridade alta de acompanhamento",

            text:
                "O pedido apresenta risco muito elevado. " +
                "Vale sinalizar a entrega para acompanhamento " +
                "e revisar o prazo prometido ao cliente."

        };

    }


    if (probabilityPct >= 61) {

        return {

            title:
                "Atenção recomendada",

            text:
                "O risco está acima do ideal. " +
                "Acompanhe a entrega e considere medidas " +
                "preventivas para evitar impacto na experiência do cliente."

        };

    }


    if (probabilityPct >= 31) {

        return {

            title:
                "Monitoramento preventivo",

            text:
                "O pedido apresenta risco moderado. " +
                "Não exige ação imediata, mas vale acompanhar " +
                "a evolução da entrega."

        };

    }


    return {

        title:
            "Baixo risco identificado",

        text:
            "As características do pedido são semelhantes " +
            "às de entregas que normalmente chegam dentro do prazo."

    };

}


/* =========================================================
   FATORES
   ========================================================= */

function getFactorModels(result, availableModels) {

    const received =
        Array.isArray(result.factors_by_model)
            ? result.factors_by_model
            : [];

    const byName = new Map(
        received.map(group => [
            String(group.name || "").toLowerCase(),
            group
        ])
    );

    const legacyFactors =
        Array.isArray(result.factors)
            ? result.factors
            : [];

    return [...availableModels]
        .sort((first, second) => modelRank(first) - modelRank(second))
        .map(model => {

            const group = byName.get(
                String(model.name || "").toLowerCase()
            );

            if (group) return group;

            const isXgboost = /xgboost/i.test(model.name || "");

            return {
                name: model.name,
                method: isXgboost
                    ? "Fatores ainda não disponibilizados para este pedido."
                    : "Sensibilidade do MLP ainda não disponibilizada para este pedido.",
                factors: isXgboost ? legacyFactors : []
            };

        });

}


function renderFactorRows(factors) {

    if (!Array.isArray(factors) || !factors.length) {

        return `
            <p class="panel-description">
                Nenhum fator pôde ser calculado para este modelo.
            </p>
        `;

    }

    return factors.map(factor => {

        const impact = Math.max(
            0,
            Math.min(100, Number(factor.impact || 0))
        );

        const increasesRisk =
            factor.direction === "Aumenta o risco";

        return `
            <div class="bar-row">
                <div class="factor-label">
                    <strong>${escapeHtml(factor.name)}</strong>
                    <small class="factor-effect ${
                        increasesRisk ? "increase" : "decrease"
                    }">${escapeHtml(factor.direction || "Impacto relativo")}</small>
                </div>
                <div class="bar-track">
                    <div class="bar-value" style="width: ${impact}%"></div>
                </div>
                <span class="bar-percent">${Math.round(impact)}%</span>
            </div>
        `;

    }).join("");

}


function renderFactorModels(factorModels) {

    return factorModels.map(model => {

        const isXgboost = /xgboost/i.test(model.name || "");

        return `
            <article class="model-factors-card ${
                isXgboost ? "xgboost" : "mlp"
            }">
                <div class="model-factors-heading">
                    <span>Fatores do modelo</span>
                    <h3>${escapeHtml(model.name)}</h3>
                </div>
                <p class="model-factors-method">
                    ${escapeHtml(model.method || "Impacto relativo das variáveis.")}
                </p>
                <div class="bar-chart">
                    ${renderFactorRows(model.factors)}
                </div>
            </article>
        `;

    }).join("");

}


/* =========================================================
   MODELOS
   ========================================================= */

function getModels(
    result,
    probability,
    delayed
) {

    /*
        Quando houver Random Forest,
        Árvore de Decisão etc., basta o backend
        retornar result.models.
    */

    if (
        Array.isArray(result.models) &&
        result.models.length
    ) {

        return sortModels(result.models);

    }


    return sortModels([

        {

            name:
                result.main_model ||
                "XGBoost",

            probability:
                probability,

            prediction:
                delayed ? 1 : 0

        }

    ]);

}


function isModelDelayed(model) {

    if (model?.prediction === 1 || model?.prediction === true) {
        return true;
    }

    if (model?.prediction === 0 || model?.prediction === false) {
        return false;
    }

    const threshold = /xgboost/i.test(model?.name || "") ? .20 : .30;
    return Number(model?.probability || 0) >= threshold;

}


function modelRank(model) {

    const name = String(model?.name || "").toLowerCase();

    if (name.includes("xgboost")) {
        return 0;
    }

    if (name.includes("mlp")) {
        return 1;
    }

    return 2;

}


function sortModels(models) {

    return [...models].sort(
        (first, second) => modelRank(first) - modelRank(second)
    );

}


function buildModelStatistics(rows) {

    const statistics = new Map();

    rows.forEach(result => {

        const models = getModels(
            result,
            getProbability(result),
            isDelayed(result)
        );

        models.forEach(model => {

            const name = String(model?.name || "Modelo");
            const probability = Math.max(
                0,
                Math.min(1, Number(model?.probability || 0))
            );

            if (!statistics.has(name)) {
                statistics.set(name, {
                    name,
                    total: 0,
                    delayedCount: 0,
                    probabilitySum: 0
                });
            }

            const item = statistics.get(name);
            item.total += 1;
            item.delayedCount += isModelDelayed(model) ? 1 : 0;
            item.probabilitySum += probability;

        });

    });

    return sortModels([...statistics.values()]);

}


function renderModelProbabilityChips(models) {

    return models
        .map(model => `
            <span class="order-model-probability">
                <strong>${escapeHtml(model.name)}</strong>
                ${percentage(model.probability)}%
            </span>
        `)
        .join("");

}


function renderModelProbabilityList(models) {

    return models
        .map(model => `
            <div class="model-probability-item">
                <span>${escapeHtml(model.name)}</span>
                <strong>${percentage(model.probability)}%</strong>
            </div>
        `)
        .join("");

}


/* =========================================================
   ESTATÍSTICAS DO LOTE
   ========================================================= */

const total =

    batchResult?.total ??

    results.length;


const delayedCount =

    batchResult?.delayed_count ??

    results
        .filter(isDelayed)
        .length;


const onTimeCount =

    batchResult?.on_time_count ??

    total - delayedCount;


const modelStatistics =
    buildModelStatistics(results);


/* =========================================================
   CABEÇALHO
   ========================================================= */

document
    .getElementById(
        "batchAnalysisId"
    )
    .textContent =

        batchResult?.analysis_id ||

        "—";


document
    .getElementById(
        "batchModeTag"
    )
    .textContent =

        batchResult?.demo_mode

            ? "Modo teste"

            : "API";


document
    .getElementById(
        "batchDescription"
    )
    .textContent =

        `${total} pedidos foram analisados. ` +

        `As probabilidades de cada modelo estão disponíveis no resumo e em cada pedido.`;


/* =========================================================
   KPIs GERAIS
   ========================================================= */

const modelSummaryBlocks =
    modelStatistics
        .map(item => {

            const onTime = item.total - item.delayedCount;
            const averageProbability = percentage(
                item.probabilitySum / Math.max(item.total, 1)
            );
            const modelClass = /xgboost/i.test(item.name) ? "xgboost" : "mlp";

            return `
                <section class="model-summary-block ${modelClass}">
                    <div class="model-summary-heading">
                        <span>Resultado do modelo</span>
                        <h3>${escapeHtml(item.name)}</h3>
                    </div>
                    <div class="model-summary-metrics">
                        <article class="model-summary-metric">
                            <span>Pedidos analisados</span>
                            <strong>${item.total}</strong>
                        </article>
                        <article class="model-summary-metric delay">
                            <span>Com risco de atraso</span>
                            <strong>${item.delayedCount}</strong>
                        </article>
                        <article class="model-summary-metric ontime">
                            <span>Dentro do prazo</span>
                            <strong>${onTime}</strong>
                        </article>
                        <article class="model-summary-metric">
                            <span>Risco médio</span>
                            <strong>${averageProbability}%</strong>
                        </article>
                    </div>
                </section>
            `;

        })
        .join("");


document
    .getElementById(
        "batchSummary"
    )
    .innerHTML = modelSummaryBlocks;


/* =========================================================
   CRIA UM ACCORDION PARA CADA PEDIDO
   ========================================================= */

const batchResultsContainer =
    document.getElementById(
        "batchResults"
    );


batchResultsContainer.innerHTML =

    results

        .map(

            (result, index) => {


                /* =========================================
                   DADOS PRINCIPAIS
                   ========================================= */

                const delayed =
                    isDelayed(result);


                const probability =
                    getProbability(result);


                const probabilityPct =
                    percentage(probability);


                const riskLevel =
                    getRiskLevel(

                        probability,

                        result.risk_level

                    );


                const recommendation =
                    getRecommendation(
                        probability
                    );


                const models =
                    getModels(

                        result,

                        probability,

                        delayed

                    );


                const factorModels =
                    getFactorModels(
                        result,
                        models
                    );


                const modelProbabilityChips =
                    renderModelProbabilityChips(models);


                const modelProbabilityList =
                    renderModelProbabilityList(models);


                const pedidoId =

                    result.pedido_id ??

                    index + 1;


                /* =========================================
                   FATORES
                   ========================================= */

                const factorsHtml =
                    renderFactorModels(factorModels);


                /* =========================================
                   COMPARAÇÃO DE MODELOS
                   ========================================= */

                const modelsHtml =

                    models

                        .map(

                            model => {


                                const modelProbability =

                                    percentage(
                                        model.probability
                                    );


                                const modelDelayed =

                                    model.prediction === 1 ||

                                    model.prediction === true;


                                return `

                                    <div class="model-row">

                                        <span class="model-name">

                                            ${escapeHtml(
                                                model.name
                                            )}

                                        </span>


                                        <div class="model-track">

                                            <div
                                                class="model-fill"
                                                style="
                                                    width:
                                                    ${modelProbability}%;
                                                "
                                            >
                                            </div>

                                        </div>


                                        <strong>

                                            ${modelProbability}%

                                        </strong>


                                        <span
                                            class="
                                                model-prediction

                                                ${
                                                    modelDelayed

                                                        ? "delay"

                                                        : "ontime"
                                                }
                                            "
                                        >

                                            ${
                                                modelDelayed

                                                    ? "Atraso"

                                                    : "No prazo"
                                            }

                                        </span>

                                    </div>

                                `;

                            }

                        )

                        .join("");


                /* =========================================
                   ACCORDION COMPLETO
                   ========================================= */

                return `

                    <details
                        class="
                            order-accordion

                            ${
                                delayed
                                    ? "delay"
                                    : "ontime"
                            }
                        "
                    >


                        <!-- ================================
                             PARTE FECHADA DO ACCORDION
                             ================================ -->

                        <summary class="order-summary">


                            <div class="order-summary-main">


                                <span class="order-chevron">
                                    ›
                                </span>


                                <div class="order-summary-title">

                                    <strong>

                                        Pedido #${escapeHtml(
                                            pedidoId
                                        )}

                                    </strong>


                                    <div class="order-summary-models">
                                        ${modelProbabilityChips}
                                    </div>

                                </div>

                            </div>



                            <span
                                class="
                                    batch-result-tag

                                    ${
                                        delayed
                                            ? "delay"
                                            : "ontime"
                                    }
                                "
                            >

                                ${
                                    delayed

                                        ? "RISCO DE ATRASO"

                                        : "DENTRO DO PRAZO"
                                }

                            </span>

                        </summary>



                        <!-- ================================
                             CONTEÚDO ABERTO
                             ================================ -->

                        <div class="order-content">


                            <!-- ============================
                                 MESMA PRIMEIRA LINHA DO
                                 RESULTADO.HTML
                                 ============================ -->

                            <section class="result-grid">


                                <!-- PREDIÇÃO PRINCIPAL -->

                                <article
                                    class="
                                        result-card
                                        prediction-card

                                        ${
                                            delayed
                                                ? "delay"
                                                : "ontime"
                                        }
                                    "
                                >

                                    <span class="eyebrow">

                                        Predição principal

                                    </span>


                                    <div class="prediction-badge">

                                        ${
                                            delayed

                                                ? "RISCO DE ATRASO"

                                                : "DENTRO DO PRAZO"
                                        }

                                    </div>


                                    <h2>

                                        ${
                                            delayed

                                                ? "O pedido apresenta risco de atraso."

                                                : "O pedido tende a chegar dentro do prazo."
                                        }

                                    </h2>


                                    <p>

                                        ${
                                            delayed

                                                ?

                                                `O modelo estima ${probabilityPct}% de probabilidade de atraso para esta entrega.`

                                                :

                                                `O modelo estima ${100 - probabilityPct}% de probabilidade de entrega sem atraso.`
                                        }

                                    </p>


                                    <div class="model-caption">

                                        Modelo principal:

                                        <strong>

                                            ${escapeHtml(
                                                result.main_model ||
                                                "XGBoost"
                                            )}

                                        </strong>

                                    </div>

                                </article>



                                <!-- PROBABILIDADE -->

                                <article
                                    class="
                                        result-card
                                        probability-card
                                    "
                                >

                                    <span class="eyebrow">

                                        Probabilidade de atraso

                                    </span>


                                    <div class="probability-number">

                                        ${probabilityPct}%

                                    </div>


                                    <div class="model-probability-list">

                                        ${modelProbabilityList}

                                    </div>


                                    <div class="risk-track">

                                        <div
                                            class="risk-fill"
                                            style="
                                                width:
                                                ${probabilityPct}%;
                                            "
                                        >
                                        </div>

                                    </div>


                                    <div class="risk-scale">

                                        <span>
                                            Baixo
                                        </span>

                                        <span>
                                            Moderado
                                        </span>

                                        <span>
                                            Alto
                                        </span>

                                        <span>
                                            Muito alto
                                        </span>

                                    </div>


                                    <div class="risk-level">

                                        Nível de risco:

                                        <strong>

                                            ${escapeHtml(
                                                riskLevel
                                            )}

                                        </strong>

                                    </div>

                                </article>

                            </section>



                            <!-- ============================
                                 EXPLICABILIDADE +
                                 AÇÃO RECOMENDADA
                                 ============================ -->

                            <section class="dashboard-grid">


                                <!-- FATORES -->

                                <article
                                    class="
                                        panel
                                        panel-wide
                                    "
                                >

                                    <div class="panel-heading">

                                        <div>

                                            <span class="eyebrow">

                                                Explicabilidade por modelo

                                            </span>


                                            <h2>

                                                Fatores que influenciaram
                                                a previsão

                                            </h2>

                                        </div>


                                        <span class="tag">

                                            XGBoost + MLP

                                        </span>

                                    </div>


                                    <p class="panel-description">

                                        Cada bloco mostra os cinco
                                        fatores de maior impacto para
                                        aquele modelo.

                                    </p>


                                    <div class="model-factors-grid">

                                        ${factorsHtml}

                                    </div>

                                </article>



                                <!-- RECOMENDAÇÃO -->

                                <article class="panel">

                                    <div class="panel-heading">

                                        <div>

                                            <span class="eyebrow">

                                                Ação recomendada

                                            </span>


                                            <h2>

                                                O que fazer agora?

                                            </h2>

                                        </div>

                                    </div>


                                    <div
                                        class="
                                            recommendation

                                            ${
                                                probabilityPct >= 61
                                                    ? "high"
                                                    : ""
                                            }
                                        "
                                    >

                                        <strong>

                                            ${escapeHtml(
                                                recommendation.title
                                            )}

                                        </strong>


                                        ${escapeHtml(
                                            recommendation.text
                                        )}

                                    </div>

                                </article>

                            </section>



                            <!-- ============================
                                 COMPARAÇÃO DOS MODELOS
                                 ============================ -->

                            <section class="panel">

                                <div class="panel-heading">

                                    <div>

                                        <span class="eyebrow">

                                            Comparativo

                                        </span>


                                        <h2>

                                            Probabilidades por modelo

                                        </h2>

                                    </div>


                                    <span class="tag">

                                        XGBoost + MLP

                                    </span>

                                </div>


                                <p class="panel-description">

                                    Cada modelo calcula o risco separadamente
                                    para este pedido. Não há combinação das probabilidades.

                                </p>


                                <div class="model-comparison">

                                    ${modelsHtml}

                                </div>

                            </section>


                        </div>

                    </details>

                `;

            }

        )

        .join("");
