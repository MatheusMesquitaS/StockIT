# StockIT

Olá! 
Comecei este projeto durante meu estágio em TI, quando percebi que o controle do estoque de equipamentos ainda dependia de planilhas espalhadas entre as unidades. Toda vez que alguém precisava de um notebook, um monitor ou um toner, a pergunta era a mesma: "tem isso em estoque?". Responder levava mais tempo do que deveria.

A ideia inicial era simples: um lugar só para cadastrar os itens e registrar quem pegou o quê. Com o uso no dia a dia, o time foi trazendo pedidos e o sistema foi crescendo. Primeiro veio a separação por unidade, depois os perfis de acesso, o filtro por tipo, o controle de toner por cor e uma aba para registrar a configuração dos notebooks e desktops (RAM, SSD e saúde da bateria), que acabou sendo das partes mais úteis na hora de decidir qual máquina entregar para quem.

Algumas coisas nasceram mais por gosto do que por necessidade, como o tema escuro, a troca de idioma e a sidebar recolhível. Mas foram justamente elas que me fizeram aprender mais sobre CSS, sessões no Flask e organização de templates.

Esta é uma versão adaptada para portfólio. Removi tudo que identificava a empresa, e os dados que aparecem aqui são fictícios.

O que dá pra fazer
Cadastrar, editar e movimentar itens, com histórico de entradas e retiradas
Separar o estoque por unidade, com acesso de administrador e de usuário padrão
Registrar a configuração de notebooks e desktops, incluindo o estado da bateria
Controlar toners por cor
Personalizar o dashboard, o tema e o idioma de cada usuário
Feito com
Python, Flask e SQLite no back-end. No front, HTML, CSS e JavaScript puro, sem framework, porque queria entender o que estava acontecendo em cada parte da tela.


O que ainda quero fazer
Exportar o estoque para Excel
Ver o histórico completo de um equipamento específico
Escrever testes automatizados





# StockIT

Sistema web para controle de estoque de equipamentos e suprimentos de TI, com suporte a múltiplas unidades, perfis de acesso, tema escuro e interface em três idiomas.

> Projeto desenvolvido por **Matheus Mesquita**. Todos os dados desta versão são fictícios.

## Funcionalidades

**Estoque**
- Cadastro, edição e exclusão lógica de itens (o histórico de movimentações é preservado)
- Tipos de item: Notebook, Desktop, Monitor, Celular, Toner, Cabos, periféricos e outros
- Filtro por tipo e busca por nome, patrimônio ou número de série
- Alertas visuais de baixo estoque e item sem estoque
- Toners com cor (Black, Cyan, Magenta e Yellow)
- Aba de configuração para Notebook e Desktop: processador, memória RAM (Single/Dual Channel), tipo e capacidade de armazenamento, além de saúde e status da bateria para notebooks

**Movimentações**
- Registro de entradas e retiradas, com validação de saldo
- Histórico completo com busca e filtros por tipo e unidade

**Usuários e acesso**
- Perfis Administrador e Padrão
- Usuário padrão enxerga somente a própria unidade; o administrador alterna entre unidades ou vê todas
- Senhas com hash e regras de complexidade
- Redefinição de senha pelo administrador e alteração de senha pelo próprio usuário

**Experiência**
- Dashboard com indicadores, estoque por tipo e últimas movimentações
- Página Meu Perfil com estatísticas pessoais e preferências
- Tema claro, escuro ou seguindo o dispositivo
- Interface em português, inglês e espanhol, escolhida por usuário
- Personalização dos blocos exibidos no dashboard
- Sidebar recolhível e layout responsivo

## Tecnologias

- Python 3 e Flask
- SQLite
- Jinja2, HTML, CSS e JavaScript, sem frameworks de front-end

## Como executar

```bash
# 1. Crie e ative um ambiente virtual
python -m venv venv
venv\Scripts\activate            # Windows
# source venv/bin/activate       # Linux/macOS

# 2. Instale as dependências
pip install -r requirements.txt

# 3. (Opcional) Popule com dados de demonstração
python seed_demo.py --reset

# 4. Inicie
python app.py
```

Acesse `http://127.0.0.1:8080`.

### Acessos de demonstração

| Perfil | Usuário | Senha |
|---|---|---|
| Administrador | `admin` | `Admin@123` |
| Padrão | `ana.souza` | `Demo@123` |

Troque essas senhas antes de qualquer uso real.

## Configuração

As configurações são lidas de variáveis de ambiente ou de um arquivo `.env` na raiz do projeto. Copie `.env.example` para `.env` e ajuste:

| Variável | Descrição | Padrão |
|---|---|---|
| `SECRET_KEY` | Chave de sessão do Flask | gerada aleatoriamente a cada execução |
| `ADMIN_PASSWORD` | Senha do admin criado na primeira execução | `Admin@123` |
| `TEMP_PASSWORD` | Senha aplicada no reset feito pelo admin | `Temp@123` |
| `DATABASE_PATH` | Caminho do banco SQLite | `estoque.db` |
| `HOST` / `PORT` | Endereço e porta | `127.0.0.1` / `8080` |
| `FLASK_DEBUG` | `1` ativa o modo debug | `0` |

Para disponibilizar na rede local, use `HOST=0.0.0.0`. Em produção, defina uma `SECRET_KEY` fixa e use um servidor WSGI, como o Waitress.

## Estrutura

```text
├── app.py              # Rotas, regras de negócio e migrações do banco
├── translations.py     # Textos em pt-BR, en-US e es-ES
├── seed_demo.py        # Dados fictícios para demonstração
├── templates/          # Páginas Jinja2
└── static/
    ├── css/estilo.css
    └── img/            # Logo e ícones SVG
```



