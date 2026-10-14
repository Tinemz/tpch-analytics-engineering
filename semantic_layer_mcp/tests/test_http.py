"""Transporte HTTP: a chave no caminho é a única porta de entrada. Offline, como o contrato."""

from pathlib import Path

import pytest
from starlette.testclient import TestClient

from semantic_layer_mcp.engine import SemanticLayerEngine
from semantic_layer_mcp.server import create_server, http_path, http_settings

PROJECT = Path(__file__).resolve().parents[2] / "tpch"
SECRET = "a" * 40
HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
LIST_TOOLS = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}


def test_http_path_recusa_chave_curta(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MCP_PATH_SECRET", "curta")
    with pytest.raises(SystemExit):
        http_path()


def test_http_path_recusa_caractere_fora_de_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MCP_PATH_SECRET", "a" * 40 + "/x")
    with pytest.raises(SystemExit):
        http_path()


@pytest.fixture(scope="module")
def client() -> TestClient:
    engine = SemanticLayerEngine(project_path=PROJECT, profiles_path=PROJECT)
    engine.load()
    app = create_server(engine, **http_settings(f"/mcp/{SECRET}")).streamable_http_app()
    with TestClient(app) as c:
        yield c


@pytest.mark.parametrize("path", ["/mcp", "/mcp/", f"/mcp/{SECRET[:-1]}", "/", "/sse"])
def test_caminho_sem_a_chave_da_404(client: TestClient, path: str) -> None:
    assert client.post(path, json=LIST_TOOLS, headers=HEADERS).status_code == 404


def test_caminho_com_a_chave_lista_as_tools(client: TestClient) -> None:
    response = client.post(f"/mcp/{SECRET}", json=LIST_TOOLS, headers=HEADERS)
    assert response.status_code == 200
    names = {tool["name"] for tool in response.json()["result"]["tools"]}
    assert {"list_metrics", "get_dimensions", "query_metrics"} <= names
