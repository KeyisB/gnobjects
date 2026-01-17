from typing import Optional, Union, List

from KeyisBTools.models.serialization import SerializableType

from .objects import GNResponse, FileObject, CORSObject, TempDataGroup, TempDataObject

COMMAND_TREE: dict[tuple[str, ...], Union[str, int, bool]] = {}
# path-prefix -> set(full_paths)
COMMAND_PREFIX: dict[tuple[str, ...], set[tuple[str, ...]]] = {}


def register_command(path: tuple[str, ...]):
    def decorator(cls):
        cls._command_path = path

        COMMAND_TREE[path] = cls.cls_command

        # важно: НЕ создаём запись для полного пути, только для префиксов
        for i in range(1, len(path)):
            prefix = path[:i]
            COMMAND_PREFIX.setdefault(prefix, set()).add(path)

        return cls

    return decorator




class GNFastCommand(GNResponse):
    """
    # Быстрый ответ
    """
    def __init__(self,
                 payload: Optional[Union[SerializableType, TempDataGroup, TempDataObject]] = None,
                 cookies: Optional[dict] = None
                 ) -> None:

        command = getattr(self, "cls_command", None) # type: ignore
        if command is None:
            command = 'gn:client:undefined'

        super().__init__(command=command, payload=payload, cookies=cookies)


class AllGNFastCommands:

    @register_command(("ok",))
    class ok(GNFastCommand):
        """
        # Корректный ответ
        """
        cls_command = True
        def __init__(self,
                 payload: Optional[Union[SerializableType, TempDataGroup, TempDataObject]] = None,
                 cookies: Optional[dict] = None
                 ) -> None:
            """
            # Корректный ответ
            """
            super().__init__(payload, cookies)

    
    @register_command(('Rejected', ))
    class Rejected(GNFastCommand):
        """
        # Запрос отклонён
        Сервер отклонил запрос из за бизнес-логики. (не связано с доступом)
        Пример: Ошибка или ограничение на сервере, из-за которого запрос не может быть обработан.
        Используется для обозначения отказа в обработке запроса.
        """
        cls_command = "gn:app:402"
       
    @register_command(('UnprocessableEntity', ))
    class UnprocessableEntity(GNFastCommand):
        """
        # Некорректные данные
        Ошибка указывает, что сервер понял запрос, но не может его обработать из-за неверного содержания. 
        Пример: передан payload с правильной структурой, но поля содержат некорректные значения (например, строка вместо числа).
        Используется, когда данные формально корректны, но нарушают бизнес-логику.
        """
        cls_command = "gn:app:422"


    @register_command(('BadRequest', ))
    class BadRequest(GNFastCommand):
        """
        # Неправильный синтаксис url или параметров
        Сервер не может понять запрос из-за ошибок в структуре или параметрах. 
        Пример: отсутствует обязательный параметр или указан некорректный формат даты.
        Часто используется при валидации входных данных на уровне запроса.
        """
        cls_command = "gn:app:400"


    @register_command(('Forbidden', ))
    class Forbidden(GNFastCommand):
        """
        # Доступ запрещён, даже при наличии авторизации
        Клиент аутентифицирован, но не имеет прав для выполнения действия. 
        Пример: пользователь вошёл в систему, но пытается изменить чужие данные.
        Используется для разграничения прав доступа.
        """
        cls_command = "gn:app:403"


    @register_command(('Unauthorized', ))
    class Unauthorized(GNFastCommand):
        """
        # Требуется авторизация
        Ошибка возвращается, если запрос требует входа, но клиент не предоставил или предоставил неверные данные авторизации. 
        Пример: отсутствует заголовок Authorization или токен недействителен.
        Используется для защиты закрытых API-эндпоинтов.
        """
        cls_command = "gn:app:401"


    @register_command(('NotFound', ))
    class NotFound(GNFastCommand):
        """
        # Ресурс не найден
        Запрошенный объект или путь не существует на сервере. 
        Пример: попытка получить пользователя с несуществующим ID.
        Часто используется для API-ответов на невалидные ссылки.
        """
        cls_command = "gn:app:404"


    @register_command(('MethodNotAllowed', ))
    class MethodNotAllowed(GNFastCommand):
        """
        # Метод запроса не поддерживается данным ресурсом
        Ресурс существует, но используемый gn-метод недопустим. 
        Пример: к ресурсу разрешён только GET, а клиент делает POST.
        Используется для ограничения набора действий над конкретными ресурсами.
        """
        cls_command = "gn:app:405"



    @register_command(('InternalServerError', ))
    class InternalServerError(GNFastCommand):
        """
        # Внутренняя ошибка сервера
        Сервер столкнулся с непредвиденной ситуацией, которая не позволяет выполнить запрос. 
        Пример: необработанное исключение в коде приложения.
        Используется как универсальная ошибка для внутренних сбоев.
        """
        cls_command = "gn:app:500"


    @register_command(('NotImplemented', ))
    class NotImplemented(GNFastCommand):
        """
        # Метод или функционал ещё не реализован
        Сервер распознаёт запрос, но не поддерживает требуемый функционал. 
        Пример: метод API описан в документации, но ещё не реализован.
        Используется для обозначения незавершённых частей системы.
        """
        cls_command = "gn:app:501"


    @register_command(('ServiceUnavailable', ))
    class ServiceUnavailable(GNFastCommand):
        """
        # Сервис временно недоступен
        Сервер не может обработать запрос из-за перегрузки или обслуживания. 
        Пример: база данных недоступна или сервис в режиме обновления.
        Используется для сигнализации о временных проблемах.
        """
        cls_command = "gn:app:503"


    class transport:
        """
        # transport
        """
        cls_command = "gn:transport"

        @register_command(("transport", 'NetworkUnreachable'))
        class NetworkUnreachable(GNFastCommand):
            """
            # Сеть недостижима
            Узел не может быть доставлен: маршрута нет, либо маршрутизатор отклоняет пакеты.
            """
            cls_command = "gn:transport:1"


        @register_command(("transport", 'HostUnreachable'))
        class HostUnreachable(GNFastCommand):
            """
            # Хост недостижим
            Узел существует в сети, но не отвечает: ARP/ND отсутствует, либо интерфейс недоступен.
            """
            cls_command = "gn:transport:2"


        @register_command(("transport", 'PortUnreachable'))
        class PortUnreachable(GNFastCommand):
            """
            # Порт недоступен
            UDP-ответ ICMP Port Unreachable или отсутствие слушателя на порту.
            """
            cls_command = "gn:transport:3"


        @register_command(("transport", 'SendTimeout'))
        class SendTimeout(GNFastCommand):
            """
            # Таймаут отправки
            UDP-сокет не принял пакет в системный буфер до истечения лимита.
            """
            cls_command = "gn:transport:4"


        @register_command(("transport", 'ReceiveTimeout'))
        class ReceiveTimeout(GNFastCommand):
            """
            # Таймаут получения
            Нет ни одного транспортного пакета в заданный интервал.
            """
            cls_command = "gn:transport:5"


        @register_command(("transport", 'SocketClosed'))
        class SocketClosed(GNFastCommand):
            """
            # Сокет закрыт
            Операция недоступна: сокет был закрыт до завершения обработки.
            """
            cls_command = "gn:transport:6"


        @register_command(("transport", 'AddressInvalid'))
        class AddressInvalid(GNFastCommand):
            """
            # Некорректный адрес
            Некорректный IPv4/IPv6/mapped адрес или недопустимый формат.
            """
            cls_command = "gn:transport:7"


        @register_command(("transport", 'AddressNotAvailable'))
        class AddressNotAvailable(GNFastCommand):
            """
            # Адрес недоступен
            Локальный адрес не может быть использован для bind/route.
            """
            cls_command = "gn:transport:8"


        @register_command(("transport", 'ConnectionIdMismatch'))
        class ConnectionIdMismatch(GNFastCommand):
            """
            # Ошибка ConnectionID
            Пакет не относится к данному соединению: CID не совпадает с локальными маршрутами.
            """
            cls_command = "gn:transport:9"


        @register_command(("transport", 'QuicInitialLost'))
        class QuicInitialLost(GNFastCommand):
            """
            # Потерян Initial
            Ни один QUIC Initial не был подтверждён в допустимое время.
            """
            cls_command = "gn:transport:10"


        @register_command(("transport", 'QuicHandshakeTimeout'))
        class QuicHandshakeTimeout(GNFastCommand):
            """
            # Таймаут QUIC-handshake
            Клиент или сервер не завершил crypto-handshake в ожидаемое окно.
            """
            cls_command = "gn:transport:11"


        @register_command(("transport", 'QuicVersionMismatch'))
        class QuicVersionMismatch(GNFastCommand):
            """
            # Несовпадение версий QUIC
            Удалённая сторона не поддерживает требуемую версию GN-QUIC.
            """
            cls_command = "gn:transport:12"


        @register_command(("transport", 'QuicFrameInvalid'))
        class QuicFrameInvalid(GNFastCommand):
            """
            # Некорректный транспортный фрейм
            Фрейм структуры QUIC (до уровня GN) повреждён или нарушает формат.
            """
            cls_command = "gn:transport:13"


        @register_command(("transport", 'PacketDropped'))
        class PacketDropped(GNFastCommand):
            """
            # Пакет отброшен
            Пакет потерян на пути или ядро его сбросило (буфер NIC/kernel).
            """
            cls_command = "gn:transport:14"


        @register_command(("transport", 'TransportProtocolError'))
        class TransportProtocolError(GNFastCommand):
            """
            # Ошибка транспортного протокола
            Некорректная последовательность сообщений, неразрешимый конфликт состояний.
            """
            cls_command = "gn:transport:15"

        @register_command(("transport", 'ConnectionError'))
        class ConnectionError(GNFastCommand):
            """
            # Неизвесная ошибка поключения
            """
            cls_command = "gn:transport:16"
    
    class app:
        """
        # app
        """
        cls_command = "gn:app"

        @register_command(("app", 'UnprocessableEntity'))
        class UnprocessableEntity(GNFastCommand):
            """
            # Некорректные данные
            Ошибка указывает, что сервер понял запрос, но не может его обработать из-за неверного содержания. 
            Пример: передан payload с правильной структурой, но поля содержат некорректные значения (например, строка вместо числа).
            Используется, когда данные формально корректны, но нарушают бизнес-логику.
            """
            cls_command = "gn:app:422"


        @register_command(("app", 'BadRequest'))
        class BadRequest(GNFastCommand):
            """
            # Неправильный синтаксис url или параметров
            Сервер не может понять запрос из-за ошибок в структуре или параметрах. 
            Пример: отсутствует обязательный параметр или указан некорректный формат даты.
            Часто используется при валидации входных данных на уровне запроса.
            """
            cls_command = "gn:app:400"

        @register_command(("app", 'Rejected'))
        class Rejected(GNFastCommand):
            """
            # Запрос отклонён
            Сервер отклонил запрос из за бизнес-логики. (не связано с доступом)
            Пример: Ошибка или ограничение на сервере, из-за которого запрос не может быть обработан.
            Используется для обозначения отказа в обработке запроса.
            """
            cls_command = "gn:app:402"

        @register_command(("app", 'Unauthorized'))
        class Unauthorized(GNFastCommand):
            """
            # Требуется авторизация
            Ошибка возвращается, если запрос требует входа, но клиент не предоставил или предоставил неверные данные авторизации. 
            Пример: отсутствует заголовок Authorization или токен недействителен.
            Используется для защиты закрытых API-эндпоинтов.
            """
            cls_command = "gn:app:401"

        @register_command(("app", 'Forbidden'))
        class Forbidden(GNFastCommand):
            """
            # Доступ запрещён, даже при наличии авторизации
            Клиент аутентифицирован, но не имеет прав для выполнения действия. 
            Пример: пользователь вошёл в систему, но пытается изменить чужие данные.
            Используется для разграничения прав доступа.
            """
            cls_command = "gn:app:403"


        @register_command(("app", 'NotFound'))
        class NotFound(GNFastCommand):
            """
            # Ресурс не найден
            Запрошенный объект или путь не существует на сервере. 
            Пример: попытка получить пользователя с несуществующим ID.
            Часто используется для API-ответов на невалидные ссылки.
            """
            cls_command = "gn:app:404"


        @register_command(("app", 'MethodNotAllowed'))
        class MethodNotAllowed(GNFastCommand):
            """
            # Метод запроса не поддерживается данным ресурсом
            Ресурс существует, но используемый gn-метод недопустим. 
            Пример: к ресурсу разрешён только GET, а клиент делает POST.
            Используется для ограничения набора действий над конкретными ресурсами.
            """
            cls_command = "gn:app:405"



        @register_command(("app", 'InternalServerError'))
        class InternalServerError(GNFastCommand):
            """
            # Внутренняя ошибка сервера
            Сервер столкнулся с непредвиденной ситуацией, которая не позволяет выполнить запрос. 
            Пример: необработанное исключение в коде приложения.
            Используется как универсальная ошибка для внутренних сбоев.
            """
            cls_command = "gn:app:500"


        @register_command(("app", 'NotImplemented'))
        class NotImplemented(GNFastCommand):
            """
            # Метод или функционал ещё не реализован
            Сервер распознаёт запрос, но не поддерживает требуемый функционал. 
            Пример: метод API описан в документации, но ещё не реализован.
            Используется для обозначения незавершённых частей системы.
            """
            cls_command = "gn:app:501"


        @register_command(("app", 'ServiceUnavailable'))
        class ServiceUnavailable(GNFastCommand):
            """
            # Сервис временно недоступен
            Сервер не может обработать запрос из-за перегрузки или обслуживания. 
            Пример: база данных недоступна или сервис в режиме обновления.
            Используется для сигнализации о временных проблемах.
            """
            cls_command = "gn:app:503"
    
    class dns:
        """
        # DNS
        """
        cls_command = "gn:dns"

        @register_command(("dns", 'DomainAccessDenied'))
        class DomainAccessDenied(GNFastCommand):
            """
            # DNS Доступ к домену запрещён
            Запрос был отклонён из-за настроек доступа.
            """
            cls_command = "gn:dns:601"


        @register_command(("dns", 'InvalidVerificationAlgorithm'))
        class InvalidVerificationAlgorithm(GNFastCommand):
            """
            # DNS Не удалось подтвердить личность запроса
            Возможно неправильный алгоритм шифрования.
            Совет: Проверьте правильность выбора алгоритма шифрования. Необходим алгоритм по умолчанию gn:upd:1
            """
            cls_command = "gn:dns:602"

        @register_command(("dns", 'DomainBlocked'))
        class DomainBlocked(GNFastCommand):
            """
            # DNS Запрашиваемый домен заблокирован
            """
            cls_command = "gn:dns:605"

        @register_command(("dns", 'DomainNotFound'))
        class DomainNotFound(GNFastCommand):
            """
            # DNS Запрашиваемый домен не найден
            Домен отсутствует в системе или не имеет действующих записей.
            Совет: проверьте правильность домена. И его присутсивие в открытой зоне.
            """
            cls_command = "gn:dns:606"

    class cors:
        """
        # CORS
        """
        cls_command = "gn:cors"

        @register_command(("cors", 'OriginNotAllowed'))
        class OriginNotAllowed(GNFastCommand):
            """
            # CORS Запрещённый источник
            Источник запроса (Origin) не разрешён в списке `allow_origins`.
            Пример: запрос с домена, который отсутствует в политике безопасности.
            """
            cls_command = "gn:cors:701"


        @register_command(("cors", 'MethodNotAllowed'))
        class MethodNotAllowed(GNFastCommand):
            """
            # CORS Запрещённый метод
            Метод запроса не разрешён в списке `allow_methods`.
            Пример: попытка выполнить `delete` при разрешённых только `get` и `post`.
            """
            cls_command = "gn:cors:702"


        @register_command(("cors", 'ClientTypeNotAllowed'))
        class ClientTypeNotAllowed(GNFastCommand):
            """
            # CORS Запрещённый тип клиента
            Тип клиента отсутствует в списке `allow_client_types`.
            Пример: доступ разрешён только 'proxy' и 'server', но запрос пришёл от 'client'.
            """
            cls_command = "gn:cors:703"


        @register_command(("cors", 'TransportProtocolNotAllowed'))
        class TransportProtocolNotAllowed(GNFastCommand):
            """
            # CORS Запрещённый транспортный протокол
            Используемый транспортный протокол не разрешён в списке `allow_transport_protocols`.
            Пример: попытка доступа через gn:quik:dev при разрешённом только gn:quik:real.
            """
            cls_command = "gn:cors:704"


        @register_command(("cors", 'RouteProtocolNotAllowed'))
        class RouteProtocolNotAllowed(GNFastCommand):
            """
            # CORS Запрещённый маршрутный протокол
            Указанный маршрутный протокол не разрешён в списке `allow_route_protocols`.
            Пример: запрос с использованием нестандартного маршрута.
            """
            cls_command = "gn:cors:705"


        @register_command(("cors", 'RequestProtocolNotAllowed'))
        class RequestProtocolNotAllowed(GNFastCommand):
            """
            # CORS Запрещённый протокол запроса
            Протокол, указанный в запросе, не разрешён в списке `allow_request_protocols`.
            Пример: запрос с использованием нестандартного протокола.
            """
            cls_command = "gn:cors:706"

    class kdc:
        """
        # CORS
        """
        cls_command = "gn:kdc"

        @register_command(("kdc", 'DecryptRequestFailed'))
        class DecryptRequestFailed(GNFastCommand):
            """
            # KDC Ошибка расшифровки запроса
            Не удалось расшифровать входящий запрос.  
            Пример: переданный клиентом зашифрованный блок не совпадает с ожидаемым форматом или ключами.
            """
            cls_command = "gn:kdc:891"


        @register_command(("kdc", 'DecryptResponseFailed'))
        class DecryptResponseFailed(GNFastCommand):
            """
            # KDC Ошибка расшифровки ответа
            Не удалось расшифровать ответ сервера.  
            Пример: клиент не смог корректно расшифровать данные, возвращённые сервером.
            """
            cls_command = "gn:kdc:892"


        @register_command(("kdc", 'SignatureVerificationFailed'))
        class SignatureVerificationFailed(GNFastCommand):
            """
            # KDC Ошибка проверки подписи
            Подпись запроса или ответа не прошла валидацию.  
            Пример: данные были изменены или использован неверный ключ.
            """
            cls_command = "gn:kdc:893"


        @register_command(("kdc", 'DomainVerificationFailed'))
        class DomainVerificationFailed(GNFastCommand):
            """
            # KDC Ошибка проверки домена
            Не удалось подтвердить указанный домен.
            """
            cls_command = "gn:kdc:894"


        @register_command(("kdc", 'InvalidRequestFormat'))
        class InvalidRequestFormat(GNFastCommand):
            """
            # KDC Некорректный формат запроса
            Запрос имеет недопустимый или повреждённый формат.
            """
            cls_command = "gn:kdc:895"


        @register_command(("kdc", 'InvalidResponseFormat'))
        class InvalidResponseFormat(GNFastCommand):
            """
            # KDC Некорректный формат ответа
            Ответ имеет недопустимый или повреждённый формат.  
            Пример: сервер вернул некорректный блок сессионных данных.
            """
            cls_command = "gn:kdc:896"


        @register_command(("kdc", 'ServerSessionKeyMissing'))
        class ServerSessionKeyMissing(GNFastCommand):
            """
            # KDC Ошибка получения сессионных ключей
            Не удалось получить сессионные ключи сервера.
            """
            cls_command = "gn:kdc:897"


        @register_command(("kdc", 'ServerSessionKeySignatureFailed'))
        class ServerSessionKeySignatureFailed(GNFastCommand):
            """
            # KDC Ошибка подписи сессионных ключей
            Подпись при получении сессионных ключей сервера не прошла валидацию. 
            """
            cls_command = "gn:kdc:898"



globals().update({
    name: obj
    for name, obj in AllGNFastCommands.__dict__.items()
    if isinstance(obj, type) and issubclass(obj, GNFastCommand)
})







