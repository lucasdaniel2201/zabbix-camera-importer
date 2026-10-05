# CONTEXT.md

Ultima atualizacao: migracao para API JSON-RPC, v1.5.0.

## O que e

App desktop que importa, em lote, hosts de camera de CFTV para o Zabbix 6.4 a
partir de uma planilha `.xlsx` ou `.csv`. Usado por quem administra os cameras e
precisa criar os hosts no Zabbix sem digitar um por um. A interface e PySide6 e o
transporte e a API JSON-RPC do Zabbix (`api_jsonrpc.php`).

O app e o unico ponto de entrada do projeto. Nao existe linha de comando.

## Mapa do codigo

- `zabbix_importer.py` - core. Cliente da API, dataclasses
  (`CameraRecord`, `ImportOptions`, `ZabbixApiError`), funcoes puras de
  normalizacao e montagem do host, classificacao de erro e escrita de relatorios.
- `app/main.py` - entrada do app (`python -m app.main`), fonte, paleta, folha de
  estilo, `app_error.log` e `excepthook`.
- `app/main_window.py` - janela principal: login, escolha da planilha, opcoes de
  criacao, preview, importacao.
- `app/session.py` - `SessionWorker`, dono da sessao do Zabbix, roda em `QThread`.
- `app/spreadsheet.py` - leitura/validacao da planilha e geracao do modelo.
- `app/paths.py` - caminhos no codigo-fonte e no `.exe`.
- `app/toast.py` - notificacoes.
- `consolidate.py` - resumo de varios relatorios JSON.

O core e importado pela UI como `import zabbix_importer as core`. `ImportOptions`
mora no core; `app/session.py` reexporta (`ImportOptions = core.ImportOptions`).

## Decisoes de arquitetura

**`user.logout` nunca e chamado.** O token expira sozinho pelo timeout de sessao
do servidor. Fechar a conexao HTTP (`ZabbixApiClient.close`) nao invalida o token,
entao fechar o app ou clicar em "Sair" nao desloga o usuario do Zabbix. Ha teste
em `tests/test_importer.py::TestClientRequest::test_close_nao_chama_user_logout`.

**Um `host.create` por host, em vez de `host.massadd`.** `host.massadd` seria
atomico, mas um erro derrubaria o lote inteiro e o relatorio perderia o
detalhe linha a linha. Host por host mantem o relatorio honesto: cada linha tem
status e mensagem proprios.

**Pre-consulta com `host.get` antes do lote.** `existing_hosts()` consulta os
nomes tecnicos finais em blocos de 200 (`HOST_GET_CHUNK`) e marca como `exists`
sem gastar chamada de criacao. Falha na pre-consulta nao aborta a importacao - o
lote segue e `classify_api_error` ainda reconhece "already exists" como `exists`
(fallback para corrida entre a consulta e a criacao).

**`inventory_mode=0` (manual), nao `-1` (desabilitado).** Decisao consciente do
dono: o inventario preenchido pela planilha precisa poder ser editado a mao no
Zabbix depois.

**Mapeamento de inventario preserva o comportamento antigo do formulario web**,
inclusive `inventory.type` = modelo (nao fabricante) e `inventory.name` =
fabricante. Parece invertido, mas e o que o Zabbix ja tinha preenchido antes da
migracao; mudar isso mudaria os hosts ja existentes. Nao "corrigir" sem pedido
explicito.

**Erro classificado por codigo JSON-RPC, nao por texto de frontend.** O
`ZabbixApiError` carrega `code`/`message`/`data` do envelope; a classificacao
trabalha em cima disso. Nao ha mais texto de formulario para casar.

**Nomes passam por uma funcao so.** `host_names()` e a fonte unica do nome
tecnico e do nome visivel - log, pre-consulta e payload usam a saida dela, para
log e host nunca divergirem.

**`requests` com TLS verificado.** O servidor alvo tem HTTPS com certificado
valido. Nao adicionar `verify=False`.

**Importacao em thread dedicada.** `SessionWorker` vive em uma `QThread` e emite
sinais para a UI, para uma importacao longa nao travar a interface. O cancelamento
e por flag, checada entre linhas.

**Prefixo de relatorio `zabbix-import-`.** `REPORT_PREFIX` no core. O
`consolidate.py` le tambem o prefixo legado `zabbix-web-import-` para o
historico anterior a migracao continuar contando.

## Armadilhas conhecidas

- **`beautifulsoup4` foi removido do `requirements.txt`.** Existia so para raspar
  o token CSRF do frontend web. Nao reintroduzir: o transporte agora e JSON-RPC.
- **Ao editar o `.spec`, nao excluir modulos stdlib usados por dependencias.**
  `email` (requests/urllib3) e `xml` (openpyxl) ja quebraram o executavel quando
  foram excluidos. As exclusoes seguras sao modulos Qt grandes que o app nao usa.
- **O `.spec` aponta para `run_app.py`** e declara `zabbix_importer` em
  `hiddenimports` (o app importa o core da raiz do projeto).
- **`app/paths.py` decide onde gravar** testando escrita de verdade, porque
  `os.access(..., W_OK)` nao e confiavel no Windows. Recurso embutido vem de
  `sys._MEIPASS`; saida gerada (relatorios, log) nunca vai para la.
- **`app/` e a raiz precisam estar no `sys.path`.** Varios modulos fazem
  `sys.path.insert` da raiz antes de `import zabbix_importer as core`, para
  funcionar do codigo-fonte e empacotado.
- **Testes nao tocam a rede.** `TestClientRequest` troca `client._session.post`
  por um `fake_post` e enfileira respostas.

## Como rodar

Testes (120 no total, stdlib `unittest`, sem rede):

```powershell
python -m unittest discover -s tests -v
```

App:

```powershell
python -m app.main
```

ou `pythonw run_app.py` (producao, sem console).

Resumo de varias execucoes:

```powershell
python .\consolidate.py
```

Executavel:

```powershell
pip install "pyinstaller>=6,<7"
python -m PyInstaller --clean --noconfirm ImportadorCameras.spec
```

Instalador (Inno Setup 6):

```powershell
& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" instalador.iss
```

## Versao

Versao em dois lugares, que precisam andar juntas: `version_info.txt`
(metadados do `.exe`) e `AppVersion` em `instalador.iss`. O `AppId` do instalador
nao muda entre versoes - e ele que permite atualizar por cima e desinstalar.