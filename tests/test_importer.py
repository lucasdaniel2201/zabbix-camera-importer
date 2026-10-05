"""Testes do core de importacao (zabbix_importer.py).

Cobrem o que ja causou ou poderia causar bugs reais: normalizacao de nome,
montagem do host para a API (parametros de host.create), classificacao de
erro da API e o comportamento do cliente JSON-RPC (auth, retry, chunking).
"""

import json
import socket
import sys
import unittest
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import zabbix_importer as core  # noqa: E402


def make_record(**overrides) -> core.CameraRecord:
    base = {
        "csv_index": 1,
        "name": "CAM-TESTE-01",
        "vendor": "Hikvision",
        "model": "DS-2CD2043G2-I",
        "firmware": "1.0.0",
        "ip": "10.0.0.10",
        "mac_address": "AA-BB-CC-DD-EE-FF",
    }
    base.update(overrides)
    return core.CameraRecord(**base)


def make_options(**overrides) -> core.ImportOptions:
    base = {
        "group_ids": ["1"],
        "template_ids": ["10001"],
        "proxy_id": "2",
        "port": "10051",
    }
    base.update(overrides)
    return core.ImportOptions(**base)


class TestNormalizeZabbixName(unittest.TestCase):
    def test_remove_acentos(self):
        self.assertEqual(core.normalize_zabbix_name("Câmera São Paulo"), "Camera Sao Paulo")

    def test_remove_cedilha_e_til(self):
        self.assertEqual(core.normalize_zabbix_name("Ação Bênção"), "Acao Bencao")

    def test_barra_vira_hifen(self):
        self.assertEqual(core.normalize_zabbix_name("A/B"), "A-B")
        self.assertEqual(core.normalize_zabbix_name("A\\B"), "A-B")
        self.assertEqual(core.normalize_zabbix_name("A//B"), "A-B")

    def test_remove_caracteres_invalidos(self):
        # parenteses, virgula e dois-pontos nao sao aceitos pelo Zabbix
        self.assertEqual(core.normalize_zabbix_name("CAM (1), fundo"), "CAM 1 fundo")

    def test_preserva_caracteres_permitidos(self):
        self.assertEqual(core.normalize_zabbix_name("CAM-A_1.2 x"), "CAM-A_1.2 x")

    def test_colapsa_espacos(self):
        self.assertEqual(core.normalize_zabbix_name("  CAM   01  "), "CAM 01")

    def test_texto_vazio(self):
        self.assertEqual(core.normalize_zabbix_name(""), "")

    def test_apenas_invalidos_vira_vazio(self):
        self.assertEqual(core.normalize_zabbix_name("()[]{}"), "")

    def test_nome_longo_com_hifens(self):
        self.assertEqual(
            core.normalize_zabbix_name("CAM-ENTRADA-PRINCIPAL-BLOCO-A"),
            "CAM-ENTRADA-PRINCIPAL-BLOCO-A",
        )


class TestHostNames(unittest.TestCase):
    def test_sem_prefixo_nem_sufixo(self):
        technical, visible = core.host_names("CAM-01", make_options())
        self.assertEqual(technical, "CAM-01")
        self.assertEqual(visible, "CAM-01")

    def test_prefixo_e_sufixo_do_nome_tecnico(self):
        technical, visible = core.host_names(
            "CAM-01", make_options(host_prefix="CAM - ", host_suffix=" - v1")
        )
        self.assertEqual(technical, "CAM - CAM-01 - v1")
        # Nome visivel tem prefixo/sufixo proprios (vazios aqui).
        self.assertEqual(visible, "CAM-01")

    def test_prefixo_e_sufixo_do_nome_visivel(self):
        technical, visible = core.host_names(
            "CAM-01", make_options(visible_name_prefix="CAM ", visible_name_suffix=" (SP)")
        )
        self.assertEqual(technical, "CAM-01")
        self.assertEqual(visible, "CAM CAM-01 (SP)")

    def test_app_nao_aplica_sufixo_por_padrao(self):
        """O app nao usa sufixo; o antigo default do CLI (' - v1') nao vem aqui."""
        _technical, visible = core.host_names("CAM-01", core.ImportOptions())
        self.assertEqual(visible, "CAM-01")

    def test_nome_normalizado_antes_de_prefixar(self):
        technical, _visible = core.host_names("Câmera João (fundo)", make_options())
        self.assertEqual(technical, "Camera Joao fundo")

    def test_nome_vazio_fica_vazio(self):
        technical, visible = core.host_names("", make_options())
        self.assertEqual(technical, "")
        self.assertEqual(visible, "")

    def test_visivel_fica_vazio_nao_tecnico(self):
        _technical, visible = core.host_names(
            "CAM-01", make_options(visible_name_prefix="", visible_name_suffix="")
        )
        self.assertEqual(visible, "CAM-01")


class TestBuildHostParams(unittest.TestCase):
    def test_campos_basicos(self):
        params = core.build_host_params(
            record=make_record(),
            technical_name="CAM-TESTE-01",
            visible_name="CAM-TESTE-01",
            options=make_options(),
        )
        self.assertEqual(params["host"], "CAM-TESTE-01")
        self.assertEqual(params["name"], "CAM-TESTE-01")

    def test_status_e_inventory_mode_sao_0(self):
        params = core.build_host_params(
            record=make_record(),
            technical_name="X",
            visible_name="X",
            options=make_options(),
        )
        self.assertEqual(params["status"], "0")  # monitorado
        self.assertEqual(params["inventory_mode"], "0")  # manual (Q7)

    def test_interface_type_agent_e_main_obrigatorio(self):
        params = core.build_host_params(
            record=make_record(),
            technical_name="X",
            visible_name="X",
            options=make_options(),
        )
        iface = params["interfaces"][0]
        self.assertEqual(iface["type"], "1")  # agent (doc 6.4 hostinterface)
        self.assertEqual(iface["main"], "1")  # obrigatorio na API
        self.assertEqual(iface["ip"], "10.0.0.10")
        self.assertEqual(iface["port"], "10051")
        self.assertEqual(iface["useip"], "1")
        self.assertEqual(iface["dns"], "")

    def test_grupos_e_templates_repetidos(self):
        params = core.build_host_params(
            record=make_record(),
            technical_name="X",
            visible_name="X",
            options=make_options(group_ids=["1", "2"], template_ids=["10001", "10002"]),
        )
        self.assertEqual(params["groups"], [{"groupid": "1"}, {"groupid": "2"}])
        self.assertEqual(
            params["templates"], [{"templateid": "10001"}, {"templateid": "10002"}]
        )

    def test_templates_vazio_nao_envia_chave(self):
        params = core.build_host_params(
            record=make_record(),
            technical_name="X",
            visible_name="X",
            options=make_options(template_ids=[]),
        )
        self.assertEqual(params["templates"], [])

    def test_proxy_presente_quando_informado(self):
        params = core.build_host_params(
            record=make_record(),
            technical_name="X",
            visible_name="X",
            options=make_options(proxy_id="2"),
        )
        self.assertEqual(params["proxy_hostid"], "2")

    def test_proxy_omitido_quando_vazio(self):
        params = core.build_host_params(
            record=make_record(),
            technical_name="X",
            visible_name="X",
            options=make_options(proxy_id=""),
        )
        self.assertNotIn("proxy_hostid", params)

    def test_inventario_preserva_mapeamento_do_formulario(self):
        params = core.build_host_params(
            record=make_record(),
            technical_name="X",
            visible_name="X",
            options=make_options(),
        )
        inv = params["inventory"]
        self.assertEqual(inv["name"], "Hikvision")      # fabricante (como no form)
        self.assertEqual(inv["type"], "DS-2CD2043G2-I")  # modelo (como no form)
        self.assertEqual(inv["vendor"], "Hikvision")
        self.assertEqual(inv["hardware"], "DS-2CD2043G2-I")
        self.assertEqual(inv["macaddress_a"], "AA-BB-CC-DD-EE-FF")
        self.assertEqual(inv["hardware_full"], "DS-2CD2043G2-I | Firmware: 1.0.0")

    def test_inventario_sem_firmware(self):
        params = core.build_host_params(
            record=make_record(firmware=""),
            technical_name="X",
            visible_name="X",
            options=make_options(),
        )
        self.assertEqual(params["inventory"]["hardware_full"], "DS-2CD2043G2-I")

    def test_descricao_enviada_quando_presente(self):
        params = core.build_host_params(
            record=make_record(description="Camera do portao principal"),
            technical_name="X",
            visible_name="X",
            options=make_options(),
        )
        self.assertEqual(params["description"], "Camera do portao principal")

    def test_descricao_omitida_quando_vazia(self):
        params = core.build_host_params(
            record=make_record(description=""),
            technical_name="X",
            visible_name="X",
            options=make_options(),
        )
        self.assertNotIn("description", params)

    def test_tags_enviadas(self):
        params = core.build_host_params(
            record=make_record(tags=[("site", "MATRIZ"), ("andar", "2")]),
            technical_name="X",
            visible_name="X",
            options=make_options(),
        )
        self.assertEqual(params["tags"], [{"tag": "site", "value": "MATRIZ"}, {"tag": "andar", "value": "2"}])

    def test_sem_tags_quando_lista_vazia(self):
        params = core.build_host_params(
            record=make_record(tags=[]),
            technical_name="X",
            visible_name="X",
            options=make_options(),
        )
        self.assertNotIn("tags", params)

    def test_nome_do_host_e_normalizado(self):
        params = core.build_host_params(
            record=make_record(name="Câmera São João (fundo)"),
            technical_name="Camera Sao Joao fundo",
            visible_name="Camera Sao Joao fundo",
            options=make_options(),
        )
        self.assertEqual(params["host"], "Camera Sao Joao fundo")


class TestClassifyApiError(unittest.TestCase):
    def test_erro_generico_e_error(self):
        status, message = core.classify_api_error(ValueError("boom"))
        self.assertEqual(status, "error")
        self.assertEqual(message, "boom")

    def test_host_ja_existe_em_ingles(self):
        exc = core.ZabbixApiError(-32602, "Invalid params", "Host with the same name already exists.")
        status, message = core.classify_api_error(exc)
        self.assertEqual(status, "exists")
        self.assertIn("already exists", message)

    def test_host_ja_existe_com_acento(self):
        exc = core.ZabbixApiError(-32602, "Invalid params", "Já existe um host com este nome")
        status, _message = core.classify_api_error(exc)
        self.assertEqual(status, "exists")

    def test_sem_permissao_da_mensagem_clara(self):
        exc = core.ZabbixApiError(
            -32602, "Invalid params",
            "No permissions to referred object or it does not exist!",
        )
        status, message = core.classify_api_error(exc)
        self.assertEqual(status, "error")
        self.assertIn("Sem permissao", message)
        self.assertIn("Write", message)

    def test_erro_de_transporte_vira_error(self):
        status, _message = core.classify_api_error(ConnectionError("timeout"))
        self.assertEqual(status, "error")


class TestParseApiResult(unittest.TestCase):
    def test_sucesso_com_hostids(self):
        status, message = core.parse_api_result({"hostids": ["123"]})
        self.assertEqual(status, "created")
        self.assertIn("123", message)

    def test_resposta_inesperada(self):
        status, message = core.parse_api_result({"foo": "bar"})
        self.assertEqual(status, "error")
        self.assertIn("inesperada", message)


class TestReportPaths(unittest.TestCase):
    def test_prefixo_novo(self):
        log, json, csv = core.report_paths(Path("reports"), "20250101-120000")
        self.assertEqual(log.name, f"{core.REPORT_PREFIX}20250101-120000.log")
        self.assertEqual(json.name, f"{core.REPORT_PREFIX}20250101-120000.json")
        self.assertEqual(csv.name, f"{core.REPORT_PREFIX}20250101-120000.csv")


class TestCameraRecord(unittest.TestCase):
    def test_descricao_e_tags_tem_padrao(self):
        record = make_record()
        self.assertEqual(record.description, "")
        self.assertEqual(record.tags, [])

    def test_nao_existe_mais_coluna_server(self):
        self.assertFalse(hasattr(make_record(), "server"))


class FakeResponse:
    """Resposta HTTP minima para exercitar o cliente sem rede."""

    def __init__(self, body, text: str = "", raises: bool = False) -> None:
        self._body = body
        self.text = text or ""
        self._raises = raises

    def raise_for_status(self) -> None:
        if self._raises:
            raise AssertionError("status HTTP Would Raise For Status")

    def json(self):
        if self._body is _INVALID:
            raise ValueError("Expecting value: line 1 column 1 (char 0)")
        return self._body


_INVALID = object()


def rpc_result(result):
    return {"jsonrpc": "2.0", "result": result, "id": 1}


def rpc_error(code, message, data=""):
    return {
        "jsonrpc": "2.0",
        "error": {"code": code, "message": message, "data": data},
        "id": 1,
    }


class TestClientRequest(unittest.TestCase):
    """Cobre o envelope JSON-RPC: autenticacao, erro, relogin e chunking."""

    def setUp(self) -> None:
        self.client = core.ZabbixApiClient("https://zabbix.example.com", "admin", "s3nh4")
        self.queue: list = []
        self.calls: list = []

        def fake_post(url, data=None, headers=None, timeout=None):
            self.calls.append({"url": url, "payload": json.loads(data.decode("utf-8")), "headers": headers or {}})
            if not self.queue:
                raise AssertionError("chamada sem resposta preparada")
            return self.queue.pop(0)

        self.client._session.post = fake_post  # type: ignore[method-assign]

    def _queue_login(self, token: str = "TOKEN-1", version: str = "6.4.21") -> None:
        self.queue.append(FakeResponse(rpc_result(
            {"sessionid": token, "user": "admin", "debug_mode": False}
        )))
        self.queue.append(FakeResponse(rpc_result(version)))

    def test_url_da_api_acerta_o_endpoint(self):
        self.assertEqual(self.client.api_url, "https://zabbix.example.com/api_jsonrpc.php")

    def test_login_nao_manda_token_e_usa_username(self):
        self._queue_login()
        self.client.login()
        login_call = self.calls[0]
        self.assertEqual(login_call["payload"]["method"], "user.login")
        self.assertNotIn("auth", login_call["payload"])  # exigido pela API 6.4
        self.assertNotIn("Authorization", login_call["headers"])
        self.assertEqual(login_call["payload"]["params"]["username"], "admin")

    def test_login_consulta_a_versao_do_servidor(self):
        self._queue_login(version="6.4.21")
        info = self.client.login()
        self.assertEqual(self.calls[1]["payload"]["method"], "apiinfo.version")
        self.assertEqual(self.client.server_version, "6.4.21")
        self.assertEqual(info["server_version"], "6.4.21")

    def test_chamada_autenticada_manda_bearer(self):
        self._queue_login()
        self.client.login()
        self.queue.append(FakeResponse(rpc_result([])))
        self.client.call("hostgroup.get")
        call = self.calls[-1]
        self.assertEqual(call["payload"]["auth"], "TOKEN-1")
        self.assertEqual(call["headers"]["Authorization"], "Bearer TOKEN-1")
        self.assertEqual(call["headers"]["Content-Type"], "application/json-rpc")

    def test_erro_da_api_vira_excecao_com_code_e_data(self):
        self._queue_login()
        self.client.login()
        self.queue.append(FakeResponse(rpc_error(-32602, "Invalid params", "campo obrigatorio")))
        with self.assertRaises(core.ZabbixApiError) as ctx:
            self.client.create_host({"host": "X"})
        self.assertEqual(ctx.exception.code, -32602)
        self.assertEqual(ctx.exception.data, "campo obrigatorio")
        self.assertEqual(ctx.exception.method, "host.create")
        self.assertIn("-32602", str(ctx.exception))

    def test_sessao_expirada_reloga_uma_vez_e_tenta_de_novo(self):
        self._queue_login()
        self.client.login()
        calls_before = len(self.calls)
        # 1a tentativa falha por sessao expirada; o relogin devolve TOKEN-2.
        self.queue.append(FakeResponse(rpc_error(-32602, "Invalid params", "Session terminated, re-login, please.")))
        self.queue.append(FakeResponse(rpc_result({"sessionid": "TOKEN-2", "user": "admin"})))
        self.queue.append(FakeResponse(rpc_result(["123"])))

        result = self.client.call("host.create", {"host": "X"})

        self.assertEqual(result, ["123"])
        methods = [c["payload"]["method"] for c in self.calls[calls_before:]]
        self.assertEqual(methods, ["host.create", "user.login", "host.create"])
        self.assertEqual(self.calls[-1]["headers"]["Authorization"], "Bearer TOKEN-2")

    def test_sessao_expirada_repetida_propaga_o_erro(self):
        self._queue_login()
        self.client.login()
        expirado = rpc_error(-32602, "Invalid params", "Session terminated, re-login, please.")
        self.queue.extend([
            FakeResponse(expirado),
            FakeResponse(rpc_result({"sessionid": "TOKEN-2", "user": "admin"})),
            FakeResponse(expirado),
            FakeResponse(rpc_result({"sessionid": "TOKEN-3", "user": "admin"})),
            FakeResponse(expirado),
        ])
        with self.assertRaises(core.ZabbixApiError):
            self.client.call("host.create", {"host": "X"})
        # Duas tentativas no metodo: nao fica relogando em laco.
        host_creates = [
            c for c in self.calls if c["payload"]["method"] == "host.create"
        ]
        self.assertEqual(len(host_creates), 2)

    def test_erro_de_permissao_nao_tenta_relogin(self):
        self._queue_login()
        self.client.login()
        self.queue.append(FakeResponse(rpc_error(
            -32602, "Invalid params",
            "No permissions to referred object or it does not exist!",
        )))
        with self.assertRaises(core.ZabbixApiError):
            self.client.call("host.create", {"host": "X"})
        self.assertEqual(self.calls[-1]["payload"]["method"], "host.create")

    def test_resposta_nao_json_vira_erro_com_http(self):
        self._queue_login()
        self.client.login()
        self.queue.append(FakeResponse(_INVALID, text="<html>login</html>"))
        with self.assertRaises(core.ZabbixApiError) as ctx:
            self.client.call("hostgroup.get")
        self.assertIn("login", str(ctx.exception))

    def test_existing_hosts_fatia_em_blocos(self):
        self._queue_login()
        self.client.login()
        nomes = [f"CAM-{i:03d}" for i in range(250)]
        for bloco in (nomes[:200], nomes[200:]):
            self.queue.append(FakeResponse(rpc_result(
                [{"host": h} for h in bloco[:1]]
            )))

        existentes = self.client.existing_hosts(nomes)

        host_gets = [c for c in self.calls if c["payload"]["method"] == "host.get"]
        self.assertEqual(len(host_gets), 2)
        self.assertEqual(len(host_gets[0]["payload"]["params"]["filter"]["host"]), 200)
        self.assertEqual(len(host_gets[1]["payload"]["params"]["filter"]["host"]), 50)
        self.assertEqual(existentes, {"CAM-000", "CAM-200"})

    def test_existing_hosts_com_lista_vazia_nao_chama_api(self):
        self.assertEqual(self.client.existing_hosts([]), set())
        self.assertEqual(self.calls, [])

    def test_existing_hosts_deduplica_nomes(self):
        self._queue_login()
        self.client.login()
        self.queue.append(FakeResponse(rpc_result([])))
        self.client.existing_hosts(["CAM-01", "CAM-01", "CAM-02"])
        host_get = [c for c in self.calls if c["payload"]["method"] == "host.get"][-1]
        self.assertEqual(host_get["payload"]["params"]["filter"]["host"], ["CAM-01", "CAM-02"])

    def test_close_nao_chama_user_logout(self):
        """Decisao do projeto: o token expira sozinho; nao invalidamos no servidor."""
        self._queue_login()
        self.client.login()
        self.client.close()
        self.assertEqual(
            [c["payload"]["method"] for c in self.calls if "user." in c["payload"]["method"]],
            ["user.login"],
        )


class TestPreferIPv4(unittest.TestCase):
    """Resolucao por IPv4: sem Happy Eyeballs, cada IPv6 inoperante custa ~21s."""

    @staticmethod
    def _enderecos() -> list:
        return [
            (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("2606:4700::1", 443)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("104.21.72.11", 443)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("172.67.173.105", 443)),
        ]

    def setUp(self) -> None:
        self.real = socket.getaddrinfo
        # Resolucao falsa: o contexto tem de devolver IPv4 sem tocar na rede.
        socket.getaddrinfo = lambda *a, **k: self._enderecos()

    def tearDown(self) -> None:
        socket.getaddrinfo = self.real

    def test_descarta_ipv6_durante_o_bloco(self):
        with core._ipv4_only():
            achados = socket.getaddrinfo("zabbix.example.com", 443)
        familias = [a[0] for a in achados]
        self.assertNotIn(socket.AF_INET6, familias)
        self.assertEqual(familias, [socket.AF_INET, socket.AF_INET])

    def test_restaura_getaddrinfo_ao_sair(self):
        antes = socket.getaddrinfo
        with core._ipv4_only():
            pass
        self.assertIs(socket.getaddrinfo, antes)

    def test_restaura_getaddrinfo_mesmo_com_excecao(self):
        """Se a chamada levantar, o patch nao pode ficar por cima do processo."""
        antes = socket.getaddrinfo
        with self.assertRaises(RuntimeError):
            with core._ipv4_only():
                raise RuntimeError("falha no meio da chamada")
        self.assertIs(socket.getaddrinfo, antes)

    def test_sem_ipv4_na_lista_usa_tudo(self):
        """So IPv6 continua valendo: melhor tentar do que nao conectar."""
        so_ipv6 = [a for a in self._enderecos() if a[0] == socket.AF_INET6]
        socket.getaddrinfo = lambda *a, **k: so_ipv6
        with core._ipv4_only():
            achados = socket.getaddrinfo("zabbix.example.com", 443)
        self.assertEqual([a[0] for a in achados], [socket.AF_INET6])

    def test_adapter_montado_na_session_do_cliente(self):
        client = core.ZabbixApiClient("https://zabbix.example.com", "admin", "s3nh4")
        for prefixo in ("https://", "http://"):
            adapter = client._session.get_adapter(prefixo + "api_jsonrpc.php")
            self.assertIsInstance(adapter, core._IPv4Adapter)

    def test_adapter_so_iv4_durante_o_envio(self):
        """O send do adapter resolve sem IPv6, e restaura ao terminar."""
        client = core.ZabbixApiClient("https://zabbix.example.com", "admin", "s3nh4")
        adapter = client._session.get_adapter("https://api_jsonrpc.php")
        antes = socket.getaddrinfo

        resolvidos: list = []
        super_send = requests.adapters.HTTPAdapter.send

        def send_que_espia(self, request, **kwargs):
            resolvidos.extend(a[0] for a in socket.getaddrinfo("zabbix.example.com", 443))
            return FakeResponse(rpc_result({}))

        try:
            requests.adapters.HTTPAdapter.send = send_que_espia
            request = requests.Request("POST", "https://zabbix.example.com/api_jsonrpc.php").prepare()
            adapter.send(request, timeout=1)
        finally:
            requests.adapters.HTTPAdapter.send = super_send

        self.assertTrue(resolvidos, "o send do adapter nao chegou a resolver")
        self.assertNotIn(socket.AF_INET6, resolvidos)
        self.assertIs(socket.getaddrinfo, antes)

def test_fora_do_adapter_resolve_com_ipv6_de_novo(self):
        """O efeito nao vaza: fora do send, a resolucao volta a ter IPv6."""
        with core._ipv4_only():
            pass
        familias = [a[0] for a in socket.getaddrinfo("zabbix.example.com", 443)]
        self.assertIn(socket.AF_INET6, familias)


if __name__ == "__main__":
    unittest.main(verbosity=2)
