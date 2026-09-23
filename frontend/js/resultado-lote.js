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

function getFactors(result) {

    /*
        Primeiro tenta usar os fatores reais
        enviados pelo backend.
    */

    if (
        Array.isArray(result.factors) &&
        result.factors.length
    ) {

        return result.factors;

    }


    /*
        Caso a API atual ainda não envie factors,
        mostramos uma mensagem no lugar de inventar
        explicabilidade.
    */

    return [];

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

        return result.models;

    }


    /*
        Por enquanto só existe o PKL do XGBoost.
    */

    return [

        {

            name:
                result.main_model ||
                "XGBoost",

            probability:
                probability,

            prediction:
                delayed ? 1 : 0

        }

    ];

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

        `Abra cada pedido para visualizar o diagnóstico individual.`;


/* =========================================================
   KPIs GERAIS
   ========================================================= */

document
    .getElementById(
        "batchSummary"
    )
    .innerHTML = `


        <article class="batch-stat">

            <span>
                Pedidos analisados
            </span>

            <strong>
                ${total}
            </strong>

        </article>



        <article
            class="
                batch-stat
                batch-stat-delay
            "
        >

            <span>
                Com risco de atraso
            </span>

            <strong>
                ${delayedCount}
            </strong>

        </article>



        <article
            class="
                batch-stat
                batch-stat-ontime
            "
        >

            <span>
                Dentro do prazo
            </span>

            <strong>
                ${onTimeCount}
            </strong>

        </article>

    `;


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


                const factors =
                    getFactors(result);


                const models =
                    getModels(

                        result,

                        probability,

                        delayed

                    );


                const pedidoId =

                    result.pedido_id ??

                    index + 1;


                /* =========================================
                   FATORES
                   ========================================= */

                let factorsHtml;


                if (factors.length) {

                    factorsHtml =

                        factors

                            .map(

                                factor => {


                                    const impact =

                                        Math.max(

                                            0,

                                            Math.min(

                                                100,

                                                Number(
                                                    factor.impact || 0
                                                )

                                            )

                                        );


                                    return `

                                        <div class="bar-row">

                                            <strong>

                                                ${escapeHtml(
                                                    factor.name
                                                )}

                                            </strong>


                                            <div class="bar-track">

                                                <div
                                                    class="bar-value"
                                                    style="
                                                        width:
                                                        ${impact}%;
                                                    "
                                                >
                                                </div>

                                            </div>


                                            <span class="bar-percent">

                                                ${Math.round(
                                                    impact
                                                )}%

                                            </span>

                                        </div>

                                    `;

                                }

                            )

                            .join("");

                }


                else {

                    factorsHtml = `

                        <div class="batch-empty-state">

                            Os fatores de influência ainda não
                            foram disponibilizados pelo modelo
                            para este pedido.

                        </div>

                    `;

                }


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


                                    <span>

                                        ${
                                            probabilityPct
                                        }% de probabilidade de atraso

                                    </span>

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

                                                Explicabilidade

                                            </span>


                                            <h2>

                                                Fatores que influenciaram
                                                a previsão

                                            </h2>

                                        </div>


                                        <span class="tag">

                                            Visão simplificada

                                        </span>

                                    </div>


                                    <p class="panel-description">

                                        Quanto maior a barra,
                                        maior a influência daquele
                                        fator nesta previsão.

                                    </p>


                                    <div class="bar-chart">

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

                                            Como os modelos avaliaram
                                            este pedido

                                        </h2>

                                    </div>


                                    <span class="tag">

                                        Não é ensemble

                                    </span>

                                </div>


                                <p class="panel-description">

                                    Atualmente apenas o XGBoost
                                    está conectado. Os demais modelos
                                    poderão ser adicionados posteriormente.

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