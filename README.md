# IA-Teddy

Este documento explica as decisões de projeto, a arquitetura e como executar, usar e testar esta aplicação.

Inicialmente, o plano era utilizar um LLM local (zephyr-7b-beta.Q4_K_M.gguf). Devido a limitações de hardware durante o desenvolvimento, optou-se por utilizar a API do Gemini para viabilizar a conclusão do projeto.

Aqui está a documentação do Gemini: https://ai.google.dev/gemini-api/docs

Para configurar o projeto, remova o '#' da variável de ambiente `GEMINI_API_KEY`. A chave fornecida é destinada exclusivamente para avaliação deste projeto.

## Tabela de Conteúdos

1.  [Arquitetura](#1-arquitetura)
2.  [Fluxo e Lógica da Aplicação](#2-fluxo-e-lógica-da-aplicação)
3.  [Como Executar o Projeto](#3-como-executar-o-projeto)
4.  [Como Usar a API](#4-como-usar-a-api)
5.  [Garantia de Qualidade e Testes](#5-garantia-de-qualidade-e-testes)
6.  [Como Parar a Aplicação](#6-como-parar-a-aplicação)
7.  [Próximos Passos e Melhorias Futuras](#7-próximos-passos-e-melhorias-futuras)

---

## 1. Arquitetura

Para garantir uma solução moderna, escalável e de fácil manutenção, foi adotada uma arquitetura de microsserviços containerizada com Docker. A API central, construída com FastAPI, orquestra todo o fluxo de trabalho.

O diagrama a seguir ilustra a conexão entre os componentes:
```mermaid
graph TD
    subgraph "Cliente"
        A[Usuário/Recrutador]
    end

    subgraph "Aplicação (Docker)"
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

### Componentes Principais:

*   **`FastAPI (app/main.py)`**: O FastAPI foi escolhido por sua alta performance, tipagem de dados com Pydantic e pela capacidade de gerar documentação interativa (Swagger) automaticamente. Ele é o coração do projeto, recebendo as requisições e coordenando as tarefas.
*   **`Módulo OCR (app/ocr.py)`**: Para extrair texto dos documentos, foi implementado um módulo que usa `easyocr` e `PyMuPDF`. A lógica primeiro tenta uma extração de texto nativa do PDF, que é mais rápida. Se isso não funcionar bem (em casos de PDFs escaneados), o sistema parte para o OCR, convertendo as páginas em imagens e extraindo o texto delas.
*   **`Módulo LLM (app/llm.py)`**: Este módulo serve como ponte para a inteligência artificial do Google. A decisão de usar a API do Gemini em vez de um modelo local tornou a aplicação mais leve. O módulo é responsável por fazer a "engenharia de prompt", ou seja, montar a pergunta certa para o Gemini e garantir que a resposta venha no formato JSON esperado.
*   **`Módulo de Storage (app/storage.py)`**: Para a persistência dos dados de auditoria, foi escolhido o MongoDB. Sua natureza NoSQL e schema flexível são ideais para armazenar os outputs do LLM, que podem variar. Este módulo gerencia a conexão e o salvamento dos logs.
*   **`Docker (Dockerfile, docker-compose.yml)`**: O Docker foi utilizado para empacotar a aplicação e suas dependências. Isso resolve o clássico "funciona na minha máquina", garantindo que qualquer pessoa com Docker possa rodar o projeto com um único comando, sem se preocupar com dependências.

---

## 2. Fluxo e Lógica da Aplicação

Quando uma requisição chega ao endpoint `/analyze`, este é o fluxo programado:

### Passo 1: Recepção e Validação (`app/main.py`)
O FastAPI recebe os arquivos e a `query` (se houver). Graças ao Pydantic, a validação dos tipos de dados é automática.

```python
# app/main.py: Ponto de entrada da API
@app.post("/analyze", ...)
async def analyze_resumes(
    files: List[UploadFile] = File(...),
    query: Optional[str] = Form(None),
    ...
):
    # ...
```

### Passo 2: Extração de Texto (`app/ocr.py`)
Para cada arquivo, o módulo de OCR é acionado. A função `process_file` decide se o arquivo é um PDF ou imagem e aplica a estratégia de extração correta.

```python
# app/ocr.py: Lógica de extração de texto
async def process_file(file_content: bytes, filename: str):
    if is_pdf(filename):
        return await process_pdf(file_content, filename)
    elif is_image(filename):
        return await process_image(file_content, filename)
```

### Passo 3: Engenharia de Prompt e Chamada ao Gemini (`app/llm.py`)
Esta é a parte mais inteligente do sistema. Com o texto em mãos, o código decide qual prompt construir:
*   **Modo Ranking (com `query`)**: Um prompt é montado pedindo ao Gemini para atuar como um recrutador e avaliar o currículo com base na `query`, retornando uma pontuação (`score`) e uma `justification`.
*   **Modo Sumarização (sem `query`)**: É solicitado ao Gemini que extraia os dados mais importantes do currículo.

A diretiva mais crítica adicionada ao prompt foi: **"Return ONLY a valid JSON object"**. Isso força a IA a retornar uma resposta estruturada, evitando a necessidade de analisar texto livre e imprevisível.

```python
# app/llm.py: Interação com a IA
async def evaluate_resume(resume_text: str, query: str, file_name: str):
    prompt = f"""
    You are a specialized recruitment assistant...
    Evaluate the following resume in relation to the specified query/job role.
    ...
    Return ONLY a valid JSON object...
    """
    # A função _call_gemini_api cuida do envio para o Google
    result = await _call_gemini_api(prompt)
```
`httpx` é utilizado para fazer a chamada à API do Gemini de forma assíncrona, uma boa prática para não bloquear a aplicação enquanto se espera por uma resposta externa.

### Passo 4: Resposta Final e Log (`app/main.py` e `app/storage.py`)
Após receber a resposta estruturada do Gemini, o endpoint `/analyze` a formata na resposta final para o usuário. Como última etapa, um registro de log (`LogEntry`) é criado e salvo no MongoDB para fins de auditoria.

```python
# app/storage.py: Função para salvar os logs
async def save_log(log_entry: LogEntry):
    log_dict = log_entry.model_dump()
    db.logs.insert_one(log_dict)
```

---

## 3. Como Executar o Projeto

Para rodar o projeto, siga os passos abaixo.

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
O `docker-compose.yml` foi configurado para que toda a stack seja iniciada com um único comando:
```bash
docker-compose up --build -d
```
*   `--build`: Garante que a imagem Docker seja reconstruída com as últimas alterações.
*   `-d`: Roda os contêineres em segundo plano.

---

## 4. Como Usar a API

Após a inicialização, a API pode ser utilizada de duas formas principais.

### Pela Documentação Interativa (Swagger)
Esta é a forma mais fácil. O FastAPI foi configurado para gerar uma documentação rica e interativa.
1.  Abra seu navegador e acesse: **[http://localhost:8000/docs](http://localhost:8000/docs)**
2.  Expanda o endpoint `/analyze` e clique em **"Try it out"**.
3.  Preencha os campos (faça o upload dos arquivos, adicione uma `query` se quiser) e clique em **"Execute"**. Você verá a requisição e a resposta em tempo real.

### Pela Linha de Comando (cURL)
Para quem prefere a linha de comando, pode-se usar o `curl`.
**Exemplo de Ranking:**
```bash
curl -X 'POST' 'http://localhost:8000/analyze' -F 'files=@/caminho/curriculo1.pdf' -F 'query=Desenvolvedor Python com experiência em AWS'
```

---

## 5. Garantia de Qualidade e Testes

Para garantir o funcionamento esperado, foi criado um conjunto de testes de integração no arquivo `app/__tet/test_integracao.py`. Estes não são testes unitários; eles testam o fluxo completo da aplicação.

Para executá-los, basta rodar o seguinte comando após subir a aplicação com `docker-compose`:
```bash
python3 app/__tet/test_integracao.py
```

A seguir, a descrição do que cada teste verifica:

*   `test_verificar_variaveis_ambiente()`: Garante que o ambiente está configurado corretamente, checando se a `GEMINI_API_KEY` foi carregada a partir do arquivo `.env`.
*   `test_verificar_cvs()`: Verifica se os arquivos de currículo para os testes realmente existem no diretório `recursos/`.
*   `test_fastapi_online()`: Um teste de sanidade. Faz uma requisição para a página de documentação (`/docs`) para confirmar que o servidor FastAPI está no ar e respondendo.
*   `test_conexao_mongodb()`: Testa a conexão com o MongoDB inserindo e deletando um documento de teste. Isso garante que a comunicação com o banco de dados está funcional.
*   `test_fluxo_completo_cv_sumario()`: Primeiro teste de ponta a ponta. Simula o envio de múltiplos CVs **sem uma query** e verifica se a API retorna um status 200, e se a resposta contém a chave `"summaries"` com um resumo para cada CV enviado.
*   `test_fluxo_completo_cv_ranking()`: Segundo teste de ponta a ponta. Envia os mesmos CVs, mas desta vez **com uma query**, e valida se a resposta contém a chave `"ranking"` e se cada item no ranking possui `score` e `justification`.

A passagem de todos os testes indica uma alta confiança na integração e no funcionamento correto dos componentes da aplicação.

---

## 6. Como Parar a Aplicação

Para parar e remover os contêineres criados pelo Docker Compose, use o comando:
```bash
docker-compose down
```

---

## 7. Próximos Passos e Melhorias Futuras

Embora a solução atual seja robusta e funcional, alguns pontos podem ser aprimorados em futuras iterações para tornar o sistema ainda mais poderoso, escalável e amigável.

### Execução de LLM Local (Self-Hosting)
Conforme mencionado, a decisão de usar a API do Gemini foi um contorno para limitações de hardware. Uma melhoria significativa seria integrar um LLM de código aberto (como Llama 3, Mixtral ou Phi-3) para ser executado localmente dentro de um contêiner Docker.
*   **Benefícios**: Maior privacidade dos dados (os CVs não saem da infraestrutura), ausência de custos por chamada de API e controle total sobre o modelo.
*   **Desafios**: Exigiria um ambiente com hardware mais robusto (especialmente GPU) e um gerenciamento mais complexo do ciclo de vida do modelo.

### Frontend Interativo
A interação via Swagger UI é ótima para desenvolvedores, mas um usuário final (como um recrutador) se beneficiaria de uma interface gráfica dedicada. Um frontend simples poderia ser construído com Streamlit ou um mais elaborado com React/Vue.js. Isso permitiria:
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
A extração de texto atual é eficaz, mas não entende a estrutura do documento. Poderiam ser empregados modelos de `Document AI` (como o LayoutLM da Microsoft) para realizar uma análise de layout. Isso permitiria extrair informações de forma estruturada (ex: "seção de experiência", "lista de habilidades") antes mesmo de enviar ao LLM, resultando em prompts mais precisos e respostas de maior qualidade.

### Cobertura de Testes Ampliada
Atualmente, o projeto conta com testes de integração que validam o fluxo completo. Para aumentar a confiabilidade e facilitar a manutenção, seria interessante adicionar **testes unitários** para cada módulo (`ocr.py`, `llm.py`, `storage.py`). Isso permitiria testar a lógica de cada componente de forma isolada, capturando bugs mais cedo no ciclo de desenvolvimento.

### Observabilidade e Monitoramento
Para um ambiente de produção, é crucial entender o que está acontecendo. Um stack de observabilidade poderia ser implementado, por exemplo:
*   **Logs Estruturados**: Para facilitar a busca e análise.
*   **Métricas com Prometheus**: Para monitorar a latência da API, taxa de erros, uso de recursos dos contêineres, etc.
*   **Tracing com OpenTelemetry**: Para seguir uma requisição através de todos os microsserviços e identificar gargalos.
