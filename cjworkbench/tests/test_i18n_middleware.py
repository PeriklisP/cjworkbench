from django.test import RequestFactory, SimpleTestCase
from django.http import HttpResponse
from cjworkbench.middleware.i18n import SetCurrentLocaleMiddleware
from django.contrib.auth.models import AnonymousUser, User
from cjworkbench.i18n import default_locale
from django.utils.translation import get_language

non_default_locale = "el"
unsupported_locale = "jp"


def mock_response(request):
    response = HttpResponse()
    response.request = request
    return response


class MockUser:
    def __init__(self, locale_preference=None):
        self.is_authenticated = True
        if locale_preference:
            self.locale_id = locale_preference


class SetCurrentLocaleMiddlewareTest(SimpleTestCase):
    """
    Tests the SetCurrentLocaleMiddleware.
            
    A registered user with a locale preference will be served a locale with the following order of preference:
        1. Current GET request parameter, if the locale is supported
        2. User preference, if the locale is supported
        3. Accept-Language HTTP header, if the header is valid and contains a supported locale
        4. Default locale
    The selected locale will not modify the user's preferences
    In case any locale is already stored in session, it will be ignored
    
    A non-registered user will be served the locale with the following order of preference:
        1. Current GET request parameter, if the locale is supported
        2. Session, if the locale is supported
        3. Accept-Language HTTP header, if the header is valid and contains a supported locale
        4. Default locale
    """

    def setUp(self):
        self.factory = RequestFactory()

    def _mock_request(
        self,
        user=None,
        session_locale=None,
        accept_language_header=None,
        request_locale=None,
    ):
        request = self.factory.get(
            "/" if not request_locale else ("/?locale=" + request_locale)
        )
        request.session = {"locale_id": session_locale}
        request.user = user or AnonymousUser()
        if accept_language_header:
            request.META["HTTP_ACCEPT_LANGUAGE"] = accept_language_header
        return request

    def _process_request(self, **kwargs):
        return SetCurrentLocaleMiddleware(mock_response)(
            self._mock_request(**kwargs)
        ).request

    def test_anonymous_user_default(self):
        # anonymous #4
        request = self._process_request()
        self.assertEqual(request.locale_id, default_locale)

    def test_anonymous_user_header_only_supported(self):
        # anonymous #3, a simple case: only a supported locale is requested
        request = self._process_request(accept_language_header=non_default_locale)
        self.assertEqual(request.locale_id, non_default_locale)
        self.assertEqual(get_language(), non_default_locale)

    def test_anonymous_user_header_invalid(self):
        # anonymous #3, invalid header
        request = self._process_request(accept_language_header="invalid header content")
        self.assertEqual(request.locale_id, default_locale)
        self.assertEqual(get_language(), default_locale)

    def test_anonymous_user_header_nonsupported(self):
        # anonymous #3, only a non-supported locale is requested
        request = self._process_request(accept_language_header=unsupported_locale)
        self.assertEqual(request.locale_id, default_locale)
        self.assertEqual(get_language(), default_locale)

    def test_anonymous_user_header_multiple(self):
        # anonymous #3, multiple locales requested, one of them is supported
        request = self._process_request(
            accept_language_header="%s,%s;q=0.5"
            % (unsupported_locale, non_default_locale)
        )
        self.assertEqual(request.locale_id, non_default_locale)
        self.assertEqual(get_language(), non_default_locale)

    def test_anonymous_user_session_supported(self):
        # anonymous #2, supported locale
        request = self._process_request(
            accept_language_header=default_locale, session_locale=non_default_locale
        )
        self.assertEqual(request.locale_id, non_default_locale)
        self.assertEqual(get_language(), non_default_locale)

    def test_anonymous_user_session_unsupported(self):
        # anonymous #2, non-supported locale
        request = self._process_request(
            accept_language_header=non_default_locale, session_locale=unsupported_locale
        )
        self.assertEqual(request.locale_id, non_default_locale)
        self.assertEqual(get_language(), non_default_locale)

    def test_anonymous_user_request_supported(self):
        # anonymous #1, valid locale
        request = self._process_request(
            accept_language_header=default_locale,
            session_locale=default_locale,
            request_locale=non_default_locale,
        )
        self.assertEqual(request.locale_id, non_default_locale)
        self.assertEqual(get_language(), non_default_locale)

    def test_anonymous_user_request_unsupported(self):
        # anonymous #1, invalid locale
        request = self._process_request(request_locale=unsupported_locale)
        self.assertEqual(request.locale_id, default_locale)
        self.assertEqual(get_language(), default_locale)

    def test_registered_user_default(self):
        # registered #4
        request = self._process_request(
            user=MockUser(locale_preference=unsupported_locale)
        )
        self.assertEqual(request.locale_id, default_locale)
        self.assertEqual(get_language(), default_locale)
        self.assertEqual(request.user.locale_id, unsupported_locale)

    def test_registered_user_no_session(self):
        # registered, session is ignored
        request = self._process_request(
            user=MockUser(locale_preference=unsupported_locale),
            session_locale=non_default_locale,
        )
        self.assertEqual(request.locale_id, default_locale)
        self.assertEqual(get_language(), default_locale)
        self.assertEqual(request.user.locale_id, unsupported_locale)

    def test_registered_user_header_supported(self):
        # registered #3, supported locale
        request = self._process_request(
            user=MockUser(locale_preference=unsupported_locale),
            accept_language_header=non_default_locale,
        )
        self.assertEqual(request.locale_id, non_default_locale)
        self.assertEqual(get_language(), non_default_locale)
        self.assertEqual(request.user.locale_id, unsupported_locale)

    def test_registered_user_header_nonsupported(self):
        # registered #3, non-supported locale
        request = self._process_request(
            user=MockUser(locale_preference=unsupported_locale),
            accept_language_header=unsupported_locale,
        )
        self.assertEqual(request.locale_id, default_locale)
        self.assertEqual(get_language(), default_locale)
        self.assertEqual(request.user.locale_id, unsupported_locale)

    def test_registered_user_preferences(self):
        # registered #2
        request = self._process_request(
            user=MockUser(locale_preference=non_default_locale),
            accept_language_header=default_locale,
        )
        self.assertEqual(request.locale_id, non_default_locale)
        self.assertEqual(get_language(), non_default_locale)
        self.assertEqual(request.user.locale_id, non_default_locale)

    def test_registered_user_request_supported(self):
        # registered #1, supported locale
        request = self._process_request(
            user=MockUser(locale_preference=non_default_locale),
            request_locale=default_locale,
        )
        self.assertEqual(request.locale_id, default_locale)
        self.assertEqual(get_language(), default_locale)
        self.assertEqual(request.user.locale_id, non_default_locale)

    def test_registered_user_request_unsupported(self):
        # registered #1, non-supported locale
        request = self._process_request(
            user=MockUser(locale_preference=non_default_locale),
            request_locale=unsupported_locale,
        )
        self.assertEqual(request.locale_id, non_default_locale)
        self.assertEqual(get_language(), non_default_locale)
        self.assertEqual(request.user.locale_id, non_default_locale)
