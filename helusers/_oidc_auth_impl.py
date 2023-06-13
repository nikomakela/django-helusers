import logging
import requests
from django.utils.encoding import smart_str
from django.utils.functional import cached_property
from django.utils.translation import gettext as _
from oidc_auth.authentication import JSONWebTokenAuthentication
from oidc_auth.util import cache
from rest_framework.authentication import get_authorization_header
from rest_framework.exceptions import AuthenticationFailed

from .authz import UserAuthorization
from .settings import api_token_auth_settings
from .user_utils import get_or_create_user

logger = logging.getLogger(__name__)


class ApiTokenAuthentication(JSONWebTokenAuthentication):
    def __init__(self, settings=None, **kwargs):
        self.settings = settings or api_token_auth_settings
        super(ApiTokenAuthentication, self).__init__(**kwargs)

    @property
    # This method is used if the drf-oidc-auth dependecy version is 1.0.0 or greater
    def claims_options(self):
        _claims_options = super().claims_options

        audiences = self.settings.AUDIENCE
        if isinstance(audiences, str):
            audiences = [self.settings.AUDIENCE]

        _claims_options["aud"] = {
            "essential": True,
            "values": audiences
        }
        return _claims_options

    @cached_property
    def auth_scheme(self):
        return self.settings.AUTH_SCHEME or 'Bearer'

    @property
    def oidc_config(self):
        return self.get_oidc_config()

    @cache(ttl=api_token_auth_settings.OIDC_CONFIG_EXPIRATION_TIME)
    def get_oidc_config(self):
        issuer = self.settings.ISSUER
        if not isinstance(issuer, str):
            issuer = issuer[0]
        url = issuer + '/.well-known/openid-configuration'
        return requests.get(url).json()

    def authenticate(self, request):
        jwt_value = self.get_jwt_value(request)
        if jwt_value is None:
            return None

        try:
            payload = self.decode_jwt(jwt_value)
        except AuthenticationFailed as e:
            logger.debug("Invalid token signature")
            raise

        # Some OPs may provide the "amr" incorrectly as a string, while the
        # specification dictates it must be an array of strings. Fix that here.
        if isinstance(payload.get("amr"), str):
            payload["amr"] = [payload["amr"]]
            logger.debug(
                'Modified "amr" claim to be an array of strings instead of a string.'
            )

        logger.debug("Token payload decoded as: {}".format(payload))

        self.validate_claims(payload)

        user_resolver = self.settings.USER_RESOLVER  # Default: resolve_user
        try:
            user = user_resolver(request, payload)
        except ValueError as e:
            raise AuthenticationFailed(str(e)) from e
        auth = UserAuthorization(user, payload, self.settings)

        if self.settings.REQUIRE_API_SCOPE_FOR_AUTHENTICATION:
            api_scope = self.settings.API_SCOPE_PREFIX
            if not auth.has_api_scope_with_prefix(api_scope):
                raise AuthenticationFailed(
                    _("Not authorized for API scope \"{api_scope}\"")
                    .format(api_scope=api_scope))

        return (user, auth)

    def get_jwt_value(self, request):
        auth = get_authorization_header(request).split()

        logger.debug("Authorization header: {}".format(auth))

        if not auth or smart_str(auth[0]).lower() != self.auth_scheme.lower():
            return None

        if len(auth) == 1:
            raise AuthenticationFailed(
                _("Invalid Authorization header. No credentials provided"))
        elif len(auth) > 2:
            raise AuthenticationFailed(
                _("Invalid Authorization header. "
                  "Credentials string should not contain spaces."))

        return auth[1]

    def authenticate_header(self, request):
        return '{auth_scheme} realm="{realm}"'.format(
            auth_scheme=self.auth_scheme,
            realm=self.www_authenticate_realm)

    # This method is only used if the drf-oidc-auth dependecy version is less than 1.0.0
    def get_audiences(self, api_token):
        return {self.settings.AUDIENCE}


def resolve_user(request, payload):
    return get_or_create_user(payload, oidc=True)
