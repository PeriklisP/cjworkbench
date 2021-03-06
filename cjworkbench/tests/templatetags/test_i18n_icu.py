import logging
import re

from babel.messages.catalog import Catalog
from django.template import Context, Template
from django.test import SimpleTestCase

from cjworkbench.templatetags.i18n_icu import trans_html
from cjworkbench.tests.i18n.util import mock_app_catalogs


def mock_context(locale_id="en"):
    return {"i18n": {"locale_id": locale_id}}


class TransTemplateTagTests(SimpleTestCase):
    # Tests that `noop=True` returns `None`
    def test_trans_noop(self):
        catalog = Catalog()
        catalog.add("id", string="Hello {a} {b}!")
        with mock_app_catalogs({"en": catalog}):
            self.assertIsNone(
                trans_html(mock_context(), "id", noop=True, default="Hello {a} {b}!")
            )

    # Tests that the default argument is ignored
    def test_default_is_ignored(self):
        catalog = Catalog()
        catalog.add("id", string="Hello")
        with mock_app_catalogs({"en": catalog}):
            self.assertEqual(
                trans_html(mock_context(), "id", default="Nothing"), "Hello"
            )

    # Tests that `arg_XX` arguments replace variables in the message.
    # The order of `arg` arguments is not important.
    # Numeric arguments work correctly
    def test_trans_params(self):
        catalog = Catalog()
        catalog.add("id", string="Hello {a} {0} {b}")
        with mock_app_catalogs({"en": catalog}):
            self.assertEqual(
                trans_html(
                    mock_context(),
                    "id",
                    default="Hello {a} {0} {b}",
                    arg_b="2",
                    arg_a="you",
                    arg_0="!",
                ),
                "Hello you ! 2",
            )

    # Tests that tags without attributes are supported
    def test_trans_tag_without_attributes(self):
        catalog = Catalog()
        catalog.add("id", string="Hello <b0>{param_b}</b0>!")
        with mock_app_catalogs({"en": catalog}):
            self.assertEqual(
                trans_html(
                    mock_context(),
                    "id",
                    default="Hello <b0>{param_b}</b0>!",
                    arg_param_b="there",
                    tag_b0="",
                ),
                "Hello <b>there</b>!",
            )

    # Tests that when a message does not exist in the context locale, it is returned in the default locale
    def test_default_locale(self):
        catalog = Catalog()
        catalog.add("id", "Hello")
        with mock_app_catalogs({"en": catalog, "el": Catalog()}):
            self.assertEqual(
                trans_html(mock_context("el"), "id", default="Hello"), "Hello"
            )

    # Tests that when a message does not exist in the catalogs, `None` is returned
    def test_missing_message(self):
        with mock_app_catalogs({"en": Catalog()}):
            with self.assertRaises(KeyError):
                trans_html(mock_context(), "id", default="Hello")

    # Tests the combination of properties of placeholder tags and of message parameters.
    # 0) In settings where there are multiple tags, some of which have to be deleted, all of them are processed
    # 1) `tag_XX_YY` arguments are used to replace placeholders; existing attributes are removed
    # 2) Tags without attributes are supported
    # 3) Tags or placeholders that have no counterpart in the arguments are removed
    # 4) The order of `tag` arguments is not important
    # 5) Special characters, except for the ones of valid tags, are escaped, even in tag attributes and in args
    # 6) Nested tags are not tolerated
    # 7) `arg_XX` arguments are replaced correctly
    def test_trans_tag_placeholders(self):
        catalog = Catalog()
        catalog.add(
            "id",
            string='<em0>Hello</em0> <span0 class="nope">{first}</span0><span1></span1> {second} <a0>{a}<b></b></a0> < <a1>there<</a1>!<br /><script type="text/javascript" src="mybadscript.js"></script>',
        )
        with mock_app_catalogs({"en": catalog}):
            self.assertEqual(
                trans_html(
                    mock_context(),
                    "id",
                    default='<em0>Hello</em0> <span0 class="nope">{first}</span0><span1></span1> {second} <a0>{a}<b></b></a0> < <a1>there<</a1>!<br /><script type="text/javascript" src="mybadscript.js"></script>',
                    arg_a="you",
                    tag_a0_href="/you",
                    tag_a1_href="/there?a=b&c=d",
                    tag_a1_class="red big",
                    tag_span0_id="hi",
                    tag_em0="",
                    tag_div0_class="red big",
                    arg_first="hello",
                    arg_second="&",
                ),
                '<em>Hello</em> <span id="hi">hello</span> &amp; <a href="/you">you</a> &lt; <a class="red big" href="/there?a=b&amp;c=d">there&lt;</a>!',
            )

    def test_trans_html_with_missing_context_i18n(self):
        # context[i18n] needs to be managed by the caller. And sometimes, the
        # caller has a bug. (Seen 2019-08-2019-12-06 01:57:19.327 GMT.) We want
        # Django's exception-handling code to be able to call trans_html().
        #
        # Calling trans_html without a context[i18n] is always a bug. So let's
        # test that it's logged.
        catalog = Catalog()
        catalog.add("id", string="Show the message")
        with mock_app_catalogs({"en": catalog}):
            with self.assertLogs(level=logging.ERROR) as cm:
                result = trans_html(
                    {"invalid-context": "yup"}, "id", default="Show the message"
                )
            self.assertEqual(result, "Show the message")
            self.assertRegex(
                cm.output[0],
                re.escape(
                    "ERROR:cjworkbench.templatetags.i18n_icu:"
                    "Missing context['i18n']['locale_id'] translating message_id id"
                ),
            )
