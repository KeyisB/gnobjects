# Отчёт по аудиту библиотек `gnserver` и `gnobjects`

Дата: 2026-05-23
Объём: прочитаны все `.py`-файлы обеих библиотек (кроме данных-констант в `_crt.py`, которые являются зашифрованным блобом, и вендорной обёртки `oqs/oqs.py` — она проверена, замечаний по логике нет, это сторонний код liboqs-python).

> Этот документ — **только отчёт**. Никакие правки в код не вносились.
> Серьёзность помечена: 🔴 критично · 🟠 важно · 🟡 средне · ⚪ мелочь/качество.

---

## 0. Резюме

Найдено несколько **реальных багов корректности** (часть приводит к 500-ответам вместо корректных кодов, часть — к неверному сопоставлению команд ответа), одна **серьёзная утечка секретов в логи**, и большой набор **возможностей ускорения горячего пути** (decode запроса, dispatch, сериализация payload, доступ к `CommandObject`, обработка датаграмм).

Самые приоритетные пункты:
1. 🔴 `CORSObject` не сохраняет `except_client_types_domains` → AttributeError → 500 вместо `cors:ClientTypeNotAllowed`.
2. 🔴 Дубли/перезапись `cls_command` в дереве команд (`DomainNotFound`, `Core.DnsCore`) → неверное сопоставление ответов.
3. 🔴 Логирование секретного `kdc_key` в открытом виде (hex + userFriendly) в PQ-handshake.
4. 🟠 Линейный поиск по словарям при декоде каждого запроса вместо готовых реверс-таблиц.
5. 🟠 Двойная сериализация payload на каждом ответе/запросе при отправке.

---

## 1. Баги корректности

### 1.1 🔴 `CORSObject.__init__` не сохраняет `except_client_types_domains`
Файл: `gnserver/src/GNServer/server/_models.py:154-203`

В сигнатуре есть параметр `except_client_types_domains` (строка 164), но в теле `__init__` он **не присваивается** в `self`. Сохраняется только `self.except_object_types_domains = except_object_types_domains` (строка 202).

В резолвере CORS он читается:
`gnserver/src/GNServer/server/_cors_resolver.py:142`
```python
if cors.except_client_types_domains is None or request.client.domain not in cors.except_client_types_domains:
```
Поскольку атрибута нет → `AttributeError`. Эта ветка выполняется именно тогда, когда тип клиента **не** разрешён, т.е. вместо корректного `cors.ClientTypeNotAllowed` (403) клиент получит `InternalServerError` (500), т.к. исключение перехватывается общим обработчиком в `_app.py:_handle_request`.
Также `except_client_types_domains`, переданный пользователем, фактически **игнорируется**.

**Решение:** добавить `self.except_client_types_domains = except_client_types_domains`.

### 1.2 🔴 Перезапись и дубли `cls_command` в дереве быстрых команд
Файл: `gnobjects/src/gnobjects/net/fastcommands.py`

`register_command` пишет `COMMAND_TREE[path] = cls.cls_command`. Один и тот же `path` регистрируется несколько раз с **разными** значениями — выигрывает последний по порядку определения класс:

- `("gn", 'Types', 'DomainNotFound')` регистрируется трижды:
  - строка 728: `cls_command = "gn:gn:tps:dnf"`
  - строки 868-874: `cls_command = "gn:gn:lyr:nex:domain:dnf"`
  - строки 905-911: `cls_command = "gn:gn:lyr:os:api"`

  Итог: `COMMAND_TREE[("gn","Types","DomainNotFound")] == "gn:gn:lyr:os:api"`. То есть проверка `response.command.gn.Types.DomainNotFound` сравнивает значение команды с `"gn:gn:lyr:os:api"`, а не с `"gn:gn:tps:dnf"`. Сервер, отдавший `"gn:gn:tps:dnf"`, **не будет распознан** как DomainNotFound.

- `Core.DnsCore` (`layer`-ветка), строки 898-903: `cls_command = "gn:gn:lyr:os:api"` — это явная копипаста (то же значение, что у `OriginShieldApi`, строка 903). Скорее всего должно быть что-то вроде `"gn:gn:lyr:core:..."`. В результате одна и та же строка команды соответствует трём разным семантикам.

**Решение:** сделать значения `cls_command` уникальными и убрать дублирующие `@register_command` с конфликтующими path.

### 1.3 🟠 Опечатка `@register_command(('NoResponse'))` — строка вместо кортежа
Файл: `gnobjects/src/gnobjects/net/fastcommands.py:75`
```python
@register_command(('NoResponse'))   # это строка 'NoResponse', а не кортеж ('NoResponse',)
```
Из-за этого в `register_command` `path = 'NoResponse'`, и в `COMMAND_PREFIX` добавляются мусорные ключи-срезы строки (`'N'`, `'No'`, `'Nos'`, …) — `for i in range(1, len(path))`. Функционально верхнеуровневый `NoResponse` срабатывает «случайно» (ключ и `_command_path` совпадают как строки), но дерево префиксов засоряется. Правильно: `('NoResponse',)`.

### 1.4 🟠 Async-generator-обработчики маршрутов приводят к 500
Файл: `gnserver/src/GNServer/server/_app.py:478-479` и `:807-818`

В `dispatchRequest`:
```python
if self._route_is_asyncgen[rid]:
    return r.handler(**kw)   # возвращает async_generator
```
А в `_handle_request`:
```python
response = await self._api.dispatchRequest(request, self)
if not isinstance(response, GNResponse):
    await self.sendResponseFromRequest(request, AllGNFastCommands.InternalServerError(...))
```
Возвращённый async-generator не является `GNResponse`, поэтому такой маршрут всегда даёт `InternalServerError`. Либо это незавершённая фича стриминга, либо баг. Нужно либо реализовать обработку async-gen (обернуть в стрим-ответ), либо убрать ветку.

### 1.5 🟡 `Url.setUrl(Url)` не копирует `isIp`
Файл: `gnobjects/src/gnobjects/net/objects.py:76-85`

При копировании из другого `Url` копируются все поля, кроме `self.isIp`. После копирования `isIp` остаётся в значении по умолчанию (`False`), что ломает `build()` (ветка оборачивания IPv6 в скобки) и определение IP-адреса для скопированных URL.

### 1.6 🟡 `decode_varlen_1248` не проверяет длину буфера
Файл: `gnobjects/src/gnobjects/net/_data_pack_f.py:81-100`

В отличие от `decode_varlen_2358` (есть проверки `len(b) < size`), `decode_varlen_1248` читает `b[0]` без проверки и `b[:size]` без контроля усечения. На усечённом буфере вернёт неверную длину или бросит `IndexError` вместо `IncompleteGNFrameError`. Функция используется в разборе заголовков контейнеров (ITP/STP/VFSD/FAT/DMP) — путь, куда приходят данные из сети.

### 1.7 🟡 Легаси-функции wire-формата рассинхронизированы с новым форматом
Файл: `gnobjects/src/gnobjects/net/_data_pack.py`
- `compress_TempDataObject` / `decompress_TempDataObject` (строки 1184-1327) работают со старым байтовым форматом (`b0`/`b1`, биты method/path/payload, `common_gnrequest_compressTypes`), который **не совпадает** с актуальными контейнерами `_Aracada_container_packer` (там тип контейнера в первых 2 байтах). Если их вызвать на новых контейнерах — повреждение данных.
- `unpack_temp_data_group` (строки 1349-1358) при `version==0` вызывает `unpack_temp_data_object_v0`, а не `unpack_temp_data_group_v0` — явная ошибка.

Похоже на мёртвый код. Рекомендую удалить или пометить как deprecated, чтобы случайно не вызвать.

### 1.8 🟡 `GNTime.fromUNIX/toUNIX` в ветке по умолчанию даёт отрицательное «GN-время»
Файл: `gnobjects/src/gnobjects/time.py:15-33`

При `_set is None` (значение по умолчанию):
```python
fromUNIX -> base - float(unix)   # base ~ 1735689600 (2025-01-01), unix ~ 1747... → отрицательное
toUNIX   -> base - float(gn)
```
Пара взаимно-обратна (round-trip корректен), но само значение «GN-времени» выходит отрицательным для текущих дат, тогда как ожидается «секунды с 2025-01-01» (т.е. `unix - base`). Логика веток, вероятно, перепутана. Нужно подтверждение ожидаемой семантики.

### 1.9 ⚪ `CommandObject` объявляет `__eq__`/`__ne__` без `__hash__`
Файл: `gnobjects/src/gnobjects/net/objects.py:2923-2929`

При определении `__eq__` Python обнуляет `__hash__` → объект становится нехешируемым. Если `CommandObject` где-то используется как ключ словаря/множества — `TypeError`. Сейчас явных таких мест нет, но это латентный риск.

### 1.10 ⚪ Изменяемые значения по умолчанию в `CORSObject`
Файл: `gnserver/src/GNServer/server/_models.py:157-158`
`allow_object_types=['user','service']`, `allow_client_types=['net','local','server']` — общие изменяемые списки на все экземпляры. Антипаттерн; при будущей мутации даст перекрёстные эффекты.

### 1.11 ⚪ Несогласованная валидация `abs_id`
Файл: `gnobjects/src/gnobjects/abs/id.py:64-98`
`from_abs_to_gwis` проверяет нулевыми только первые 5 байт, но извлекает gwisid из `[24:32]` (т.е. байты 5..23 не проверяются), тогда как `is_abs_id_gwisid` проверяет `[0:24]`. Рекомендуется единый инвариант.

### 1.12 ⚪ `_convert_value` не обрабатывает `X | Y` (PEP 604)
Файл: `gnserver/src/GNServer/server/_routes.py:97`
`if origin is Union:` — не покрывает `types.UnionType` (синтаксис `int | None`). В `_func_params_validation.py` оба варианта обрабатываются, здесь — нет. Параметры пути/квери с аннотацией `int | None` не приведутся.

---

## 2. Безопасность

### 2.1 🔴 Логирование секретного `kdc_key` в открытом виде
Файл: `gnserver/src/GNServer/_gn_pq_handshake.py:547-549` и `:602-604`
```python
f"kdc_key_fp={kdc_key.hex() if kdc_key else 'none'} "
f"kdc_key={kdc_key if kdc_key else 'none'} "
f"kdc_key_uf={userFriendly.encode(kdc_key) if kdc_key else 'none'}"
```
В DEBUG-лог пишется **полный секретный ключ KDC** (и raw, и hex, и userFriendly). Это долгоживущий секрет соединения/домена. Любой, у кого есть доступ к логам (или включён DEBUG), получает ключевой материал.
**Решение:** удалить вывод самого ключа; оставить максимум короткий fingerprint (например, первые 8 символов хеша), а не сам ключ.

### 2.2 🟠 Множество `print()` в горячем пути транспорта/KDC
Файлы:
- `gnserver/src/GNServer/server/_datagram_enc.py:210` — `print('requestKeyIfNotExist: initByKeyid', ...)` (логирует keyid)
- `gnserver/src/GNServer/server/_datagram_enc.py:827` — `print(f"_init_encrypted_initial_connection start keyid=... data_len=...")`
- `gnserver/src/GNServer/server/_datagram_enc.py:934` — `print(f"requestKeyIfNotExist: _fetch_key_and_resume: ...")`

`print` идёт напрямую в stdout (минуя уровни логирования), создаёт шум, тормозит обработку датаграмм и потенциально раскрывает метаданные (keyid). Заменить на `logger.debug`.

### 2.3 🟡 Тестовые скрипты `t.py` в обоих репозиториях
`gnserver/t.py`, `gnobjects/t.py` — модифицированы (видны в git status). Это не часть библиотек; их не должно быть в дистрибутиве. Проверить, нет ли в них секретов/доменов, и исключить из пакета.

### 2.4 🟡 `GNProtocolParser.get` — гонка на «быстром пути»
Файл: `gnobjects/src/gnobjects/net/gnTransportProtocolParser.py:302-320`
Быстрый путь делает `self._cache.get(raw)` и `self._cache.move_to_end(raw)` **вне** `self._lock`, а медленный путь под локом вызывает `_evict_if_needed()` (`popitem`). Класс заявляет потокобезопасность через `RLock`, но `move_to_end`/чтение `OrderedDict` параллельно с мутацией из другого потока могут привести к `RuntimeError`/повреждению. В пределах одного event-loop (asyncio) это безопасно, но при многопоточном использовании — нет. Либо убрать претензию на потокобезопасность, либо защитить чтение.

---

## 3. Производительность горячего пути и «компиляция при старте»

> Это основной запрос. Ниже — где тратится CPU на каждый запрос/датаграмму и что можно предвычислить/скомпилировать.

### 3.1 🟠 Линейный поиск в декоде каждого запроса вместо готовых реверс-таблиц
Файл: `gnobjects/src/gnobjects/net/_data_pack.py`
В `unpack_gnrequest_v0` (строки 520-524) и `unpack_gnrequest_header_v0` (строки 692-696) определяется локальная `lookup_by_value`, которая **линейно** сканирует словарь `common_gnrequest_transports/methods/routes` для каждого транспорта/метода/маршрута на **каждый** входящий запрос.

При этом в этом же модуле уже есть готовые реверс-словари: `_rev_dataTypes`, `_rev_inTypes`, `_rev_methods` (строки 81-83). Для transports/routes их нет, но их легко предпосчитать один раз на уровне модуля.

**Выигрыш:** O(1) вместо O(n) на каждый декод заголовка запроса (самый горячий путь сервера). Низкий риск.

### 3.2 🟠 Двойная сериализация payload при отправке
Файлы: `gnobjects/src/gnobjects/net/objects.py` (`__init__` и `iterSerializedPayload`/`serialize`).

В `GNRequest.__init__`/`GNResponse.__init__` payload уже сериализуется один раз: `raw_payload = self._tdo.serialize()` и кладётся в `_AsyncPayloadState(initial_payload=raw_payload, complete=True)` (строки ~1511-1517 и ~2454-2460).

Но на пути отправки `iterSerializedPayload` (строки 1959-1961, 2574-2576) и `serialize` (1846, 2488) снова вызывают `self._tdo.serialize()` — **повторное** msgpack/zstd-кодирование того же payload. Для каждого ответа сервера это лишняя полная сериализация.

**Выигрыш:** закэшировать сериализованные байты в `TempDataObject`/состоянии и переиспользовать (или брать из `_payload_state._materialize_complete_payload()`), исключив повторный проход. Для крупных payload экономия существенная.

### 3.3 🟠 `_convert_value` пересчитывает `get_origin/get_args` на каждый параметр запроса
Файл: `gnserver/src/GNServer/server/_routes.py:87-106`, вызывается из `gnserver/src/GNServer/server/_app.py:408, 422`.

Для каждого path- и query-параметра на каждый запрос вызываются `get_origin(ann)`/`get_args(ann)` и поиск в `_CONVERTER_FUNC`. Это можно **скомпилировать один раз при регистрации маршрута**: построить для каждого имени параметра готовую функцию-конвертер (как уже делается для body-моделей в `Schema`). Тогда в dispatch останется только вызов готовой функции.

### 3.4 🟠 Пересборка и сортировка набора маршрутов-кандидатов на каждый запрос
Файл: `gnserver/src/GNServer/server/_app.py:201-224` (`_collect_candidate_routes`)

На каждый запрос:
- строится `set` первых сегментов,
- собирается `dict by_id`,
- в конце `sorted(by_id.values(), key=lambda r: self._route_order.get(id(r),0))`.

Порядок маршрутов фиксирован на момент регистрации, поэтому buckets в индексах (`_route_static_index`, `_route_dynamic_prefix_index`, `_route_dynamic_fallback_index`) можно хранить **уже отсортированными** при `_index_route`, и тогда слияние кандидатов делается без повторной сортировки. Это убирает аллокацию dict+sort из каждого запроса.

### 3.5 🟠 Дорогой `CommandObject.__getattribute__` на каждом доступе к команде
Файл: `gnobjects/src/gnobjects/net/objects.py:2868-2916`

`CommandObject` переопределяет `__getattribute__`, и **любой** доступ к атрибуту (включая `.value`) проходит через цепочку проверок: строковые сравнения, `getattr(cls, name)`, `isinstance(..., type)`, построение кортежей пути, создание объектов `_CommandPath`, поиск в `COMMAND_TREE`/`COMMAND_PREFIX`.

Это бьёт по горячему клиентскому пути, например в `gnserver/src/GNServer/client/_client.py:1167`:
```python
if resp.command.transport and not resp.command.transport.NoResponse:
```
— здесь на каждый ответ создаются `_CommandPath` и сканируются множества `COMMAND_PREFIX`. Аналогично `r1.command.ok`, `rs.command.ok`, и большой диагностический лог в `_kdc_object.py:349` (`bool(rs.command.app)`, `bool(rs.command.cors)` и т.д. — много дорогих доступов).

**Рекомендации:** кэшировать резолв (например, заранее построить `dict[значение_команды] -> set(путей)` и проверять принадлежность по значению за O(1)); не переопределять `__getattribute__` для системных полей (`value`); вынести «успех» в обычный property.

### 3.6 🟠 Повторные парсинги транспорт-протокола и `from_addr_to_maddr` на пакет
- `request.transportObject` (`gnobjects/.../objects.py:2329-2335`) парсит протокол (через кэш `GN_PARSER`), но в обработке dev-транспорта вызывается несколько раз за запрос (сервер `_resolve_dev_transport_request/_response`, клиент `_resolve_requests_transport`). Стоит закэшировать результат на самом `request`.
- `DatagramEndpoint.from_addr_to_maddr` (`_datagram_enc.py:1163-1172`) вызывается несколько раз на одну датаграмму: в `datagram_received` (fast-path), в `_inbound_worker`, в `_handle_datagram`, в `sendto`. Каждый раз — конкатенация строки + кортеж. Вычислять один раз и пробрасывать.

### 3.7 🟠 Логирование INFO на каждый запрос/ответ с энергичным f-string
Файлы:
- `gnserver/src/GNServer/server/_app.py:836` — `logger.info(f'[>] ... {response.command}')`
- `gnserver/src/GNServer/client/_client.py:461` — `logger.info(f'[<] Response: ...')`

f-string собирается **до** вызова `logger.info`, т.е. стоимость форматирования (включая дорогой `response.command` через `__getattribute__`/`__str__`) платится всегда, независимо от уровня. На нагрузке это заметно. Использовать ленивое логирование (`logger.info('%s', ...)`) или гард `if logger.isEnabledFor(INFO)`.

### 3.8 🟡 `response.ok()` без payload всё равно везёт STP(None)
Файл: `gnobjects/src/gnobjects/net/objects.py:2441-2460`
Если payload не модель/не TDO и равен `None`, ветка `else` всё равно делает `TempDataObject.STP(None)`. `serialize` даёт контейнер (2B тип + varint версии + 1B compression + msgpack nil) ≈ 5 байт, и `hasPayload` становится `True`. Т.е. каждый «пустой» ответ всё равно несёт payload-контейнер и проходит полный путь отправки payload. Если `None` трактовать как «нет payload», экономится payload-кадр и лишний `send_stream_data` на каждый такой ответ.

### 3.9 🟡 Пересоздание zstd-компрессора/декомпрессора на каждый объект
Файл: `gnobjects/src/gnobjects/net/objects.py:2119-2125`, `_compress_object`/`_decompress_object`
`_new_zstd_compressor(level)`/`_new_zstd_decompressor()` создают новый `ZstdCompressor/Decompressor` на каждый payload. Для одношагового сжатия их можно кэшировать по уровню, уменьшая накладные расходы на мелких частых сообщениях.

### 3.10 🟡 Повторный разбор заголовка контейнера при стриме
Файл: `gnobjects/src/gnobjects/net/objects.py:996-1073` (`_try_parse_container_header`)
При многочанковом payload заголовок повторно парсится (`unpack_temp_data_header(bytes(self._header_probe))`) с пересозданием `bytes(...)` из `bytearray` на каждый feed, пока не наберётся. На мелких чанках это лишние копии/парсинги.

### 3.11 🟡 AES-OCB через PyCryptodome в пер-датаграммном пути
Файл: `gnserver/src/GNServer/server/_datagram_enc.py:313-338`
Шифрование каждой датаграммы — `AES.new(..., MODE_OCB, ...)` (PyCryptodome) с созданием объекта шифра на каждый вызов. В проекте уже есть зависимость `cryptography` (HKDF/X25519). `AESGCM`/`ChaCha20Poly1305` из `cryptography` обычно быстрее на AES-NI. Стоит замерить и, возможно, перейти (с учётом совместимости wire-формата nonce/tag — потребуется версия формата).

### 3.12 🟡 Кандидаты на компиляцию (Cython/mypyc) при сборке
Наибольшая отдача — чистые байтовые операции в самом горячем пути:
- `gnobjects/src/gnobjects/net/_data_pack_f.py` — varint enc/dec (`encode/decode_varlen_1248/2358`, `*_data_with_len`, `pack/unpack_byte_*`). Маленький, чистый, вызывается на каждый кадр и контейнер — идеальный кандидат.
- `gnobjects/src/gnobjects/net/_data_pack.py` — `unpack_gnrequest_header_v0`, `unpack_temp_data_header`, `unpack_*_header`, `pack_gnrequest_header_v0`, `pack_gnresponse_header_v0`.
- `gnobjects/src/gnobjects/net/objects.py` — `_AsyncPayloadState` (буферизация/нарезка чанков) и `_Aracada_container_packer`.

Можно собирать в нативный модуль при установке без изменения публичного API.

### 3.13 ⚪ Двойной проход по `kw` в dispatch
Файл: `gnserver/src/GNServer/server/_app.py:407-425`
Сначала строится `kw` по path-params, затем добавляются query-params, затем `kw = {k:v for k,v in kw.items() if k in params}` — повторная пересборка словаря. Можно фильтровать по `params` сразу при вставке.

---

## 4. Прочее / качество кода

- ⚪ **Двойная конфигурация логирования.** `gnserver/src/GNServer/server/_app.py:60-74` настраивает логгер `GNServer` (handler, DEBUG) на уровне импорта, и параллельно есть `gnserver/src/GNServer/config.py` (`rebuild_log_config`). Две точки конфигурации могут конфликтовать (дублирование хендлеров/уровней).
- ⚪ **Мёртвый код `__info_dg_count_s`.** `_datagram_enc.py:645-647`: первая строка `return`, затем недостижимый `logger.debug`. Счётчик `__info_dg_count` инкрементируется, но никогда не выводится.
- ⚪ **Закомментированные блоки** в `_app.py` (1014-1031), `_client.py` (432-460, 966-976) — стоит удалить или оформить как задачи.
- ⚪ **`run()` в `_app.py` парсит TLS PEM вручную** (строки 929-964) разбиением по `-----BEGIN PRIVATE KEY-----`. Хрупко к вариациям PEM (CRLF, несколько ключей, типы ключей EC/RSA). Лучше использовать штатные загрузчики.
- ⚪ **`_models.py: CORSObject.serialize/deserialize` асимметричны.** `serialize` не кодирует `allow_object_types`, `except_*`; `deserialize` их не восстанавливает. Если предполагается передача CORS по сети — данные теряются (если только это не намеренно «server-side only»).
- ⚪ **`_app.py:fastFile`/`staticDir`** нормализуют путь по-разному; стоит вынести нормализацию в один helper.
- ⚪ **`GNResponse(Exception)`** не вызывает `super().__init__` с сообщением — при логировании «как исключения» сторонними инструментами `args` пуст. Не критично (есть `__str__`), но нестандартно.

---

## 5. Что покрывает этот отчёт и что нет

**Покрывает:**
- Корректность wire-кодеков (`_data_pack.py`, `_data_pack_f.py`), контейнеров (`objects.py`), быстрых команд (`fastcommands.py`), модели (`base_model.py`).
- Диспетчеризацию и валидацию параметров сервера (`_app.py`, `_func_params_validation.py`, `_routes.py`, `_cors_resolver.py`, `_models.py`).
- Клиент и транспорт (`_client.py`, `_client_quic_shell.py`, `_datagram_enc.py`).
- PQ-handshake/сессии/QUIC-интеграцию (`_gn_pq_session.py`, `_gn_pq_handshake.py`, `_gn_pq_quic.py`), KDC (`_kdc_object.py`).
- Утилиты (`domains.py`, `tools.py`, `gnTransportProtocolParser.py`, `values.py`, `time.py`, `abs/*`, `gwis/*`, `config.py`, обёртку `oqs/*`).

**Не покрывает (требует уточнения/доп. проверки):**
- Криптостойкость самого протокола PQ-handshake (порядок подписей, привязка домена, защита от downgrade/replay) — сделан беглый просмотр логики, формальный криптоаудит не проводился. Отдельно стоит проверить: 1) что `encType==2` (PQ без KDC) с `accept_any_server_domain=True` не допускает MITM по подмене сертификатного домена; 2) корректность перехода ключей `setSessionRoot64_receive_only`/`applyPendingKeyOut` при потере пакетов.
- Содержимое зашифрованных констант `_crt.py` и CA-ключа в `_ctr_ca_pub.py` (проверена только логика доступа `get_gn_pq_ca_public_key`).
- Поведение под реальной нагрузкой/конкуренцией (только статический анализ).
- Совместимость предлагаемых оптимизаций с другими потребителями библиотек вне этих двух репозиториев.

---

## 6. Рекомендованный порядок исправлений

1. 🔴 `except_client_types_domains` в `CORSObject` (1.1) — простая правка, убирает 500.
2. 🔴 Удалить вывод `kdc_key` в логи (2.1).
3. 🔴 Развести дубли `cls_command` (1.2) — иначе ответы DomainNotFound/Core не распознаются.
4. 🟠 Использовать реверс-таблицы в декоде запроса (3.1) и убрать двойную сериализацию (3.2).
5. 🟠 Заменить `print` на `logger.debug` (2.2); ленивое INFO-логирование (3.7).
6. 🟠 Предкомпиляция конвертеров параметров и предсортировка маршрутов (3.3, 3.4); оптимизация `CommandObject` (3.5).
7. 🟡 Остальные пункты разделов 1 и 3 по приоритету; рассмотреть компиляцию `_data_pack_f.py` (3.12).
