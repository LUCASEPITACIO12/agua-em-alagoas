# Água em Alagoas

Painel estático com as amostras de vigilância do SISAGUA em Alagoas, de 2014 em diante: cloro residual livre, turbidez, coliformes totais e *Escherichia coli*.

## Gerar localmente

Precisa só de Python 3 e usa apenas a biblioteca padrão.

```bash
python tools/fetch_sisagua.py
python tools/build.py
```

O resultado é `site/index.html`. O primeiro download leva cerca de 30 minutos. Use `--all` para baixar de novo também os anos antigos.

## Publicar com atualização quinzenal

1. Crie um repositório no GitHub e envie esta pasta.
2. Em Settings > Pages, escolha GitHub Actions como origem.
3. Em Actions, rode "Atualizar painel" uma vez.

Depois disso, ele roda nos dias 1 e 16 de cada mês. Se a API falhar ou faltar um ano, o site anterior continua no ar.

## Fonte e tratamento

- Fonte: API `apidadosabertos.saude.gov.br/sisagua/vigilancia-parametros-basicos`, com 1.000 linhas por página. Para 2018, as contagens e chaves das amostras bateram integralmente com o CSV oficial (`tools/compare_csv.py`).
- Excluídas: coletas que não são de rotina, água bruta da captação, duplicatas exatas, resultados ilegíveis, cloro acima de 20 mg/L e turbidez acima de 1.000 uT. Os dois tetos são decisões deste painel para isolar prováveis erros de digitação.
- O número da amostra não identifica a amostra sozinho, porque se repete entre municípios e datas.
- `codigo_ibge` vem vazio em boa parte dos anos, então o município é identificado pelo nome e cruzado com o IBGE.
- Critérios: Portaria GM/MS 888/2021. Mínimo de 0,2 mg/L de cloro (art. 32), máximo de 5 mg/L (Anexo 9), turbidez de até 5 uT (art. 28, § 2º), *Escherichia coli* ausente (Anexo 1).
- Categorias do cloro: Insuficiente (abaixo de 0,2), Adequado (0,2 a 2,0), Alerta (acima de 2,0 até 5,0) e Acima do máximo (mais de 5). O limite de 2 mg/L é critério do painel, não da portaria; Alerta não conta como fora do padrão.
- Opção "SAA: rede de distribuição e estação de tratamento": amostras de SAA com procedência `SISTEMA DE DISTRIBUIÇÃO` ou `ESTAÇÃO DE TRATAMENTO DE ÁGUA`. Continua sendo vigilância do setor saúde e não avalia cada prestador.
- Coliformes totais aparecem como percentual com presença, sem julgar conformidade, porque a tolerância da norma depende do sistema e do mês.
- Municípios com menos de 30 amostras no período ficam hachurados no mapa e no fim da tabela.
