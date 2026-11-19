-- =====================================================================
-- Athena - Pipeline Petróleo Brent (FIAP MLET Fase 2)
-- Workgroup: primary | Database: default
-- A tabela default.petroleo_media_movel é criada PELO GLUE JOB (sem crawler).
-- =====================================================================

-- 0) Confirmar que o Glue criou a tabela e as partições
SHOW TABLES IN default;
SHOW CREATE TABLE default.petroleo_media_movel;
SHOW PARTITIONS default.petroleo_media_movel;

-- 1) Seleção básica dos dados
SELECT data, preco_brent_usd, media_movel_7d, qtd_obs_janela, ano, mes
FROM default.petroleo_media_movel
ORDER BY data DESC
LIMIT 20;

-- 2) Preço x média móvel em um período (partition pruning por ano)
SELECT data, preco_brent_usd, media_movel_7d,
       ROUND(preco_brent_usd - media_movel_7d, 2) AS desvio_vs_mm
FROM default.petroleo_media_movel
WHERE ano BETWEEN 2020 AND 2022
ORDER BY data;

-- 3) Média anual da média móvel + mínimo e máximo
SELECT ano,
       ROUND(AVG(media_movel_7d), 2) AS media_anual,
       ROUND(MIN(media_movel_7d), 2) AS minimo,
       ROUND(MAX(media_movel_7d), 2) AS maximo,
       COUNT(*)                      AS dias_uteis
FROM default.petroleo_media_movel
GROUP BY ano
ORDER BY ano DESC;

-- 4) Dias em que o preço ficou >10% acima da média móvel (picos)
SELECT data, preco_brent_usd, media_movel_7d
FROM default.petroleo_media_movel
WHERE preco_brent_usd > media_movel_7d * 1.10
ORDER BY data DESC
LIMIT 20;

-- =====================================================================
-- OPCIONAL: tabela da camada RAW (para mostrar o dado bruto particionado)
-- Usa partition projection => não precisa de MSCK REPAIR. Troque <BUCKET>.
-- =====================================================================
CREATE EXTERNAL TABLE IF NOT EXISTS default.petroleo_brent_raw (
  data             date,
  preco_brent_usd  double
)
PARTITIONED BY (dt_ingestao string)
STORED AS PARQUET
LOCATION 's3://<BUCKET>/raw/petroleo_brent/'
TBLPROPERTIES (
  'projection.enabled'           = 'true',
  'projection.dt_ingestao.type'  = 'date',
  'projection.dt_ingestao.range' = '2024-01-01,NOW',
  'projection.dt_ingestao.format'= 'yyyy-MM-dd',
  'storage.location.template'    = 's3://<BUCKET>/raw/petroleo_brent/dt_ingestao=${dt_ingestao}/'
);

SELECT * FROM default.petroleo_brent_raw ORDER BY data DESC LIMIT 10;

-- =====================================================================
-- FALLBACK: se por algum motivo o Glue não criar a tabela, use este DDL
-- (equivalente ao que o job gera). Depois rode MSCK REPAIR.
-- =====================================================================
-- CREATE EXTERNAL TABLE IF NOT EXISTS default.petroleo_media_movel (
--   data date, preco_brent_usd double, media_movel_7d double,
--   qtd_obs_janela int, mes int
-- )
-- PARTITIONED BY (ano int)
-- STORED AS PARQUET
-- LOCATION 's3://<BUCKET>/refined/petroleo_media_movel/';
-- MSCK REPAIR TABLE default.petroleo_media_movel;
