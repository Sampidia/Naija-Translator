class AppError(Exception):
    """Base application error."""


class ProviderConfigError(AppError):
    pass


class InferenceError(AppError):
    pass


class StorageError(AppError):
    pass
