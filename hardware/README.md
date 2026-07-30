# Hardware

- `platforms.md` — выбор ESP32 dev-board (топ-5 из 10+ исследованных кандидатов, 12 параметров)
- `bom.csv` — перечень компонентов (Bill of Materials)
- `electronics/` — схемы (KiCad), см. подкаталог
- `mechanical/` — 3D модели корпуса и радиатора

## Итоговая стоимость BOM

Комплектующие (без учета КПД потерь при сборке, пайке и труда):

```
$ python3 -c "
import csv
total = 0
with open('bom.csv') as f:
    for row in csv.DictReader(f):
        total += int(row['Кол-во']) * float(row['Примерная цена USD'])
print(f'Итого: \${total:.0f}')
"
Итого: $1326
```

Наибольшая статья расходов — батарея LiFePO4 48V 30Ah (~$700, 53% от BOM),
что ожидаемо для автономного полевого аппарата (см.
`docs/battery_energy_budget.md`).
