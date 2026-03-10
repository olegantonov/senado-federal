"""
Cliente async para API de Dados Abertos do Senado Federal.
Base: https://legis.senado.leg.br/dadosabertos

Uso:
    from senate_client import get_senado_client
    
    async def main():
        client = get_senado_client()
        try:
            # Listar senadores atuais
            senators = await client.lista_senadores_atuais()
            
            # Pesquisar matérias
            materias = await client.pesquisar_materia(sigla="PL", ano=2026)
            
            # Votações da semana
            from datetime import date, timedelta
            votacoes = await client.get_votacoes_periodo(
                date.today() - timedelta(days=7),
                date.today()
            )
        finally:
            await client.close()
"""
import asyncio
from datetime import date, timedelta
from typing import Any

import httpx


BASE_URL = "https://legis.senado.leg.br/dadosabertos"

# Timeout padrão para requisições (45s)
DEFAULT_TIMEOUT = 45.0


class SenadoClient:
    def __init__(self, timeout: float = DEFAULT_TIMEOUT):
        self.client: httpx.AsyncClient | None = None
        self.timeout = timeout

    async def _get_client(self) -> httpx.AsyncClient:
        if self.client is None or self.client.is_closed:
            self.client = httpx.AsyncClient(
                base_url=BASE_URL,
                timeout=httpx.Timeout(self.timeout),
                follow_redirects=True
            )
        return self.client

    async def close(self):
        if self.client and not self.client.is_closed:
            await self.client.aclose()

    async def _get(self, path: str, params: dict | None = None) -> dict:
        client = await self._get_client()
        response = await client.get(path, params=params)
        response.raise_for_status()
        return response.json()

    async def _get_list(self, path: str, params: dict | None = None) -> list:
        """Executa GET e retorna lista, lidando com estrutura variável."""
        data = await self._get(path, params)
        
        # Navega pelo JSON para encontrar a lista
        def find_list(obj: Any) -> list | None:
            if obj is None:
                return None
            if isinstance(obj, list):
                return obj
            if isinstance(obj, dict):
                for value in obj.values():
                    result = find_list(value)
                    if result is not None:
                        return result
            return None
        
        result = find_list(data)
        return result if result else []

    # ========== PLENÁRIO ==========

    async def get_agenda_plenario_dia(self, data: date | None = None) -> dict:
        """Agenda do plenario para um dia específico (YYYYMMDD)."""
        if data is None:
            data = date.today()
        data_str = data.strftime("%Y%m%d")
        return await self._get(f"/plenario/agenda/dia/{data_str}.json")

    async def get_agenda_plenario_mes(self, ano: int, mes: int) -> dict:
        """Agenda do plenario para um mês (YYYYMM)."""
        yyyymm = f"{ano}{mes:02d}"
        return await self._get(f"/plenario/agenda/mes/{yyyymm}.json")

    async def get_votacoes_periodo(self, data_inicio: date, data_fim: date) -> list[dict]:
        """Lista de votações em um período."""
        inicio = data_inicio.strftime("%Y%m%d")
        fim = data_fim.strftime("%Y%m%d")
        data = await self._get(f"/plenario/lista/votacao/{inicio}/{fim}.json")
        votacoes = data.get("ListaVotacoes", {}).get("Votacoes", {}).get("Votacao", [])
        return votacoes if isinstance(votacoes, list) else [votacoes] if votacoes else []

    # ========== COMISSÕES ==========

    async def get_agenda_comissao_dia(self, data: date | None = None) -> dict:
        """Agenda das comissões para um dia."""
        if data is None:
            data = date.today()
        data_str = data.strftime("%Y%m%d")
        return await self._get(f"/comissao/agenda/dia/{data_str}.json")

    async def get_agenda_comissao_periodo(self, data_inicio: date, data_fim: date) -> dict:
        """Agenda das comissões em um período."""
        inicio = data_inicio.strftime("%Y%m%d")
        fim = data_fim.strftime("%Y%m%d")
        return await self._get(f"/comissao/agenda/{inicio}/{fim}.json")

    async def get_lista_comissoes(self) -> list[dict]:
        """Lista de todas as comissões."""
        data = await self._get("/comissao/lista.json")
        comissoes = data.get("ListaComissoes", {}).get("Comissoes", {}).get("Comissao", [])
        return comissoes if isinstance(comissoes, list) else [comissoes] if comissoes else []

    # ========== SENADORES ==========

    async def lista_senadores_atuais(self) -> list[dict]:
        """Lista de senators em exercício."""
        data = await self._get("/senador/lista/atual.json")
        return data.get("ListaParlamentarEmExercicio", {}).get("Parlamentares", {}).get("Parlamentar", [])

    async def buscar_senador_por_nome(self, nome: str) -> list[dict]:
        """Busca senators pelo nome (contém)."""
        todos = await self.lista_senadores_atuais()
        nome_lower = nome.lower()
        return [s for s in todos if nome_lower in s.get("IdentificacaoParlamentar", {}).get("NomeParlamentar", "").lower()]

    async def get_senador_detalhe(self, codigo: str) -> dict | None:
        """Detalhe de um senador pelo código."""
        data = await self._get(f"/senador/{codigo}.json")
        return data.get("DetalheParlamentar", {}).get("Parlamentar")

    async def get_autorias_senador(self, codigo: str) -> list[dict]:
        """Lista de autoria de um senator."""
        data = await self._get(f"/senador/{codigo}/autorias.json")
        autorias = data.get("ListaAutoriasParlamentar", {}).get("Autorias", {}).get("Autoria", [])
        return autorias if isinstance(autorias, list) else [autorias] if autorias else []

    async def get_discursos_senador(self, codigo: str, data_inicio: date | None = None, data_fim: date | None = None) -> list[dict]:
        """Discursos de um senator em um período."""
        params = {}
        if data_inicio:
            params["dataIni"] = data_inicio.strftime("%Y%m%d")
        if data_fim:
            params["dataFim"] = data_fim.strftime("%Y%m%d")
        data = await self._get(f"/senador/{codigo}/discursos.json", params)
        return data.get("ListaDiscursos", {}).get("Discursos", {}).get("Discurso", [])

    # ========== MATÉRIAS / PROPOSIÇÕES ==========

    async def pesquisar_materia(self, sigla: str | None = None, numero: str | None = None, ano: int | None = None, tramitando: bool = True) -> list[dict]:
        """Pesquisa matérias por sigla, número e ano."""
        params: dict[str, Any] = {}
        if sigla:
            params["sigla"] = sigla
        if numero:
            params["numero"] = numero
        if ano:
            params["ano"] = str(ano)
        if tramitando:
            params["tramitando"] = "S"
        
        data = await self._get("/materia/pesquisa/lista.json", params)
        materias = data.get("PesquisaBasicaMateria", {}).get("Materias", {}).get("Materia", [])
        return materias if isinstance(materias, list) else [materias] if materias else []

    async def get_materia_detalhe(self, codigo: str) -> dict | None:
        """Detalhe de uma matéria pelo código."""
        data = await self._get(f"/materia/{codigo}.json")
        return data.get("DetalheMateria", {}).get("Materia")

    async def get_materia_movimentacoes(self, codigo: str) -> list[dict]:
        """Movimentações de uma matéria."""
        data = await self._get(f"/materia/movimentacoes/{codigo}.json")
        movimentacoes = data.get("MovimentacaoMateria", {}).get("Movimentacao", [])
        return movimentacoes if isinstance(movimentacoes, list) else [movimentacoes] if movimentacoes else []

    async def get_materia_tramitacao(self, codigo: str) -> list[dict]:
        """Tramitações de uma matéria."""
        data = await self._get(f"/materia/tramitacao/{codigo}.json")
        tramitacoes = data.get("TramitacaoMateria", {}).get("Tramitacao", [])
        return tramitacoes if isinstance(tramitacoes, list) else [tramitacoes] if tramitacoes else []

    # ========== UTILITÁRIOS ==========

    async def get_materias_recentes(self, dias: int = 7) -> list[dict]:
        """Busca matérias apresentadas nos últimos N dias."""
        hoje = date.today()
        inicio = hoje - timedelta(days=dias)
        data_str = inicio.strftime("%Y%m%d")
        
        data = await self._get("/materia/pesquisa/lista.json", {
            "dataApresentacaoIni": data_str,
            "tramitando": "S",
            "itens": 50
        })
        materias = data.get("PesquisaBasicaMateria", {}).get("Materias", {}).get("Materia", [])
        return materias if isinstance(materias, list) else [materias] if materias else []

    async def get_votacoes_semana(self) -> list[dict]:
        """Votações da última semana."""
        return await self.get_votacoes_periodo(date.today() - timedelta(days=7), date.today())

    async def get_agenda_semana(self) -> dict:
        """Agenda do plenario para a semana atual."""
        hoje = date.today()
        dia_semana = hoje.weekday()
        inicio = hoje - timedelta(days=dia_semana)
        fim = inicio + timedelta(days=6)
        
        # Baixa mês a mês
        meses: dict[str, list] = {}
        cursor = date(inicio.year, inicio.month, 1)
        fim_mes = date(fim.year, fim.month, 1)
        
        all_events = []
        while cursor <= fim_mes:
            key = f"{cursor.year}{cursor.month:02d}"
            meses[key] = await self.get_agenda_plenario_mes(cursor.year, cursor.month)
            
            # Extrai eventos do mês
            mes_data = meses[key]
            def extract_events(obj: Any) -> list:
                if isinstance(obj, list):
                    return obj
                if isinstance(obj, dict):
                    for v in obj.values():
                        result = extract_events(v)
                        if result:
                            return result
                return []
            
            all_events.extend(extract_events(mes_data))
            cursor = date(cursor.year, cursor.month + 1, 1) if cursor.month < 12 else date(cursor.year + 1, 1, 1)
        
        return all_events


# Instância global
_client: SenadoClient | None = None


def get_senado_client() -> SenadoClient:
    """Retorna instância singleton do cliente."""
    global _client
    if _client is None:
        _client = SenadoClient()
    return _client


async def close_senado_client():
    """Fecha o cliente global."""
    global _client
    if _client:
        await _client.close()
        _client = None


# ========== FACADE FUNCTIONS (uso direto) ==========

async def lista_senadores_atuais() -> list[dict]:
    """Facade: lista de senators atuais."""
    client = get_senado_client()
    return await client.lista_senadores_atuais()


async def buscar_senador(nome: str) -> list[dict]:
    """Facade: busca senator por nome."""
    client = get_senado_client()
    return await client.buscar_senador_por_nome(nome)


async def pesquisar_materia(sigla: str | None = None, numero: str | None = None, ano: int | None = None) -> list[dict]:
    """Facade: pesquisa matéria."""
    client = get_senado_client()
    return await client.pesquisar_materia(sigla, numero, ano)


async def get_votacoes_semana() -> list[dict]:
    """Facade: votações da semana."""
    client = get_senado_client()
    return await client.get_votacoes_semana()


async def get_materias_recentes(dias: int = 7) -> list[dict]:
    """Facade: matérias recentes."""
    client = get_senado_client()
    return await client.get_materias_recentes(dias)
