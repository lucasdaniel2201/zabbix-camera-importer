import argparse
import csv
import getpass
import json
import logging
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import requests
from bs4 import BeautifulSoup

DEFAULT_GROUP_IDS: list[str] = []
DEFAULT_TEMPLATE_IDS: list[str] = []
DEFAULT_PROXY_ID = ""
DEFAULT_PROXY_NAME = ""
DEFAULT_PORT = "10051"
DEFAULT_INTERFACE_ID = "1"
DEFAULT_HOST_PREFIX = ""
DEFAULT_HOST_SUFFIX = " - v1"
DEFAULT_VISIBLE_NAME_PREFIX = ""
DEFAULT_VISIBLE_NAME_SUFFIX = " - v1"


@dataclass
class CameraRecord:
    csv_index: int
    name: str
    vendor: str
    model: str
    firmware: str
    ip: str
    mac_address: str
    description: str = ""
    tags: list[tuple[str, str]] = field(default_factory=list)


class ZabbixWebError(RuntimeError):
    pass


class ZabbixWebClient:
    def __init__(self, base_url: str, username: str, password: str, timeout: int = 60) -> None:
        self.base_url = base_url.rstrip("/") + "/"
        self.username = username
        self.password = password
        self.timeout = timeout
        self.session = requests.Session()

    def login(self) -> None:
        response = self.session.post(
            self.base_url + "index.php",
            data={
                "name": self.username,
                "password": self.password,
                "autologin": "1",
                "enter": "Conectar-se",
            },
            timeout=self.timeout,
            allow_redirects=True,
        )
        response.raise_for_status()

        response_text = response.text
        if "zbx_session" not in self.session.cookies:
            raise ZabbixWebError("Sessao web nao criada apos login.")
        if 'class="signin-container"' in response_text:
            if "Incorrect user name or password" in response_text:
                raise ZabbixWebError("Login invalido.")
            if "Nome de usuário ou senha incorretos ou a conta está temporariamente bloqueada." in response_text:
                raise ZabbixWebError(
                    "Login invalido: nome de usuario ou senha incorretos, ou a conta esta temporariamente bloqueada."
                )
            raise ZabbixWebError("Login nao concluido: o Zabbix retornou para a tela de autenticacao.")

    def fetch_host_form_csrf(self) -> str:
        response = self._get_page("zabbix.php?action=host.edit")

        soup = BeautifulSoup(response.text, "html.parser")
        form = soup.find("form", {"id": "host-form"})
        if form is None:
            raise ZabbixWebError("Formulario de host nao encontrado.")

        csrf_input = form.find("input", {"name": "_csrf_token"})
        if csrf_input is None or not csrf_input.get("value"):
            raise ZabbixWebError("Token CSRF do formulario de host nao encontrado.")

        return csrf_input["value"]

    def create_host(self, form_data: list[tuple[str, str]]) -> dict[str, Any]:
        return self._post_form("zabbix.php?action=host.create", form_data)

    def fetch_options(self) -> dict[str, list[tuple[str, str]]]:
        """Lista grupos, proxies e templates visiveis para a sessao (API via cookie).

        Retorna: {"groups": [(id, nome), ...], "proxies": [(id, host), ...],
        "templates": [(id, host), ...]} ordenados por nome.
        """
        groups = self._api("hostgroup.get", {"output": ["groupid", "name"], "sortfield": "name"})
        proxies = self._api("proxy.get", {"output": ["proxyid", "host"], "sortfield": "host"})
        templates = self._api("template.get", {"output": ["templateid", "host"], "sortfield": "host"})
        return {
            "groups": [(item["groupid"], item["name"]) for item in groups],
            "proxies": [(item["proxyid"], item["host"]) for item in proxies],
            "templates": [(item["templateid"], item["host"]) for item in templates],
        }

    def _get_page(self, path: str) -> requests.Response:
        """GET de pagina autenticada; se a sessao expirou, reloga e tenta de novo."""
        for _attempt in range(2):
            response = self.session.get(self.base_url + path, timeout=self.timeout)
            response.raise_for_status()
            if "Você não está autenticado" not in response.text:
                return response
            self.login()
        raise ZabbixWebError("Sessao nao autenticada apos tentativa de novo login.")

    def _post_form(self, path: str, form_data: list[tuple[str, str]]) -> dict[str, Any]:
        """POST de formulario; reloga e tenta de novo se a sessao expirou no meio."""
        for _attempt in range(2):
            response = self.session.post(
                self.base_url + path,
                data=form_data,
                timeout=self.timeout,
                allow_redirects=True,
            )
            response.raise_for_status()
            try:
                return response.json()
            except json.JSONDecodeError:
                if "Você não está autenticado" in response.text:
                    self.login()
                    continue
                raise ZabbixWebError(f"Resposta inesperada do Zabbix: {response.text[:500]}") from None
        raise ZabbixWebError("Sessao nao autenticada apos tentativa de novo login.")

    def _api(self, method: str, params: dict[str, Any]) -> Any:
        """Chamada JSON-RPC usando a sessao web autenticada (cookie)."""
        payload = {"jsonrpc": "2.0", "method": method, "params": params, "id": 1}
        response = self.session.post(
            self.base_url + "api_jsonrpc.php",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json-rpc"},
            timeout=self.timeout,
        )
        response.raise_for_status()
        body = response.json()
        if "error" in body:
            error = body["error"]
            detail = error.get("data") or error.get("message") or "sem detalhes"
            raise ZabbixWebError(f"{method} falhou: {detail}")
        return body["result"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Cria hosts no Zabbix via frontend web e gera log + relatorio final."
    )
    parser.add_argument(
        "--csv",
        type=Path,
        default=Path("cameras_normalized.csv"),
        help="Caminho do CSV de origem.",
    )
    parser.add_argument(
        "--url",
        required=True,
        help="URL base do Zabbix, ex.: https://zabbix.suaempresa.com",
    )
    parser.add_argument(
        "--username",
        help="Usuario do Zabbix. Se omitido, e pedido no terminal.",
    )
    parser.add_argument(
        "--password",
        help="Senha do Zabbix. Se omitida, e pedida no terminal (sem eco).",
    )
    parser.add_argument(
        "--offset",
        type=int,
        default=0,
        help="Indice inicial no CSV.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Quantidade maxima de registros a processar no lote. Padrao: todos a partir do offset.",
    )
    parser.add_argument(
        "--group-id",
        action="append",
        default=list(DEFAULT_GROUP_IDS),
        help="ID do host group destino. Pode ser informado mais de uma vez.",
    )
    parser.add_argument(
        "--template-id",
        action="append",
        default=list(DEFAULT_TEMPLATE_IDS),
        help="ID do template a vincular. Pode ser informado mais de uma vez.",
    )
    parser.add_argument(
        "--proxy-id",
        default=DEFAULT_PROXY_ID,
        help="ID do proxy destino.",
    )
    parser.add_argument(
        "--proxy-name",
        default=DEFAULT_PROXY_NAME,
        help="Nome do proxy. Usado apenas no relatorio.",
    )
    parser.add_argument(
        "--port",
        default=DEFAULT_PORT,
        help="Porta da interface agent.",
    )
    parser.add_argument(
        "--host-prefix",
        default=DEFAULT_HOST_PREFIX,
        help="Prefixo do host tecnico. Default: vazio (layout V1).",
    )
    parser.add_argument(
        "--visible-name-prefix",
        default=DEFAULT_VISIBLE_NAME_PREFIX,
        help="Prefixo do nome visivel. Default: vazio (layout V1).",
    )
    parser.add_argument(
        "--host-suffix",
        default=DEFAULT_HOST_SUFFIX,
        help="Sufixo do host tecnico. Default: ' - v1' (layout V1).",
    )
    parser.add_argument(
        "--visible-name-suffix",
        default=DEFAULT_VISIBLE_NAME_SUFFIX,
        help="Sufixo do nome visivel. Default: ' - v1' (layout V1).",
    )
    parser.add_argument(
        "--report-dir",
        type=Path,
        default=Path("reports"),
        help="Diretorio onde o log e os relatorios serao salvos.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=60,
        help="Timeout HTTP em segundos.",
    )
    return parser.parse_args()


def setup_logging(log_path: Path) -> logging.Logger:
    logger = logging.getLogger("zabbix_web_batch_import")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    return logger


def get_csv_value(row: dict[str, str], *column_names: str) -> str:
    for column_name in column_names:
        value = row.get(column_name)
        if value is not None:
            return value.strip()
    return ""


def read_csv(csv_path: Path, offset: int, limit: int | None = None) -> list[CameraRecord]:
    if offset < 0:
        raise ValueError("--offset nao pode ser negativo.")
    if limit is not None and limit <= 0:
        raise ValueError("--limit precisa ser maior que zero.")

    with csv_path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        rows = list(reader)

    sliced_rows = rows[offset:]
    if limit is not None:
        sliced_rows = sliced_rows[:limit]

    records: list[CameraRecord] = []
    for csv_index, row in enumerate(sliced_rows, start=offset + 1):
        records.append(
            CameraRecord(
                csv_index=csv_index,
                name=get_csv_value(row, "Name"),
                vendor=get_csv_value(row, "Vendor"),
                model=get_csv_value(row, "Model"),
                firmware=get_csv_value(row, "Firmware"),
                ip=get_csv_value(row, "IP", "IP/Name"),
                mac_address=get_csv_value(row, "MAC address"),
            )
        )

    return records


def normalize_zabbix_name(name: str) -> str:
    """Remove acentos e caracteres invalidos para nomes de host no Zabbix."""
    # Decompoe caracteres acentuados (ex: C + cedilha → C + combining cedilla)
    normalized = unicodedata.normalize("NFKD", name)
    # Remove diacriticos (acentos, cedilha, til, etc.), mantendo apenas ASCII
    ascii_name = normalized.encode("ascii", "ignore").decode("ascii")
    # Substitui / e outros caracteres problematicos por hifen
    ascii_name = re.sub(r"[/\\]+", "-", ascii_name)
    # Remove outros caracteres nao permitidos (mantem letras, numeros, espacos, hifen, underscore, ponto)
    ascii_name = re.sub(r"[^a-zA-Z0-9 ._\-]", "", ascii_name)
    # Remove espacos multiplos
    ascii_name = re.sub(r"\s+", " ", ascii_name).strip()
    return ascii_name


def build_form_data(
    csrf_token: str,
    record: CameraRecord,
    args: argparse.Namespace,
) -> list[tuple[str, str]]:
    safe_name = normalize_zabbix_name(record.name)
    host_name = f"{args.host_prefix}{safe_name}{args.host_suffix}"
    visible_name = f"{args.visible_name_prefix}{safe_name}{args.visible_name_suffix}".strip()

    data: list[tuple[str, str]] = [
        ("_csrf_token", csrf_token),
        ("host", host_name),
        ("visiblename", visible_name or record.name),
    ]

    for template_id in args.template_id:
        data.append(("add_templates[]", template_id))

    for group_id in args.group_id:
        data.append(("groups[]", group_id))

    data.extend(
        [
            (f"interfaces[{DEFAULT_INTERFACE_ID}][items]", ""),
            (f"interfaces[{DEFAULT_INTERFACE_ID}][isNew]", "true"),
            (f"interfaces[{DEFAULT_INTERFACE_ID}][interfaceid]", DEFAULT_INTERFACE_ID),
            (f"interfaces[{DEFAULT_INTERFACE_ID}][type]", "1"),
            (f"interfaces[{DEFAULT_INTERFACE_ID}][ip]", record.ip),
            (f"interfaces[{DEFAULT_INTERFACE_ID}][dns]", ""),
            (f"interfaces[{DEFAULT_INTERFACE_ID}][useip]", "1"),
            (f"interfaces[{DEFAULT_INTERFACE_ID}][port]", args.port),
            ("mainInterfaces[1]", DEFAULT_INTERFACE_ID),
            ("status", "0"),
            ("inventory_mode", "0"),
            ("host_inventory[name]", record.vendor),
            ("host_inventory[type]", record.model),
            ("host_inventory[vendor]", record.vendor),
            ("host_inventory[hardware]", record.model),
            ("host_inventory[macaddress_a]", record.mac_address),
        ]
    )
    data.append(
        (
            "host_inventory[hardware_full]",
            f"{record.model} | Firmware: {record.firmware}" if record.firmware else record.model,
        )
    )
    if args.proxy_id:
        data.append(("proxy_hostid", args.proxy_id))
    if record.description:
        data.append(("description", record.description))
    for tag_index, (tag_key, tag_value) in enumerate(record.tags):
        data.append((f"tags[{tag_index}][tag]", tag_key))
        data.append((f"tags[{tag_index}][value]", tag_value))

    return data


def parse_result(payload: dict[str, Any]) -> tuple[str, str]:
    if "success" in payload:
        title = payload["success"].get("title", "Host added")
        return "created", title

    if "error" in payload:
        error = payload["error"]
        title = error.get("title", "Erro")
        messages = error.get("messages", [])
        message = " | ".join(messages) if messages else title

        # Normaliza acentos para deteccao de "ja existe" independente de encoding
        lowered = message.lower()
        lowered_ascii = unicodedata.normalize("NFKD", lowered).encode("ascii", "ignore").decode("ascii")
        if "already exists" in lowered or "ja existe" in lowered or "ja existe" in lowered_ascii:
            return "exists", message
        return "error", message

    return "error", "Resposta sem bloco success/error."


def write_json_report(path: Path, summary: dict[str, Any], results: list[dict[str, Any]]) -> None:
    payload = {"summary": summary, "results": results}
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def write_csv_report(path: Path, results: list[dict[str, Any]]) -> None:
    fieldnames = [
        "csv_index",
        "host",
        "visible_name",
        "ip",
        "status",
        "message",
        "vendor",
        "model",
    ]
    with path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)


def main() -> int:
    args = parse_args()
    if not args.username:
        args.username = input("Usuario do Zabbix: ").strip()
    if not args.password:
        args.password = getpass.getpass("Senha do Zabbix: ")
    if not args.username or not args.password:
        print("Erro: usuario e senha sao obrigatorios.", file=sys.stderr)
        return 2
    if not args.group_id:
        print(
            "Erro: informe ao menos um grupo de host destino (--group-id).",
            file=sys.stderr,
        )
        return 2

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    report_dir = args.report_dir
    report_dir.mkdir(parents=True, exist_ok=True)

    log_path = report_dir / f"zabbix-web-import-{timestamp}.log"
    json_report_path = report_dir / f"zabbix-web-import-{timestamp}.json"
    csv_report_path = report_dir / f"zabbix-web-import-{timestamp}.csv"

    logger = setup_logging(log_path)
    logger.info("Inicio da execucao.")
    logger.info("CSV: %s", args.csv.resolve())
    logger.info("URL: %s", args.url)
    logger.info("Proxy: %s (%s)", args.proxy_name, args.proxy_id)

    logger.info("Host groups: %s", ", ".join(args.group_id))
    logger.info("Templates: %s", ", ".join(args.template_id))

    try:
        records = read_csv(args.csv, args.offset, args.limit)
        if not records:
            logger.warning("Nenhum registro encontrado a partir do offset informado.")
            return 0

        client = ZabbixWebClient(
            base_url=args.url,
            username=args.username,
            password=args.password,
            timeout=args.timeout,
        )
        client.login()
        logger.info("Login web realizado com sucesso.")

        results: list[dict[str, Any]] = []
        created = 0
        exists = 0
        errors = 0

        for record in records:
            safe_name = normalize_zabbix_name(record.name)
            host_name = f"{args.host_prefix}{safe_name}{args.host_suffix}"
            visible_name = f"{args.visible_name_prefix}{safe_name}{args.visible_name_suffix}".strip() or record.name
            logger.info("Processando CSV#%s | %s | %s", record.csv_index, host_name, record.ip)

            try:
                csrf_token = client.fetch_host_form_csrf()
                form_data = build_form_data(csrf_token, record, args)
                payload = client.create_host(form_data)
                status, message = parse_result(payload)
            except Exception as exc:
                status = "error"
                message = str(exc)

            result = {
                "csv_index": record.csv_index,
                "host": host_name,
                "visible_name": visible_name,
                "ip": record.ip,
                "status": status,
                "message": message,
                "vendor": record.vendor,
                "model": record.model,
            }
            results.append(result)

            if status == "created":
                created += 1
                logger.info("Criado | %s", host_name)
            elif status == "exists":
                exists += 1
                logger.warning("Ja existia | %s | %s", host_name, message)
            else:
                errors += 1
                logger.error("Falhou | %s | %s", host_name, message)

        summary = {
            "timestamp": timestamp,
            "url": args.url,
            "proxy_id": args.proxy_id,
            "proxy_name": args.proxy_name,
            "csv": str(args.csv.resolve()),
            "offset": args.offset,
            "processed": len(results),
            "created": created,
            "exists": exists,
            "errors": errors,
            "log_path": str(log_path.resolve()),
            "json_report_path": str(json_report_path.resolve()),
            "csv_report_path": str(csv_report_path.resolve()),
        }

        write_json_report(json_report_path, summary, results)
        write_csv_report(csv_report_path, results)

        logger.info("Execucao finalizada.")
        logger.info(
            "Resumo | processados=%s | criados=%s | existentes=%s | erros=%s",
            summary["processed"],
            summary["created"],
            summary["exists"],
            summary["errors"],
        )
        logger.info("Log: %s", log_path.resolve())
        logger.info("Relatorio JSON: %s", json_report_path.resolve())
        logger.info("Relatorio CSV: %s", csv_report_path.resolve())

        return 0 if errors == 0 else 1
    except Exception as exc:
        logger.exception("Falha geral na execucao: %s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
