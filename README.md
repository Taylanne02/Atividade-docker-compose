# Aplicacao Django com Docker Compose

Projeto desenvolvido para a atividade de Docker Compose.

## Servicos

- **web** - Django com Gunicorn (porta 8000 interna)
- **nginx** - Proxy reverso (porta 8000 exposta)
- **db** - PostgreSQL 16 (porta 5432 interna)

## Estrutura

```
projeto-django-docker/
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── nginx/
│   └── default.conf
└── app/
    ├── manage.py
    ├── config/
    │   ├── settings.py
    │   ├── urls.py
    │   └── wsgi.py
    └── arquivos/
        ├── models.py
        ├── views.py
        ├── forms.py
        ├── urls.py
        └── templates/
```

## Ambiente virtual (venv)

O projeto ja possui um venv na pasta `.venv`. Para ativar:

```bash
# Linux / macOS
source .venv/bin/activate

# Windows (CMD)
.venv\Scripts\activate

# Windows (PowerShell)
.venv\Scripts\Activate.ps1
```

Para instalar as dependencias dentro do venv:

```bash
pip install -r requirements.txt
```

Para desativar:

```bash
deactivate
```

## Como executar (entre na pasta onde está localizado o projeto)

```bash
# Construir e iniciar os containers
sudo docker compose up --build -d

# Verificar se os containers estao rodando
sudo docker compose ps
```

A aplicacao ficara disponivel em: **http://localhost:8000**

## Parar a aplicacao

```bash
# Parar os containers (preserva volumes)
sudo docker compose down

# Parar e APAGAR tudo (volumes, dados, imagens)
sudo docker compose down -v --rmi all
```

## Verificar persistencia dos uploads

Os arquivos enviados sao salvos no volume Docker `media_data`. Para verificar:

```bash
# Listar arquivos dentro do container
docker compose exec web ls -la /app/media/uploads/

# Copiar um arquivo do volume para a maquina local
docker compose cp django-web:/app/media/uploads/ ./uploads_bkp/

# Verificar o volume criado
docker volume ls
docker volume inspect projeto-django-docker_media_data
```

### Teste de persistencia

1. Suba a aplicacao: `docker compose up --build -d`
2. Acesse http://localhost:8000 e faca upload de um arquivo
3. Pare os containers: `docker compose down`
4. Suba novamente: `docker compose up -d`
5. Acesse http://localhost:8000 - o arquivo continua listado

Para apagar tudo (incluindo uploads):
```bash
docker compose down -v
```

## Variaveis de ambiente (Banco de dados)

| Variavel        | Valor padrao   |
|-----------------|----------------|
| POSTGRES_DB     | arquivosdb     |
| POSTGRES_USER   | django         |
| POSTGRES_PASSWORD | django123    |
