# Importador de Câmeras para Zabbix

[![Testes](https://github.com/lucasdaniel2201/zabbix-camera-importer/actions/workflows/tests.yml/badge.svg)](https://github.com/lucasdaniel2201/zabbix-camera-importer/actions/workflows/tests.yml)
[![Licença: MIT](https://img.shields.io/badge/licen%C3%A7a-MIT-blue.svg)](LICENSE)
[![Plataforma: Windows 10/11](https://img.shields.io/badge/Windows-10%2F11-0078D6.svg)]()
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)]()

Importa em lote hosts de câmera de CFTV para o Zabbix a partir de uma planilha
(`.xlsx` ou `.csv`). Serve para quem prefere linha de comando e para quem quer
uma interface gráfica: os dois fluxos usam exatamente a mesma lógica de login,
normalização e criação de hosts.

A criação dos hosts usa o **frontend web** do Zabbix (login mais `POST` do
formulário `host.create`), e não a API por token. É o que faz o app funcionar
também em ambientes onde a API HTTP está bloqueada ou nenhum token está
disponível.

**Projetos relacionados:** este app é o par do
[netbox-device-importer](https://github.com/lucasdaniel2201/netbox-device-importer),
que **documenta** o mesmo parque de câmeras e switches no NetBox. Um registra o
que existe; este coloca o que existe para **monitorar**. A planilha de entrada
pode ser a mesma nos dois.

**Sumário**

- [Para quem vai usar](#para-quem-vai-usar)
- [Telas](#telas)
- [Como usar](#como-usar)
- [A planilha modelo](#a-planilha-modelo)
- [Layout aplicado no Zabbix](#layout-aplicado-no-zabbix)
- [Regras da importação](#regras-da-importação)
- [Relatórios](#relatórios)
- [Linha de comando](#linha-de-comando)
- [Credenciais](#credenciais)
- [Arquitetura](#arquitetura)
- [Testes](#testes)
- [Build do executável](#build-do-executável)
- [Instalador e portátil](#instalador-e-portátil)
- [Ao lançar uma nova versão](#ao-lançar-uma-nova-versão)
- [Onde o app grava arquivos](#onde-o-app-grava-arquivos)
- [Limitações conhecidas](#limitações-conhecidas)
- [Status](#status)
- [Estrutura do projeto](#estrutura-do-projeto)
- [Controle de versão](#controle-de-versão)
- [Licença](#licença)

## Para quem vai usar

Baixe o `ImportadorZabbixSetup-<versão>.exe` mais recente na página de
**Releases** do repositório e execute. A instalação é **por usuário** (não pede
administrador), cria atalho no Menu Iniciar e tem desinstalador.

Requisitos: Windows 10/11 x64. Não precisa de Python instalado.

A mesma Release traz o **executável portátil** (`ImportadorZabbix.exe`), para o
caso de não dar para instalar. A escolha entre os dois está em *Instalador e
portátil*, mais abaixo.

## Telas

| Login | Planilha carregada | Importação em andamento |
| --- | --- | --- |
| ![Tela de login, com usuário e senha do Zabbix](docs/screenshots/login.png) | ![Preview da planilha validada, com grupos, templates e proxy selecionados](docs/screenshots/planilha.png) | ![Barra de progresso e botão de cancelar durante a importação](docs/screenshots/importacao.png) |

Os prints são gerados por um utilitário de desenvolvimento
(`tools/screenshots.py`), rodando o app sem abrir janela, e usam apenas dados
fictícios.

## Como usar

O app tem duas telas: **login** (usuário e senha do Zabbix) e o **ambiente de
importação** (planilha, opções de criação e preview).

### Login

- A URL do Zabbix e a porta da interface ficam em **Configurações**, no canto do
  card de login. A URL é usada na conexão; a porta, na criação dos hosts.
- Usuário e senha são pedidos na tela e **não são gravados em disco**. A senha
  some do campo assim que a conexão dá certo.
- Ao conectar, o app busca no servidor os **grupos, templates e proxies**
  disponíveis e preenche os seletores. O botão "Atualizar listas" refaz a
  consulta a qualquer momento, e "Sair" encerra a sessão e limpa as listas.

### Ambiente de importação

1. **Baixar modelo de exemplo**: um popup permite escolher as colunas opcionais
   do modelo. As colunas fixas são apenas **Nome do host** e **IP**. O arquivo
   `modelo_cameras.xlsx` é gerado onde você escolher.
2. **Escolher planilha**: aceita `.xlsx` ou `.csv`. O app valida linha a linha e
   mostra o **preview** do que será criado, com os nomes já normalizados.
3. **Opções de criação**: prefixo e sufixo (opcionais) e a escolha de grupos,
   templates e proxy. Grupos e templates aceitam **múltipla seleção** e **começam
   sem nenhuma marcação**; sem ao menos um grupo, a importação fica bloqueada.
4. **Importar**: o progresso aparece por câmera, com botão de cancelar. Ao final,
   um resumo mostra criados, já existentes e erros, além do caminho do relatório.

## A planilha modelo

Colunas: Nome do host, IP, Fabricante, Modelo, Firmware, Endereço MAC, Unidade,
Etiqueta, Descrição.

- **Nome do host**: obrigatório. É normalizado para ASCII antes de ir ao Zabbix
  (o Zabbix rejeita acentos e alguns caracteres).
- **IP**: obrigatório. É o IP da interface `agent` da câmera.
- **Fabricante + Modelo + Firmware + Endereço MAC**: vão para o inventário do
  host (`name`, `hardware`, `hardware_full` e `macaddress_a`).
- **Etiqueta**: formato `chave:valor`, com várias separadas por `;`
  (ex.: `site:MATRIZ`).
- **Descrição**: campo Description do host no Zabbix.
- **Unidade**: apenas orientação para quem preenche, não vai para o Zabbix.

Cabeçalhos antigos também são aceitos como alternativa (ex.: `Name`, `IP/Nome`,
`Fabricante:`, `MAC`), porque a planilha de câmeras existe em mais de um formato
de exportação.

**Grupo de host, template e proxy não vêm da planilha**: são escolhidos na tela
do app (ou por argumento, no CLI) e aplicados a todas as linhas.

## Layout aplicado no Zabbix

Valores usados na criação do host:

- `host` técnico e nome visível: o `Nome do host` da planilha, com prefixo e
  sufixo opcionais.
- interface: `agent`, com o IP da câmera e a porta configurada (padrão `10051`).
- inventário: `name` = fabricante, `hardware` = modelo, `hardware_full` = modelo
  com firmware, `macaddress_a` = MAC.
- status: monitorado, sem inventário automático.

## Regras da importação

**Normalização.** Nomes são convertidos para ASCII; uma linha cujo nome mude é
marcada com **aviso** no preview e o nome final aparece na coluna "Nome final no
Zabbix".

**Duplicados bloqueiam.** Dois nomes que colidem depois da normalização são
tratados como **erro**: a importação fica bloqueada até você corrigir na planilha.

**Validação antes de enviar.** Enquanto houver linha com IP vazio, formato de IP
inválido ou nome inválido, o botão de importar não libera. O que está em branco
na coluna Nome é ignorado e contabilizado como linha ignorada, junto com as
marcadas como "troca realizada".

**Hosts existentes não interrompem o lote.** Um host que já existe no Zabbix é
detectado e contabilizado como `exists`, e o lote segue.

**Falha de sessão no meio do caminho.** Se a sessão expirar durante uma execução
longa, o app reloga uma vez e continua.

## Relatórios

Cada execução grava três arquivos em `reports/`:

| Arquivo | Conteúdo |
| --- | --- |
| `zabbix-web-import-<data-hora>.log` | Uma linha por host. |
| `zabbix-web-import-<data-hora>.json` | Resumo da execução mais o resultado por linha. |
| `zabbix-web-import-<data-hora>.csv` | Resultado por linha, em planilha. |

O `consolidate.py` junta o resumo de várias execuções em um resumo único, para
revisar um lote grande depois.

## Linha de comando

O importador cria hosts para um intervalo do CSV. É **obrigatório** informar ao
menos um grupo de destino:

```powershell
python .\zabbix_web_batch_import.py --url "https://seu-zabbix" --group-id 1 --offset 0 --limit 5
```

Execução em lotes (fluxo padrão), pedindo usuário e senha no terminal:

```powershell
python .\run_batches.py --group-id 1
```

Para um layout diferente, passe as opções de layout do importador:

```powershell
python .\run_batches.py --group-id 1 --host-prefix "CAM - " --visible-name-prefix "CAM "
```

O `run_batches.py` roda o importador em lotes de 25 registros, avisando (sem
parar) se algum lote terminar com erro. Prefixo e sufixo de host e de nome
visível também são configuráveis por `--host-prefix`, `--host-suffix`,
`--visible-name-prefix` e `--visible-name-suffix`.

Para preparar a planilha e revisar o resumo de várias execuções:

```powershell
python .\xlsx_to_csv.py --input caminho\da\planilha.xlsx --output cameras_normalized.csv
python .\validate_camera_names.py .\cameras_normalized.csv
python .\consolidate.py
```

Os dados de entrada (`*.xlsx`, `cameras_normalized.csv`) **não são versionados**:
contêm informação do ambiente do cliente. O `exemplo_cameras.csv` existe com
dados fictícios, para testar o fluxo:

```powershell
python .\zabbix_web_batch_import.py --url "https://seu-zabbix" --group-id 1 --csv .\exemplo_cameras.csv
```

## Credenciais

Nenhuma credencial fica salva em disco, e os dois fluxos pedem os dados na hora:

- **App gráfico**: tela de login. A senha não é gravada em lugar nenhum.
- **Linha de comando** (`run_batches.py`): pede usuário e senha no terminal; a
  senha é digitada sem eco (`getpass`). Nada de arquivo `.env`.

O `zabbix_web_batch_import.py` também aceita `--username` e `--password` para
automação; nesse caso a senha fica visível na linha de comando.

## Arquitetura

O princípio é o mesmo dos projetos irmãos: **a interface pede, o worker executa.**
Nenhuma tela fala com a rede.

```
app/main_window.py  (UI — thread principal)
     |  emite sinais do Qt
     v
app/session.py — SessionWorker  (QObject em QThread propria)
     |
     v
zabbix_web_batch_import.py — core (login web + host.create)
     |
     +-- HTTP/form  --> frontend do Zabbix (/index.php)
     +-- JSON-RPC   --> /api_jsonrpc.php  (grupos, templates, proxies)
```

- `zabbix_web_batch_import.py` concentra a regra de negócio e é reaproveitado
  pela CLI, pelos scripts de lote e pela interface gráfica. É a peça que garante
  que os dois fluxos criem hosts exatamente do mesmo jeito.
- `app/main_window.py` nunca chama a rede: emite sinais do Qt e reage a sinais de
  volta. É o que mantém a janela respondendo.
- `app/session.py` tem o `SessionWorker`, um `QObject` movido para uma `QThread`
  com `moveToThread`. Login, busca das listas e importação rodam nessa thread, e
  o Qt entrega os resultados por conexão enfileirada.
- `app/spreadsheet.py` é puro de propósito: lê e valida a planilha sem tocar na
  rede, o que o torna testável offline.
- A **listagem** de grupos, templates e proxies usa o JSON-RPC da própria sessão
  (cookie), sem token; a **criação** dos hosts usa o formulário web.

## Testes

```powershell
python -m unittest discover -s tests
```

São **102 testes**, apenas com a stdlib (`unittest`), e rodam **sem rede nem
Zabbix**. Cobrem a normalização de nomes, a leitura da resposta do Zabbix, a
montagem do formulário, as colunas da planilha, a validação linha a linha, as
regras de UX das notificações, a resolução de caminhos e a ausência de
credencial embutida no código.

Rode antes de alterar o importador ou o módulo de planilha: são esses testes que
protegem contra a volta de erros já corrigidos (nome duplicado, IP inválido,
proxy omitido, coluna obrigatória ausente).

O CI roda essa suíte no Python 3.12 e 3.14, e o Ruff em separado. O estado está
no badge no topo.

## Build do executável

```powershell
pip install "pyinstaller>=6,<7"
python -m PyInstaller --clean --noconfirm ImportadorZabbix.spec
```

Gera `dist\ImportadorZabbix.exe`: arquivo único, sem console, com ícone e os
metadados de `version_info.txt`. Os assets (ícone e fonte Inter) vão embutidos e
são resolvidos por `app/paths.py`.

Atenção ao editar o `.spec`: não exclua da stdlib módulos que as dependências
usam. `email` (usado por `requests`/`urllib3`) e `xml` (usado por `openpyxl`) já
quebraram o executável quando foram excluídos.

## Instalador e portátil

A Release publica dois binários. **Use o instalador, salvo se não puder.**

| Binário | Quando usar |
| --- | --- |
| `ImportadorZabbixSetup-<versão>.exe` (instalador) | **Padrão.** Instala por usuário em `%LOCALAPPDATA%\Programs\Importador Zabbix`, sem pedir administrador; cria atalho no Menu Iniciar e, opcionalmente, na Área de Trabalho; instala o desinstalador e é atualizável por cima. |
| `ImportadorZabbix.exe` (portátil) | Quando não der para rodar instalador (política da máquina) ou quando o app precisar rodar de pendrive ou pasta de rede. Não cria atalho nem desinstalador: o arquivo roda de onde estiver. |

Para **gerar** os dois, requer o [Inno Setup 6](https://jrsoftware.org/isdl.php)
— o executável vem do PyInstaller, acima:

```powershell
& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" instalador.iss
```

O `instalador.iss` empacota o `dist\ImportadorZabbix.exe` já gerado, por isso o
PyInstaller roda primeiro.

## Ao lançar uma nova versão

1. Atualize `AppVersion` no `instalador.iss`.
2. Atualize a versão no `version_info.txt`.
3. Registre a versão no `CHANGELOG.md`.
4. Gere o executável e o instalador.
5. Publique a Release no GitHub com os dois binários.

**Nunca mude o `AppId`** do instalador daqui para frente: é ele que permite
atualizar por cima e desinstalar corretamente. (A versão 1.0.0 foi a exceção: o
`AppId` mudou junto com o nome do produto, que colidia com o do app do NetBox.)

O que não versionar: `build/` e `dist/` (artefatos). O `ImportadorZabbix.spec` e
o `instalador.iss` **são** versionados — são a configuração do build.

## Onde o app grava arquivos

| Conteúdo | Local |
| --- | --- |
| Relatórios (`reports/`) e `app_error.log` | Código-fonte: raiz do projeto. `.exe`: ao lado do executável; se a pasta não for gravável, `%LOCALAPPDATA%\ImportadorZabbix`. |

Resolvido por `app/paths.py`.

## Limitações conhecidas

- **Sessão web, não token.** O app depende do formulário web do Zabbix, que não é
  uma API estável: um upgrade de versão do Zabbix pode mudar o formulário e
  exigir ajuste no importador. A listagem das listas, por outro lado, usa
  JSON-RPC e é mais estável.
- **Grupo de host obrigatório.** Não há default no código: sem um grupo marcado a
  importação não começa.
- **Sem retomada automática.** O `run_batches.py` avisa ao final se um lote
  terminou com erro, mas não reprocessa sozinho.
- **Nome longo.** O Zabbix tem limite de tamanho no campo de nome do host; nomes
  muito longos são truncados na normalização.

## Status

- **Pronto:** login web, busca de grupos/templates/proxies, geração de planilha
  modelo com colunas opcionais, preview com validação linha a linha,
  normalização e bloqueio de duplicados, importação em lotes com progresso e
  cancelamento, relatórios em log/JSON/CSV, consolidação de execuções,
  instalador Inno Setup e portátil, e CI rodando os 102 testes.
- **Fora do escopo, por decisão de projeto:** uso da API por token do Zabbix
  (justamente para funcionar onde ela está bloqueada) e retomada automática de
  lote com erro.

## Estrutura do projeto

| Caminho | Função |
| --- | --- |
| `zabbix_web_batch_import.py` | Importador principal: login web e `host.create`. O core. |
| `run_batches.py` | Executa o importador em lotes de 25; pede credenciais no terminal. |
| `consolidate.py` | Consolida os relatórios JSON de várias execuções em um resumo. |
| `xlsx_to_csv.py` | Converte a planilha de origem em CSV normalizado. |
| `validate_camera_names.py` | Normaliza a coluna de nome (ASCII) e valida duplicados. |
| `run_app.py` | Ponto de entrada do executável (usado pelo PyInstaller). |
| `app/` | Código da interface gráfica (módulos abaixo). |
| `app/main.py` | Ponto de entrada do app: `QApplication`, fonte Inter, paleta e janela. |
| `app/main_window.py` | Janela com as telas de login e de importação. |
| `app/session.py` | `SessionWorker`: thread única que detém a sessão com o Zabbix. |
| `app/spreadsheet.py` | Leitura e validação de `.xlsx`/`.csv` e geração do modelo. |
| `app/toast.py` | Notificações não invasivas no canto superior direito. |
| `app/paths.py` | Caminhos no código-fonte e no `.exe` (assets e pastas graváveis). |
| `app/assets/` | Ícone do app e fonte Inter (`assets/fonts/`). |
| `tests/` | Testes automatizados (`unittest`), sem rede. |
| `tools/screenshots.py` | Utilitário de desenvolvimento que gera as telas deste README. |
| `docs/screenshots/` | As imagens usadas neste README. |
| `ImportadorZabbix.spec` | Configuração do build do PyInstaller. |
| `instalador.iss` | Configuração do instalador (Inno Setup 6). |
| `version_info.txt` | Metadados do `.exe` (nome, versão, empresa). |
| `pyproject.toml` | Configuração do Ruff (lint). |
| `requirements.txt` | Dependências de execução, com versão fixada. |
| `requirements-dev.txt` | Dependências de desenvolvimento (`ruff`). |
| `LICENSE` | Licença do projeto (MIT). |
| `CHANGELOG.md` | Histórico de mudanças por versão. |
| `reports/` | Relatórios gerados a cada execução (não versionado). |

## Para quem vai mexer no código

```powershell
pip install -r requirements.txt
python -m app.main
```

Dependências de execução: `openpyxl`, `requests`, `beautifulsoup4` e `PySide6`
(`requirements.txt`, com versão fixada).

Para o lint (o CI roda exatamente este comando):

```powershell
pip install -r requirements-dev.txt
python -m ruff check .
```

## Controle de versão

O projeto está sob git. O `.gitignore` exclui `reports/`, `app_error.log`,
`__pycache__/`, `build/`, `dist/`, planilhas (`*.xlsx`) e
`cameras_normalized.csv`. Nenhuma credencial nem dado de cliente é versionado: o
`.env` é proibido por decisão de projeto e o `.spec`/`instalador.iss` são
versionados de propósito, por serem a configuração do build.

## Licença

MIT — veja [LICENSE](LICENSE).

## Autor

**Lucas Daniel Santos**

- GitHub: [@lucasdaniel2201](https://github.com/lucasdaniel2201)
- LinkedIn: [lucas-santos](https://www.linkedin.com/in/lucas-santos-a620011b9)
