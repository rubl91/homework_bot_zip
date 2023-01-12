class StatusCodeError(Exception):
    """Ошибка кода ответа."""

    pass


class JSONError(Exception):
    """Ошибка при преобразовании JSON к типам Python."""

    pass


class EmptyDictInResponseError(Exception):
    """Пустой словарь в ответе."""

    pass
