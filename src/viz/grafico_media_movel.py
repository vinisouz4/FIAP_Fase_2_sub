"""
Visualização: preço do Brent x média móvel de 7 dias (últimos anos).

Fonte dos dados:
  - padrão : consulta a tabela default.petroleo_media_movel no Athena (via awswrangler)
  - --csv  : arquivo CSV local com colunas data, preco_brent_usd, media_movel_7d (teste offline)

Uso:
    python grafico_media_movel.py --desde 2015 --saida ../../output/grafico_media_movel.png
"""
import argparse
import os

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

EVENTOS = [
    ("2008-07-03", "Pico pré-crise\n2008"),
    ("2014-11-27", "OPEP mantém\nprodução (2014)"),
    ("2020-04-20", "Covid-19\n(2020)"),
    ("2022-03-08", "Guerra na\nUcrânia (2022)"),
]


def carregar(args) -> pd.DataFrame:
    if args.csv:
        df = pd.read_csv(args.csv, parse_dates=["data"])
    else:
        import awswrangler as wr

        sql = f"""
            SELECT data, preco_brent_usd, media_movel_7d
            FROM {args.database}.{args.table}
            WHERE ano >= {args.desde}
            ORDER BY data
        """
        df = wr.athena.read_sql_query(sql, database=args.database, ctas_approach=False)
        df["data"] = pd.to_datetime(df["data"])
    return df.sort_values("data").reset_index(drop=True)


def plotar(df: pd.DataFrame, saida: str):
    plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False})
    fig, (ax1, ax2) = plt.subplots(
        2, 1, figsize=(14, 9), gridspec_kw={"height_ratios": [3, 1.4]}, constrained_layout=True
    )

    # Painel 1: série diária + média móvel
    ax1.plot(df["data"], df["preco_brent_usd"], color="#b0bec5", lw=0.8, label="Preço diário (US$/barril)")
    ax1.plot(df["data"], df["media_movel_7d"], color="#d84315", lw=1.8, label="Média móvel 7 dias")
    ymax = df["preco_brent_usd"].max()
    for dt, rotulo in EVENTOS:
        d = pd.Timestamp(dt)
        if df["data"].min() <= d <= df["data"].max():
            ax1.axvline(d, color="#455a64", ls="--", lw=0.8)
            ax1.text(d, ymax * 0.98, rotulo, fontsize=8, ha="center", va="top",
                     bbox=dict(fc="white", ec="none", alpha=0.8))
    imax = df["media_movel_7d"].idxmax()
    imin = df["media_movel_7d"].idxmin()
    for i, cor in ((imax, "#2e7d32"), (imin, "#c62828")):
        ax1.annotate(f"{df.loc[i, 'media_movel_7d']:.1f}\n{df.loc[i, 'data']:%d/%m/%Y}",
                     (df.loc[i, "data"], df.loc[i, "media_movel_7d"]),
                     textcoords="offset points", xytext=(0, 14 if i == imax else -30),
                     ha="center", color=cor, fontsize=8, arrowprops=dict(arrowstyle="-", color=cor))
    ax1.set_title("Petróleo Brent (FOB) - preço diário x média móvel de 7 dias", fontsize=14, weight="bold")
    ax1.set_ylabel("US$ por barril")
    ax1.margins(y=0.15)
    ax1.grid(alpha=0.25)
    ax1.legend(loc="upper right", bbox_to_anchor=(1, 0.88))
    ax1.xaxis.set_major_locator(mdates.YearLocator())
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))

    # Painel 2: média anual da média móvel (tendência de longo prazo)
    anual = df.assign(ano=df["data"].dt.year).groupby("ano")["media_movel_7d"].mean()
    ax2.bar(anual.index.astype(str), anual.values, color="#ef6c00")
    for x, v in zip(anual.index.astype(str), anual.values):
        ax2.text(x, v + 1, f"{v:.0f}", ha="center", fontsize=8)
    ax2.set_title("Média anual da média móvel de 7 dias", fontsize=11)
    ax2.set_ylabel("US$ por barril")
    ax2.grid(axis="y", alpha=0.25)

    os.makedirs(os.path.dirname(os.path.abspath(saida)), exist_ok=True)
    fig.savefig(saida, dpi=150)
    print(f"Gráfico salvo em {saida}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--desde", type=int, default=2015, help="ano inicial")
    ap.add_argument("--database", default=os.getenv("GLUE_DATABASE", "default"))
    ap.add_argument("--table", default=os.getenv("GLUE_TABLE", "petroleo_media_movel"))
    ap.add_argument("--csv", help="CSV local (em vez do Athena)")
    ap.add_argument("--saida", default="output/grafico_media_movel.png")
    a = ap.parse_args()
    d = carregar(a)
    if a.csv:
        d = d[d["data"].dt.year >= a.desde]
    plotar(d, a.saida)
