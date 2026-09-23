# География пяти районов кейса

`astana_districts.geojson` содержит выборку административных контуров OpenStreetMap, полученную через Overpass API 23 сентября 2026 года. Поле `osm_timestamp` в файле содержит время исходной базы. Координаты — WGS84, порядок `[долгота, широта]`, геометрия — MultiPolygon.

| Район в кейсе | Исходный объект |
|---|---|
| Есиль | [OSM relation 3479876](https://www.openstreetmap.org/relation/3479876) |
| Алматы | [OSM relation 3482819](https://www.openstreetmap.org/relation/3482819) |
| Сарыарка | [OSM relation 3486954](https://www.openstreetmap.org/relation/3486954) |
| Байконур | [OSM relation 8593081](https://www.openstreetmap.org/relation/8593081) |
| Нура | [OSM relation 20593940](https://www.openstreetmap.org/relation/20593940) |

© [OpenStreetMap contributors](https://www.openstreetmap.org/copyright). Данные распространяются по лицензии [Open Database License 1.0](https://opendatacommons.org/licenses/odbl/1-0/). Атрибуция также показана под картой приложения. Уличную подложку предоставляет CARTO; ее ресурсы загружаются отдельно браузером.

Скрипт `scripts/fetch_districts.py` объединяет пути отношений в замкнутые кольца, сохраняет внутренние кольца и проверяет геометрию перед записью. Подписи размещаются внутри контуров при построении карты. Это выборка пяти районов учебного датасета, а не полная административная карта Астаны и не подтверждение официальных границ. Показатели, доли населения, баллы и прогнозы на карте взяты из синтетического кейса, а не из OSM.

Обновление из корня проекта:

```powershell
.\.venv\Scripts\python.exe scripts/fetch_districts.py
```

Обычный запуск приложения не обращается к Overpass: геометрия читается из локального файла.
