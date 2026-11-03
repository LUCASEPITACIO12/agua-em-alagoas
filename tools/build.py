"""Trata os CSVs de data/raw, agrega por mês e gera site/index.html a partir de tools/template.html."""
import collections
import csv
import datetime as dt
import gzip
import json
import pathlib
import re
import time
import unicodedata
import urllib.request

RAIZ = pathlib.Path(__file__).resolve().parent.parent
RAW = RAIZ / "data" / "raw"
PARAMS = {
    "Cloro residual livre (mg/L)": "cloro",
    "Turbidez (uT)": "turbidez",
    "Coliformes totais": "coliformes",
    "Escherichia coli": "ecoli",
}
ORDEM = ["cloro", "turbidez", "coliformes", "ecoli"]
TIPOS = ["SAA", "SAC", "SAI"]
ANO_INICIAL = 2014
# Portaria GM/MS 888/2021: art. 32 (mínimo), Anexo 9 (máximo), art. 28 §2º e Anexo 11 (turbidez)
CLORO_MIN, CLORO_MAX, TURBIDEZ_MAX = 0.2, 5.0, 5.0
# Critério de interpretação do painel, não da portaria: acima disto e até o máximo é "alerta"
CLORO_ALERTA = 2.0
# Procedências que formam a visão da água entregue pelos sistemas (SAA)
PROCEDENCIAS_REDE = {"SISTEMA DE DISTRIBUIÇÃO", "ESTAÇÃO DE TRATAMENTO DE ÁGUA"}
# Acima disto tratamos como erro de digitação: sai do cálculo e é contado à parte
TETO_PLAUSIVEL = {"cloro": 20.0, "turbidez": 1000.0}
IBGE_MUNICIPIOS = "https://servicodados.ibge.gov.br/api/v1/localidades/estados/27/municipios"
IBGE_MALHA = (
    "https://servicodados.ibge.gov.br/api/v3/malhas/estados/27"
    "?intrarregiao=municipio&qualidade=minima&formato=application/vnd.geo%2Bjson"
)


def normaliza(nome):
    sem_acento = unicodedata.normalize("NFD", nome).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Z ]", "", sem_acento.upper()).strip()


def numero(texto):
    """Converte '1,5', '1.460,00', ',08' e '2,' em float; devolve None se não for número."""
    texto = (texto or "").strip()
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    if not re.fullmatch(r"\d*\.?\d*", texto) or not re.search(r"\d", texto):
        return None
    return float(texto)


def classifica(parametro, resultado):
    """Devolve 'ok', 'baixo', 'alerta', 'alto', 'implausivel' ou 'invalido'."""
    if parametro in ("coliformes", "ecoli"):
        valor = (resultado or "").strip().upper()
        return {"AUSENTE": "ok", "PRESENTE": "alto"}.get(valor, "invalido")
    valor = numero(resultado)
    if valor is None:
        return "invalido"
    if valor > TETO_PLAUSIVEL[parametro]:
        return "implausivel"
    if parametro == "cloro":
        if valor < CLORO_MIN:
            return "baixo"
        if valor > CLORO_MAX:
            return "alto"
        return "alerta" if valor > CLORO_ALERTA else "ok"
    return "alto" if valor > TURBIDEZ_MAX else "ok"


def baixa_json(url, arquivo):
    """Lê a cópia salva em tools/ (o IBGE não responde aos runners do GitHub); sem ela, baixa da API.

    tools/27 é a malha dos municípios e tools/municipios.json é a lista, ambos baixados do IBGE.
    """
    local = RAIZ / "tools" / arquivo
    for tentativa in range(6):
        if local.exists():
            bruto = local.read_bytes()
            break
        try:
            with urllib.request.urlopen(url, timeout=120) as resp:
                bruto = resp.read()
            break
        except Exception as erro:
            if tentativa == 5:
                raise
            print(f"  nova tentativa ({erro})")
            time.sleep(10 * (tentativa + 1))
    # o IBGE responde em gzip mesmo sem o cliente pedir
    return json.loads(gzip.decompress(bruto) if bruto[:2] == b"\x1f\x8b" else bruto)


def mapa_svg(codigos_ibge):
    """Projeta a malha do IBGE em caminhos SVG, com a escala corrigida pela latitude de Alagoas."""
    malha = baixa_json(IBGE_MALHA, "27")
    pontos = []
    for f in malha["features"]:
        g = f["geometry"]
        poligonos = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
        f["_poligonos"] = poligonos
        pontos += [p for pol in poligonos for anel in pol for p in anel]
    x0, x1 = min(p[0] for p in pontos), max(p[0] for p in pontos)
    y0, y1 = min(p[1] for p in pontos), max(p[1] for p in pontos)
    largura = 800
    escala = largura / (x1 - x0)
    kx = 0.986  # cos(9,5°): um grau de longitude é mais curto que um de latitude em Alagoas
    altura = round((y1 - y0) * escala / kx)
    caminhos = {}
    for f in malha["features"]:
        d = ""
        for pol in f["_poligonos"]:
            for anel in pol:
                d += "M" + "L".join(f"{(p[0]-x0)*escala:.1f},{(y1-p[1])*escala/kx:.1f}" for p in anel) + "Z"
        caminhos[f["properties"]["codarea"]] = d
    return {"w": largura, "h": altura, "paths": {codigos_ibge[c]: d for c, d in caminhos.items() if c in codigos_ibge}}


def main():
    arquivos = sorted(RAW.glob("vigilancia_al_*.csv"))
    ibge = baixa_json(IBGE_MUNICIPIOS, "municipios.json")
    por_nome = {normaliza(m["nome"]): m for m in ibge}
    csv.field_size_limit(10**7)

    vistos = set()
    celulas = collections.defaultdict(lambda: [0, 0, 0, 0])  # n, baixo, alto, alerta
    regionais = collections.defaultdict(collections.Counter)
    excluidas = collections.Counter()
    atrasos = []
    anos = collections.Counter()
    ultima_coleta = ultimo_registro = ""
    hoje = dt.date.today()
    total = 0

    for arquivo in arquivos:
        with arquivo.open(encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                total += 1
                anos[r["ano"]] += 1
                parametro = PARAMS.get(r["parametro"])
                # o número da amostra se repete entre municípios e datas; a chave precisa de todos
                chave = (r["numero_da_amostra"], r["parametro"], r["municipio"], r["data_da_coleta"],
                         r["hora_da_coleta"], r["codigo_forma_de_abastecimento"], r["resultado"])
                if chave in vistos:
                    excluidas["duplicada"] += 1
                    continue
                vistos.add(chave)
                if parametro is None:
                    continue
                if r["motivo_da_coleta"] != "Rotina":
                    excluidas["nao_rotina"] += 1
                    continue
                if "CAPTA" in r["procedencia_da_coleta"]:
                    excluidas["agua_bruta"] += 1
                    continue
                coleta = r["data_da_coleta"][:10]
                if not coleta or r["tipo_da_forma_de_abastecimento"] not in TIPOS:
                    excluidas["sem_data_ou_tipo"] += 1
                    continue
                classe = classifica(parametro, r["resultado"])
                if classe in ("implausivel", "invalido"):
                    excluidas[f"{classe}_{parametro}"] += 1
                    continue
                nome = normaliza(r["municipio"])
                if nome not in por_nome:
                    excluidas["municipio_desconhecido"] += 1
                    continue
                regionais[nome][r["regional_de_saude"]] += 1
                registro = (r["data_de_registro_no_sisagua"] or "")[:10]
                ultima_coleta = max(ultima_coleta, coleta)
                ultimo_registro = max(ultimo_registro, registro)
                if registro and (hoje - dt.date.fromisoformat(coleta)).days <= 365:
                    atrasos.append((dt.date.fromisoformat(registro) - dt.date.fromisoformat(coleta)).days)
                rede = int(r["procedencia_da_coleta"] in PROCEDENCIAS_REDE)
                c = celulas[(nome, coleta[:7], parametro, r["tipo_da_forma_de_abastecimento"], rede)]
                c[0] += 1
                c[1] += classe == "baixo"
                c[2] += classe == "alto"
                c[3] += classe == "alerta"

    faltando = [a for a in range(ANO_INICIAL, hoje.year + 1) if str(a) not in anos]
    if faltando or not celulas:
        raise SystemExit(f"Dados incompletos, faltam os anos {faltando}; site anterior mantido")

    atrasos.sort()
    atraso_p90 = atrasos[int(0.9 * (len(atrasos) - 1))] if atrasos else 0
    corte = dt.date.fromisoformat(ultimo_registro) - dt.timedelta(days=atraso_p90)

    nomes = sorted(por_nome, key=lambda n: por_nome[n]["nome"])
    indice = {n: i for i, n in enumerate(nomes)}
    municipios = []
    for n in nomes:
        regional = regionais[n].most_common(1)[0][0] if regionais[n] else ""
        municipios.append({"nome": por_nome[n]["nome"], "reg": regional})
    meses = sorted({k[1] for k in celulas})
    im = {m: i for i, m in enumerate(meses)}
    linhas = [
        [indice[n], im[m], ORDEM.index(p), TIPOS.index(t), rede, *v]
        for (n, m, p, t, rede), v in sorted(celulas.items())
    ]
    dados = {
        "gerado": hoje.isoformat(),
        "ultimaColeta": ultima_coleta,
        "ultimoRegistro": ultimo_registro,
        "atrasoP90": atraso_p90,
        "provisorioDesde": corte.isoformat()[:7],
        "totalBruto": total,
        "excluidas": excluidas,
        "municipios": municipios,
        "regionais": sorted({m["reg"] for m in municipios if m["reg"]}),
        "meses": meses,
        "linhas": linhas,
        "mapa": mapa_svg({str(por_nome[n]["id"]): indice[n] for n in nomes}),
    }
    saida = RAIZ / "site"
    saida.mkdir(exist_ok=True)
    modelo = (RAIZ / "tools" / "template.html").read_text(encoding="utf-8")
    json_dados = json.dumps(dados, ensure_ascii=False, separators=(",", ":"))
    (saida / "index.html").write_text(modelo.replace("/*__DADOS__*/null", json_dados), encoding="utf-8")
    print(f"{total} linhas lidas, {sum(c[0] for c in celulas.values())} usadas, excluídas: {dict(excluidas)}")
    print(f"última coleta {ultima_coleta}, último registro {ultimo_registro}, atraso p90 {atraso_p90} dias")
    print(f"site/index.html: {(saida / 'index.html').stat().st_size / 1e6:.1f} MB, {len(linhas)} células")


if __name__ == "__main__":
    main()
