"""Baixa da API do SISAGUA as amostras de vigilância de Alagoas (parâmetros básicos).

Grava um CSV compactado por ano. Os anos fechados ficam em data/historico/, que é
guardado no repositório e só é baixado uma vez. Os dois anos mais recentes vão
para data/recente/ e são sempre baixados de novo, porque a alimentação do SISAGUA
é retroativa. Use --all para baixar de novo também os anos fechados.
"""
import argparse
import csv
import datetime as dt
import gzip
import io
import json
import pathlib
import time
import urllib.parse
import urllib.request

API = "https://apidadosabertos.saude.gov.br/sisagua/vigilancia-parametros-basicos"
UF = "AL"
ANO_INICIAL = 2014
PAGE = 1000  # teto da API, mesmo que se peça mais
PARAMETROS = ["Cloro residual livre (mg/L)", "Turbidez (uT)", "Coliformes totais", "Escherichia coli"]
DADOS = pathlib.Path(__file__).resolve().parent.parent / "data"
HISTORICO = DADOS / "historico"
RECENTE = DADOS / "recente"
# Linhas por ano na última atualização: uma queda grande indica problema na API, não nos dados
CONTAGENS = DADOS / "contagens.json"
QUEDA_MAXIMA = 0.10
# Só o que o painel usa e algumas colunas de identificação. Endereço, coordenadas e
# campos de texto livre ficam de fora, porque o repositório é público.
COLUNAS = [
    "ano", "mes", "regional_de_saude", "municipio", "codigo_ibge",
    "numero_da_amostra", "motivo_da_coleta",
    "tipo_da_forma_de_abastecimento", "codigo_forma_de_abastecimento", "nome_da_forma_de_abastecimento",
    "data_da_coleta", "hora_da_coleta", "data_de_registro_no_sisagua",
    "procedencia_da_coleta", "ponto_de_coleta", "zona",
    "parametro", "resultado",
]


def pagina(ano, mes, parametro, numero):
    # desde novembro de 2026 a API trata offset como número da página, não da linha
    query = urllib.parse.urlencode(
        {"limit": PAGE, "offset": numero, "uf": UF, "ano": ano, "mes": mes, "parametro": parametro}
    )
    for tentativa in range(6):
        try:
            with urllib.request.urlopen(f"{API}?{query}", timeout=180) as resp:
                return json.load(resp)["parametros"]
        except Exception as erro:
            if tentativa == 5:
                raise
            print(f"  nova tentativa ({erro})")
            time.sleep(5 * (tentativa + 1))


def baixar_ano(ano):
    linhas = []
    for mes in range(1, 13):
        for parametro in PARAMETROS:
            vistas = set()
            numero = 0
            # segue até uma página vazia, para não perder dados se a API reduzir o tamanho da página
            while bloco := pagina(ano, mes, parametro, numero):
                chaves = {json.dumps(l, sort_keys=True, ensure_ascii=False) for l in bloco}
                # se a API voltar a tratar offset como linha, as páginas se repetem quase inteiras
                if len(chaves & vistas) > len(chaves) // 2:
                    raise SystemExit(f"{ano}-{mes:02d} {parametro}: páginas repetidas, a paginação da API mudou")
                vistas |= chaves
                linhas += bloco
                numero += 1
    # a paginação por offset pode repetir linhas se a base mudar durante a coleta
    unicas = {json.dumps(l, sort_keys=True, ensure_ascii=False): l for l in linhas}
    return list(unicas.values()), len(linhas) - len(unicas)


def grava(linhas, arquivo):
    """Grava só COLUNAS, com as linhas ordenadas e o gzip sem data: o arquivo só muda se os dados mudarem.

    Devolve False quando o conteúdo é igual ao do arquivo existente e nada foi gravado.
    """
    texto = io.StringIO()
    escritor = csv.writer(texto, lineterminator="\n")
    escritor.writerow(COLUNAS)
    escritor.writerows(sorted(["" if l.get(c) is None else str(l[c]) for c in COLUNAS] for l in linhas))
    conteudo = texto.getvalue().encode("utf-8")
    if arquivo.exists() and gzip.decompress(arquivo.read_bytes()) == conteudo:
        return False
    temporario = arquivo.with_suffix(".tmp")
    with temporario.open("wb") as saida, gzip.GzipFile(filename="", mode="wb", fileobj=saida, mtime=0) as gz:
        gz.write(conteudo)
    temporario.replace(arquivo)
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="baixa de novo também os anos fechados")
    args = ap.parse_args()
    HISTORICO.mkdir(parents=True, exist_ok=True)
    RECENTE.mkdir(parents=True, exist_ok=True)
    contagens = json.loads(CONTAGENS.read_text(encoding="utf-8")) if CONTAGENS.exists() else {}
    atual = dt.date.today().year
    for ano in range(ANO_INICIAL, atual + 1):
        fechado = ano < atual - 1
        arquivo = (HISTORICO if fechado else RECENTE) / f"vigilancia_al_{ano}.csv.gz"
        if fechado and arquivo.exists() and not args.all:
            continue
        linhas, repetidas = baixar_ano(ano)
        if not linhas:
            # não sobrescreve um arquivo bom com uma resposta vazia da API
            if arquivo.exists():
                raise SystemExit(f"{ano}: API devolveu zero linhas; arquivo existente mantido")
            print(f"{ano}: sem dados")
            continue
        anterior = contagens.get(str(ano))
        if anterior and len(linhas) < (1 - QUEDA_MAXIMA) * anterior:
            raise SystemExit(
                f"{ano}: {len(linhas)} linhas, contra {anterior} na última atualização. A API pode ter mudado; "
                "nada foi gravado. Se a queda for real, apague data/contagens.json e rode de novo."
            )
        mudou = grava(linhas, arquivo)
        contagens[str(ano)] = len(linhas)
        print(f"{ano}: {len(linhas)} linhas ({repetidas} repetidas removidas){'' if mudou else ', sem mudança'}", flush=True)
    CONTAGENS.write_text(json.dumps(contagens, indent=1, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
