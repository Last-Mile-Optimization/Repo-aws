/* =========================================================
   RECUPERA O RESULTADO DA ANÁLISE
   ========================================================= */

const result = JSON.parse(
    sessionStorage.getItem(
        "predictionResult"
    ) || "null"
);


/*
   Se alguém abrir resultado.html diretamente,
   sem ter realizado uma análise antes,
   volta para a página inicial.
*/

if (!result) {

    window.location.href =
        "index.html";

}


/* =========================================================
   INFORMAÇÕES PRINCIPAIS
   ========================================================= */

const probability =
    Math.round(
        result.probability * 100
    );


const isDelay =
    result.prediction === 1;


/* ID da análise */

document.getElementById(
    "analysisId"
).textContent =
    result.analysis_id || "—";


/* Modelo principal */

document.getElementById(
    "mainModelName"
).textContent =
    result.main_model ||
    "Deep Learning";


/* =========================================================
   CARD PRINCIPAL DA PREVISÃO
   ========================================================= */

const predictionCard =
    document.getElementById(
        "predictionCard"
    );


predictionCard.classList.add(
    isDelay
        ? "delay"
        : "ontime"
);


/* Badge */

document.getElementById(
    "predictionBadge"
).textContent =

    isDelay

        ? "RISCO DE ATRASO"

        : "DENTRO DO PRAZO";


/* Título */

document.getElementById(
    "predictionTitle"
).textContent =

    isDelay

        ? "O pedido apresenta risco de atraso."

        : "O pedido tende a chegar dentro do prazo.";


/* Descrição */

document.getElementById(
    "predictionDescription"
).textContent =

    isDelay

        ? `O modelo estima ${probability}% de probabilidade de atraso para esta entrega.`

        : `O modelo estima ${100 - probability}% de probabilidade de entrega sem atraso.`;


/* =========================================================
   PROBABILIDADE DE ATRASO
   ========================================================= */

document.getElementById(
    "probabilityNumber"
).textContent =
    `${probability}%`;


/* Barra */

document.getElementById(
    "riskFill"
).style.width =
    `${probability}%`;


/* Nível de risco */

document.getElementById(
    "riskLevel"
).textContent =
    result.risk_level;


/* =========================================================
   EXPLICABILIDADE
   FATORES QUE MAIS INFLUENCIARAM
   ========================================================= */

const factorsChart =
    document.getElementById(
        "factorsChart"
    );


factorsChart.innerHTML =

    result.factors
        .map(item => `

            <div class="bar-row">

                <strong>
                    ${item.name}
                </strong>

                <div class="bar-track">

                    <div
                        class="bar-value"
                        style="width: ${item.impact}%">
                    </div>

                </div>

                <span class="bar-percent">
                    ${item.impact}%
                </span>

            </div>

        `)
        .join("");


/* =========================================================
   RECOMENDAÇÃO PARA A EMPRESA
   ========================================================= */

const recommendation =
    document.getElementById(
        "recommendation"
    );


recommendation.classList.toggle(
    "high",
    probability >= 61
);


/*
   A recomendação muda conforme
   a probabilidade calculada.
*/

if (probability >= 81) {

    recommendation.innerHTML = `

        <strong>
            Prioridade alta de acompanhamento
        </strong>

        O pedido apresenta risco muito elevado.

        Vale sinalizar a entrega para acompanhamento
        e revisar o prazo prometido ao cliente.

    `;

}

else if (probability >= 61) {

    recommendation.innerHTML = `

        <strong>
            Atenção recomendada
        </strong>

        O risco está acima do ideal.

        Acompanhe a entrega e considere medidas
        preventivas para evitar impacto na
        experiência do cliente.

    `;

}

else if (probability >= 31) {

    recommendation.innerHTML = `

        <strong>
            Monitoramento preventivo
        </strong>

        O pedido apresenta risco moderado.

        Não exige ação imediata, mas vale
        acompanhar a evolução da entrega.

    `;

}

else {

    recommendation.innerHTML = `

        <strong>
            Baixo risco identificado
        </strong>

        As características do pedido são
        semelhantes às de entregas que
        normalmente chegam dentro do prazo.

    `;

}


/* =========================================================
   COMPARAÇÃO ENTRE OS MODELOS
   ========================================================= */

const modelsChart =
    document.getElementById(
        "modelsChart"
    );


modelsChart.innerHTML =

    result.models
        .map(model => {

            const modelProbability =
                Math.round(
                    model.probability * 100
                );


            return `

                <div class="model-row">

                    <span class="model-name">
                        ${model.name}
                    </span>


                    <div class="model-track">

                        <div
                            class="model-fill"
                            style="
                                width:
                                ${modelProbability}%
                            ">
                        </div>

                    </div>


                    <strong>
                        ${modelProbability}%
                    </strong>


                    <span
                        class="
                            model-prediction
                            ${
                                model.prediction
                                    ? "delay"
                                    : "ontime"
                            }
                        "
                    >

                        ${
                            model.prediction

                                ? "Atraso"

                                : "No prazo"
                        }

                    </span>

                </div>

            `;

        })
        .join("");


/* =========================================================
   K-MEANS
   PERFIL DO PEDIDO
   ========================================================= */

document.getElementById(
    "clusterName"
).textContent =
    result.cluster.name;


document.getElementById(
    "clusterDescription"
).textContent =
    result.cluster.description;


/*
   Estatísticas do cluster
*/

document.getElementById(
    "clusterStats"
).innerHTML =

    result.cluster.stats

        .map(
            ([label, value]) => `

                <div class="stat">

                    <span>
                        ${label}
                    </span>

                    <strong>
                        ${value}
                    </strong>

                </div>

            `
        )

        .join("");


/* =========================================================
   DBSCAN
   DETECÇÃO DE PEDIDOS FORA DO PADRÃO
   ========================================================= */

const patternStatus =
    document.getElementById(
        "patternStatus"
    );


patternStatus.classList.toggle(
    "outlier",
    result.dbscan.is_outlier
);


patternStatus.innerHTML = `

    <strong>

        ${
            result.dbscan.is_outlier

                ? "⚠ Padrão incomum identificado"

                : "✓ Pedido dentro de um padrão conhecido"
        }

    </strong>

    ${result.dbscan.text}

`;


/* =========================================================
   PCA
   VISUALIZAÇÃO 2D
   ========================================================= */

function drawPCA() {

    const canvas =
        document.getElementById(
            "pcaCanvas"
        );


    const ctx =
        canvas.getContext("2d");


    const width =
        canvas.width;


    const height =
        canvas.height;


    ctx.clearRect(
        0,
        0,
        width,
        height
    );


    /* =====================================================
       GERADOR PSEUDOALEATÓRIO

       Utilizado apenas para que os pontos históricos
       fiquem sempre nas mesmas posições.
       ===================================================== */

    const seed = 42;

    let x = seed;


    function rand() {

        x =
            (
                x * 1664525 +
                1013904223
            ) % 4294967296;


        return (
            x /
            4294967296
        );

    }


    /* =====================================================
       PEDIDOS HISTÓRICOS
       ===================================================== */

    ctx.fillStyle =
        "#a7b5bc";


    ctx.globalAlpha =
        0.48;


    for (
        let i = 0;
        i < 95;
        i++
    ) {

        const cx =

            width *

            (
                0.18 +
                rand() * 0.64
            );


        const cy =

            height *

            (
                0.18 +
                rand() * 0.64
            );


        ctx.beginPath();


        ctx.arc(
            cx,
            cy,
            4,
            0,
            Math.PI * 2
        );


        ctx.fill();

    }


    /* =====================================================
       POSIÇÃO DO NOVO PEDIDO
       ===================================================== */

    const px =

        width / 2 +

        (
            result.pca_point.x /
            3
        ) *

        (
            width * 0.38
        );


    const py =

        height / 2 -

        (
            result.pca_point.y /
            3
        ) *

        (
            height * 0.38
        );


    /* Novo pedido */

    ctx.globalAlpha = 1;


    ctx.fillStyle =
        "#ff7d49";


    ctx.beginPath();


    ctx.arc(
        px,
        py,
        10,
        0,
        Math.PI * 2
    );


    ctx.fill();


    /* Contorno */

    ctx.strokeStyle =
        "#132432";


    ctx.lineWidth =
        2;


    ctx.beginPath();


    ctx.arc(
        px,
        py,
        15,
        0,
        Math.PI * 2
    );


    ctx.stroke();


    /* Texto */

    ctx.fillStyle =
        "#132432";


    ctx.font =
        "700 14px system-ui";


    ctx.fillText(

        "Novo pedido",

        Math.min(
            px + 18,
            width - 110
        ),

        Math.max(
            py - 12,
            20
        )

    );

}


/*
   Executa o desenho.
*/

drawPCA();


/* =========================================================
   RESUMO DOS DADOS INFORMADOS
   ========================================================= */

const input =
    result.input;


/*
   Dados originais + algumas features
   derivadas.
*/

const featureSummary = [

    [
        "Data da compra",
        input.purchase_date
    ],

    [
        "Horário",
        input.purchase_time
    ],

    [
        "Valor do produto",

        `R$ ${
            Number(input.price)
                .toFixed(2)
                .replace(".", ",")
        }`
    ],

    [
        "Frete",

        `R$ ${
            Number(input.freight_value)
                .toFixed(2)
                .replace(".", ",")
        }`
    ],

    [
        "Peso",

        `${
            Number(
                input.product_weight_g
            ).toLocaleString(
                "pt-BR"
            )
        } g`
    ],

    [
        "Volume",

        `${
            Number(
                result.features.volume_cm3
            ).toLocaleString(
                "pt-BR"
            )
        } cm³`
    ],

    [
        "Distância",

        `${
            Number(
                input.distance_km
            ).toLocaleString(
                "pt-BR"
            )
        } km`
    ],

    [
        "Mesma cidade",

        input.same_city
            ? "Sim"
            : "Não"
    ],

    [
        "Hora derivada",

        result.features
            .purchase_hour
    ],

    [
        "Dia da semana",

        result.features
            .purchase_day_of_week
    ],

    [
        "Fim de semana",

        result.features
            .is_weekend

            ? "Sim"

            : "Não"
    ]

];


/* =========================================================
   EXIBE O RESUMO
   ========================================================= */

document.getElementById(
    "inputSummary"
).innerHTML =

    featureSummary

        .map(
            ([label, value]) => `

                <div class="summary-item">

                    <span>
                        ${label}
                    </span>

                    <strong>
                        ${value}
                    </strong>

                </div>

            `
        )

        .join("");