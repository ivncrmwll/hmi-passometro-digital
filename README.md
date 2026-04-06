# 🏥 Passômetro Digital — HMINSN

Sistema de gerenciamento de pacientes internados, desenvolvido para o Hospital Materno Infantil Nossa Senhora de Nazareth - HMINSN, com o intuito de facilitar as "passagens de plantão das equipes de enfermagem". Permite o controle de leitos, admissões, altas, transferências e evasões por setor.

## 📋 Funcionalidades

- Login com autenticação por CPF e senha
- Controle de pacientes por setor e leito
- Registro de admissão, alta, transferência e evasão
- Painel administrativo com gerenciamento de usuários
- Log de auditoria de todas as ações
- Exportação de relatórios em CSV e PDF
- Proteção contra ataques de força bruta (rate limiting)
- Proteção CSRF em todos os formulários

## 👥 Níveis de Acesso

| Cargo | Permissões |
|---|---|
| Global Admin | Acesso total ao sistema |
| Coord. de Ala | Gerencia usuários e pacientes do próprio setor |
| Enfermeiro(a) | Gerencia pacientes do próprio setor |

## 🚀 Como instalar

### Pré-requisitos
- Python 3.10 ou superior
- pip

### Passo a passo

**1. Clone o repositório:**
```bash
git clone https://github.com/ivncrmwll/hmi-passometro-digital.git
cd hmi-passometro-digital
```

**2. Instale as dependências:**
```bash
pip install -r requirements.txt
```

**3. Crie o arquivo `.env` na raiz do projeto:**
```
SECRET_KEY=sua_chave_secreta_aqui
ADMIN_SENHA=senha_do_admin
RESET_SENHA=senha_padrao_de_reset
```

**4. Inicialize o banco de dados:**
```bash
python -m flask db upgrade
```

**5. Rode o servidor:**
```bash
python app.py
```

**6. Acesse no navegador:**
```
http://localhost:5000
```

## 🔐 Credenciais padrão do Admin

| Campo | Valor |
|---|---|
| CPF | 00000000000 |
| Senha | definida no `.env` |

> ⚠️ Troque a senha do admin imediatamente após o primeiro acesso.

## 🛠️ Tecnologias utilizadas

- [Flask](https://flask.palletsprojects.com/) — framework web
- [SQLAlchemy](https://www.sqlalchemy.org/) — ORM para banco de dados
- [Flask-Migrate](https://flask-migrate.readthedocs.io/) — migrações de banco
- [Flask-WTF](https://flask-wtf.readthedocs.io/) — proteção CSRF
- [Flask-Limiter](https://flask-limiter.readthedocs.io/) — rate limiting
- [fpdf2](https://py-fpdf2.readthedocs.io/) — geração de PDFs
- [Waitress](https://docs.pylonsproject.org/projects/waitress/) — servidor WSGI para produção

## 📁 Estrutura do projeto
```
hmi-passometro-digital/
│
├── app.py                  # Aplicação principal
├── requirements.txt        # Dependências
├── .env                    # Variáveis de ambiente (não vai ao GitHub)
├── .gitignore
├── migrations/             # Migrações do banco de dados
└── templates/              # Templates HTML
```

## ⚠️ Observações de segurança

- O arquivo `.env` **nunca** deve ser enviado ao GitHub
- O banco de dados `.db` **nunca** deve ser enviado ao GitHub
- Em produção, utilize um banco de dados MySQL no lugar do SQLite

## 📄 Versão

1.0 — Desenvolvido inicialmente para uso interno, em rede intranet do HMINSN.