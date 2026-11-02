"""Confere a API contra o CSV oficial do mesmo ano: uso: compare_csv.py <csv oficial> <ano>"""
import collections, csv, sys
sys.stdout.reconfigure(encoding="utf-8")
csv.field_size_limit(10**7)
oficial, ano = sys.argv[1], sys.argv[2]
P = {"Cloro residual livre (mg/L)", "Turbidez (uT)", "Coliformes totais", "Escherichia coli"}
of = collections.Counter(); chaves = collections.Counter()
with open(oficial, encoding="latin-1", newline="") as f:
    for r in csv.DictReader(f, delimiter=";"):
        if r["SG_UF"] == "AL" and r["PARAMETRO"] in P:
            of[r["PARAMETRO"]] += 1
            chaves[(r["NU_AMOSTRA"], r["PARAMETRO"], r["DT_COLETA"][:10].replace("/", "-"), r["NO_MUNICIPIO"], r["RESULTADO"])] += 1
api = collections.Counter(); ca = collections.Counter()
for r in csv.DictReader(open(f"data/raw/vigilancia_al_{ano}.csv", encoding="utf-8")):
    api[r["parametro"]] += 1
    ca[(r["numero_da_amostra"], r["parametro"], r["data_da_coleta"][:10], r["municipio"], r["resultado"])] += 1
for p in sorted(P):
    print(p, "csv", of[p], "api", api[p])
print("so no csv", sum((chaves - ca).values()), "so na api", sum((ca - chaves).values()))
print("ex so csv", list((chaves - ca))[:4]); print("ex so api", list((ca - chaves))[:4])
