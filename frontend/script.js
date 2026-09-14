document.getElementById('form-previsao').addEventListener('submit', async function(event) {
    event.preventDefault(); // Evita que a página recarregue

    // Coleta os dados digitados
    const payload = {
        distancia_km: parseFloat(document.getElementById('distancia_km').value),
        tempo_estimado_min: parseFloat(document.getElementById('tempo_estimado_min').value),
        clima_severo: parseInt(document.getElementById('clima_severo').value)
    };

    try {
        // Envia para o backend Python (mesmo IP/porta que carregou o site)
        const response = await fetch('/predict', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(payload)
        });

        const data = await response.json();
        
        // Atualiza a tela com o resultado
        const cardDiv = document.getElementById('resultado-card');
        const statusH2 = document.getElementById('status-texto');
        const probSpan = document.getElementById('probabilidade-valor');

        cardDiv.classList.remove('oculto', 'risco-alto', 'risco-baixo');
        
        if (data.previsao_atraso) {
            statusH2.innerText = "ALTO RISCO DE ATRASO";
            cardDiv.classList.add('risco-alto');
        } else {
            statusH2.innerText = "ENTREGA NO PRAZO";
            cardDiv.classList.add('risco-baixo');
        }

        probSpan.innerText = (data.probabilidade * 100).toFixed(1) + "%";
        
    } catch (error) {
        alert("Erro ao comunicar com a API: " + error);
    }
});