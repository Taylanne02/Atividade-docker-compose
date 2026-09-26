# Defesa- Explicação Técnica

A atividade realizada é um sistema de upload e gerenciamento de arquivos desenvolvido com Django, containerizado com Docker Compose, composto por três serviços: **Django (Gunicorn)**, **Nginx (proxy reverso)** e **PostgreSQL**.

---

## Sumário

1. [Visão geral da arquitetura](#1-visão-geral-da-arquitetura)
2. [Imagem Docker da aplicação Django](#2-imagem-docker-da-aplicação-django)
3. [Orquestração com Docker Compose](#3-orquestração-com-docker-compose)
4. [Comunicação entre os containers](#4-comunicação-entre-os-containers)
5. [Nginx e proxy reverso](#5-nginx-e-proxy-reverso)
6. [Persistência de dados](#6-persistência-de-dados)
7. [Fluxo do upload de um arquivo](#7-fluxo-do-upload-de-um-arquivo)
8. [Análise técnica da solução](#8-análise-técnica-da-solução)
9. [Como executar o projeto](#9-como-executar-o-projeto)

---

## 1. Visão geral da arquitetura

A aplicação é composta por três containers, cada um com uma responsabilidade específica, comunicando-se através de uma rede Docker interna criada pelo Docker Compose.

### Diagrama de implantação 

```
                         PORTA 8000 (exposta no host)
                                    │
   ┌────────────┐                   │
   │  Cliente   │ ──────────────────┤
   │ (Navegador)│   http://localhost:8000
   └────────────┘                   │
                                    ▼
┌──────────────────────────────────────────────────────────────┐
│                    REDE DOCKER: app_network                  │
│                      (driver: bridge)                        │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐     │
│  │ Container: django-nginx        Imagem: nginx:alpine │     │
│  │ Porta interna: 80              Porta exposta: 8000  │     │
│  │                                                     │     │
│  │  • Recebe requisições HTTP                          │     │
│  │  • Serve /static/ e /media/ direto (arquivos)       │     │
│  │  • Encaminha o resto para o Django (proxy reverso)  │     │
│  └──────────────────────┬──────────────────────────────┘     │
│                         │ proxy_pass                         │
│                         │ http://web:8000                    │
│                         ▼                                    │
│  ┌─────────────────────────────────────────────────────┐     │
│  │ Container: django-web         Imagem: build (Dockerfile)  │
│  │ Porta interna: 8000 (expose, não publicada)         │     │
│  │                                                     │     │
│  │  • Django 6.1 + Gunicorn (servidor WSGI)            │     │
│  │  • Processa upload e salva arquivo em /app/media    │     │
│  │  • Consulta/grava dados no PostgreSQL               │     │
│  └───────────┬────────────────────────────┬────────────┘     │
│              │                            │                   │
│              │ volumes                    │ TCP 5432          │
│              │ (media_data,               │ (host: db)        │
│              │  static_data)              ▼                   │
│              │              ┌─────────────────────────────┐   │
│              ▼              │ Container: django-db        │   │
│  ┌────────────────────┐     │ Imagem: postgres:16-alpine  │   │
│  │ VOLUMES DO DOCKER  │     │ Porta interna: 5432         │   │
│  │                    │     │                             │   │
│  │ • media_data       │     │  • Banco de dados           │   │
│  │   (uploads) ───────┼─────┼──► /var/lib/postgresql/data │   │
│  │ • static_data      │     │     (volume postgres_data)  │   │
│  │   (estáticos) ─────┼─┐   └─────────────────────────────┘   │
│  │ • postgres_data ───┼─┼─────────────▲                       │
│  │   (banco)          │ │             │                       │
│  └────────────────────┘ │             │                       │
│                         │             │                       │
└─────────────────────────┼─────────────┼───────────────────────┘
                          │             │
                          ▼             ▼
              DADOS PERSISTENTES NO HOST
        (sobrevivem à remoção dos containers)
```

## 2. Imagem Docker da aplicação Django

A imagem da aplicação é construída a partir do arquivo `Dockerfile`, presente na raiz do projeto.

```dockerfile
FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY app/ .

RUN mkdir -p /app/media /app/staticfiles

EXPOSE 8000

CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000"]
```

### Explicação de cada decisão

**`FROM python:3.12-slim` — imagem base**
É a partir daqui que a imagem é construída. Foi usada a versão 3.12 porque é compatível com o Django 6.1 instalado no projeto. A variante `slim` é uma versão reduzida da imagem oficial (base Debian sem ferramentas de compilação e pacotes desnecessários), o que deixa a imagem final menor e com menos superfície de ataque, sem perder nada que a aplicação precise — basta ter o `pip` para instalar as dependências.

**`WORKDIR /app` — diretório de trabalho**
Define que todo comando seguinte será executado dentro da pasta `/app` dentro do container. É como um "cd permanente": evita criar caminhos absolutos longos e mantém o código organizado em um único lugar.

**`ENV PYTHONDONTWRITEBYTECODE=1` e `ENV PYTHONUNBUFFERED=1` — variáveis de ambiente**
- `PYTHONDONTWRITEBYTECODE=1` impede que o Python gere arquivos `.pyc` (cache de compilação). Em containers, esses arquivos não trazem benefício e só ocupam espaço.
- `PYTHONUNBUFFERED=1` força a saída do Python (print, logs) a aparecer imediatamente, sem ficar guardada em buffer. Assim, `docker compose logs` mostra os eventos em tempo real.

**`COPY requirements.txt .` + `RUN pip install --no-cache-dir -r requirements.txt` — instalação das dependências**
Primeiro é copiado apenas o arquivo de dependências e depois instalado, antes de copiar o código da aplicação. Isso aproveita o cache de camadas do Docker, enquanto o `requirements.txt` não mudar, essa camada, que demora mais para ser construída, é reaproveitada nas próximas builds. 

- `--no-cache-dir` descarta o cache do `pip` dentro da imagem, reduzindo o tamanho final.
- Dependências instaladas (ver `requirements.txt`): `Django`, `gunicorn`, `psycopg2-binary` (driver de conexão com o PostgreSQL), `asgiref` e `sqlparse` (dependências do próprio Django).

**`COPY app/ .` — organização dos arquivos**
Copia o conteúdo da pasta `app/` para dentro de `/app` no container. A estrutura resultante é:

```
/app/
├── manage.py
├── config/      (settings.py, urls.py, wsgi.py, asgi.py)
└── arquivos/    (models.py, views.py, templates/, migrations/)
```

**`RUN mkdir -p /app/media /app/staticfiles` — criação dos diretórios**
Cria as pastas que receberão os arquivos enviados pelos usuários (`media`) e os arquivos estáticos coletados (`staticfiles`). O `mkdir -p` não falha se a pasta já existir. Criar aqui garante que os diretórios existam mesmo antes de os volumes serem montados.

**`EXPOSE 8000` — documentação da porta**
Declara que a aplicação usa a porta 8000 internamente. Não publica a porta no host, isso é feito no `docker-compose.yml`. 

**`CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000"]` — inicialização**
Comando padrão executado quando o container inicia:
- `gunicorn` — servidor WSGI para produção, que substitui o servidor de desenvolvimento do Django. Ele é mais performático, lida com múltiplas requisições simultâneas e é adequado para ambientes reais.
- `config.wsgi:application` — módulo WSGI do projeto (`config/wsgi.py`), porta de entrada do Django para servidores WSGI.
- `--bind 0.0.0.0:8000` — escuta em todas as interfaces de rede do container na porta 8000. O `0.0.0.0` é essencial, pois se fosse `127.0.0.1`, o Gunicorn só aceitaria conexões vindas de dentro do próprio container e o Nginx não conseguiria alcançá-lo.

> **Por que o Gunicorn e não o `runserver` do Django?** O `runserver` é um servidor de desenvolvimento: single-thread por padrão, sem tratamento adequado de erros e explicitamente documentado pelo Django como não apto para produção. O Gunicorn é o padrão da comunidade Python para produção.

---

## 3. Orquestração com Docker Compose

O arquivo `docker-compose.yml` declara os três serviços, os volumes, a rede e as dependências entre eles. Ele é o roteiro que o Docker Compose executa com um único comando.

```yaml
services:
  web:
    build: .
    container_name: django-web
    command: gunicorn config.wsgi:application --bind 0.0.0.0:8000
    volumes:
      - media_data:/app/media
      - static_data:/app/staticfiles
    expose:
      - "8000"
    environment:
      POSTGRES_DB: arquivosdb
      POSTGRES_USER: django
      POSTGRES_PASSWORD: django123
      POSTGRES_HOST: db
      POSTGRES_PORT: "5432"
    depends_on:
      db:
        condition: service_healthy
    networks:
      - app_network

  nginx:
    image: nginx:alpine
    container_name: django-nginx
    ports:
      - "8000:80"
    volumes:
      - ./nginx/default.conf:/etc/nginx/conf.d/default.conf:ro
      - media_data:/app/media:ro
      - static_data:/app/staticfiles:ro
    depends_on:
      - web
    networks:
      - app_network

  db:
    image: postgres:16-alpine
    container_name: django-db
    environment:
      POSTGRES_DB: arquivosdb
      POSTGRES_USER: django
      POSTGRES_PASSWORD: django123
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U django -d arquivosdb"]
      interval: 5s
      timeout: 5s
      retries: 10
    networks:
      - app_network

volumes:
  media_data:
  static_data:
  postgres_data:

networks:
  app_network:
    driver: bridge
```

### Serviço `web` — aplicação Django

| Propriedade | Valor | Responsabilidade |
|---|---|---|
| `build: .` | Constrói a imagem do `Dockerfile` local | Não usa imagem pronta: a aplicação é nossa |
| `command` | `gunicorn config.wsgi:application --bind 0.0.0.0:8000` | Sobrepõe o `CMD` do Dockerfile (mesmo efeito, mantido para clareza) |
| `volumes` | `media_data:/app/media`, `static_data:/app/staticfiles` | Persiste uploads e estáticos |
| `expose: "8000"` | Só declara a porta interna | Não publica no host, o tráfego só chega pelo Nginx |
| `environment` | Variáveis do banco | Configuram a conexão com o PostgreSQL (lidas pelo `settings.py` via `os.getenv`) |
| `depends_on` | `condition: service_healthy` | Só inicia depois que o banco passar no healthcheck |
| `networks` | `app_network` | Entra na rede compartilhada |

### Serviço `nginx` — proxy reverso

| Propriedade | Valor | Responsabilidade |
|---|---|---|
| `image: nginx:alpine` | Imagem oficial em base Alpine | Imagem pronta e leve, não precisa de build |
| `ports: "8000:80"` | Host 8000 → container 80 | Única porta pública da solução |
| `./nginx/default.conf:...:ro` | Config montada em modo somente leitura | O Nginx lê a config do projeto; `:ro` impede alteração de dentro do container |
| `media_data:/app/media:ro` | Volume de uploads montado como somente leitura | O Nginx serve os arquivos, nunca os altera |
| `static_data:/app/staticfiles:ro` | Volume de estáticos somente leitura | Idem |
| `depends_on: web` | Espera o Django subir | Ordem de inicialização |

### Serviço `db` — PostgreSQL

| Propriedade | Valor | Responsabilidade |
|---|---|---|
| `image: postgres:16-alpine` | PostgreSQL 16 em base Alpine | Versão estável e leve |
| `environment` | `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | Cria o banco e o usuário no primeiro boot |
| `volumes` | `postgres_data:/var/lib/postgresql/data` | Persistência dos dados do banco |
| `healthcheck` | `pg_isready` a cada 5s, 10 tentativas | Verifica se o banco está aceitando conexões |

### Política de inicialização (ordem de subida)

A ordem é controlada por `depends_on` + `healthcheck`:

1. **`db`** sobe primeiro e passa a responder `pg_isready` (healthcheck OK).
2. **`web`** só é iniciado depois (`condition: service_healthy`) — assim o Django não tenta conectar em um banco que ainda não está pronto.
3. **`nginx`** sobe por último, esperando o `web`.

### Volumes e rede declarados

```yaml
volumes:        # volumes nomeados, persistidos pelo Docker
  media_data:       → uploads dos usuários
  static_data:      → arquivos estáticos coletados
  postgres_data:    → dados do PostgreSQL

networks:
  app_network:      # rede bridge privada do projeto
    driver: bridge
```

---

## 4. Comunicação entre os containers

### Como os containers se encontram

Quando o Docker Compose cria a rede `app_network` (driver `bridge`), ele também cria um **DNS interno**: cada serviço passa a ser resolvível pelo **nome do serviço** definido no `docker-compose.yml`.

```
Nome do serviço     →    Endereço IP interno (atribuído dinamicamente)
    web             →    172.18.0.3   (exemplo)
    nginx           →    172.18.0.2   (exemplo)
    db              →    172.18.0.4   (exemplo)
```

Não é preciso decorar IP, basta usar o nome do serviço como hostname. Por isso, as configurações usam `web`, `db` e não endereços IP, que mudariam a cada reinicialização.

### Nginx → Django/Gunicorn

```nginx
proxy_pass http://web:8000;
```

- O Nginx resolve `web` via DNS interno da rede `app_network`.
- Conecta na porta 8000 interna do container `django-web`.
- Essa porta está declarada com `expose` (visível só dentro da rede) e não com `ports`, que a publicaria no host, ou seja, o Gunicorn é alcançável apenas pelo Nginx, nunca diretamente de fora.

```
nginx (porta 80)  -> HTTP ->  web:8000 (Gunicorn)     [rede interna]
```

### Django → PostgreSQL

```python
# app/config/settings.py
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME":     os.getenv("POSTGRES_DB", "arquivosdb"),
        "USER":     os.getenv("POSTGRES_USER", "django"),
        "PASSWORD": os.getenv("POSTGRES_PASSWORD", "django123"),
        "HOST":     os.getenv("POSTGRES_HOST", "db"),   # <- nome do serviço
        "PORT":     os.getenv("POSTGRES_PORT", "5432"),
    }
}
```

- O valor de `HOST` vem da variável `POSTGRES_HOST: db` definida no `docker-compose.yml`.
- `db` é o nome do serviço no Compose, resolvido pelo DNS interno, conecta na porta 5432 do container do banco.
- A porta 5432 não está em `ports`, logo é inacessível de fora da rede `app_network`.

```
web (Django)  -> TCP 5432 ->  db:5432 (PostgreSQL)     [rede interna]
```

### Portas internas x externas

| Serviço | Porta interna | Porta pública | Quem acessa |
|---|---|---|---|
| nginx | 80 | **8000** (`ports: "8000:80"`) | Cliente (host) |
| web | 8000 (`expose`) | nenhuma | Somente o Nginx |
| db | 5432 (`nenhuma declaração`) | nenhuma | Somente o Django |

> **Regra prática:** `ports` = abre para o mundo; `expose` = só documenta a porta dentro da rede; nada declarado = visível apenas na rede do Compose (que é o caso da porta 5432, protegida por estar fora de `ports`).

---

## 5. Nginx e proxy reverso

### Papel do Nginx na arquitetura

O Nginx é a porta de entrada única da solução. Toda requisição chega primeiro nele, que decide o destino:

1. **Arquivos estáticos** (`/static/`, `/media/`) -> ele mesmo serve, direto dos volumes, sem gastar o Django.
2. **Demais requisições** (`/`, `/admin/`) -> encaminha para o Django via `proxy_pass`.

Isso é o proxy reverso, um intermediário que recebe pedidos do cliente e os repassa para o servidor de aplicação, que fica escondido atrás da rede interna.

```
Cliente ──► Nginx ──┬── /static/ e /media/ → serve direto (volumes)
                    └── /qualquer-coisa    → proxy_pass → web:8000
```

### Configuração utilizada (`nginx/default.conf`)

```nginx
server {
    listen 80;                          # Escuta na porta 80 (interna do container)

    location /static/ {                 # Requisições a arquivos estáticos
        alias /app/staticfiles/;        # servidos direto do volume static_data
    }

    location /media/ {                  # Requisições a uploads
        alias /app/media/;              # servidos direto do volume media_data
    }

    location / {                        # Todo o resto (aplicação)
        proxy_pass http://web:8000;     # encaminha para o Django
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### Trecho a trecho

- **`listen 80`**: o Nginx escuta na porta 80 dentro do container. O mapeamento `ports: "8000:80"` do Compose traduz isso para a porta 8000 no host, por isso o site abre em `http://localhost:8000`.

- **`location /static/` + `alias /app/staticfiles/`**: qualquer URL iniciada por `/static/` é resolvida como arquivo dentro de `/app/staticfiles/`. Como o volume `static_data` está montado nesse caminho (e como `:ro`), o Nginx lê os arquivos direto do disco, sem passar pelo Django, muito mais rápido.

- **`location /media/` + `alias /app/media/`**: mesma lógica para os arquivos enviados pelos usuários. Como o volume `media_data` também está montado aqui, o Nginx serve os uploads sem depender do container do Django.

- **`location /` + `proxy_pass http://web:8000`**: o curinga, tudo que não casou com os casos acima é repassado para o Django. O `web` é resolvido pelo DNS interno (item 4).

- **`proxy_set_header`**: repassa informações do cliente original ao Django. Sem esses cabeçalhos, o Django veria como origem apenas o IP do próprio Nginx, perderia o IP real do usuário e não saberia se a conexão era HTTP ou HTTPS.

| Cabeçalho | O que faz |
|---|---|
| `Host $host` | Mantém o domínio/original (necessário para o `ALLOWED_HOSTS` do Django) |
| `X-Real-IP` | IP real do cliente |
| `X-Forwarded-For` | Cadeia de IPs percorrida (para logs e auditoria) |
| `X-Forwarded-Proto` | Protocolo original (http/https), usado pelo Django para gerar URLs absolutas |

### Fluxo das portas

```
localhost:8000  →  [host]  ──►  nginx:80  ──►  web:8000  ──►  db:5432
                    público       interno        interno        interno
```

---

## 6. Persistência de dados

Containers são efêmeros, ou seja, ao executar `docker compose down`, tudo que está dentro deles (sistema de arquivos, banco, uploads) é apagado. Para que os dados sobrevivam, foi usado volumes Docker, diretórios gerenciados pelo Docker, que ficam fora do ciclo de vida dos containers.

A solução usa três volumes nomeados, declarados na raiz do `docker-compose.yml`:

| Volume | Montado em | Conteúdo |
|---|---|---|
| `postgres_data` | `db:/var/lib/postgresql/data` | Banco de dados PostgreSQL |
| `media_data` | `web:/app/media` e `nginx:/app/media:ro` | Arquivos enviados pelos usuários |
| `static_data` | `web:/app/staticfiles` e `nginx:/app/staticfiles:ro` | Arquivos estáticos coletados |

### 6.1 Persistência do PostgreSQL

O diretório de dados oficial do PostgreSQL (`/var/lib/postgresql/data`) é mapeado para o volume `postgres_data`. Todas as tabelas, inclusive o registro de cada arquivo enviado (model `Arquivo`), ficam gravadas nesse volume.

### 6.2 Persistência dos arquivos enviados

O Django grava cada upload em `MEDIA_ROOT/uploads/` (= `/app/media/uploads/`), que está mapeado para o volume `media_data`. Como o Nginx monta o mesmo volume em modo `:ro`, ele consegue servir o arquivo baixado sem precisar pedir ao Django.

```
Upload do usuário
      │
      ▼
web:/app/media/uploads/arquivo.pdf   ◄── mesmos dados ──►   nginx:/app/media/uploads/arquivo.pdf
      │                                                            │
      └──────────────────► volume media_data ◄─────────────────────┘
                            (persistente no host)
```

### 6.3 O que acontece se os containers forem removidos?

| Comando | Containers | Volumes | Dados após recriar |
|---|---|---|---|
| `docker compose down` | removidos | **preservados** | tudo continua lá, banco, uploads e estáticos |
| `docker compose down -v` | removidos | **apagados** | banco zerado e uploads perdidos |

Ou seja: basta `docker compose down` e depois `docker compose up -d` que a aplicação volta com todos os dados intactos.

---

## 7. Fluxo do upload de um arquivo

### Passo a passo

1. **Navegador** — o usuário acessa `http://localhost:8000`, escolhe um arquivo e envia o formulário (`POST /` com `enctype="multipart/form-data"`).
2. **Nginx** — recebe a requisição na porta 8000 (→ container, porta 80). A URL `/` não é `/static/` nem `/media/`, então cai no bloco `location /` e é encaminhada por `proxy_pass` para `web:8000`.
3. **Gunicorn** — recebe a requisição e a entrega ao Django (via WSGI).
4. **Django (view `lista_arquivos`)** — valida o formulário (`ArquivoForm`) e, se válido, salva o modelo `Arquivo`.
5. **Gravação do arquivo** — o `FileField(upload_to="uploads/")` grava o conteúdo em `/app/media/uploads/<nome>`, que está mapeado no volume `media_data`, o arquivo vai direto para o volume persistente.
6. **Gravação do registro** — o Django insere a linha (`nome`, `arquivo`, `enviado_em`) na tabela `arquivos_arquivo` do PostgreSQL, no volume `postgres_data`.
7. **Redirecionamento** — o Django responde com `302 Redirect` para `GET /`; a página reexibida lista o novo arquivo.
8. **Download posterior** — ao clicar no link, a URL é `/media/uploads/...`, cai no `location /media/` do Nginx, servida direto do volume, sem passar pelo Django.

### Diagrama de sequência (UML)

```
 Navegador        Nginx          Gunicorn/Django       Volume            PostgreSQL
     │               │                 │              media_data           (db)
     │  POST / (arq) │                 │                 │                  │
     │──────────────►│                 │                 │                  │
     │               │  proxy_pass     │                 │                  │
     │               │  web:8000       │                 │                  │
     │               │────────────────►│                 │                  │
     │               │                 │ valida form     │                  │
     │               │                 │ (ArquivoForm)   │                  │
     │               │                 │                 │                  │
     │               │                 │  grava arquivo  │                  │
     │               │                 │ /app/media/...  │                  │
     │               │                 │────────────────►│                  │
     │               │                 │                 │ (salvo)          │
     │               │                 │  INSERT registro│                  │
     │               │                 │───────────────────────────────────►│
     │               │                 │                 │   (linha salva)  │
     │               │                 │◄───────────────────────────────────│
     │               │  302 Redirect / │                 │                  │
     │               │◄────────────────│                 │                  │
     │  302 /        │                 │                 │                  │
     │◄──────────────│                 │                 │                  │
     │  GET /        │                 │                 │                  │
     │──────────────►│  proxy_pass     │                 │                  │
     │               │────────────────►│  lista do banco │                  │
     │               │                 │───────────────────────────────────►│
     │               │                 │◄───────────────────────────────────│
     │  HTML (200)   │◄────────────────│                 │                  │
     │◄──────────────│                 │                 │                  │
     │               │                 │                 │                  │
     │  GET /media/  │                 │                 │                  │
     │  arquivo      │  lê direto do volume (não passa pelo Django)         │
     │──────────────►│─────────────────────────────────►│                  │
     │  arquivo (200)│◄─────────────────────────────────│                  │
     │◄──────────────│                 │                 │                  │
```

---

## 8. Análise técnica da solução

### Vantagens

1. **Separação clara de responsabilidades** — cada container faz uma coisa: o Nginx expõe e distribui, o Django processa, o PostgreSQL armazena. Qualquer um pode ser trocado ou atualizado sem afetar os demais, como por exemplo, trocar a imagem do Nginx não exige rebuild do Django.
2. **Dados realmente persistentes** — uploads e banco ficam em volumes nomeados, garantindo que `docker compose down` + `up` não perca nada. 
3. **Segurança por escondimento** — apenas a porta 8000 é pública, Gunicorn e PostgreSQL ficam isolados na rede interna `app_network`. Um atacante de fora não alcança o banco nem o servidor de aplicação diretamente.
4. **Reprodutibilidade** — todo o ambiente é descrito em código (`Dockerfile` + `docker-compose.yml`), qualquer máquina com Docker levanta a mesma aplicação com um comando.

### Limitações ou problemas da implementação atual

1. **Configurações inadequadas para produção em `settings.py`** — `DEBUG = True`, expõe tracebacks e variáveis, `SECRET_KEY` fixa e versionada no código, e credenciais de banco com valores padrão no próprio `docker-compose.yml`.
2. **Sem HTTPS** — o tráfego trafega em texto puro (HTTP). Em produção, dados e cookies ficariam expostos a interceptação.
3. **Instância única de cada serviço** — um único Gunicorn e um único Nginx: se o processo cair, a aplicação inteira fica fora do ar, e não há como absorver picos de tráfego (sem réplicas nem balanceamento).
4. **Ausência de validação de uploads e de testes** — não há limite de tamanho ou tipo de arquivo nem testes automatizados garantindo que mudanças futuras não quebrem a aplicação.

### Melhorias para um ambiente de produção

1. **Configuração de segurança** — mover `SECRET_KEY`, senhas e `DEBUG` para variáveis de ambiente (arquivo `.env` fora do versionamento), desligar `DEBUG` e configurar `SECURE_*` (HTTPS, cookies seguros).
2. **HTTPS e reverse proxy completo** — adicionar TLS no Nginx (certificado Let's Encrypt) e liberar a porta 443; manter a porta 80 apenas redirecionando para HTTPS.
3. **Alta disponibilidade e robustez** — healthcheck também no `web`, `restart: unless-stopped` nos serviços, múltiplos workers no Gunicorn (ex.: `--workers 4`), réplicas do Django com balanceamento no Nginx, além de limites de upload (`client_max_body_size` no Nginx + `FILE_UPLOAD_MAX_MEMORY_SIZE` no Django) e testes automatizados.

---

## 9. Como executar o projeto

### Requisitos

- Docker Engine + Docker Compose
- (Opcional) Python 3.12 + venv para rodar localmente sem Docker

### Ambiente virtual (venv)

```bash
# Linux / macOS
source .venv/bin/activate

# Windows (CMD)
.venv\Scripts\activate

# Instalar dependências
pip install -r requirements.txt

# Desativar
deactivate
```

### Subir a aplicação

```bash
# Entre na pasta do projeto (estava em documentos)
cd ~/Documentos/projeto-django-docker

# Construir as imagens e iniciar os containers
sudo docker compose up --build -d

# Verificar o status
sudo docker compose ps
```

Acessar: **http://localhost:8000**

### Parar a aplicação

```bash
# Para os containers (preserva os volumes/dados)
sudo docker compose down

# Para e APAGA tudo (volumes, dados e imagens)
sudo docker compose down -v --rmi all
```

### Verificar a persistência dos uploads

```bash
# Listar os arquivos salvos no volume
sudo docker compose exec web ls -la /app/media/uploads/

# Conferir os volumes criados
sudo docker volume ls
sudo docker volume inspect projeto-django-docker_media_data
```

**Teste de persistência:**

1. `sudo docker compose up --build -d`
2. Acesse http://localhost:8000 e envie um arquivo
3. `sudo docker compose down` (para os containers)
4. `sudo docker compose up -d` (sobe de novo)
5. Acesse http://localhost:8000 -> o arquivo continua listado

### Variáveis de ambiente (banco de dados)

| Variável | Valor padrão |
|---|---|
| `POSTGRES_DB` | `arquivosdb` |
| `POSTGRES_USER` | `django` |
| `POSTGRES_PASSWORD` | `django123` |
| `POSTGRES_HOST` | `db` |
| `POSTGRES_PORT` | `5432` |

---

## Estrutura do repositório

```
projeto-django-docker/
├── README.md              # esta documentação técnica
├── Dockerfile             # imagem da aplicação Django
├── docker-compose.yml     # orquestração dos 3 containers
├── requirements.txt       # dependências Python
├── nginx/
│   └── default.conf       # configuração do proxy reverso
└── app/
    ├── manage.py
    ├── config/
    │   ├── settings.py    # banco, volumes, hosts
    │   ├── urls.py
    │   └── wsgi.py        # entrada WSGI (Gunicorn)
    └── arquivos/
        ├── models.py      # modelo Arquivo (upload)
        ├── views.py       # lógica de upload/listagem
        ├── forms.py       # formulário de upload
        ├── urls.py
        └── templates/
            ├── base.html          # layout/design
            └── arquivos/lista.html
```

## Tecnologias

| Tecnologia | Versão | Função |
|---|---|---|
| Python | 3.12 | Linguagem |
| Django | 6.1 | Framework web |
| Gunicorn | 26.2 | Servidor WSGI de produção |
| Nginx | Alpine | Proxy reverso |
| PostgreSQL | 16 | Banco de dados |
| Docker / Compose | - | Containerização e orquestração |
