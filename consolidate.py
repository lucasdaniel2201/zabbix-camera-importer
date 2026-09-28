"""Consolida todos os relatorios JSON dos lotes em um resumo final."""
import json
from pathlib import Path

REPORT_DIR = Path(__file__).resolve().parent / "reports"
json_files = sorted(REPORT_DIR.glob("zabbix-web-import-*.json"))

total_processed = 0
total_created = 0
total_exists = 0
total_errors = 0
error_details = []

for jf in json_files:
    with jf.open("r", encoding="utf-8") as f:
        data = json.load(f)
    s = data["summary"]
    total_processed += s["processed"]
    total_created += s["created"]
    total_exists += s["exists"]
    total_errors += s["errors"]

    # Coletar erros individuais
    for r in data["results"]:
        if r["status"] == "error":
            error_details.append(f"  CSV#{r['csv_index']}: {r['host']} | {r['message']}")

print("=" * 60)
print("  RESUMO FINAL - IMPORTACAO ZABBIX")
print("=" * 60)
print(f"  Total processados : {total_processed}")
print(f"  Criados           : {total_created}")
print(f"  Ja existentes     : {total_exists}")
print(f"  Erros             : {total_errors}")
print(f"  Relatorios        : {len(json_files)} arquivos")
print("=" * 60)

if error_details:
    print(f"\n  Detalhes dos erros ({len(error_details)}):")
    for e in error_details:
        print(e)
else:
    print("\n  Nenhum erro encontrado!")

print(f"\n  Relatorios em: {REPORT_DIR}")
