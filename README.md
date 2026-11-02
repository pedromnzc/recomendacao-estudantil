# Sistema de Recomendação Híbrido para Plataforma de Ensino

API em FastAPI que recomenda materiais didáticos (livros, artigos e vídeos) para alunos, conforme o enunciado em `Projeto Pratico.pdf`. Ela combina três modelos de recomendação e calcula as métricas de avaliação offline e online.

| Endpoint | Método | O que faz |
|----------|--------|-----------|
| `/recomendacoes/{id_aluno}?modelo=hibrido` | GET | 5 materiais para o aluno. `modelo`: `conteudo`, `colaborativo`, `conhecimento` ou `hibrido` (padrão) |
| `/feedback` | POST | Registra clique, minutos de uso e nota da pesquisa de satisfação |
| `/metricas/online` | GET | Taxa de clique (CTR), tempo médio de engajamento e satisfação média |
| `/metricas/offline` | GET | Precisão@K, Recall@K, F1-Score, RMSE, cobertura e diversidade |

## Como rodar

Todos os comandos são executados **na raiz do projeto**, porque os CSVs são lidos por caminho relativo.

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows  (Linux/Mac: source .venv/bin/activate)
pip install -r requirements.txt
uvicorn app.main:app --reload
```

- Swagger (documentação interativa): http://127.0.0.1:8000/docs
- Testes automatizados: `pytest -q`

Os dados que a API usa já vêm no repositório, então não é preciso rodar o `app/data.py` (veja [Dados](#dados)).

### Rodando com Docker

Com o Docker Desktop aberto, na raiz do projeto:

```bash
docker compose up --build
```

1. O serviço `tests` instala as dependências e roda o `pytest -v`.
2. Se todos os testes passarem, o serviço `api` sobe a API em http://127.0.0.1:8000/docs. Se algum falhar, a API não sobe.

Para parar: `Ctrl+C` e depois `docker compose down`.

## Dados

| Arquivo | Conteúdo |
|---------|----------|
| `data/dados_alunos.csv` | 10.000 alunos: curso, período, disciplinas cursadas e áreas de interesse |
| `data/materiais_didaticos.csv` | 10.000 materiais: título, tipo, área, nível, descrição e autor |
| `data/interacoes.csv` | 10.000.000 interações de 2023: tipo, avaliação (1 a 5), duração e data |

O `app/data.py` remove as interações de alunos ou materiais que não existem nos cadastros e salva o resultado em `data/interacoes_limpas.csv`. Os ids das interações vão até 100.000 (alunos) e 50.000 (materiais), mas só existem 10.000 de cada. Por isso sobram **200.622** das 10 milhões de interações (2%).

> O `data/interacoes.csv` tem 466 MB e passa do limite de 100 MB por arquivo do GitHub, por isso não está no repositório. O `data/interacoes_limpas.csv` (9 MB) já vem pronto. Para gerá-lo de novo, coloque o arquivo bruto em `data/` e rode `python app/data.py`.

Outras características dos dados, que explicam os resultados das métricas:
- **Alunos:** os 10.000 são só **8 perfis** repetidos.
- **Materiais:** os 10.000 são só **10 títulos**, cada um com 1.000 exemplares iguais. Por isso as recomendações mostram **no máximo um material de cada título**.
- **Notas:** foram sorteadas de 1 a 5, sem relação com o perfil do aluno.
- **Colunas ausentes:** não há notas das disciplinas nem downloads, que o enunciado cita.

---

## Modelos

Os quatro modelos ficam em `app/main.py`, nos blocos numerados de 1 a 4. Todos recomendam só materiais que o aluno ainda não viu.

### 1. Filtragem baseada em conteúdo

O perfil do aluno (curso, disciplinas cursadas e áreas de interesse) e o texto de cada material (título, descrição e área) viram vetores TF-IDF. A pontuação é a similaridade de cosseno entre eles, de 0 a 1.

### 2. Filtragem colaborativa

- **Alunos parecidos:** os que deram nota 4 ou 5 a algum material a que o aluno também deu 4 ou 5.
- **Nota prevista:** para cada material, a média das notas que os alunos parecidos deram a ele. Se nenhum deles avaliou o material, a previsão é a média geral das notas.
- **Recomendação:** os materiais com as maiores notas previstas. Essa mesma previsão é usada no RMSE.

### 3. Modelo baseado em conhecimento

Regras baseadas nos requisitos das disciplinas (tabela `REQUISITOS_POR_AREA` no início de `app/main.py`):
- **Material iniciante:** não tem requisito.
- **Material intermediário ou avançado:** o aluno precisa ter cursado uma das disciplinas-requisito da área. Exemplo: Deep Learning, da área IA, exige IA ou ML.
- **Pontuação:** entre os materiais liberados, o de nível mais alto vem primeiro. Avançado vale 1; intermediário, 0,67; iniciante, 0,33.

### 4. Híbrido

```
pontuação = 0,4 × conteúdo + 0,3 × colaborativo + 0,3 × conhecimento
```

- As três partes vão de 0 a 1. A nota prevista pelo colaborativo é dividida por 5.
- Só entram os materiais liberados pelas regras do modelo de conhecimento.

### Exemplo

```bash
curl "http://127.0.0.1:8000/recomendacoes/1?modelo=conteudo"
```

```json
{
  "aluno": {"nome": "João Silva", "curso": "Engenharia de Software", "periodo": 5, "disciplinas_cursadas": "Algoritmos, Banco de Dados, IA", "areas_interesse": "ML, Programação, Cloud"},
  "modelo": "conteudo",
  "recomendacoes": [
    {"id_material": 1, "titulo": "Introdução a Algoritmos", "tipo": "livro", "area": "Programação", "nivel": "Iniciante", "descricao": "Fundamentos de algoritmos e estruturas de dados", "autor": "Thomas Cormen", "pontuacao": 0.558},
    {"id_material": 3, "titulo": "ML Avançado", "tipo": "livro", "area": "IA", "nivel": "Avançado", "descricao": "Técnicas avançadas de machine learning", "autor": "Aurélien Géron", "pontuacao": 0.329}
  ]
}
```

A resposta traz os 5 materiais; o exemplo mostra só os 2 primeiros. Abaixo, as listas de cada modelo para o João, com a pontuação:

| # | Conteúdo | Colaborativo | Conhecimento | Híbrido |
|---|----------|--------------|--------------|---------|
| 1 | Introdução a Algoritmos (0,558) | Aprendendo Python (5,0) | ML Avançado (1,0) | ML Avançado (0,732) |
| 2 | ML Avançado (0,329) | Banco de Dados NoSQL (5,0) | Deep Learning (0,667) | Introdução a Algoritmos (0,623) |
| 3 | Banco de Dados NoSQL (0,298) | Introdução a Algoritmos (5,0) | Banco de Dados NoSQL (0,667) | Banco de Dados NoSQL (0,619) |
| 4 | Deep Learning (0,101) | ML Avançado (5,0) | Introdução a Algoritmos (0,333) | Deep Learning (0,54) |
| 5 | Aprendendo Python (0,084) | UX Moderno (5,0) | Aprendendo Python (0,333) | Aprendendo Python (0,434) |

Os requisitos em ação:
- **Carlos** (aluno 3) cursou Redes. No modelo de conhecimento, o primeiro material dele é Segurança em Redes (avançado, pontuação 1,0).
- **Juliana** (aluna 6) só cursou Python e Estatística. Esses requisitos não liberam nenhum material intermediário ou avançado. Por isso o conhecimento e o híbrido recomendam a ela só os 4 títulos iniciantes.

Erros: `404` se o aluno não existe e `422` se o modelo não existe.

## Métricas online

- **Exibições:** cada material devolvido por `/recomendacoes` conta como uma exibição.
- **`/feedback`:** registra o que o aluno fez com a recomendação: se clicou (`clicou`), quantos minutos usou o material (`minutos_de_uso`) e a nota da pesquisa de satisfação (`nota_de_satisfacao`, de 1 a 5).

```bash
curl -X POST "http://127.0.0.1:8000/feedback" \
     -H "Content-Type: application/json" \
     -d '{"clicou": true, "minutos_de_uso": 30, "nota_de_satisfacao": 4}'
```

Depois de uma recomendação (5 exibições) e desse feedback, `GET /metricas/online` devolve:

```json
{"exibicoes": 5, "cliques": 1, "taxa_de_clique": 0.2, "tempo_medio_de_engajamento": 30.0, "satisfacao_media": 4}
```

Os contadores ficam em memória e zeram quando a API reinicia.

## Métricas offline

`GET /metricas/offline` (cerca de 5 s):
- **Divisão temporal:** os modelos aprendem com as interações até outubro de 2023 e são testados com as de novembro e dezembro, em 100 alunos sorteados.
- **Acerto:** recomendar um título que o aluno avaliou com nota 4 ou 5 no teste.
- **RMSE:** compara as notas previstas pela filtragem colaborativa com as notas reais do teste.

---

## Relatório

### Arquitetura

```
data/interacoes.csv ──► app/data.py ──► data/interacoes_limpas.csv
                                                 │
data/dados_alunos.csv ───────────────┐           │
data/materiais_didaticos.csv ────────┼───────────┤
                                     ▼           ▼
                                   app/main.py (FastAPI)
           ┌─────────────────┬──────────┴──────┬────────────────┐
       Conteúdo         Colaborativo      Conhecimento    Métricas offline
       (TF-IDF)       (notas previstas)     (regras)         e online
           └─────────────────┴──► Híbrido ◄────┘
```

O `app/main.py` está nesta ordem:
1. Leitura dos dados e constantes, incluindo a base de conhecimento.
2. Os três modelos e o híbrido.
3. A função `recomendar`, que ordena as pontuações, tira o que o aluno já viu e deixa um material por título.
4. Os endpoints.

Os testes ficam em `tests/test_api.py`.

### Métricas comparativas

Resultado de `GET /metricas/offline` (listas de 5 materiais, 100 alunos):

| Modelo | Precisão@5 | Recall@5 | F1-Score | Cobertura | Diversidade |
|--------|-----------:|---------:|---------:|----------:|------------:|
| Conteúdo | 0,176 | 0,476 | 0,257 | 0,10% | 0,79 |
| Colaborativo | 0,190 | 0,547 | 0,282 | 3,12% | 0,92 |
| Conhecimento | 0,150 | 0,423 | 0,221 | 0,10% | 0,74 |
| Híbrido | 0,158 | 0,458 | 0,235 | 3,73% | 0,78 |
| *Lista aleatória (referência)* | *0,178* | *0,500* | *0,263* | | |

- **Cobertura:** fração dos 10.000 materiais que aparece em alguma recomendação.
- **Diversidade:** número de áreas diferentes na lista ÷ tamanho da lista.
- **RMSE da filtragem colaborativa:** **1,547**. Prever sempre a média erraria cerca de 1,41, que é o desvio padrão de notas sorteadas de 1 a 5.

**Análise:**
- **Acerto:** todos os modelos acertam mais ou menos o mesmo que uma lista aleatória. As diferenças entre eles são do tamanho da variação de uma amostra de 100 alunos. O colaborativo também erra as notas um pouco mais que a média. Isso não é defeito dos modelos: as notas dos dados foram sorteadas, então não há preferência para aprender.
- **Cobertura e diversidade:** é onde os modelos se diferenciam.
  - Conteúdo e conhecimento olham só o título e o perfil. Os 1.000 exemplares de cada título empatam e sempre ganha o primeiro, então a cobertura fica em 0,10% (10 materiais).
  - Colaborativo e híbrido variam o exemplar recomendado (3% a 4%).
  - O colaborativo tem a lista mais diversa (0,92), porque não depende do perfil.
- **Métricas online:** dependem de alunos reais usando o sistema. A API já registra exibições, cliques, tempo de uso e satisfação.

### Pontos fortes e fracos

| Modelo | Pontos fortes | Pontos fracos |
|--------|---------------|---------------|
| Conteúdo | Funciona para aluno novo (usa só o perfil). Fácil de explicar. | Recomenda o que o aluno já domina. Depende de palavras em comum. |
| Colaborativo | Não precisa de metadados. Descobre materiais fora do perfil. Lista mais diversa. | Não funciona sem histórico. Ignora os requisitos. Cada material tem poucas notas, então muitas previsões empatam em 5,0. |
| Conhecimento | Respeita os requisitos das disciplinas. Regras fáceis de conferir e ajustar. | Regras escritas à mão. Não usa os interesses nem o comportamento. Muitos empates. |
| Híbrido | Junta perfil, comportamento e regras. Nunca recomenda material sem requisito. | Pesos escolhidos à mão. Mais lento, porque roda os três modelos. |

### Sugestões de melhorias

1. Usar dados reais ou gerados com padrão (notas maiores nas áreas de interesse), com ids válidos e catálogo variado.
2. Incluir as notas das disciplinas, para regras como "nota ≥ 7 em Estatística libera ML Avançado".
3. Trocar o TF-IDF por embeddings de texto, que entendem sinônimos (ex.: Robótica e IoT).
4. No colaborativo, pesar a média pela semelhança entre os alunos ou usar fatoração de matrizes, para reduzir os empates.
5. Aprender os pesos do híbrido com os dados, em vez de fixá-los.
6. Guardar as métricas online em banco de dados e separá-las por modelo, para fazer um teste A/B.
