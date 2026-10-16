# Examples

`numbers.sample.csv` shows the minimal input shape — a single `number` column.

```bash
python3 -m patent_intel.gp resolve examples/numbers.sample.csv --col number --lang ENGLISH -o /tmp/meta.csv
```

Any CSV/XLSX column of publication numbers works; pass the column name with `--col`.
