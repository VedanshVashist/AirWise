import os
import unittest
from unittest.mock import patch

import campaign_service as service


class CampaignTests(unittest.TestCase):
    def setUp(self):
        self.config = patch.dict(os.environ, {
            "OPENAI_API_KEY": "test-key",
            "UPSTASH_REDIS_REST_URL": "https://test.upstash.io",
            "UPSTASH_REDIS_REST_TOKEN": "test-token",
        }, clear=True)
        self.config.start()
        self.addCleanup(self.config.stop)
        self.data = {"audience": "Neighbours"}

    @patch.object(service, "post_json")
    def test_template_without_credentials(self, post):
        del os.environ["OPENAI_API_KEY"]
        self.assertEqual(service.campaign_headline(self.data)["author"], "Airwise template")
        post.assert_not_called()

    @patch.object(service, "post_json")
    def test_quota_exhaustion_and_outage(self, post):
        post.side_effect = [[{"result": 26}, {"result": 1}], OSError()]
        for _ in range(2):
            self.assertEqual(service.campaign_headline(self.data)["author"], "Airwise template")
        self.assertTrue(all("upstash.io" in call.args[0] for call in post.call_args_list))

    @patch.object(service, "post_json")
    def test_ai_receives_only_fixed_topic_and_returns_only_copy(self, post):
        post.side_effect = [[{"result": 1}, {"result": 1}],
                            {"choices": [{"message": {"content": "Give our trees room to grow"}}]}]
        result = service.campaign_headline({**self.data, "prompt": "private detail"})
        self.assertEqual(result, {"headline": "Give our trees room to grow", "author": "OpenAI headline"})
        self.assertNotIn("private detail", str(post.call_args_list))

    @patch.object(service, "post_json")
    def test_invalid_audience(self, post):
        with self.assertRaises(KeyError):
            service.campaign_headline({"audience": "arbitrary prompt"})
        post.assert_not_called()
