# Changelog

Todas as mudanças notáveis deste projeto serão documentadas neste arquivo.

O formato é baseado no [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/),
e este projeto segue [Versionamento Semântico](https://semver.org/lang/pt-BR/).

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

[1.0.1]: https://github.com/lucasdaniel2201/zabbix-camera-importer/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/lucasdaniel2201/zabbix-camera-importer/releases/tag/v1.0.0
