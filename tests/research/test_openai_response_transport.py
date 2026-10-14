"""Transport uses fake HTTP; NEVER asserts any live model request worked."""
import json

import httpx
import pytest

from research.llm.openai_response_transport import OpenAIResponsesResearcher, RemoteModelError


def test_no_api_key_rejected_before_ever_calling_network(monkeypatch):
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    with pytest.raises(RemoteModelError, match='OPENAI_API_KEY'):
        OpenAIResponsesResearcher(model='gpt-5.5')


def test_mocked_response_extracts_one_json_object_without_server_tools():
    seen = []
    def handler(request):
        seen.append(request)
        payload = json.loads(request.content)
        assert payload['store'] is False
        assert payload['text']['format']['type'] == 'json_object'
        assert payload['max_output_tokens'] <= 6000
        assert 'tools' not in payload
        assert 'required_output_json_schema' in json.loads(payload['input'])
        assert request.url.host == 'api.openai.com'
        return httpx.Response(200, json={
            'status': 'completed', 'output': [{
                'type': 'message', 'content': [{
                    'type': 'output_text', 'text': '{"plan_id":"example"}',
                }],
            }],
        })
    provider = OpenAIResponsesResearcher(
        model='gpt-5.5', api_key='mock-test-only', transport=httpx.MockTransport(handler),
    )
    assert provider.propose({'output_contract': 'AlgorithmPlan'}) == {
        'plan_id': 'example'
    }
    assert len(seen) == 1


def test_invalid_remote_refusal_or_status_never_claims_result():
    for status, response in (
        (429, {}),
        (200, {'status': 'incomplete', 'output': []}),
        (200, {'status': 'completed', 'output': []}),
        (200, {'status': 'completed', 'output': [{
            'type': 'message', 'content': [{
                'type': 'output_text', 'text': '{not-json}',
            }],
        }]}),
    ):
        def fake_response(
            _: httpx.Request, status: int = status, response: dict = response,
        ) -> httpx.Response:
            return httpx.Response(status, json=response)
        provider = OpenAIResponsesResearcher(
            model='gpt-5.5', api_key='fake',
            transport=httpx.MockTransport(fake_response),
        )
        with pytest.raises(RemoteModelError):
            provider.propose({'schema': 'research-diagnostic-context-v1'})
