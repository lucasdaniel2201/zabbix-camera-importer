"""Sessao unica com o Zabbix, executada em thread dedicada.

O SessionWorker e dono de um unico ZabbixApiClient (e do seu token):
logar, listar grupos/templates/proxies e importar acontecem todos na mesma
thread e reusam o mesmo token - sem novo login entre importacoes.
"""

import sys
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import zabbix_importer as core  # noqa: E402
from app.paths import output_dir  # noqa: E402
from app.spreadsheet import parse_tags  # noqa: E402


def report_dir_path() -> Path:
    """Pasta de relatorios (ao lado do .exe quando empacotado)."""
    return output_dir("reports")


# ImportOptions agora vem do core (zabbix_importer.py)
ImportOptions = core.ImportOptions


class SessionWorker(QObject):
    # Sinais de requisicao: emitidos pela UI (main thread) e executados na
    # thread da sessao via conexao enfileirada.
    request_connect = Signal(object, object, object)
    request_refresh = Signal()
    request_import = Signal(object, object)
    request_cancel = Signal()
    request_logout = Signal()

    connected = Signal(str)  # usuario conectado
    disconnected = Signal()
    connect_failed = Signal(str)
    options_ready = Signal(list, list, list)  # groups, proxies, templates: [(id, nome)]
    options_failed = Signal(str)
    progress = Signal(int, int, str, str)  # indice, total, host, status
    log = Signal(str)
    import_done = Signal(dict)
    import_failed = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._client: core.ZabbixApiClient | None = None
        self._url = ""
        self._username = ""
        self._cancel = False

        self.request_connect.connect(self.connect_zabbix)
        self.request_refresh.connect(self.refresh_options)
        self.request_import.connect(self.import_rows)
        self.request_cancel.connect(self.cancel)
        self.request_logout.connect(self.logout)

    # ------------------------------------------------------------------ estado
    @property
    def connected_client(self) -> core.ZabbixApiClient | None:
        return self._client

    @property
    def url(self) -> str:
        return self._url

    # ------------------------------------------------------------ acoes (slots)
    @Slot(object, object, object)
    def connect_zabbix(self, url: str, username: str, password: str) -> None:
        try:
            client = core.ZabbixApiClient(base_url=url, username=username, password=password)
            client.login()
        except Exception as exc:
            self.connect_failed.emit(str(exc))
            return

        self._client = client
        self._url = url.rstrip("/")
        self._username = username
        self._cancel = False
        self.connected.emit(username)
        self.refresh_options()

    @Slot()
    def refresh_options(self) -> None:
        client = self._client
        if client is None:
            self.options_failed.emit("Nao ha sessao conectada.")
            return
        try:
            opts = client.fetch_options()
        except Exception as exc:
            self.options_failed.emit(f"Falha ao consultar opcoes do Zabbix: {exc}")
            return
        self.options_ready.emit(opts["groups"], opts["proxies"], opts["templates"])

    @Slot(object, object)
    def import_rows(self, rows: list, options: ImportOptions) -> None:
        """Importa registros validos usando a sessao ja aberta."""
        client = self._client
        if client is None:
            self.import_failed.emit("Sessao desconectada. Conecte novamente.")
            return

        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        try:
            report_dir = report_dir_path()
        except Exception as exc:
            self.import_failed.emit(f"Falha ao criar a pasta de relatorios: {exc}")
            return

        log_path = report_dir / f"{core.REPORT_PREFIX}{timestamp}.log"
        json_report_path = report_dir / f"{core.REPORT_PREFIX}{timestamp}.json"
        csv_report_path = report_dir / f"{core.REPORT_PREFIX}{timestamp}.csv"

        lines: list[str] = []

        def emit_log(message: str) -> None:
            lines.append(message)
            self.log.emit(message)

        # Pre-consulta hosts existentes para evitar erros "ja existe"
        all_host_names = []
        for row in rows:
            technical, _visible = core.host_names(row.name_normalized, options)
            all_host_names.append(technical)

        existing: set[str] = set()
        if all_host_names:
            try:
                existing = client.existing_hosts(all_host_names)
                if existing:
                    emit_log(f"Hosts ja existentes detectados: {len(existing)}")
            except Exception as exc:
                emit_log(f"Aviso: falha ao verificar hosts existentes: {exc}")

        emit_log(f"=== Importacao iniciada em {timestamp} ===")
        emit_log(f"Registros validos: {len(rows)}")
        emit_log(f"URL: {options.url or self._url}")

        results: list[dict] = []
        created = 0
        exists = 0
        errors = 0
        canceled = False
        total = len(rows)

        for index, row in enumerate(rows, start=1):
            if self._cancel:
                canceled = True
                emit_log("Execucao cancelada pelo usuario.")
                break

            record = core.CameraRecord(
                csv_index=row.row_number,
                name=row.name_normalized,
                vendor=row.cells.get("Vendor", ""),
                model=row.cells.get("Model", ""),
                firmware=row.cells.get("Firmware", ""),
                ip=row.cells.get("IP", ""),
                mac_address=row.cells.get("MAC address", ""),
                description=row.cells.get("Description", ""),
                tags=parse_tags(row.cells.get("Tag", "")),
            )
            technical, visible = core.host_names(row.name_normalized, options)

            # Ja existe? Marca sem chamar a API
            if technical in existing:
                status = "exists"
                message = "Host ja existe"
                emit_log(f"Ja existia | {technical}")
            else:
                try:
                    host_params = core.build_host_params(
                        record=record,
                        technical_name=technical,
                        visible_name=visible,
                        options=options,
                    )
                    result = client.create_host(host_params)
                    status, message = core.parse_api_result(result)
                except Exception as exc:
                    status, message = core.classify_api_error(exc)

            results.append({
                "csv_index": row.row_number,
                "host": technical,
                "visible_name": visible,
                "ip": row.cells.get("IP", ""),
                "status": status,
                "message": message,
                "vendor": row.cells.get("Vendor", ""),
                "model": row.cells.get("Model", ""),
            })

            if status == "created":
                created += 1
                emit_log(f"Criado | {technical}")
            elif status == "exists":
                exists += 1
                emit_log(f"Ja existia | {technical} | {message}")
            else:
                errors += 1
                emit_log(f"Falhou | {technical} | {message}")

            self.progress.emit(index, total, technical, status)

        summary = {
            "timestamp": timestamp,
            "url": options.url or self._url,
            "proxy_id": options.proxy_id,
            "proxy_name": options.proxy_name,
            "csv": "planilha (app)",
            "offset": 0,
            "processed": len(results),
            "created": created,
            "exists": exists,
            "errors": errors,
            "canceled": canceled,
            "log_path": str(log_path.resolve()),
            "json_report_path": str(json_report_path.resolve()),
            "csv_report_path": str(csv_report_path.resolve()),
        }

        try:
            with log_path.open("w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
            core.write_json_report(json_report_path, summary, results)
            core.write_csv_report(csv_report_path, results)
            emit_log("=== Execucao finalizada ===")
            emit_log(
                f"Resumo | processados={summary['processed']} | "
                f"criados={created} | existentes={exists} | erros={errors}"
            )
            emit_log(f"Relatorios salvos em: {report_dir}")
        except Exception as exc:
            self.import_failed.emit(f"Falha ao salvar relatorios: {exc}")

        self.import_done.emit(summary)

    @Slot()
    def cancel(self) -> None:
        self._cancel = True

    @Slot()
    def logout(self) -> None:
        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                pass
        self._client = None
        self._url = ""
        self._username = ""
        self._cancel = False
        self.disconnected.emit()
