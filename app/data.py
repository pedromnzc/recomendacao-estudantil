import pandas as pd

alunos = pd.read_csv("data/dados_alunos.csv")
materiais = pd.read_csv("data/materiais_didaticos.csv")
interacoes = pd.read_csv("data/interacoes.csv")

# 98% das interações apontam para alunos ou materiais que não existem nos cadastros
# (os ids vão até 100.000 e 50.000, mas só há 10.000 alunos e 10.000 materiais).
aluno_existe = interacoes["id_aluno"].isin(alunos["id_aluno"])
material_existe = interacoes["id_material"].isin(materiais["id_material"])
interacoes_limpas = interacoes[aluno_existe & material_existe]

interacoes_limpas.to_csv("data/interacoes_limpas.csv", index=False)
print(f"Interações lidas: {len(interacoes):,} | mantidas: {len(interacoes_limpas):,}")
