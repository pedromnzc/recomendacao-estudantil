import pytest
from fastapi.testclient import TestClient

import app.main as api

cliente = TestClient(api.app)
MODELOS = ["conteudo", "colaborativo", "conhecimento", "hibrido"]


def buscar_recomendacoes(id_aluno, modelo):
    resposta = cliente.get(f"/recomendacoes/{id_aluno}", params={"modelo": modelo})
    assert resposta.status_code == 200
    return resposta.json()["recomendacoes"]


@pytest.mark.parametrize("modelo", MODELOS)
def test_recomendacoes(modelo):
    recomendacoes = buscar_recomendacoes(1, modelo)
    assert len(recomendacoes) == 5
    titulos = {recomendacao["titulo"] for recomendacao in recomendacoes}
    assert len(titulos) == 5  # no máximo um material de cada título
    pontuacoes = [recomendacao["pontuacao"] for recomendacao in recomendacoes]
    assert pontuacoes == sorted(pontuacoes, reverse=True)
    recomendados = {recomendacao["id_material"] for recomendacao in recomendacoes}
    vistos = set(api.interacoes.loc[api.interacoes["id_aluno"] == 1, "id_material"])
    assert not recomendados & vistos  # nada que o aluno já viu


def test_conteudo_segue_o_perfil():
    # João cursou Algoritmos e se interessa por Programação
    assert buscar_recomendacoes(1, "conteudo")[0]["titulo"] == "Introdução a Algoritmos"


def test_conhecimento_prioriza_o_nivel_mais_alto():
    # Carlos cursou Redes, requisito do material avançado "Segurança em Redes"
    primeira_recomendacao = buscar_recomendacoes(3, "conhecimento")[0]
    assert primeira_recomendacao["titulo"] == "Segurança em Redes"
    assert primeira_recomendacao["pontuacao"] == 1


@pytest.mark.parametrize("modelo", ["conhecimento", "hibrido"])
def test_requisitos_bloqueiam_materiais(modelo):
    # Juliana só cursou Python e Estatística, que não liberam nenhum material intermediário
    # ou avançado (ex.: Deep Learning exige IA ou ML)
    niveis = {recomendacao["nivel"] for recomendacao in buscar_recomendacoes(6, modelo)}
    assert niveis == {"Iniciante"}


def test_erros():
    assert cliente.get("/recomendacoes/999999").status_code == 404
    assert cliente.get("/recomendacoes/1", params={"modelo": "outro"}).status_code == 422
    feedback_invalido = {"clicou": True, "nota_de_satisfacao": 6}
    assert cliente.post("/feedback", json=feedback_invalido).status_code == 422


def test_metricas_online(monkeypatch):
    # Zera os contadores para não depender das recomendações feitas pelos outros testes
    metricas_zeradas = {
        "exibicoes": 0,
        "cliques": 0,
        "minutos_de_uso": [],
        "notas_de_satisfacao": [],
    }
    monkeypatch.setattr(api, "metricas_online", metricas_zeradas)

    cliente.get("/recomendacoes/1")  # 5 materiais exibidos
    feedback = {"clicou": True, "minutos_de_uso": 30, "nota_de_satisfacao": 4}
    assert cliente.post("/feedback", json=feedback).status_code == 200

    assert cliente.get("/metricas/online").json() == {
        "exibicoes": 5,
        "cliques": 1,
        "taxa_de_clique": 0.2,
        "tempo_medio_de_engajamento": 30,
        "satisfacao_media": 4,
    }


def test_metricas_offline():
    corpo = cliente.get("/metricas/offline").json()
    assert list(corpo["modelos"]) == MODELOS
    for metricas_do_modelo in corpo["modelos"].values():
        assert all(0 <= valor <= 1 for valor in metricas_do_modelo.values())
    assert corpo["rmse_colaborativo"] > 0
