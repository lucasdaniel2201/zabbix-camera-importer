"""Janela principal do app de importacao de cameras para o Zabbix."""

import sys
from pathlib import Path

from PySide6.QtCore import QEvent, Qt, QThread, Signal
from PySide6.QtGui import QColor, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QStyle,
    QStyleOptionComboBox,
    QStylePainter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import zabbix_importer as core  # noqa: E402
from app.session import ImportOptions, SessionWorker  # noqa: E402
from app.spreadsheet import (  # noqa: E402
    COLUMNS_BY_KEY,
    FIXED_COLUMNS,
    SheetResult,
    read_file,
    writable_optional_columns,
    write_example_template,
)
from app.toast import ToastManager  # noqa: E402

DEFAULT_URL = "http://localhost/zabbix"
# Alturas dos banners (usadas tambem para nao cobrir com notificacoes).
LOGIN_BANNER_HEIGHT = 190
SETUP_BANNER_HEIGHT = 76
# Colunas fixas do preview; as demais entram conforme as colunas da planilha.
PREVIEW_BASE_COLUMNS = [
    "Linha",
    "Nome (original)",
    "Nome final no Zabbix",
    "IP",
    "MAC",
    "Fabricante",
    "Modelo",
]
PREVIEW_EXTRA_COLUMNS = [
    ("Tag", "Etiqueta"),
    ("Description", "Descrição"),
    ("Unidade", "Unidade"),
]
PREVIEW_STATUS_COLUMN = "Situacao"
TEMPLATE_FILENAME = "modelo_cameras.xlsx"
NO_PROXY = ("", "Sem proxy")


class ColumnsDialog(QDialog):
    """Escolha das colunas opcionais do modelo de planilha."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Colunas do modelo")
        self.setModal(True)
        self.setMinimumWidth(440)

        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        layout.addWidget(QLabel("Colunas fixas (sempre incluidas):"))
        fixed = QLabel(", ".join(COLUMNS_BY_KEY[key].label for key in FIXED_COLUMNS))
        fixed.setWordWrap(True)
        fixed.setStyleSheet("color: #6b7280;")
        layout.addWidget(fixed)

        hint = QLabel(
            "Escolha as colunas extras do modelo. Grupo de host, template e proxy sao "
            "definidos aqui na tela, na etapa de importacao (nao vao na planilha)."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #6b7280;")
        layout.addWidget(hint)
        layout.addSpacing(4)

        self._boxes: dict[str, QCheckBox] = {}
        for spec in writable_optional_columns():
            box = QCheckBox(spec.label)
            box.setChecked(True)
            box.setToolTip(spec.hint)
            layout.addWidget(box)
            self._boxes[spec.key] = box

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton("Cancelar")
        cancel.clicked.connect(self.reject)
        confirm = QPushButton("Gerar modelo")
        confirm.setObjectName("primaryButton")
        confirm.clicked.connect(self.accept)
        buttons.addWidget(cancel)
        buttons.addWidget(confirm)
        layout.addLayout(buttons)

    def selected_columns(self) -> list[str]:
        return [key for key, box in self._boxes.items() if box.isChecked()]


class MultiSelectCombo(QComboBox):
    """QComboBox com itens marcaveis (checkbox) e selecao multipla.

    O texto exibido resume os itens marcados; o popup nao fecha ao marcar.
    """

    selectionChanged = Signal()

    def __init__(self, placeholder: str, parent=None) -> None:
        super().__init__(parent)
        self._placeholder = placeholder
        self._model = QStandardItemModel(self)
        self.setModel(self._model)
        self._model.itemChanged.connect(self.update)
        self._model.itemChanged.connect(lambda _item: self.selectionChanged.emit())
        self.setMaxVisibleItems(12)
        self.setMinimumWidth(240)
        self.view().viewport().installEventFilter(self)
        self.setCurrentIndex(-1)

    def eventFilter(self, watched, event) -> bool:  # noqa: N802
        # Clique em qualquer parte da linha marca/desmarca o item e o popup
        # permanece aberto (o clique e consumido antes do comportamento padrao).
        if watched is self.view().viewport():
            if event.type() == QEvent.Type.MouseButtonPress:
                index = self.view().indexAt(event.pos())
                if index.isValid():
                    self._toggle(index.row())
                    event.accept()
                    return True
            elif event.type() == QEvent.Type.MouseButtonRelease:
                event.accept()
                return True
        return super().eventFilter(watched, event)

    def _toggle(self, row: int) -> None:
        item = self._model.item(row)
        new_state = (
            Qt.CheckState.Unchecked
            if item.checkState() == Qt.CheckState.Checked
            else Qt.CheckState.Checked
        )
        item.setCheckState(new_state)

    def _add_option(self, item_id: str, name: str) -> None:
        item = QStandardItem(name)
        item.setData(item_id, Qt.ItemDataRole.UserRole)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        item.setCheckState(Qt.CheckState.Unchecked)
        self._model.appendRow(item)

    def set_items(
        self,
        items: list[tuple[str, str]],
        preferred_ids: list[str],
        select_first_if_empty: bool = True,
    ) -> None:
        """Substitui as opcoes mantendo a selecao atual (ou marcando os preferidos)."""
        previously = self.selected_ids()
        self._model.clear()
        for item_id, name in items:
            self._add_option(item_id, name)

        wanted = previously or preferred_ids or []
        checked_any = False
        for item_id in wanted:
            row = self._row_of(item_id)
            if row is not None:
                self._model.item(row).setCheckState(Qt.CheckState.Checked)
                checked_any = True
        if not checked_any and self._model.rowCount() and select_first_if_empty:
            self._model.item(0).setCheckState(Qt.CheckState.Checked)
        self.update()

    def _row_of(self, item_id: str) -> int | None:
        for row in range(self._model.rowCount()):
            if str(self._model.item(row).data(Qt.ItemDataRole.UserRole)) == str(item_id):
                return row
        return None

    def selected_ids(self) -> list[str]:
        ids = []
        for row in range(self._model.rowCount()):
            item = self._model.item(row)
            if item.checkState() == Qt.CheckState.Checked:
                ids.append(str(item.data(Qt.ItemDataRole.UserRole)))
        return ids

    def _selected_names(self) -> list[str]:
        names = []
        for row in range(self._model.rowCount()):
            item = self._model.item(row)
            if item.checkState() == Qt.CheckState.Checked:
                names.append(item.text())
        return names

    def reset(self) -> None:
        self._model.clear()
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QStylePainter(self)
        option = QStyleOptionComboBox()
        self.initStyleOption(option)
        names = self._selected_names()
        if not names:
            option.currentText = self._placeholder
        elif len(names) <= 2:
            option.currentText = "; ".join(names)
        else:
            option.currentText = "; ".join(names[:2]) + f" (+{len(names) - 2})"
        painter.drawComplexControl(QStyle.ComplexControl.CC_ComboBox, option)
        painter.drawControl(QStyle.ControlElement.CE_ComboBoxLabel, option)


class SettingsDialog(QDialog):
    """Configuracoes: URL do Zabbix, porta e encerramento de sessao."""

    def __init__(self, url: str, port: str, connected: bool, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Configuracoes")
        self.setModal(True)
        self.setMinimumWidth(380)
        self._logout_requested = False

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        form = QFormLayout()
        self.url_edit = QLineEdit(url)
        self.port_spin = QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(int(port))
        form.addRow("URL do Zabbix:", self.url_edit)
        form.addRow("Porta da interface:", self.port_spin)
        layout.addLayout(form)

        note = QLabel("A URL e usada na proxima conexao. A porta e usada na criacao dos hosts.")
        note.setWordWrap(True)
        note.setStyleSheet("color: #666;")
        layout.addWidget(note)

        buttons = QHBoxLayout()
        save_button = QPushButton("Salvar")
        save_button.setObjectName("primaryButton")
        save_button.clicked.connect(self.accept)
        cancel_button = QPushButton("Cancelar")
        cancel_button.clicked.connect(self.reject)
        buttons.addStretch(1)
        buttons.addWidget(cancel_button)
        buttons.addWidget(save_button)
        layout.addLayout(buttons)

        if connected:
            def on_logout() -> None:
                self._logout_requested = True
                self.accept()

            logout_button = QPushButton("Encerrar sessao")
            logout_button.setStyleSheet(
                "QPushButton { color: #b3261e; border: 1px solid #b3261e; background: transparent; }"
            )
            logout_button.clicked.connect(on_logout)
            layout.addWidget(logout_button)

    @property
    def url(self) -> str:
        return self.url_edit.text().strip()

    @property
    def port(self) -> str:
        return str(self.port_spin.value())

    @property
    def logout_requested(self) -> bool:
        return self._logout_requested


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Importador de Cameras - Zabbix")
        self.resize(1240, 900)

        self._sheet: SheetResult | None = None
        self._file_path: Path | None = None
        self._connected = False
        self._session_username = ""
        self._proxy_names: dict[str, str] = {}
        self._importing = False
        self._url = DEFAULT_URL
        self._port = core.DEFAULT_PORT

        self._build_ui()
        self._start_session_thread()

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        self._stack = QStackedWidget()
        self.setCentralWidget(self._stack)
        self._stack.addWidget(self._build_login_page())
        self._stack.addWidget(self._build_setup_page())
        self._toast = ToastManager(self)
        self._toast.set_top_offset(LOGIN_BANNER_HEIGHT + 14)
        self._update_import_button()

    def _build_login_page(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        outer.addWidget(self._build_brand_banner(LOGIN_BANNER_HEIGHT))

        body = QVBoxLayout()
        body.setContentsMargins(24, 28, 24, 20)
        body.addStretch(1)

        card = QFrame()
        card.setObjectName("card")
        card.setFixedWidth(440)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(32, 30, 32, 26)
        card_layout.setSpacing(10)

        title = QLabel("Acesse sua conta")
        title.setObjectName("cardTitle")
        subtitle = QLabel("Entre com seu usuario do Zabbix para comecar.")
        subtitle.setObjectName("cardSubtitle")
        subtitle.setWordWrap(True)
        card_layout.addWidget(title)
        card_layout.addWidget(subtitle)
        card_layout.addSpacing(8)

        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.username_edit = QLineEdit()
        self.username_edit.setPlaceholderText("ex.: seu.usuario")
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_edit.setPlaceholderText("Sua senha")
        self.password_edit.returnPressed.connect(self._on_connect_clicked)
        form.addRow(self._field_label("Usuario"), self.username_edit)
        form.addRow(self._field_label("Senha"), self.password_edit)
        card_layout.addLayout(form)

        self.login_error_label = QLabel("")
        self.login_error_label.setWordWrap(True)
        self.login_error_label.setStyleSheet("color: #cf1620; font-weight: 600;")
        self.login_error_label.hide()
        card_layout.addWidget(self.login_error_label)

        card_layout.addSpacing(4)
        self.login_button = QPushButton("Entrar")
        self.login_button.setObjectName("primaryButton")
        self.login_button.setMinimumHeight(40)
        self.login_button.clicked.connect(self._on_connect_clicked)
        card_layout.addWidget(self.login_button)

        settings_row = QHBoxLayout()
        settings_row.addStretch(1)
        self.settings_button = QPushButton("Configuracoes")
        self.settings_button.setObjectName("flatButton")
        self.settings_button.clicked.connect(self._open_settings)
        settings_row.addWidget(self.settings_button)
        card_layout.addLayout(settings_row)

        body.addWidget(card, 0, Qt.AlignmentFlag.AlignHCenter)
        body.addStretch(1)

        footer = QLabel("Importador de Cameras para o Zabbix")
        footer.setObjectName("loginFooter")
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        body.addWidget(footer)

        outer.addLayout(body, stretch=1)
        return page

    def _build_brand_banner(self, height: int) -> QFrame:
        banner = QFrame()
        banner.setObjectName("brandBanner")
        banner.setFixedHeight(height)
        row = QHBoxLayout(banner)
        row.setContentsMargins(34, 16, 34, 16)
        row.setSpacing(18)

        text_col = QVBoxLayout()
        text_col.setSpacing(0)
        title = QLabel("Importador de Cameras")
        title.setObjectName("brandTitle")
        subtitle = QLabel("Envio de cameras para o Zabbix")
        subtitle.setObjectName("brandSubtitle")
        text_col.addWidget(title)
        text_col.addWidget(subtitle)
        row.addLayout(text_col)
        row.addStretch(1)
        return banner

    def _build_setup_page(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Banner da marca com a sessao
        banner = QFrame()
        banner.setObjectName("brandBanner")
        banner.setFixedHeight(SETUP_BANNER_HEIGHT)
        bar = QHBoxLayout(banner)
        bar.setContentsMargins(26, 12, 26, 12)
        bar.setSpacing(14)

        text_col = QVBoxLayout()
        text_col.setSpacing(0)
        title = QLabel("Importador de Cameras")
        title.setObjectName("brandTitle")
        subtitle = QLabel("Envio de cameras para o Zabbix")
        subtitle.setObjectName("brandSubtitle")
        text_col.addWidget(title)
        text_col.addWidget(subtitle)
        bar.addLayout(text_col)
        bar.addStretch(1)

        self.session_label = QLabel("")
        self.session_label.setObjectName("brandSession")
        bar.addWidget(self.session_label)

        self.refresh_button = QPushButton("Atualizar listas")
        self.refresh_button.setObjectName("bannerButton")
        self.refresh_button.clicked.connect(self._on_refresh_clicked)
        bar.addWidget(self.refresh_button)

        self.logout_button = QPushButton("Sair")
        self.logout_button.setObjectName("bannerButton")
        self.logout_button.clicked.connect(self._on_logout_clicked)
        bar.addWidget(self.logout_button)

        outer.addWidget(banner)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        layout.addWidget(self._build_sheet_box())
        layout.addWidget(self._build_options_box())

        # Preview
        self.preview_label = QLabel("Nenhuma planilha carregada.")
        self.preview_label.setWordWrap(True)
        layout.addWidget(self.preview_label)

        self.preview_table = QTableWidget(0, len(PREVIEW_BASE_COLUMNS) + 1)
        self.preview_table.setHorizontalHeaderLabels([*PREVIEW_BASE_COLUMNS, PREVIEW_STATUS_COLUMN])
        self.preview_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.preview_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.preview_table.setAlternatingRowColors(True)
        self.preview_table.verticalHeader().setVisible(False)
        self.preview_table.verticalHeader().setDefaultSectionSize(32)
        self.preview_table.setMinimumHeight(380)
        preview_font = self.font()
        preview_font.setPointSize(10)
        self.preview_table.setFont(preview_font)
        header = self.preview_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        header.setMinimumHeight(30)
        layout.addWidget(self.preview_table, stretch=1)

        # Rodape
        footer = QHBoxLayout()
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        footer.addWidget(self.progress_bar, stretch=1)
        self.cancel_button = QPushButton("Cancelar")
        self.cancel_button.setVisible(False)
        self.cancel_button.clicked.connect(self._on_cancel_clicked)
        footer.addWidget(self.cancel_button)
        self.import_button = QPushButton("Importar cameras")
        self.import_button.setEnabled(False)
        self.import_button.setObjectName("primaryButton")
        self.import_button.setMinimumHeight(36)
        self.import_button.clicked.connect(self._on_import_clicked)
        footer.addWidget(self.import_button)
        layout.addLayout(footer)

        outer.addWidget(content, stretch=1)
        return page

    def _build_sheet_box(self) -> QGroupBox:
        box = QGroupBox("1. Planilha de cameras")
        row = QHBoxLayout(box)

        self.download_template_button = QPushButton("Baixar modelo de exemplo")
        self.download_template_button.clicked.connect(self._on_download_template)
        row.addWidget(self.download_template_button)

        self.choose_file_button = QPushButton("Escolher planilha (xlsx ou csv)")
        self.choose_file_button.setObjectName("primaryButton")
        self.choose_file_button.clicked.connect(self._on_choose_file)
        row.addWidget(self.choose_file_button)

        self.file_label = QLabel("Nenhum arquivo selecionado.")
        self.file_label.setStyleSheet("color: #666;")
        row.addWidget(self.file_label, stretch=1)
        return box

    def _build_options_box(self) -> QGroupBox:
        box = QGroupBox("2. Opcoes de criacao")
        layout = QHBoxLayout(box)

        name_form = QFormLayout()
        self.prefix_edit = QLineEdit()
        self.prefix_edit.setPlaceholderText("ex.: CAM - ")
        self.suffix_edit = QLineEdit()
        self.suffix_edit.setPlaceholderText("ex.: - v1")
        name_form.addRow("Prefixo (opcional):", self.prefix_edit)
        name_form.addRow("Sufixo (opcional):", self.suffix_edit)
        layout.addLayout(name_form)

        layout.addSpacing(16)

        select_form = QFormLayout()
        self.group_combo = MultiSelectCombo("Nenhum grupo selecionado")
        self.template_combo = MultiSelectCombo("Nenhum template selecionado")
        self.proxy_combo = QComboBox()
        select_form.addRow(
            self._label_with_help("Grupos:", "Marque um ou mais grupos - o host sera adicionado a todos."),
            self.group_combo,
        )
        select_form.addRow(
            self._label_with_help("Templates:", "Marque um ou mais templates - todos serao vinculados ao host."),
            self.template_combo,
        )
        select_form.addRow("Proxy:", self.proxy_combo)
        layout.addLayout(select_form, stretch=1)

        hint = QLabel(
            "Os nomes sao normalizados (sem acentos ou caracteres invalidos) e os "
            "duplicados apos a normalizacao sao bloqueados na validacao.\n"
            "Grupos e templates aceitam multipla selecao (marque os checkbox)."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #666;")
        layout.addWidget(hint)

        for field in (self.prefix_edit, self.suffix_edit):
            field.textChanged.connect(self._refresh_preview_names)

        # Marcacao de grupo define se a importacao pode comecar.
        self.group_combo.selectionChanged.connect(self._update_import_button)
        self.template_combo.selectionChanged.connect(self._update_import_button)

        for combo in (self.group_combo, self.template_combo, self.proxy_combo):
            combo.setEnabled(False)

        return box

    # ------------------------------------------------------------ sessao thread
    def _start_session_thread(self) -> None:
        self._session_thread = QThread(self)
        self._session = SessionWorker()
        self._session.moveToThread(self._session_thread)
        self._session.connected.connect(self._on_connected)
        self._session.connect_failed.connect(self._on_connect_failed)
        self._session.disconnected.connect(self._on_disconnected)
        self._session.options_ready.connect(self._on_options_ready)
        self._session.options_failed.connect(self._on_options_failed)
        self._session.progress.connect(self._on_progress)
        self._session.import_done.connect(self._on_import_done)
        self._session.import_failed.connect(self._on_import_failed)
        self._session_thread.start()

    # ------------------------------------------------------ acoes do usuario
    def _open_settings(self) -> None:
        dialog = SettingsDialog(self._url, self._port, self._connected, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        if dialog.logout_requested:
            self._on_logout_clicked()
            return
        new_url = dialog.url or DEFAULT_URL
        if new_url != self._url:
            self._url = new_url
            self._notify("URL do Zabbix atualizada.", "info")
        self._port = dialog.port

    def _on_download_template(self) -> None:
        dialog = ColumnsDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        selected = dialog.selected_columns()

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Salvar modelo de exemplo",
            str(Path.home() / TEMPLATE_FILENAME),
            "Excel (*.xlsx)",
        )
        if not path:
            return
        try:
            write_example_template(Path(path), selected)
        except Exception as exc:
            self._notify(f"Nao foi possivel salvar o modelo: {exc}", "error")
            return
        self._notify(
            f"Modelo salvo com {len(FIXED_COLUMNS) + len(selected)} colunas. "
            "Preencha uma linha por camera, mantendo o cabecalho.",
            "success",
        )

    def _on_choose_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Escolher planilha",
            str(Path.home()),
            "Planilhas (*.xlsx *.csv);;Excel (*.xlsx);;CSV (*.csv)",
        )
        if not path:
            return
        self._load_file(Path(path))

    def _on_connect_clicked(self) -> None:
        username = self.username_edit.text().strip()
        password = self.password_edit.text()
        if not username or not password:
            self._show_login_error("Informe usuario e senha.")
            return
        self._hide_login_error()
        self.login_button.setEnabled(False)
        self.login_button.setText("Conectando...")
        for field in (self.username_edit, self.password_edit):
            field.setEnabled(False)
        self._session.request_connect.emit(self._url, username, password)

    def _on_logout_clicked(self) -> None:
        self._session.request_logout.emit()

    def _on_refresh_clicked(self) -> None:
        self._session.request_refresh.emit()

    def _on_cancel_clicked(self) -> None:
        if self._session is not None:
            self._session.request_cancel.emit()
            self.cancel_button.setEnabled(False)
            self._notify("Cancelando apos o registro atual...", "info")

    def _on_import_clicked(self) -> None:
        if self._sheet is None or self._importing:
            return
        valid_rows = self._sheet.valid_rows
        if not valid_rows:
            return

        options = self._current_options()
        self._importing = True
        self._set_importing_state(True)
        self._notify(
            f"Importando {len(valid_rows)} cameras...",
            "info",
            duration_ms=2000,
        )
        self._session.request_import.emit(valid_rows, options)

    # ------------------------------------------------------- callbacks da sessao
    def _on_connected(self, username: str) -> None:
        self._connected = True
        self._session_username = username
        self.session_label.setText(f"Conectado como {username}")
        self.password_edit.clear()
        self._go_setup()
        self._notify(f"Conectado ao Zabbix como {username}.", "success")

    def _on_connect_failed(self, message: str) -> None:
        self._connected = False
        self._go_login()
        self._show_login_error(f"Falha na conexao: {message}")
        self._notify(f"Falha na conexao: {message}", "error")

    def _on_disconnected(self) -> None:
        self._connected = False
        self._session_username = ""
        self.session_label.setText("")
        self._proxy_names = {}
        self.group_combo.reset()
        self.template_combo.reset()
        self.proxy_combo.clear()
        for combo in (self.group_combo, self.template_combo, self.proxy_combo):
            combo.setEnabled(False)
        self._go_login()
        self._notify("Sessao encerrada.", "info")
        self._update_import_button()

    def _on_options_ready(
        self,
        groups: list[tuple[str, str]],
        proxies: list[tuple[str, str]],
        templates: list[tuple[str, str]],
    ) -> None:
        # Grupos e templates comecam sem nenhuma marcacao; o proxy mantem o default.
        self.group_combo.set_items(groups, [], select_first_if_empty=False)
        self.template_combo.set_items(
            templates, core.DEFAULT_TEMPLATE_IDS, select_first_if_empty=False
        )
        proxy_items = [(proxy_id, name) for proxy_id, name in proxies]
        self._proxy_names = {proxy_id: name for proxy_id, name in proxies}
        self._fill_combo(self.proxy_combo, [NO_PROXY, *proxy_items], [core.DEFAULT_PROXY_ID])
        for combo in (self.group_combo, self.template_combo, self.proxy_combo):
            combo.setEnabled(True)

        self._refresh_preview()
        self._update_import_button()

        self._notify(
            f"Listas atualizadas: {len(groups)} grupos, {len(templates)} templates "
            f"e {len(proxies)} proxies disponiveis. Marque ao menos um grupo.",
            "info",
        )

    def _on_options_failed(self, message: str) -> None:
        self._notify(f"Falha ao buscar as listas do servidor: {message}", "error")

    def _fill_combo(
        self,
        combo: QComboBox,
        items: list[tuple[str, str]],
        preferred_ids: list[str],
    ) -> None:
        current_id = combo.currentData() if combo.count() else None
        combo.clear()
        for item_id, name in items:
            combo.addItem(name, item_id)
        if current_id is not None and combo.findData(current_id) >= 0:
            combo.setCurrentIndex(combo.findData(current_id))
            return
        for preferred_id in preferred_ids:
            index = combo.findData(preferred_id)
            if index >= 0:
                combo.setCurrentIndex(index)
                return
        if combo.count():
            combo.setCurrentIndex(0)

    # ------------------------------------------------------------- planilha
    def _load_file(self, path: Path) -> None:
        try:
            sheet = read_file(path)
        except Exception as exc:
            self._sheet = None
            self._file_path = None
            self._clear_preview()
            self._notify(f"Planilha invalida: {exc}", "error")
            return

        self._sheet = sheet
        self._file_path = path
        valid = len(sheet.valid_rows)
        errors = len(sheet.rows_with_errors)
        ignored = sheet.skipped_empty + sheet.skipped_trocas
        if errors:
            self._notify(
                f"{path.name}: {valid} linhas validas, mas {errors} com erro - "
                "corrija e carregue novamente.",
                "error",
            )
        else:
            self._notify(
                f"{path.name}: {valid} cameras prontas para importar "
                f"({ignored} ignoradas).",
                "success",
            )
        # Avisos de leitura (encoding etc.) sao complementares, nao uma nova acao.
        if sheet.file_warnings:
            self._notify("; ".join(sheet.file_warnings), "warning")
        self._refresh_preview()
        self._update_import_button()

    def _refresh_preview_names(self, *_args: object) -> None:
        if self._sheet is None:
            return
        prefix = self._typed_text(self.prefix_edit)
        suffix = self._typed_text(self.suffix_edit)
        for row_index, row in enumerate(self._sheet.rows):
            item = self.preview_table.item(row_index, 2)
            if item is not None:
                item.setText(f"{prefix}{row.name_normalized}{suffix}")

    def _preview_headers(self) -> list[str]:
        """Cabecalhos do preview: base + extras presentes na planilha + situacao."""
        headers = list(PREVIEW_BASE_COLUMNS)
        sheet = self._sheet
        if sheet is not None:
            for key, label in PREVIEW_EXTRA_COLUMNS:
                if key in sheet.columns_found:
                    headers.append(label)
        headers.append(PREVIEW_STATUS_COLUMN)
        return headers

    def _refresh_preview(self) -> None:
        sheet = self._sheet
        if sheet is None:
            return
        prefix = self._typed_text(self.prefix_edit)
        suffix = self._typed_text(self.suffix_edit)

        extra_columns = [
            key for key, _label in PREVIEW_EXTRA_COLUMNS if key in sheet.columns_found
        ]
        headers = self._preview_headers()
        self.preview_table.clearContents()
        self.preview_table.setColumnCount(len(headers))
        self.preview_table.setHorizontalHeaderLabels(headers)
        self.preview_table.setRowCount(len(sheet.rows))

        color_error = QColor("#b3261e")
        color_warning = QColor("#8a6d00")
        status_index = len(headers) - 1

        for index, row in enumerate(sheet.rows):
            cells = row.cells
            values = [
                str(row.row_number),
                row.name_original,
                f"{prefix}{row.name_normalized}{suffix}",
                cells.get("IP", ""),
                cells.get("MAC address", ""),
                cells.get("Vendor", ""),
                cells.get("Model", ""),
            ]
            values.extend(cells.get(key, "") for key in extra_columns)

            issues = row.issues
            if issues:
                values.append("ERRO: " + " | ".join(issues))
            elif row.warnings:
                values.append("aviso: " + " | ".join(row.warnings))
            else:
                values.append("OK")

            for column, text in enumerate(values):
                item = QTableWidgetItem(text)
                if issues:
                    item.setForeground(color_error)
                elif column == status_index and row.warnings:
                    item.setForeground(color_warning)
                self.preview_table.setItem(index, column, item)

        valid = len(sheet.valid_rows)
        errors = len(sheet.rows_with_errors)
        ignored = sheet.skipped_empty + sheet.skipped_trocas
        if errors:
            status = (
                f"Linhas validas: {valid} | COM ERRO: {errors} | ignoradas: {ignored}\n"
                "Corrija os erros na planilha e carregue novamente - a importacao so "
                "libera quando todas as linhas estao validas."
            )
            self.preview_label.setText(status)
            self.preview_label.setStyleSheet("color: #b3261e; font-weight: bold;")
        else:
            self.preview_label.setText(
                f"Linhas validas: {valid} | ignoradas: {ignored} | total a importar: {valid}"
            )
            self.preview_label.setStyleSheet("color: #1b7f3b; font-weight: bold;")

    @staticmethod
    def _typed_text(edit: QLineEdit) -> str:
        """Texto como digitado; preserva espacos no inicio/fim (ex.: prefixo 'CAM - ')."""
        text = edit.text()
        return text if text.strip() else ""

    @staticmethod
    def _field_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("fieldLabel")
        return label

    @staticmethod
    def _help_icon(tooltip: str) -> QLabel:
        icon = QLabel("?")
        icon.setFixedSize(16, 16)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet(
            "QLabel { background: #2563eb; color: #ffffff; border-radius: 8px;"
            " font-weight: bold; font-size: 10px; }"
        )
        icon.setCursor(Qt.CursorShape.WhatsThisCursor)
        icon.setToolTip(tooltip)
        return icon

    def _label_with_help(self, text: str, tooltip: str) -> QWidget:
        container = QWidget()
        row = QHBoxLayout(container)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)
        row.addWidget(self._field_label(text))
        row.addWidget(self._help_icon(tooltip))
        row.addStretch(1)
        return container

    # --------------------------------------------------------------- opcoes
    def _selected_id(self, combo: QComboBox) -> str:
        return str(combo.currentData() or "")

    def _current_options(self) -> ImportOptions:
        proxy_id = self._selected_id(self.proxy_combo) if self.proxy_combo.count() else core.DEFAULT_PROXY_ID
        return ImportOptions(
            url=self._url,
            port=self._port,
            host_prefix=self._typed_text(self.prefix_edit),
            host_suffix=self._typed_text(self.suffix_edit),
            visible_name_prefix=self._typed_text(self.prefix_edit),
            visible_name_suffix=self._typed_text(self.suffix_edit),
            group_ids=self.group_combo.selected_ids() or list(core.DEFAULT_GROUP_IDS),
            template_ids=self.template_combo.selected_ids() or list(core.DEFAULT_TEMPLATE_IDS),
            proxy_id=proxy_id,
            proxy_name=self._proxy_names.get(proxy_id, "") if proxy_id else "",
        )

    # ------------------------------------------------------------- estados
    def _go_login(self) -> None:
        self._stack.setCurrentIndex(0)
        self._toast.set_top_offset(LOGIN_BANNER_HEIGHT + 14)
        self.login_button.setEnabled(True)
        self.login_button.setText("Entrar")
        for field in (self.username_edit, self.password_edit):
            field.setEnabled(True)

    def _go_setup(self) -> None:
        self._stack.setCurrentIndex(1)
        self._toast.set_top_offset(SETUP_BANNER_HEIGHT + 14)
        self._update_import_button()

    def _show_login_error(self, message: str) -> None:
        self.login_error_label.setText(message)
        self.login_error_label.show()

    def _hide_login_error(self) -> None:
        self.login_error_label.hide()
        self.login_error_label.setText("")

    def _set_importing_state(self, importing: bool) -> None:
        self._importing = importing
        self.import_button.setEnabled(False)
        self.cancel_button.setVisible(importing)
        self.cancel_button.setEnabled(True)
        self.progress_bar.setVisible(importing)
        self.refresh_button.setEnabled(not importing)
        self.logout_button.setEnabled(not importing)

    def _update_import_button(self) -> None:
        sheet = self._sheet
        if self._importing:
            self.import_button.setEnabled(False)
            return
        if sheet is None or not sheet.rows:
            self.import_button.setEnabled(False)
            self.import_button.setText("Importar cameras")
            return
        valid = len(sheet.valid_rows)
        if sheet.rows_with_errors:
            self.import_button.setEnabled(False)
            self.import_button.setText("Corrija os erros na planilha")
        elif not self._connected:
            self.import_button.setEnabled(False)
            self.import_button.setText("Conecte ao Zabbix primeiro")
        elif not self.group_combo.selected_ids():
            self.import_button.setEnabled(False)
            self.import_button.setText("Marque ao menos um grupo")
        else:
            self.import_button.setEnabled(True)
            self.import_button.setText(f"Importar {valid} cameras")

    def _on_progress(self, index: int, total: int, host: str, status: str) -> None:
        self.progress_bar.setRange(0, total)
        self.progress_bar.setValue(index)
        self.progress_bar.setFormat(f"{index}/{total} | {host} | {status}")

    def _on_import_failed(self, message: str) -> None:
        self._set_importing_state(False)
        self._update_import_button()
        self._notify(f"Falha na importacao: {message}", "error")

    def _on_import_done(self, summary: dict) -> None:
        self._set_importing_state(False)
        self._update_import_button()
        canceled = summary.get("canceled")
        errors = summary["errors"]
        kind = "warning" if canceled else ("error" if errors else "success")
        parts = [
            f"Importacao concluida: {summary['created']} criados, "
            f"{summary['exists']} ja existiam, {errors} erros."
        ]
        if canceled:
            parts.append("Cancelado pelo usuario (parcial).")
        parts.append(f"Relatorio salvo em: {summary['json_report_path']}")
        self._notify(" ".join(parts), kind)

    def _clear_preview(self) -> None:
        self.preview_table.setRowCount(0)
        self.preview_label.setText("Nenhuma planilha carregada.")
        self.preview_label.setStyleSheet("color: #666;")

    def _notify(self, message: str, kind: str = "info", duration_ms: int | None = None) -> None:
        self._toast.notify(message, kind, duration_ms)

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._importing:
            answer = QMessageBox.question(
                self,
                "Importacao em andamento",
                "Ha uma importacao em andamento. Fechar a janela interrompe o processo.",
            )
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self._session.cancel()
        self._session_thread.quit()
        self._session_thread.wait(5000)
        super().closeEvent(event)
