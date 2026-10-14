import logging

from rest_framework.response import Response
from rest_framework import status
from rest_framework.exceptions import APIException, ValidationError, NotAuthenticated, PermissionDenied, NotFound

logger = logging.getLogger(__name__)


class MetierException(APIException):
    """Exception pour violation d'une règle métier (HTTP 422 par défaut)"""
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    code = "REGLE_METIER"
    message = "Règle métier non respectée"

    def __init__(self, code="REGLE_METIER", message="Règle métier non respectée", details=None, status_code=None):
        self.code = code
        self.message = message
        self.details = details or {}
        if status_code is not None:
            self.status_code = status_code
        super().__init__(detail=self.message, code=self.code)


class ConflitException(APIException):
    """Exception pour état de conflit ou doublon (HTTP 409)"""
    status_code = status.HTTP_409_CONFLICT
    code = "CONFLIT"
    message = "Conflit avec l'état actuel"

    def __init__(self, code="CONFLIT", message="Conflit avec l'état actuel", details=None):
        self.code = code
        self.message = message
        self.details = details or {}
        super().__init__(detail=self.message, code=self.code)


class CompteNonValideException(APIException):
    """Exception pour compte en attente de validation ou inactif (HTTP 403)"""
    status_code = status.HTTP_403_FORBIDDEN
    code = "COMPTE_NON_VALIDE"
    message = "Compte non validé ou inactif"

    def __init__(self, message="Compte non validé ou inactif", details=None):
        self.code = "COMPTE_NON_VALIDE"
        self.message = message
        self.details = details or {}
        super().__init__(detail=self.message, code=self.code)


class TelephoneDejaUtiliseException(ConflitException):
    def __init__(self, details=None):
        super().__init__(code="TELEPHONE_DEJA_UTILISE", message="Ce numéro de téléphone est déjà associé à un compte", details=details)


class EmailDejaUtiliseException(ConflitException):
    def __init__(self, details=None):
        super().__init__(code="EMAIL_DEJA_UTILISE", message="Cette adresse e-mail est déjà associée à un compte", details=details)


def custom_exception_handler(exc, context):
    """
    Gestionnaire universel d'exceptions conforme au contrat commun GREENGAS :
    { "code": "CODE_ERREUR", "message": "Message explicatif", "details": { ... } }
    """
    from rest_framework.views import exception_handler as drf_exception_handler
    response = drf_exception_handler(exc, context)

    if response is not None:
        code = "ERREUR"
        message = str(exc)
        details = {}

        if isinstance(exc, ValidationError):
            code = "VALIDATION"
            message = "Les données transmises sont invalides ou incomplètes"
            details = response.data
        elif isinstance(exc, NotAuthenticated):
            code = "NON_AUTHENTIFIE"
            message = "Authentification requise pour accéder à cette ressource"
        elif isinstance(exc, PermissionDenied):
            code = "ACCES_REFUSE"
            message = "Vous ne disposez pas des autorisations nécessaires"
        elif isinstance(exc, NotFound):
            code = "INTROUVABLE"
            message = "La ressource demandée n'existe pas"
        elif hasattr(exc, 'get_codes'):
            error_codes = exc.get_codes()
            if isinstance(error_codes, str):
                code = error_codes.upper()
            elif isinstance(error_codes, dict):
                code = "VALIDATION"
                details = error_codes

        # Si l'exception définit explicitement code, message ou details
        if hasattr(exc, 'code'):
            code = getattr(exc, 'code')
        if hasattr(exc, 'message'):
            message = getattr(exc, 'message')
        elif hasattr(exc, 'detail') and isinstance(exc.detail, str):
            message = exc.detail
        if hasattr(exc, 'details') and getattr(exc, 'details'):
            details = getattr(exc, 'details')

        response.data = {
            "code": code,
            "message": message,
            "details": details if details else (response.data if isinstance(response.data, dict) and 'detail' not in response.data else {})
        }
    else:
        # Erreur 500 inattendue
        request = context.get('request')
        logger.error(
            "Unhandled exception in REST API",
            exc_info=(type(exc), exc, exc.__traceback__),
            extra={'request_path': getattr(request, 'path', '')},
        )
        response = Response(
            {
                "code": "ERREUR_SERVEUR",
                "message": "Une erreur interne est survenue sur le serveur",
                "details": {}
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

    return response
