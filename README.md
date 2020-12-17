[![Build status](https://travis-ci.org/City-of-Helsinki/django-helusers.svg?branch=master)](https://travis-ci.org/City-of-Helsinki/django-helusers)
[![codecov](https://codecov.io/gh/City-of-Helsinki/django-helusers/branch/master/graph/badge.svg)](https://codecov.org/gh/City-of-Helsinki/django-helusers)
[![Requirements](https://requires.io/github/City-of-Helsinki/django-helusers/requirements.svg?branch=master)](https://requires.io/github/City-of-Helsinki/django-helusers/requirements/?branch=master)

# Django app for City of Helsinki user infrastructure

Django-helusers is your friendly app for bolting authentication into Django projects for City of Helsinki. Authentication schemes are based on [OAuth2](https://oauth.net/2/) and [OpenID Connect (OIDC)](https://openid.net/connect/).

A baseline `User` model is provided that can be used with the various authentication use cases that are supported. The model supports mapping from AD groups to Django groups based on the authentication data.

Additionally there are **optional** functionalities that can be used as needed.

Functionalities for server needing (API) access token verification:

* For servers using Django REST Framework

Functionalities for server needing to authenticate against OIDC or OAuth2 server:

* support Django session login against OIDC or OAuth2 server, including Helsinki Tunnistus service and Azure AD
* augmented login template for Django admin, adding OIDC/OAuth2 login button

## Adding django-helusers your Django project

Add:

* `django-helusers`
* `social-auth-app-django`

to your dependency management list. Django-helusers depends on
`social-auth-app-django` for implementation of the OIDC dance.

### Adding user model

helusers provides a baseline user model adding fields for Helsinki
specific information. As per Django [best practice](https://docs.djangoproject.com/en/3.0/topics/auth/customizing/#using-a-custom-user-model-when-starting-a-project)
you should subclass this model to make future customization easier:

```python

# users/models.py

from helusers.models import AbstractUser


class User(AbstractUser):
    pass
```

and reference it in settings.py:

```python
# myproject/settings.py

AUTH_USER_MODEL = 'users.User'
```

### Adding django-helusers Django apps

Django-helusers provides two Django apps: `HelusersConfig` provides the
models and templates needed for helusers to work and `HelusersAdminConfig`
reconfigures Django admin to work with helusers. The latter includes adding
a Tunnistamo login button to the admin login screen.

Additionally `social_django` app is needed for the underlying python-social-auth.

Before adding the apps, you will need to remove `django.contrib.admin`, as
`HelusersAdminConfig` is implementation of same functionality. You will get
`django.core.exceptions.ImproperlyConfigured: Application labels aren't unique, duplicates:
admin`-error, if you forget this step.

Then proceed by adding these apps to your `INSTALLED_APPS` in settings.py:

```python
INSTALLED_APPS = (
    'helusers.apps.HelusersConfig',
    'helusers.apps.HelusersAdminConfig',
    ...
    'social_django',
    ...
)
```

Us usual with `INSTALLED_APPS`, ordering matters. `HelusersConfig` must come
before `HelusersAdminConfig` and anything else providing admin templates.
Unless, of course, you wish to override the admin templates provided here.

One possible gotcha is, if you've added custom views to admin without
forwarding context from `each_context` to the your template.  Helusers
templates expect variables from `each_context` and will break if they are
missing.

### Adding Tunnistamo authentication

django-helusers ships with backend for authenticating against Tunnistamo
using OIDC. There is also a deprecated legacy OAuth2 backend using
allauth framework.

Typically you would want to support authenticating using both OIDC and local
database tables. Local users are useful for initial django admin login, before
you've delegated permissions to users coming through OIDC.

Add backend configuration to your `settings.py`:

```python
AUTHENTICATION_BACKENDS = [
    'helusers.tunnistamo_oidc.TunnistamoOIDCAuth',
    'django.contrib.auth.backends.ModelBackend',
]
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/'
```

`LOGIN_REDIRECT_URL` is the default landing URL after succesful login, if your
form did not specify anything else.

`LOGOUT_REDIRECT_URL` is the same for logout. django-helusers requires this
to be set.

You will also need to add URLs for `social_django` & `helusers` to your URL
dispatcher configuration (`urls.py`):

```python
urlpatterns = [
    ...
    path('pysocial/', include('social_django.urls', namespace='social')),
    path('helauth/', include('helusers.urls')),
    ...
]
```

You can change the paths if they conflict with your application.

Finally, you will need to configure your SESSION_SERIALIZER. helusers stores
the access token expiration time as a datetime which is not serializable
to JSON, so Django needs to be configured to use the built-in
PickleSerializer:

```python
SESSION_SERIALIZER = 'django.contrib.sessions.serializers.PickleSerializer'
```

## Configuration

### Django session login

Django session login is the usual login to Django that sets up a session
and is typically implemented using a browser cookie. This is usually done
using form with username & password fields. Django-helusers adds another
path that delegates the login to an OIDC provider. User logs in at the
provider and, upon successful return, a Django session is created for them.
For us, the main use case has been allowing logins to Django admin.

To support session login Django-helusers needs three settings that must
be configured both at Helsinki OIDC provider and your project instance.
The settings are:
* client ID
* client secret
* Tunnistamo OIDC endpoint
`Client` is OAuth2 / OIDC name for anything wanting to authenticate
users. Thus your application would be a `client`

Additionally you will need to provide your "callback URL" to the folks
configuring Tunnistamo. This is implemented by `python-social-auth` and
will, by default, be `https://app.domain/auth/complete/tunnistamo/`. During
development on your own laptop your `app.domain` would be `localhost`.

After you've received your client ID, client secret and Tunnistamo OIDC
endpoint you would configure them as follows:
```python
SOCIAL_AUTH_TUNNISTAMO_KEY = 'https://i/am/clientid/in/url/style'
SOCIAL_AUTH_TUNNISTAMO_SECRET = 'iamyoursecret'
SOCIAL_AUTH_TUNNISTAMO_OIDC_ENDPOINT = 'https://tunnistamo.example.com/'
```

Note that `client ID` becomes `KEY` and `client secret` becomes `SECRET`.

### Configuration of the DRF API authentication (using JWT tokens)

DRF API authentication is somewhat orthogonal to the session authentication.
It is a stateless authentication method, where every request is
authenticated by checking the signature of the included JWT token. It still
creates a persistent Django user, which is updated with the information
from the token with every request.

- Include `drf-oidc-auth` in your project's dependencies.
- Configure REST framework to use the `ApiTokenAuthentication` class in `settings.py`:

```python
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'helusers.oidc.ApiTokenAuthentication',
    ),
}
```

- Set your deployment-specific variables in `local_settings.py`, e.g.:

```python
OIDC_API_TOKEN_AUTH = {
    # Audience that must be present in the token for the request to be
    # accepted. Value must be agreed between your SSO service and your
    # application instance. Essentially this allows your application to
    # know that the token in meant to be used with it.
    'AUDIENCE': 'https://api.hel.fi/auth/projects',
    # Who we trust to sign the tokens. The library will request the
    # public signature keys from standard locations below this URL
    'ISSUER': 'https://api.hel.fi/sso'
    # The following can be used if you need certain OAuth2 scopes
    # for any functionality of the API. The request will be denied
    # if scopes starting with API_SCOPE_PREFIX are not present
    # in the token claims. Usually this is not needed, as checking
    # the audience is enough.
     REQUIRE_API_SCOPE_FOR_AUTHENTICATION': True,
    'API_SCOPE_PREFIX': 'projects',
}
```

### Adding tunnistamo URL to template context

If you need to access the Tunnistamo API from your JS code, you can include
the Tunnistamo base URL in your template context using helusers's context processor:

```python
TEMPLATES = [
    {
        'OPTIONS': {
            'context_processors': [
                'helusers.context_processors.settings'
            ]
        }
    }
]
```

### Carrying language preference from your application to Tunnistamo

Tunnistamo (per the OIDC specs) allows clients to specify the language used for
the login process. This allows you to carry your applications language setting
to the login screens presented by Tunnistamo.

Configure `python-social-auth` to pass the necessary argument through its
login view:
```python
SOCIAL_AUTH_TUNNISTAMO_AUTH_EXTRA_ARGUMENTS = {'ui_locales': 'fi'}
```
`fi` there is the language code that will be used when no language is requested, so change it if you you prefer some
other default language. If you don't want to set a default language at all, use an empty string `""` as the language
code.

When this setting is in place, languages can be requested using query param `ui_locales=<language code>` when starting
the login process, for example in your template
```
<a href="{% url 'helusers:auth_login' %}?next=/foobar/&ui_locales=en">Login in English</a>
```

### Disabling password logins

If you're not allowing users to log in with passwords, you may disable the
username/password form from Django admin login page by setting `HELUSERS_PASSWORD_LOGIN_DISABLED`
to `True`.

# Development

Virtual Python environment can be used. For example:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install package requirements:

```bash
pip install -e .
```

Install development requirements:

```bash
pip install -r requirements-dev.txt
```

## Running tests

```bash
pytest
```
