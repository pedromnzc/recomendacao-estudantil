from statistics import mean
from typing import Literal, get_args

import pandas as pd
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

app = FastAPI(title="Sistema de Recomendação Híbrido - Plataforma de Ensino")

alunos = pd.read_csv("data/dados_alunos.csv").set_index("id_aluno")
materiais = pd.read_csv("data/materiais_didaticos.csv").set_index("id_material")
interacoes = pd.read_csv("data/interacoes_limpas.csv")

Modelo = Literal["conteudo", "colaborativo", "conhecimento", "hibrido"]
TAMANHO_LISTA = 5  # materiais recomendados por vez (o K da Precisão@K e do Recall@K)
NOTA_GOSTOU = 4  # a partir desta nota (de 1 a 5), o aluno gostou do material
INICIO_TESTE = "2023-11-01"  # avaliação offline: treina antes desta data e testa a partir dela
ALUNOS_AVALIADOS = 100  # alunos sorteados para a avaliação offline

# Base de conhecimento: para receber um material intermediário ou avançado de uma área, o aluno
# precisa ter cursado pelo menos uma destas disciplinas. Material iniciante não tem requisito.
REQUISITOS_POR_AREA = {
    "Programação": {"Algoritmos", "Python", "Web", "Compiladores"},
    "IA": {"IA", "ML"},
    "Estatística": {"Estatística", "ML"},
    "BD": {"BD", "Banco de Dados"},
    "Segurança": {"Redes", "SO"},
    "IoT": {"Arquitetura", "Redes", "SO"},
    "Gestão": {"Gestão", "PM"},
    "UX": {"UX", "Web"},
}
# Entre os materiais liberados, os de nível mais alto vêm primeiro
PESO_DO_NIVEL = {"Iniciante": 1, "Intermediário": 2, "Avançado": 3}


# 1. Filtragem baseada em conteúdo: perfil do aluno x texto de cada material
vetorizador = TfidfVectorizer()
vetores_materiais = vetorizador.fit_transform(
    materiais["titulo"] + " " + materiais["descricao"] + " " + materiais["area"]
)


def pontuar_conteudo(id_aluno: int) -> pd.Series:
    """Similaridade de cosseno (0 a 1) entre o perfil do aluno e cada material."""
    aluno = alunos.loc[id_aluno]
    perfil = f"{aluno['curso']} {aluno['disciplinas_cursadas']} {aluno['areas_interesse']}"
    similaridades = cosine_similarity(vetorizador.transform([perfil]), vetores_materiais)[0]
    return pd.Series(similaridades, index=materiais.index)


# 2. Filtragem colaborativa: notas dos alunos que gostaram dos mesmos materiais
def prever_notas(id_aluno: int, historico: pd.DataFrame) -> pd.Series:
    """
    Nota prevista (1 a 5) para cada material: a média das notas que os alunos parecidos deram a
    ele. Alunos parecidos são os que gostaram de algum material de que o aluno também gostou.
    Material que nenhum deles avaliou recebe a média geral das notas.
    """
    gostaram = historico[historico["avaliacao"] >= NOTA_GOSTOU]
    materiais_que_gostou = gostaram.loc[gostaram["id_aluno"] == id_aluno, "id_material"]
    alunos_parecidos = gostaram.loc[gostaram["id_material"].isin(materiais_que_gostou), "id_aluno"]
    notas_dos_parecidos = historico[
        historico["id_aluno"].isin(alunos_parecidos) & (historico["id_aluno"] != id_aluno)
    ]
    media_por_material = notas_dos_parecidos.groupby("id_material")["avaliacao"].mean()
    return media_por_material.reindex(materiais.index, fill_value=historico["avaliacao"].mean())


# 3. Modelo baseado em conhecimento: regras de requisitos das disciplinas
def pontuar_conhecimento(id_aluno: int) -> pd.Series:
    """Só os materiais cujos requisitos o aluno cumpre, pontuados pelo nível (0 a 1)."""
    disciplinas_cursadas = set(alunos.loc[id_aluno, "disciplinas_cursadas"].split(", "))
    areas_liberadas = [
        area
        for area, disciplinas_requisito in REQUISITOS_POR_AREA.items()
        if disciplinas_requisito & disciplinas_cursadas
    ]
    pode_cursar = (materiais["nivel"] == "Iniciante") | materiais["area"].isin(areas_liberadas)
    return materiais.loc[pode_cursar, "nivel"].map(PESO_DO_NIVEL) / 3


# 4. Híbrido: média ponderada dos três modelos
def pontuar_hibrido(id_aluno: int, historico: pd.DataFrame) -> pd.Series:
    """Combina os três modelos nos materiais cujos requisitos o aluno cumpre."""
    conhecimento = pontuar_conhecimento(id_aluno)
    materiais_liberados = conhecimento.index
    conteudo = pontuar_conteudo(id_aluno)[materiais_liberados]
    colaborativo = prever_notas(id_aluno, historico)[materiais_liberados] / 5  # de 0 a 1
    return 0.4 * conteudo + 0.3 * colaborativo + 0.3 * conhecimento


def recomendar(modelo: Modelo, id_aluno: int, historico: pd.DataFrame = interacoes) -> pd.DataFrame:
    """Os materiais mais bem pontuados que o aluno ainda não viu, no máximo um de cada título."""
    if modelo == "conteudo":
        pontuacoes = pontuar_conteudo(id_aluno)
    elif modelo == "colaborativo":
        pontuacoes = prever_notas(id_aluno, historico)
    elif modelo == "conhecimento":
        pontuacoes = pontuar_conhecimento(id_aluno)
    else:
        pontuacoes = pontuar_hibrido(id_aluno, historico)

    materiais_vistos = historico.loc[historico["id_aluno"] == id_aluno, "id_material"]
    nao_vistos = pontuacoes.drop(materiais_vistos, errors="ignore")
    ranking = nao_vistos.sort_values(ascending=False, kind="stable")
    recomendados = materiais.loc[ranking.index].assign(pontuacao=ranking.round(3))
    # O catálogo repete os mesmos 10 títulos em 10.000 materiais: mostramos um de cada
    return recomendados.drop_duplicates("titulo").head(TAMANHO_LISTA)


# Métricas online: contadores em memória, atualizados a cada recomendação e a cada feedback
metricas_online = {"exibicoes": 0, "cliques": 0, "minutos_de_uso": [], "notas_de_satisfacao": []}


class Feedback(BaseModel):
    clicou: bool
    minutos_de_uso: float = Field(0, ge=0)
    nota_de_satisfacao: int | None = Field(None, ge=1, le=5)


@app.get("/recomendacoes/{id_aluno}")
def recomendacoes(id_aluno: int, modelo: Modelo = "hibrido"):
    """Recomenda 5 materiais ao aluno com o modelo escolhido (o híbrido é o padrão)."""
    if id_aluno not in alunos.index:
        raise HTTPException(status_code=404, detail=f"Aluno {id_aluno} não encontrado")
    recomendados = recomendar(modelo, id_aluno)
    metricas_online["exibicoes"] += len(recomendados)
    return {
        "aluno": alunos.loc[id_aluno].to_dict(),
        "modelo": modelo,
        "recomendacoes": recomendados.reset_index().to_dict(orient="records"),
    }


@app.post("/feedback")
def registrar_feedback(feedback: Feedback):
    """Registra se o aluno clicou, quantos minutos usou o material e a nota da pesquisa."""
    if feedback.clicou:
        metricas_online["cliques"] += 1
    if feedback.minutos_de_uso > 0:
        metricas_online["minutos_de_uso"].append(feedback.minutos_de_uso)
    if feedback.nota_de_satisfacao is not None:
        metricas_online["notas_de_satisfacao"].append(feedback.nota_de_satisfacao)
    return {"mensagem": "Feedback registrado"}


@app.get("/metricas/online")
def calcular_metricas_online():
    """Taxa de clique (CTR), tempo médio de engajamento e satisfação média."""
    exibicoes = metricas_online["exibicoes"]
    cliques = metricas_online["cliques"]
    minutos = metricas_online["minutos_de_uso"]
    notas = metricas_online["notas_de_satisfacao"]
    return {
        "exibicoes": exibicoes,
        "cliques": cliques,
        "taxa_de_clique": round(cliques / exibicoes, 4) if exibicoes else None,
        "tempo_medio_de_engajamento": round(mean(minutos), 2) if minutos else None,
        "satisfacao_media": round(mean(notas), 2) if notas else None,
    }


@app.get("/metricas/offline")
def calcular_metricas_offline():
    """
    Os modelos aprendem com as interações até outubro de 2023 e são testados com as de novembro
    e dezembro, em 100 alunos sorteados. Acerto = recomendar um título que o aluno avaliou com
    nota 4 ou 5 no teste. O RMSE compara as notas previstas pela filtragem colaborativa com as
    notas reais do teste.
    """
    treino = interacoes[interacoes["data"] < INICIO_TESTE]
    teste = interacoes[interacoes["data"] >= INICIO_TESTE]
    gostou_no_teste = teste[teste["avaliacao"] >= NOTA_GOSTOU]
    titulos_que_gostou = gostou_no_teste["id_material"].map(materiais["titulo"])
    titulos_relevantes = titulos_que_gostou.groupby(gostou_no_teste["id_aluno"]).agg(set)
    amostra = titulos_relevantes.sample(n=ALUNOS_AVALIADOS, random_state=42)

    metricas_por_modelo = {}
    for modelo in get_args(Modelo):
        precisoes, revocacoes, diversidades = [], [], []
        materiais_recomendados = set()
        for id_aluno, titulos_do_aluno in amostra.items():
            recomendados = recomendar(modelo, id_aluno, treino)
            acertos = len(set(recomendados["titulo"]) & titulos_do_aluno)
            precisoes.append(acertos / TAMANHO_LISTA)
            revocacoes.append(acertos / len(titulos_do_aluno))
            diversidades.append(recomendados["area"].nunique() / len(recomendados))
            materiais_recomendados.update(recomendados.index)

        precisao, revocacao = mean(precisoes), mean(revocacoes)
        medida_f1 = 2 * precisao * revocacao / (precisao + revocacao) if precisao + revocacao else 0
        metricas_por_modelo[modelo] = {
            "precisao_at_k": round(precisao, 4),
            "recall_at_k": round(revocacao, 4),
            "f1_score": round(medida_f1, 4),
            "cobertura": round(len(materiais_recomendados) / len(materiais), 4),
            "diversidade": round(mean(diversidades), 4),
        }

    notas_reais = teste[teste["id_aluno"].isin(amostra.index)]
    notas_previstas = pd.concat(
        notas_do_aluno["id_material"].map(prever_notas(id_aluno, treino))
        for id_aluno, notas_do_aluno in notas_reais.groupby("id_aluno")
    )
    rmse = ((notas_reais["avaliacao"] - notas_previstas) ** 2).mean() ** 0.5
    return {"modelos": metricas_por_modelo, "rmse_colaborativo": round(rmse, 4)}
