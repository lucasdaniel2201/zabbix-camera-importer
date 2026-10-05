"""
Importador de cameras para o Zabbix via API JSON-RPC (Zabbix 6.4).

Core unico do projeto: o app grafico (app/session.py) consome este modulo.
A autenticacao usa user.login + token no header Authorization: Bearer.

Decisoes registradas (ver CONTEXT.md):
- user.logout NUNCA e chamado (Q6=C): o token expira pelo timeout de sessao
  do servidor. Fechar a conexao HTTP nao invalida o token.
- inventory_mode = 0 (manual) em vez de -1 (desabilitado) (Q7).
- Um host.create por host em vez de host.massadd (Q4): relatorio por linha.
- Pré-consulta host.get antes do lote para marcar 'exists' sem chamada de
  criacao (Q8=a); a substring de erro continua como rede de seguranca.
"""

import csv
import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import requests

# -----------------------------------------------------------------------------
# Defaults (valores iniciais dos campos da UI; o app usa estes)
# -----------------------------------------------------------------------------

DEFAULT_GROUP_IDS: list[str] = []
DEFAULT_TEMPLATE_IDS: list[str] = []
DEFAULT_PROXY_ID = ""
DEFAULT_PROXY_NAME = ""
DEFAULT_PORT = "10051"

# Prefixo dos relatorios gerados pelo app. O consolidate.py le tambem o prefixo
# antigo (zabbix-web-import-*) para nao perder o historico.
REPORT_PREFIX = "zabbix-import-"
LEGACY_REPORT_PREFIX = "zabbix-web-import-"

# Hosts por chamada host.get na pré-consulta de existentes.
HOST_GET_CHUNK = 200


# -----------------------------------------------------------------------------
# Tipos de dados
# -----------------------------------------------------------------------------

@dataclass
class CameraRecord:
    """Registro de camera lido da planilha."""
    csv_index: int
    name: str
    vendor: str
    model: str
    firmware: str
    ip: str
    mac_address: str
    description: str = ""
    tags: list[tuple[str, str]] = field(default_factory=list)


@dataclass
class ImportOptions:
    """Opcoes de criacao do host (nao contem credenciais)."""
    url: str = ""
    host_prefix: str = ""
    host_suffix: str = ""
    visible_name_prefix: str = ""
    visible_name_suffix: str = ""
    group_ids: list[str] = field(default_factory=lambda: list(DEFAULT_GROUP_IDS))
    template_ids: list[str] = field(default_factory=lambda: list(DEFAULT_TEMPLATE_IDS))
    proxy_id: str = DEFAULT_PROXY_ID
    proxy_name: str = DEFAULT_PROXY_NAME
    port: str = DEFAULT_PORT
    timeout: int = 60


class ZabbixApiError(RuntimeError):
    """Erro devolvido pela API JSON-RPC (ou falha de transporte)."""
    def __init__(self, code: int, message: str, data: str = "", method: str = "") -> None:
        self.code = code
        self.message = message
        self.data = data
        self.method = method
        detail = f"{message}: {data}" if data else message
        prefix = f"{method} falhou (code {code})" if method else f"code {code}"
        super().__init__(f"{prefix} - {detail}")


# -----------------------------------------------------------------------------
# Cliente da API
# -----------------------------------------------------------------------------

class ZabbixApiClient:
    """Cliente JSON-RPC para a API do Zabbix 6.4.

    Nao existe user.logout: por decisao do projeto, o token expira sozinho
    pelo timeout de sessao do servidor.
    """

    def __init__(self, base_url: str, username: str, password: str, timeout: int = 60) -> None:
        self.base_url = base_url.rstrip("/") + "/"
        self.username = username
        # Mantida em memoria (nunca em disco) porque o relogin automatico
        # precisa refazer user.login quando o token expira no meio da importacao.
        self.password = password
        self.timeout = timeout
        self._session = requests.Session()
        self._token: str = ""
        self.server_version: str = ""

    @property
    def api_url(self) -> str:
        return self.base_url + "api_jsonrpc.php"

    def login(self) -> dict[str, Any]:
        """Autentica via user.login. Sem auth no payload (exigencia da API)."""
        result = self._raw_call("user.login", {
            "username": self.username,
            "password": self.password,
            "userData": True,
        }, authenticated=False)
        self._token = result["sessionid"]
        self.server_version = self._raw_call("apiinfo.version", {}, authenticated=False)
        return {
            "username": result.get("user"),
            "debug_mode": result.get("debug_mode"),
            "server_version": self.server_version,
            "url": self.base_url,
        }

    def close(self) -> None:
        """Fecha a conexao HTTP. Nao invalida o token no servidor (Q6=C)."""
        self._session.close()
        self._token = ""

    def fetch_options(self) -> dict[str, list[tuple[str, str]]]:
        """Grupos, proxies e templates visiveis para a sessao."""
        groups = self.call("hostgroup.get", {"output": ["groupid", "name"], "sortfield": "name"})
        proxies = self.call("proxy.get", {"output": ["proxyid", "host"], "sortfield": "host"})
        templates = self.call("template.get", {"output": ["templateid", "host"], "sortfield": "host"})
        return {
            "groups": [(item["groupid"], item["name"]) for item in groups],
            "proxies": [(item["proxyid"], item["host"]) for item in proxies],
            "templates": [(item["templateid"], item["host"]) for item in templates],
        }

    def existing_hosts(self, host_names: list[str]) -> set[str]:
        """Nomes tecnicos que ja existem no servidor, em blocos de HOST_GET_CHUNK."""
        unique = list(dict.fromkeys(n for n in host_names if n))
        found: set[str] = set()
        for start in range(0, len(unique), HOST_GET_CHUNK):
            chunk = unique[start:start + HOST_GET_CHUNK]
            result = self.call("host.get", {"output": ["host"], "filter": {"host": chunk}})
            found.update(item["host"] for item in result)
        return found

    def create_host(self, params: dict[str, Any]) -> dict[str, Any]:
        """host.create. Retorna o dict com hostids quando der certo."""
        return self.call("host.create", params)

    def call(self, method: str, params: dict[str, Any] | None = None) -> Any:
        """Chamada autenticada; reloga uma unica vez se a sessao expirar."""
        params = params or {}
        for attempt in range(2):
            try:
                return self._raw_call(method, params, authenticated=True)
            except ZabbixApiError as exc:
                if attempt == 0 and self._is_session_expired(exc):
                    self._relogin()
                    continue
                raise
        raise ZabbixApiError(-1, "Sessao expirada e novo login falhou", method=method)

    def _raw_call(self, method: str, params: dict[str, Any], authenticated: bool) -> Any:
        payload: dict[str, Any] = {"jsonrpc": "2.0", "method": method, "params": params, "id": 1}
        headers = {"Content-Type": "application/json-rpc"}
        if authenticated:
            if not self._token:
                raise ZabbixApiError(-32602, "Not authorized", "sessao nao autenticada", method)
            payload["auth"] = self._token
            headers["Authorization"] = f"Bearer {self._token}"

        response = self._session.post(
            self.api_url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            timeout=self.timeout,
        )
        response.raise_for_status()
        try:
            body = response.json()
        except ValueError:
            raise ZabbixApiError(
                -1, "Resposta nao e JSON", response.text[:200], method
            ) from None

        if "error" in body:
            error = body["error"]
            raise ZabbixApiError(
                int(error.get("code", -32603)),
                str(error.get("message", "Unknown error")),
                str(error.get("data", "")),
                method,
            )
        return body.get("result", {})

    def _relogin(self) -> None:
        """Relogina mantendo o mesmo usuario (token novo)."""
        self._token = ""
        result = self._raw_call("user.login", {
            "username": self.username,
            "password": self.password,
            "userData": True,
        }, authenticated=False)
        self._token = result["sessionid"]

    @staticmethod
    def _is_session_expired(exc: ZabbixApiError) -> bool:
        text = f"{exc.message} {exc.data}".lower()
        return "session terminated" in text or "not authorized" in text


# -----------------------------------------------------------------------------
# Normalizacao e nomes finais
# -----------------------------------------------------------------------------

def normalize_zabbix_name(name: str) -> str:
    """Remove acentos e caracteres invalidos para nomes de host no Zabbix."""
    normalized = unicodedata.normalize("NFKD", name)
    ascii_name = normalized.encode("ascii", "ignore").decode("ascii")
    ascii_name = re.sub(r"[/\\]+", "-", ascii_name)
    ascii_name = re.sub(r"[^a-zA-Z0-9 ._\-]", "", ascii_name)
    ascii_name = re.sub(r"\s+", " ", ascii_name).strip()
    return ascii_name


def normalize_for_match(value: str) -> str:
    """Normaliza texto para comparacao sem acento e sem caixa.

    Usado para achar 'troca realizada' e para casar cabecalhos, onde o acento
    e a caixa nao devem importar.
    """
    decomposed = unicodedata.normalize("NFKD", value or "")
    without_accents = "".join(c for c in decomposed if not unicodedata.combining(c))
    return without_accents.casefold()


def normalize_vendor(vendor: str) -> str:
    """Corrige grafia do fabricante que o Zabbix trata como padrao."""
    if vendor is None:
        return ""
    vendor = vendor.strip()
    if vendor.upper() == "HIKVISION":
        return "Hikvision"
    return vendor


def host_names(raw_name: str, options: ImportOptions) -> tuple[str, str]:
    """Nomes tecnicos e visivel finais (normalizado + prefixo/sufixo).

    Unica fonte: o log, a pré-consulta e a montagem do host usam esta funcao.
    """
    safe = normalize_zabbix_name(raw_name)
    technical = f"{options.host_prefix}{safe}{options.host_suffix}"
    visible = (
        f"{options.visible_name_prefix}{safe}{options.visible_name_suffix}"
    ).strip() or safe
    return technical, visible


# -----------------------------------------------------------------------------
# Montagem do host
# -----------------------------------------------------------------------------

def build_host_params(
    record: CameraRecord,
    technical_name: str,
    visible_name: str,
    options: ImportOptions,
) -> dict[str, Any]:
    """Parametros para host.create.

    Preserva o que o formulario web fazia hoje:
    - inventory.name = fabricante e inventory.type = modelo (ambos do CSV)
    - inventory.hardware = modelo; hardware_full = modelo | Firmware
    - status=0 (monitorado); inventory_mode=0 (manual, Q7)
    - interface type=1 (agent, verificado na doc 6.4 do hostinterface)
    - interface main=1 e obrigatorio na API (nao vem do formulario)
    """
    inventory: dict[str, str] = {
        "name": record.vendor,
        "type": record.model,
        "vendor": record.vendor,
        "hardware": record.model,
        "macaddress_a": record.mac_address,
        "hardware_full": (
            f"{record.model} | Firmware: {record.firmware}" if record.firmware else record.model
        ),
    }

    params: dict[str, Any] = {
        "host": technical_name,
        "name": visible_name,
        "status": "0",
        "inventory_mode": "0",
        "groups": [{"groupid": gid} for gid in options.group_ids],
        "templates": [{"templateid": tid} for tid in options.template_ids],
        "interfaces": [{
            "type": "1",
            "main": "1",
            "useip": "1",
            "ip": record.ip,
            "dns": "",
            "port": options.port,
        }],
        "inventory": inventory,
    }

    if options.proxy_id:
        params["proxy_hostid"] = options.proxy_id
    if record.description:
        params["description"] = record.description
    if record.tags:
        params["tags"] = [{"tag": k, "value": v} for k, v in record.tags]

    return params


# -----------------------------------------------------------------------------
# Classificacao de resultado
# -----------------------------------------------------------------------------

def classify_api_error(exc: Exception) -> tuple[str, str]:
    """Classifica a falha de uma chamada em status do relatorio.

    Status sao apenas 'created', 'exists' e 'error' (schema do relatorio e do
    consolidate.py). Erros de permissao continuam 'error', com mensagem clara.
    """
    if not isinstance(exc, ZabbixApiError):
        return "error", str(exc)

    detail = exc.data or exc.message
    lowered = f"{exc.message} {exc.data}".lower()
    ascii_lowered = unicodedata.normalize("NFKD", lowered).encode("ascii", "ignore").decode("ascii")

    if "already exists" in lowered or "ja existe" in ascii_lowered:
        return "exists", detail

    if "no permissions to referred object" in lowered or "permission denied" in lowered:
        return "error", (
            f"Sem permissao no Zabbix (code {exc.code}): {detail}. "
            "Verifique os papeis do usuario: Host inventory e Templates em Write "
            "e escrita nos host groups selecionados."
        )

    return "error", str(exc)


def parse_api_result(result: dict[str, Any]) -> tuple[str, str]:
    """Interpreta o retorno de host.create quando nao ha excecao."""
    hostids = result.get("hostids")
    if hostids:
        return "created", f"Host created (id: {hostids[0]})"
    return "error", f"Resposta inesperada da API: {str(result)[:200]}"


# -----------------------------------------------------------------------------
# Relatorios
# -----------------------------------------------------------------------------

def report_paths(report_dir: Path, timestamp: str) -> tuple[Path, Path, Path]:
    """Caminhos (log, json, csv) para uma execucao."""
    return (
        report_dir / f"{REPORT_PREFIX}{timestamp}.log",
        report_dir / f"{REPORT_PREFIX}{timestamp}.json",
        report_dir / f"{REPORT_PREFIX}{timestamp}.csv",
    )


def write_json_report(path: Path, summary: dict[str, Any], results: list[dict[str, Any]]) -> None:
    payload = {"summary": summary, "results": results}
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def write_csv_report(path: Path, results: list[dict[str, Any]]) -> None:
    fieldnames = [
        "csv_index", "host", "visible_name", "ip",
        "status", "message", "vendor", "model",
    ]
    with path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)
