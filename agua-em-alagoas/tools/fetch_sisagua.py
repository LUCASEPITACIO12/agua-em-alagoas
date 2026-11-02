"""Baixa da API do SISAGUA as amostras de vigilância de Alagoas (parâmetros básicos).

Grava um CSV por ano em data/raw/. Anos fechados só são baixados uma vez;
os dois anos mais recentes são sempre rebaixados, porque a alimentação do
SISAGUA é retroativa. Use --all para rebaixar tudo.
"""
import argparse
import csv
import datetime as dt
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
RAW = pathlib.Path(__file__).resolve().parent.parent / "data" / "raw"


def pagina(ano, mes, parametro, offset):
    query = urllib.parse.urlencode(
        {"limit": PAGE, "offset": offset, "uf": UF, "ano": ano, "mes": mes, "parametro": parametro}
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
            offset = 0
            while True:
                bloco = pagina(ano, mes, parametro, offset)
                linhas += bloco
                if len(bloco) < PAGE:
                    break
                offset += PAGE
    # a paginação por offset pode repetir linhas se a base mudar durante a coleta
    unicas = {json.dumps(l, sort_keys=True, ensure_ascii=False): l for l in linhas}
    return list(unicas.values()), len(linhas) - len(unicas)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args()
    RAW.mkdir(parents=True, exist_ok=True)
    atual = dt.date.today().year
    for ano in range(ANO_INICIAL, atual + 1):
        arquivo = RAW / f"vigilancia_al_{ano}.csv"
        if arquivo.exists() and ano < atual - 1 and not args.all:
            continue
        linhas, repetidas = baixar_ano(ano)
        if not linhas:
            # não sobrescreve um arquivo bom com uma resposta vazia da API
            if arquivo.exists():
                raise SystemExit(f"{ano}: API devolveu zero linhas; arquivo existente mantido")
            print(f"{ano}: sem dados")
            continue
        temporario = arquivo.with_suffix(".tmp")
        with temporario.open("w", newline="", encoding="utf-8") as saida:
            escritor = csv.DictWriter(saida, fieldnames=list(linhas[0].keys()))
            escritor.writeheader()
            escritor.writerows(linhas)
        temporario.replace(arquivo)
        print(f"{ano}: {len(linhas)} linhas ({repetidas} repetidas removidas)", flush=True)


if __name__ == "__main__":
    main()
