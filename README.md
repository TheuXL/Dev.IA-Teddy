# IA-Teddy

Vou explicar as decisões que tomei, a arquitetura que desenhei e como você pode executar, usar e testar esta aplicação.

Infelizmente, devido a problemas no meu PC, não consegui executar o LLM localmente. Para contornar essa limitação, decidi utilizar a API do Gemini e assim conseguir completar o desafio. Anteriormente, eu estava utilizando o modelo zephyr-7b-beta.Q4_K_M.gguf localmente.

Aqui está a documentação do Gemini: https://ai.google.dev/gemini-api/docs

Remova o '#' da variável 'GEMINI_API_KEY=AIzaSyDwPGLA3aoeWn-kA3HU80pkmyL9mVWYB4o'. Esta API é exclusivamente destinada a este teste e não funcionará em outro contexto.

## Tabela de Conteúdos

1.  [A Arquitetura que Eu Desenhei](#1-a-arquitetura-que-eu-desenhei)
2.  [O Fluxo e a Lógica que Implementei](#2-o-fluxo-e-a-lógica-que-implementei)
3.  [Como Executar o Projeto](#3-como-executar-o-projeto)
4.  [Como Usar a Minha API](#4-como-usar-a-minha-api)
5.  [Como Eu Garanto a Qualidade: Os Testes](#5-como-eu-garanto-a-qualidade-os-testes)
6.  [Como Parar a Aplicação](#6-como-parar-a-aplicação)
7.  [Próximos Passos e Melhorias Futuras](#7-próximos-passos-e-melhorias-futuras)

---

## 1. A Arquitetura que Eu Desenhei

Para garantir que a solução fosse moderna, escalável e fácil de manter, eu optei por uma arquitetura de microsserviços containerizada com Docker. A API central, que eu construí com FastAPI, orquestra todo o fluxo de trabalho.

Aqui está um diagrama que ilustra como os componentes que eu criei se conectam:
```mermaid
graph TD
    subgraph "Cliente"
        A[Usuário/Recrutador]
    end

    subgraph "Minha Aplicação (Docker)"
        B[FastAPI: /analyze]
        C[Módulo OCR]
        D[Módulo LLM/Gemini]
        E[Módulo de Storage]
    end
    
    subgraph "Serviços Externos"
        F[Google Gemini API]
        G[MongoDB]
    end

    A -- Upload de CVs + Query --> B
    B -- Bytes do arquivo --> C
    C -- Texto extraído --> B
    B -- Texto + Prompt --> D
    D -- Requisição HTTP --> F
    F -- Resposta JSON --> D
    D -- Dados estruturados --> B
    B -- Log da operação --> E
    E -- Salva no --> G
    B -- Resposta final (JSON) --> A
```

### Meus Componentes Principais:

*   **`FastAPI (app/main.py)`**: Escolhi o FastAPI pela sua alta performance, tipagem de dados com Pydantic e, principalmente, pela sua capacidade de gerar documentação interativa (Swagger) automaticamente. Ele é o coração do meu projeto, recebendo as requisições e coordenando as tarefas.
*   **`Módulo OCR (app/ocr.py)`**: Para extrair texto dos documentos, implementei um módulo que usa `easyocr` e `PyMuPDF`. A minha lógica primeiro tenta uma extração de texto nativa do PDF, que é mais rápida. Se isso não funcionar bem (em casos de PDFs escaneados), eu parto para o OCR, convertendo as páginas em imagens e extraindo o texto delas.
*   **`Módulo LLM (app/llm.py)`**: Este módulo é a minha ponte para a inteligência artificial do Google. Decidi usar a API do Gemini em vez de um modelo local para tornar a aplicação mais leve e poderosa. O módulo é responsável por fazer a "engenharia de prompt", ou seja, montar a pergunta certa para o Gemini e garantir que a resposta venha no formato JSON que eu preciso.
*   **`Módulo de Storage (app/storage.py)`**: Para a persistência dos dados de auditoria, escolhi o MongoDB. Sua natureza NoSQL e schema flexível são ideais para armazenar os outputs do LLM, que podem variar ou evoluir. Ele se alinha perfeitamente com a natureza de dados em JSON da aplicação. Este módulo gerencia a conexão e o salvamento dos logs.
*   **`Docker (Dockerfile, docker-compose.yml)`**: Eu usei o Docker para empacotar tudo. Isso resolve o clássico "funciona na minha máquina", garantindo que qualquer pessoa com Docker possa rodar o projeto com um único comando, sem se preocupar com dependências.

---

## 2. O Fluxo e a Lógica que Implementei

Quando uma requisição chega ao endpoint `/analyze`, este é o fluxo que eu programei:

### Passo 1: Recepção e Validação (`app/main.py`)
O FastAPI recebe os arquivos e a `query` (se houver). Graças ao Pydantic, a validação dos tipos de dados é automática.

```python
# app/main.py: Onde tudo começa
@app.post("/analyze", ...)
async def analyze_resumes(
    files: List[UploadFile] = File(...),
    query: Optional[str] = Form(None),
    ...
):
    # ...
```

### Passo 2: Extração de Texto (`app/ocr.py`)
Para cada arquivo, eu chamo meu módulo de OCR. A função `process_file` é a porta de entrada que decide se o arquivo é um PDF ou imagem e aplica a estratégia de extração correta.

```python
# app/ocr.py: Minha lógica de extração
async def process_file(file_content: bytes, filename: str):
    if is_pdf(filename):
        return await process_pdf(file_content, filename)
    elif is_image(filename):
        return await process_image(file_content, filename)
```

### Passo 3: Engenharia de Prompt e Chamada ao Gemini (`app/llm.py`)
Esta é a parte mais inteligente do sistema. Com o texto em mãos, meu código decide qual prompt construir:
*   **Modo Ranking (com `query`)**: Eu monto um prompt pedindo ao Gemini para atuar como um recrutador e avaliar o currículo com base na `query`, retornando uma pontuação (`score`) e uma `justification`.
*   **Modo Sumarização (sem `query`)**: Eu peço ao Gemini para extrair os dados mais importantes do currículo.

A diretiva mais crítica que eu adicionei ao prompt foi: **"Return ONLY a valid JSON object"**. Isso força a IA a me dar uma resposta estruturada, evitando que eu tenha que lidar com texto livre e imprevisível.

```python
# app/llm.py: Onde eu "converso" com a IA
async def evaluate_resume(resume_text: str, query: str, file_name: str):
    prompt = f"""
    You are a specialized recruitment assistant...
    Evaluate the following resume in relation to the specified query/job role.
    ...
    Return ONLY a valid JSON object...
    """
    # A função _call_gemini_api que criei cuida do envio para o Google
    result = await _call_gemini_api(prompt)
```
Eu uso `httpx` para fazer a chamada à API do Gemini de forma assíncrona, o que é uma boa prática para não bloquear a aplicação enquanto se espera por uma resposta externa.

### Passo 4: Resposta Final e Log (`app/main.py` e `app/storage.py`)
Após receber a resposta estruturada do Gemini, o endpoint `/analyze` a formata na resposta final para o usuário. Como última etapa, eu crio um registro de log (`LogEntry`) e o salvo no MongoDB para fins de auditoria.

```python
# app/storage.py: Minha função para salvar os logs
async def save_log(log_entry: LogEntry):
    log_dict = log_entry.model_dump()
    db.logs.insert_one(log_dict)
```

---

## 3. Como Executar o Projeto

Para rodar o projeto que criei, você só precisa seguir estes passos.

### Pré-requisitos
*   [Docker](https://www.docker.com/get-started)
*   [Docker Compose](https://docs.docker.com/compose/install/)

### Passo 1: Clonar o Repositório
```bash
git clone <repository-url>
cd Dev.IA-Teddy
```

### Passo 2: Configurar a Chave da API do Gemini
1.  Crie um arquivo `.env` na raiz do projeto:
    ```bash
    touch .env
    ```
2.  Abra este arquivo e adicione sua chave:
    ```
    GEMINI_API_KEY=sua_chave_de_api_do_gemini_aqui
    ```

### Passo 3: Construir e Executar
Eu configurei o `docker-compose.yml` para que tudo suba com um único comando:
```bash
docker-compose up --build -d
```
*   `--build`: Garante que a imagem Docker seja reconstruída com as minhas últimas alterações.
*   `-d`: Roda os contêineres em segundo plano.

---

## 4. Como Usar a Minha API

Após a inicialização, você pode interagir com a API de duas formas principais.

### Pela Documentação Interativa (Swagger)
Esta é a forma mais fácil. Eu configurei o FastAPI para gerar uma documentação rica e interativa.
1.  Abra seu navegador e acesse: **[http://localhost:8000/docs](http://localhost:8000/docs)**
2.  Expanda o endpoint `/analyze` e clique em **"Try it out"**.
3.  Preencha os campos (faça o upload dos arquivos, adicione uma `query` se quiser) e clique em **"Execute"**. Você verá a requisição e a resposta em tempo real.

### Pela Linha de Comando (cURL)
Se você preferir a linha de comando, pode usar o `curl`.
**Exemplo de Ranking:**
```bash
curl -X 'POST' 'http://localhost:8000/analyze' -F 'files=@/caminho/curriculo1.pdf' -F 'query=Desenvolvedor Python com experiência em AWS'
```

---

## 5. Como Eu Garanto a Qualidade: Os Testes

Para garantir que tudo funcione como esperado, eu criei um conjunto de testes de integração no arquivo `app/__tet/test_integracao.py`. Esses não são testes unitários; eles testam o fluxo completo da aplicação.

Para executá-los, basta rodar o seguinte comando após subir a aplicação com `docker-compose`:
```bash
python3 app/__tet/test_integracao.py
```

Aqui está o que cada teste que eu criei verifica:

*   `test_verificar_variaveis_ambiente()`: O primeiro passo é garantir que o ambiente está configurado corretamente. Este teste simplesmente checa se a `GEMINI_API_KEY` foi carregada a partir do arquivo `.env`.
*   `test_verificar_cvs()`: Eu verifico se os arquivos de currículo que uso para os testes realmente existem no diretório `recursos/`.
*   `test_fastapi_online()`: Um teste de sanidade. Ele faz uma requisição para a página de documentação (`/docs`) para confirmar que o servidor FastAPI está no ar e respondendo.
*   `test_conexao_mongodb()`: Eu testo a conexão com o MongoDB inserindo e deletando um documento de teste. Isso garante que a comunicação com o banco de dados está funcional.
*   `test_fluxo_completo_cv_sumario()`: Este é o primeiro teste de ponta a ponta. Eu simulo o envio de múltiplos CVs **sem uma query**. Então, verifico se a API retorna um status 200 e se a resposta contém a chave `"summaries"` com um resumo para cada CV enviado.
*   `test_fluxo_completo_cv_ranking()`: O segundo teste de ponta a ponta. Aqui, eu envio os mesmos CVs, mas desta vez **com uma query**. Eu valido se a resposta contém a chave `"ranking"` e se cada item no ranking possui `score` e `justification`, como esperado.

Se todos esses testes passarem, eu tenho uma alta confiança de que todos os componentes da minha aplicação estão integrados e funcionando corretamente.

---

## 6. Como Parar a Aplicação

Para parar e remover os contêineres que foram criados pelo Docker Compose, eu uso o comando:
```bash
docker-compose down
```

---

## 7. Próximos Passos e Melhorias Futuras

Embora a solução atual seja robusta e funcional, eu identifiquei vários pontos que poderiam ser aprimorados em futuras iterações para tornar o sistema ainda mais poderoso, escalável e amigável.

### Execução de LLM Local (Self-Hosting)
Como mencionei, a decisão de usar a API do Gemini foi um contorno para limitações de hardware. Uma melhoria significativa seria integrar um LLM de código aberto (como Llama 3, Mixtral ou Phi-3) para ser executado localmente dentro de um contêiner Docker.
*   **Benefícios**: Maior privacidade dos dados (os CVs não saem da sua infraestrutura), ausência de custos por chamada de API e controle total sobre o modelo.
*   **Desafios**: Exigiria um ambiente com hardware mais robusto (especialmente GPU) e um gerenciamento mais complexo do ciclo de vida do modelo.

### Frontend Interativo
A interação via Swagger UI é ótima para desenvolvedores, mas um usuário final (como um recrutador) se beneficiaria de uma interface gráfica dedicada. Eu poderia construir um frontend simples com Streamlit ou um mais elaborado com React/Vue.js. Isso permitiria:
*   Upload de arquivos com drag-and-drop.
*   Visualização clara e formatada dos rankings e resumos.
*   Filtros, ordenação e busca nos resultados.

### Processamento Assíncrono em Larga Escala
O endpoint `/analyze` atualmente processa os currículos em tempo real. Para um grande volume de documentos, isso pode levar a timeouts. A arquitetura ideal para isso seria:
1.  O endpoint recebe os arquivos e os coloca em uma fila de tarefas (usando Celery com Redis ou RabbitMQ).
2.  Retorna imediatamente um ID de tarefa para o cliente.
3.  *Workers* em segundo plano consomem a fila, processam os CVs e salvam o resultado no banco de dados.
4.  O cliente pode consultar o status da tarefa usando o ID.

### Inteligência de OCR Avançada
A extração de texto atual é eficaz, mas não entende a estrutura do documento. Eu poderia empregar modelos de `Document AI` (como o LayoutLM da Microsoft) para realizar uma análise de layout. Isso permitiria extrair informações de forma estruturada (ex: "seção de experiência", "lista de habilidades") antes mesmo de enviar ao LLM, resultando em prompts mais precisos e respostas de maior qualidade.

### Cobertura de Testes Ampliada
Atualmente, o projeto conta com testes de integração que validam o fluxo completo. Para aumentar a confiabilidade e facilitar a manutenção, eu adicionaria **testes unitários** para cada módulo (`ocr.py`, `llm.py`, `storage.py`). Isso permitiria testar a lógica de cada componente de forma isolada, capturando bugs mais cedo no ciclo de desenvolvimento.

### Observabilidade e Monitoramento
Para um ambiente de produção, é crucial entender o que está acontecendo sob o capô. Eu implementaria um stack de observabilidade, por exemplo:
*   **Logs Estruturados**: Para facilitar a busca e análise.
*   **Métricas com Prometheus**: Para monitorar a latência da API, taxa de erros, uso de recursos dos contêineres, etc.
*   **Tracing com OpenTelemetry**: Para seguir uma requisição através de todos os microsserviços e identificar gargalos.
