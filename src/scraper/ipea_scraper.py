"""
Scraper do preço do petróleo Brent (FOB) no Ipeadata -> Parquet no S3 (raw).

Fonte : http://www.ipeadata.gov.br/ExibeSerie.aspx?module=m&serid=1650971490
Saída : s3://<BUCKET>/raw/petroleo_brent/dt_ingestao=YYYY-MM-DD/petroleo_brent.parquet
        (partição diária por data de ingestão, estilo Hive)

Uso:
    python ipea_scraper.py --bucket meu-bucket            # grava no S3
    python ipea_scraper.py --local ./output/raw           # grava local (teste sem AWS)

Também pode rodar como AWS Lambda (handler: lambda_handler) se o runtime tiver
pandas/pyarrow/requests/lxml (ex.: layer AWSSDKPandas + layer com requests/lxml).
"""
import argparse
import io
import logging
import os
from datetime import date

import pandas as pd
import requests

URL = "http://www.ipeadata.gov.br/ExibeSerie.aspx?module=m&serid=1650971490&oper=view"
# Fallback: API OData oficial do Ipeadata (mesma série)
API = "http://www.ipeadata.gov.br/api/odata4/ValoresSerie(SERCODIGO='EIA366_PBRENT366')"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; FIAP-MLET-pipeline/1.0)"}
PREFIX = "raw/petroleo_brent"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("ipea_scraper")


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    """Padroniza para colunas: data (date) e preco_brent_usd (float)."""
    df = df.iloc[:, :2].copy()
    df.columns = ["data", "preco_brent_usd"]
    df["data"] = pd.to_datetime(df["data"].astype(str).str.strip(), format="%d/%m/%Y", errors="coerce")
    df["preco_brent_usd"] = pd.to_numeric(
        df["preco_brent_usd"].astype(str).str.strip().str.replace(",", ".", regex=False),
        errors="coerce",
    )
    df = df.dropna().drop_duplicates(subset="data").sort_values("data").reset_index(drop=True)
    df["data"] = df["data"].dt.date
    return df


def scrape_html() -> pd.DataFrame:
    """Scrap da tabela HTML da página do Ipeadata."""
    log.info("Baixando página do Ipeadata...")
    resp = requests.get(URL, headers=HEADERS, timeout=60)
    resp.raise_for_status()
    tables = pd.read_html(
        io.StringIO(resp.text), attrs={"id": "grd_DXMainTable"}, decimal=",", thousands="."
    )
    if not tables:
        raise ValueError("Tabela grd_DXMainTable não encontrada")
    # a tabela do DevExpress traz linhas de cabeçalho/rodapé: _normalize descarta o que não é data
    df = _normalize(tables[0])
    if df.empty:
        raise ValueError("Tabela encontrada, mas sem linhas válidas")
    return df


def fetch_api() -> pd.DataFrame:
    """Fallback via API OData (caso o layout da página mude)."""
    log.warning("Usando fallback via API OData do Ipeadata")
    resp = requests.get(API, headers=HEADERS, timeout=60)
    resp.raise_for_status()
    rows = resp.json()["value"]
    df = pd.DataFrame(rows)[["VALDATA", "VALVALOR"]]
    df["VALDATA"] = (
        pd.to_datetime(df["VALDATA"], utc=True).dt.tz_convert("America/Sao_Paulo").dt.strftime("%d/%m/%Y")
    )
    return _normalize(df)


def get_data() -> pd.DataFrame:
    try:
        df = scrape_html()
    except Exception as exc:  # noqa: BLE001
        log.error("Scrap HTML falhou (%s)", exc)
        df = fetch_api()
    log.info("%d registros (%s -> %s)", len(df), df["data"].min(), df["data"].max())
    return df


def to_parquet_bytes(df: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    df.to_parquet(buf, index=False, engine="pyarrow", compression="snappy")
    return buf.getvalue()


def save_s3(df: pd.DataFrame, bucket: str, ingest_date: date) -> str:
    import boto3

    key = f"{PREFIX}/dt_ingestao={ingest_date.isoformat()}/petroleo_brent.parquet"
    boto3.client("s3").put_object(Bucket=bucket, Key=key, Body=to_parquet_bytes(df))
    uri = f"s3://{bucket}/{key}"
    log.info("Gravado em %s", uri)
    return uri


def save_local(df: pd.DataFrame, base_dir: str, ingest_date: date) -> str:
    folder = os.path.join(base_dir, "petroleo_brent", f"dt_ingestao={ingest_date.isoformat()}")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, "petroleo_brent.parquet")
    with open(path, "wb") as fh:
        fh.write(to_parquet_bytes(df))
    log.info("Gravado em %s", path)
    return path


def lambda_handler(event=None, context=None):
    bucket = (event or {}).get("bucket") or os.environ["BUCKET"]
    uri = save_s3(get_data(), bucket, date.today())
    return {"statusCode": 200, "body": uri}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--bucket", default=os.getenv("BUCKET"), help="bucket S3 de destino")
    ap.add_argument("--local", help="pasta local (em vez do S3), útil para testar")
    args = ap.parse_args()

    data = get_data()
    today = date.today()
    if args.local:
        save_local(data, args.local, today)
    elif args.bucket:
        save_s3(data, args.bucket, today)
    else:
        ap.error("informe --bucket (ou variável BUCKET) ou --local")
