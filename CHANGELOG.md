# Changelog

Todas as mudanças notáveis deste projeto serão documentadas neste arquivo.

O formato é baseado no [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/),
e este projeto segue [Versionamento Semântico](https://semver.org/lang/pt-BR/).

## [1.5.0] - 2026-10-05

### Alterado

- **A criação de hosts passa a usar a API JSON-RPC do Zabbix 6.4**, no lugar do
  envio pelo formulário web do frontend. O login é `user.login` com usuário e
  senha, e o token viaja no header `Authorization: Bearer`. A criação é **um
  `host.create` por câmera**, contra duas requisições pesadas e parse de HTML
  de antes. O Zabbix alvo responde `6.4.21` e o certificado TLS é validado.
- **Erros passam a ser reportados pelo código JSON-RPC** (`code`, `message`,
  `data`) em vez de texto de formulário, inclusive quando falta permissão na API.
- **Pré-consulta `host.get` antes do lote**, em blocos de 200, para marcar os
  hosts já existentes sem gastar chamada de criação. Falha na pré-consulta não
  aborta a importação, e "already exists" continua reconhecido como `exists` para
  a corrida entre a consulta e a criação.
- **O login resolve o Zabbix por IPv4** (`PREFER_IPV4`). O `urllib3` não
  implementa Happy Eyeballs (RFC 8305), então cada endereço IPv6 anunciado e não
  encaminhado custava ~21s de espera. Medido na rede do escritório: a primeira
  chamada caiu de **42,4s para 276ms**. As seguintes já eram rápidas por
  keep-alive; o timeout de 60s não foi alterado.
- **Endereço padrão corrigido** para `https://howbe.clouditservice.com.br`. O
  campo de URL vinha preenchido com `http://localhost/zabbix`, resto da era do
  frontend web, e falhava com `WinError 10061` antes de qualquer chamada de API.
  A API deste Zabbix responde na raiz do domínio — `/zabbix/api_jsonrpc.php`
  devolve 404.
- Núcleo do projeto passa a ser `zabbix_importer.py` (antes
  `zabbix_web_batch_import.py`): concentra o cliente da API, as dataclasses,
  as funções puras de normalização e montagem do host, a classificação de erro e
  a escrita de relatórios. `app/session.py` e `app/spreadsheet.py` consomem esse
  mesmo núcleo.
- Relatórios gerados com o prefixo `zabbix-import-`. O `consolidate.py` também
  lê o prefixo legado `zabbix-web-import-`, para o histórico anterior continuar
  contando.
- `inventory_mode` do host é `0` (manual) e não `-1` (desabilitado), para o
  inventário preenchido pela planilha poder ser editado à mão no Zabbix depois.
  O mapeamento de inventário do formulário anterior foi preservado, inclusive
  `inventory.type` = modelo e `inventory.name` = fabricante.

### Removido

- **Linha de comando.** `run_batches.py`, `xlsx_to_csv.py` e
  `validate_camera_names.py` saem, junto com o `exemplo_cameras.csv`. O app em
  PySide6 é o único ponto de entrada e lê `.xlsx` e `.csv` direto, sem script
  intermediário. `python .\consolidate.py` continua disponível para juntar o
  resumo de várias execuções.
- `beautifulsoup4` das dependências: existia só para raspar o token CSRF do
  frontend web, e o transporte agora é JSON-RPC.

### Adicionado

- `CONTEXT.md`: decisões de arquitetura do projeto e as armadilhas conhecidas.
- Suíte com **126 testes** (`unittest`, sem rede). `tests/test_core.py` foi
  substituído por `tests/test_importer.py`, que cobre normalização de nome,
  montagem do host, classificação de erro, o envelope JSON-RPC, Bearer, o
  relogin automático, o chunking da pré-consulta e a resolução por IPv4.

## [1.0.1] - 2026-09-28

### Adicionado

- `LICENSE` MIT, `CHANGELOG.md`, `.editorconfig` e `.gitattributes`.
- CI no GitHub Actions (`.github/workflows/tests.yml`): suíte de testes no Python
  3.12 e 3.14 e lint com Ruff.
- Configuração do Ruff em `pyproject.toml` e `requirements-dev.txt`.
- `tools/screenshots.py`: utilitário de desenvolvimento que gera as telas do
  README sem abrir janela, com dados fictícios.

### Alterado

- **Produto renomeado para "Importador Zabbix".** O nome anterior colidia com o
  do app irmão do NetBox: os dois geravam `ImportadorCameras.exe`,
  `ImportadorCamerasSetup-<versão>.exe` e a mesma pasta de instalação. O nome do
  instalador, do executável, dos metadados do `.exe` e a pasta de dados do
  usuário passam a ser "ImportadorZabbix".
- **`AppId` do instalador trocado** por causa da renomeação. Instalações
  anteriores precisam instalar esta versão por cima manualmente; não há upgrade
  automático a partir do `AppId` antigo.
- Removido o `Iniciar App.bat`: era um atalho de desenvolvimento que se confundia
  com o caminho do usuário final, que é o instalador da Release. Para rodar do
  código-fonte, use `python -m app.main`.

### Corrigido

- O rótulo do arquivo selecionado na tela de importação ficava preso em "Nenhum
  arquivo selecionado." mesmo depois de carregar uma planilha.

## [1.0.0] - 2026-09-18

### Adicionado

- Importador de hosts de câmera para o Zabbix usando o **frontend web** (login e
  `POST` do formulário `host.create`), e não a API por token — funciona onde a
  API HTTP está bloqueada.
- Interface desktop (PySide6): login, busca de grupos, templates e proxies no
  servidor, planilha modelo com colunas opcionais, preview com validação linha a
  linha e importação com barra de progresso.
- Normalização de nomes para ASCII (o Zabbix rejeita acentos e alguns
  caracteres); nomes que colidem após a normalização bloqueiam a importação, para
  você corrigir na planilha.
- Validação antes de importar: IP vazio, formato de IP inválido e nome inválido
  bloqueiam o botão de importar.
- Hosts já existentes são detectados e contabilizados como `exists`, sem
  interromper o lote.
- Relatórios por execução em log, JSON e CSV, e `consolidate.py` para juntar o
  resumo de várias execuções.
- Nenhuma credencial em disco: o app pede usuário e senha na tela, e a CLI usa
  `getpass`.
- Layout do host configurável por prefixo e sufixo de nome técnico e visível, e
  por grupos, templates e proxy (múltipla seleção em grupos e templates).
- Empacotamento em `.exe` único (PyInstaller) e instalador por usuário (Inno
  Setup), com opção portátil.
- Suíte de 102 testes com `unittest` (apenas stdlib), sem rede.

[1.5.0]: https://github.com/lucasdaniel2201/zabbix-camera-importer/compare/v1.0.1...v1.5.0
[1.0.1]: https://github.com/lucasdaniel2201/zabbix-camera-importer/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/lucasdaniel2201/zabbix-camera-importer/releases/tag/v1.0.0
