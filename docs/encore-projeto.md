# Encore: como bandas usam o próprio catálogo ao vivo

> Nome provisório. "Encore" é o bis, a parte do show que a banda guarda para o que considera essencial.

## 1. Visão geral

Plataforma de análise de dados que mede como bandas tratam a própria discografia nos shows ao longo da carreira. Combina o histórico de setlists do setlist.fm com a discografia do MusicBrainz para responder perguntas sobre repertório, rotação e longevidade das músicas ao vivo.

Projeto de portfólio com foco em:
- Engenharia de dados de ponta a ponta (ingestão, modelagem, orquestração, API)
- Definição rigorosa de métricas
- Métodos analíticos com peso matemático (análise de sobrevivência, similaridade de conjuntos)

## 2. Perguntas que o projeto responde

1. A banda vive do passado ou aposta no material novo?
2. Os shows mudam de uma noite para outra ou são sempre iguais?
3. Quanto tempo uma música sobrevive no repertório depois do lançamento?
4. Como o show é estruturado (abertura, encerramento, bis) e isso muda com o tempo?
5. O repertório muda conforme país ou tipo de local?

## 3. KPIs (versão 1)

| KPI | Definição | Grão |
|---|---|---|
| Idade média do repertório | Média de (ano do show menos ano de lançamento da música) entre as músicas do show | Show, turnê |
| Peso do álbum mais recente | % das músicas do show vindas do álbum de estúdio mais recente na data do show | Show, turnê |
| Peso da era inicial | % das músicas do show vindas dos dois primeiros álbuns de estúdio | Show, turnê |
| Rotação | 1 menos a similaridade de Jaccard média entre shows consecutivos da mesma turnê | Turnê |
| Tamanho do núcleo fixo | Nº de músicas presentes em pelo menos 90% dos shows da turnê | Turnê |
| Sobrevivência de músicas | Curva de Kaplan-Meier do tempo entre lançamento e abandono da música no repertório | Álbum, banda |
| Posições-chave | Frequência de cada música como abertura, encerramento do set principal e encerramento do bis | Música, turnê |
| Variação geográfica | Similaridade de Jaccard entre o repertório agregado por país e o repertório geral da turnê | Turnê, país |
| Cobertura dos dados | % de shows conhecidos com setlist preenchido | Banda, ano |

### Regras de cálculo

- Excluir covers, playbacks e intros gravadas (marcações do setlist.fm) dos cálculos de catálogo; manter covers em análise separada, se útil.
- Músicas sem correspondência no MusicBrainz ficam fora dos KPIs de idade e peso de álbum, mas são contadas e reportadas.
- Abandono (evento da análise de sobrevivência): música ausente dos 50 shows seguintes da banda (N = 50). A contagem é por shows, não por tempo, para não confundir hiatos (Oasis, Linkin Park) com abandono. Músicas cuja última aparição está a menos de 50 shows do fim do histórico entram como censuradas. A página de metodologia mostra a sensibilidade para N = 25 e N = 100.
- A análise de sobrevivência considera só músicas do catálogo (casadas com álbum de estúdio, single, EP ou lado B), excluindo jams, solos, intros e trechos únicos.
- Medleys: o nome registrado com " / " é separado em partes, cada uma contada como execução, com flag is_medley.
- Shows sem turnê informada (11% a 19%, conforme a banda) recebem turnê inferida pela proximidade de datas com shows que têm turnê.
- Ano de lançamento da música: primeira data de lançamento oficial encontrada no MusicBrainz (álbum, single ou EP).
- Álbum de referência de cada música: primeiro álbum de estúdio que a contém.

## 4. Fontes de dados

### setlist.fm
- API REST, exige chave (gratuita para uso não comercial)
- Dados: shows, datas, locais, cidades, países, turnês, sets, músicas, marcação de bis e covers
- Dados preenchidos pela comunidade: cobertura varia por banda e época
- Termos de uso: uso apenas não comercial; cópias dos dados só como cache por curtos períodos; atribuição obrigatória em toda página que usa os dados, com o link de atribuição de cada resposta da API (ou link para a home do setlist.fm), sem nofollow e legível por buscadores
- Consequência no desenho: dados brutos do setlist.fm são efêmeros (ver seção 7)

### MusicBrainz
- API REST aberta, sem chave
- Exige User-Agent identificando a aplicação e contato
- Limite de cerca de 1 requisição por segundo
- Dados: artistas, lançamentos, gravações, datas, tipos de lançamento
- Ambas as bases usam MBID de artista, o que facilita a ligação

## 5. Recorte inicial

7 bandas, escolhidas por história interessante, contraste entre si e boa cobertura de dados.

| Banda | Papel na análise |
|---|---|
| Arctic Monkeys | Mudanças de sonoridade entre eras |
| Oasis | Ruptura: repertório antes e depois do hiato |
| Linkin Park | Ruptura: repertório antes e depois da nova formação |
| Twenty One Pilots | Discografia em eras narrativas; candidata a polo de show roteirizado |
| Muse | Polo de show fixo, com produção pesada e setlist estável |
| Metallica | Polo de rotação alta, com catálogo de 40 anos |
| Avenged Sevenfold | Mudanças de sonoridade, com eras bem distintas (do metalcore ao experimental) |

Reservas: Blur, Radiohead.

Critério de corte: banda com cobertura de dados ruim na Fase 0 é substituída por uma reserva.

Resultado da Fase 0: as 7 bandas foram mantidas.

| Banda | Shows | % com setlist | Maior pausa (meses) |
|---|---|---|---|
| Metallica | 2.192 | 97,2% | 18 |
| Twenty One Pilots | 1.083 | 96,3% | 15 |
| Oasis | 958 | 93,0% | 193 |
| Arctic Monkeys | 1.095 | 92,4% | 42 |
| Linkin Park | 1.041 | 89,9% | 84 |
| Muse | 1.722 | 89,4% | 30 |
| Avenged Sevenfold | 1.408 | 75,3% | 59 |

Álbuns excluídos manualmente (classificação errada no MusicBrainz ou fora do escopo): shows do Oasis (Manchester 1994, Eden Project 2009), The Resistance Instrumentals (Muse), St. Louis 2009 (A7X) e Lulu (Metallica). Total: 59 álbuns de estúdio.

## 6. Stack

| Camada | Tecnologia |
|---|---|
| Ingestão | Python (requests/httpx), coleta incremental |
| Armazenamento | PostgreSQL 16 na VM Oracle (instância própria do Encore, bancos `encore` e `airflow`) |
| Transformação | dbt Core (staging, intermediate, marts) |
| Análise | Python (pandas, lifelines para Kaplan-Meier) |
| Orquestração | Apache Airflow (LocalExecutor), imagem arm64 com dbt-postgres |
| API | FastAPI na VM Oracle |
| Frontend | Site estático no Cloudflare Pages, subdomínio de alexarnoni.com |
| Infra | Docker Compose, seguindo o padrão do Astraea e do Olheiro |

## 7. Arquitetura

```
setlist.fm API ──┐
                 ├──> ingestão Python ──> PostgreSQL (raw)
MusicBrainz API ─┘                              │
                                                v
                                      dbt (staging > intermediate > marts)
                                                │
                                                v
                                     análises Python (sobrevivência, Jaccard)
                                                │
                                                v
                                    FastAPI ──> frontend (Cloudflare Pages)
```

### Política de dados (termos do setlist.fm)

- Execução periódica (ex: mensal) baixa o histórico completo das bandas (cerca de 475 requisições, dentro do limite diário).
- Dados brutos do setlist.fm ficam em área temporária apenas durante a execução e são apagados ao final.
- Apenas resultados agregados (por banda, turnê, álbum e música) são persistidos e publicados.
- O site não exibe setlists individuais; quando citar um show, linka para a página dele no setlist.fm.
- Dados do MusicBrainz (CC0) podem ser persistidos normalmente.
- O repositório não contém dados do setlist.fm, nem saídas de notebook com esses dados.

### Infraestrutura na VM

- VM Oracle ARM64 (aarch64), 4 núcleos, 23 GB de RAM; todas as imagens precisam de versão arm64
- Nginx no host faz o proxy reverso público
- Portas, todas publicadas só em 127.0.0.1: API 8003, Airflow 8080 (acesso por túnel SSH), PostgreSQL 5435

### Modelo de dados (marts)

- `dim_artist`
- `dim_album`
- `dim_song` (com ano de lançamento e álbum de referência)
- `dim_venue` (cidade, país)
- `dim_tour`
- `fct_show`
- `fct_setlist_entry` (show, música, posição, set, flag de bis, flag de cover)
- `mart_show_kpis`
- `mart_tour_kpis`
- `mart_song_survival`

## 8. Desafio de qualidade de dados

Casar nomes de músicas entre setlist.fm e MusicBrainz:
- Normalização (caixa, acentos, pontuação, "feat.", sufixos como "Remastered" ou "Live")
- Separação de medleys antes da normalização
- Numerais romanos e subtítulos (ex: "Exogenesis: Symphony Part 1 (Overture)" vs "Part I: Overture")
- Release representativo de cada álbum: número de faixas mais frequente entre os releases oficiais, data mais antiga
- Classificação de não-músicas (intros, jams, solos, vídeos) como tipo "não catálogo"
- Tabela de correspondência manual para casos não resolvidos
- Métrica de qualidade principal: % de execuções (ponderado por vezes tocadas) casadas com o catálogo, além do % de títulos distintos
- Relatório de taxa de correspondência por banda
- Testes dbt: unicidade, não nulos, relacionamentos, faixa de datas válida

## 9. Fases

### Fase 0: validação (notebook, antes do Kiro)
- Puxar setlists das bandas candidatas
- Medir shows por ano e % com setlist preenchido
- Testar correspondência de nomes com o MusicBrainz
- Decidir o recorte final

### Fase 1: ingestão
- Clientes das duas APIs com rate limit, retry e paginação
- Carga inicial completa e coleta incremental
- Tabelas raw no PostgreSQL

### Fase 2: modelagem
- Modelos dbt e testes
- Correspondência de músicas

### Fase 3: análise
- Cálculo dos KPIs
- Análise de sobrevivência e similaridade
- Notebook com achados por banda

### Fase 4: API e frontend
- Endpoints por banda, turnê e música
- Páginas por banda com os principais gráficos
- Página de metodologia (definições e cobertura dos dados)

### Fase 5: automação
- Coleta periódica para turnês em andamento
- Orquestração

## 10. Fora do escopo (v1)

- Dados de streaming ou vendas
- Letras de músicas
- Recomendações ou modelos preditivos
- Bandas além do recorte inicial

## 11. Critérios de sucesso

- Pipeline reproduzível do zero com um comando
- Todos os KPIs documentados com definição e grão
- Cobertura e limitações dos dados expostas na página de metodologia
- Pelo menos 3 achados concretos por banda, escritos em linguagem clara
- README explicando pergunta, método, resultados e arquitetura
