import unittest

import helpers  # noqa: F401  (puts the scripts folder on sys.path)

from secretscan import looks_secret


class UrlQuerySecretTest(unittest.TestCase):
    def test_credential_query_keys_with_a_value_match(self):
        for url in (
            "https://bucket.s3.amazonaws.com/a.png?X-Amz-Algorithm=AWS4&X-Amz-Signature=abc123",
            "https://storage.googleapis.com/b/o?X-Goog-Signature=deadbeef",
            "https://api.example.com/cb?access_token=ya29.abc",
            "https://api.example.com/v1?api_key=k1",
            "https://api.example.com/v1?APIKEY=k1",
            "https://api.example.com/v1?aws_access_key=k1",
            "https://db.example.com/login?user=a&db_password=hunter2",
            "https://example.com/hook?refresh-token=r1",
        ):
            with self.subTest(url=url):
                self.assertTrue(looks_secret(url))

    def test_keys_without_a_value_and_lookalike_keys_do_not_match(self):
        for text in (
            "https://example.com/cb?access_token=&state=1",
            "https://example.com/cb?access_token#frag",
            "https://bucket.s3.amazonaws.com/a.png?X-Amz-SignedHeaders=host",
            "https://x.slack.com/archives/C1/p1?thread_ts=1.2&cid=C1",
            "Renamed the api_key=value setting in the docs",
            "Documented the X-Amz-Signature header",
        ):
            with self.subTest(text=text):
                self.assertFalse(looks_secret(text))


if __name__ == "__main__":
    unittest.main()
