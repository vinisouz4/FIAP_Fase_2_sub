"""
AWS Glue Job (PySpark) - média móvel do preço do petróleo Brent.

 1. Lê o Parquet raw do S3 (todas as partições dt_ingestao=...)
 2. Deduplica por data (mantém a ingestão mais recente)
 3. Calcula média móvel em janela de N dias corridos (padrão 7 = 1 semana)
 4. Grava Parquet particionado por ano no S3 refined
 5. Cria/atualiza AUTOMATICAMENTE a tabela no Glue Data Catalog (database default)
    via getSink(enableUpdateCatalog=True) - sem crawler.

Parâmetros (--KEY value): JOB_NAME, RAW_PATH, REFINED_PATH, DATABASE, TABLE, WINDOW_DAYS
"""
import sys

from awsglue.context import GlueContext
from awsglue.dynamicframe import DynamicFrame
from awsglue.job import Job
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from pyspark.sql import Window
from pyspark.sql import functions as F

args = getResolvedOptions(
    sys.argv, ["JOB_NAME", "RAW_PATH", "REFINED_PATH", "DATABASE", "TABLE", "WINDOW_DAYS"]
)
RAW_PATH = args["RAW_PATH"]
REFINED_PATH = args["REFINED_PATH"]
DATABASE = args["DATABASE"]
TABLE = args["TABLE"]
WINDOW_DAYS = int(args["WINDOW_DAYS"])

sc = SparkContext()
glue_ctx = GlueContext(sc)
spark = glue_ctx.spark_session
job = Job(glue_ctx)
job.init(args["JOB_NAME"], args)

# 1) leitura (basePath faz o Spark expor dt_ingestao como coluna)
raw = spark.read.option("basePath", RAW_PATH).parquet(RAW_PATH)

# 2) deduplicação: última ingestão vence
w_dedup = Window.partitionBy("data").orderBy(F.col("dt_ingestao").desc())
dedup = (
    raw.withColumn("_rn", F.row_number().over(w_dedup))
    .filter("_rn = 1")
    .drop("_rn", "dt_ingestao")
    .withColumn("data", F.col("data").cast("date"))
)

# 3) média móvel: janela de N dias CORRIDOS terminando na data corrente.
# O Ipea só publica dias úteis, então 7 dias corridos ~ 5 observações (qtd_obs_janela mostra isso).
secs = 86400
w_mm = (
    Window.orderBy(F.col("data").cast("timestamp").cast("long"))
    .rangeBetween(-(WINDOW_DAYS - 1) * secs, 0)
)
out = (
    dedup.withColumn("media_movel_7d", F.round(F.avg("preco_brent_usd").over(w_mm), 4))
    .withColumn("qtd_obs_janela", F.count("preco_brent_usd").over(w_mm).cast("int"))
    .withColumn("ano", F.year("data"))
    .withColumn("mes", F.month("data"))
    .orderBy("data")
)

# 4/5) escrita + catálogo automático
dyf = DynamicFrame.fromDF(out, glue_ctx, "media_movel")
glue_ctx.purge_s3_path(REFINED_PATH, options={"retentionPeriod": 0})  # recarga completa = idempotente

sink = glue_ctx.getSink(
    connection_type="s3",
    path=REFINED_PATH,
    enableUpdateCatalog=True,
    updateBehavior="UPDATE_IN_DATABASE",
    partitionKeys=["ano"],
)
sink.setFormat("glueparquet", compression="snappy")
sink.setCatalogInfo(catalogDatabase=DATABASE, catalogTableName=TABLE)
sink.writeFrame(dyf)

print(f"OK: {out.count()} linhas -> {REFINED_PATH} | tabela {DATABASE}.{TABLE}")
job.commit()
