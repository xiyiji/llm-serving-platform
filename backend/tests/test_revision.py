import asyncio

import pytest
from fastapi.testclient import TestClient
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app.main import create_app
from app.core.platform import Platform
from app.schemas import CompletionRequest
from tests.conftest import make_settings


def test_stream_http_cache(client):
    payload = {'prompt': 'http repeat', 'stream': True}
    first = client.post('/v1/chat/completions', json=payload)
    second = client.post('/v1/chat/completions', json=payload)
    assert first.status_code == second.status_code == 200
    assert first.text == second.text and '[DONE]' in first.text
    assert client.get('/v1/kv-cache/stats').json()['cache_hits'] == 1


@pytest.mark.asyncio
async def test_batch_contexts_are_independent():
    import contextvars
    from app.core.batching import BatchScheduler
    identity = contextvars.ContextVar('identity')
    scheduler = BatchScheduler(window_ms=10, max_size=2)
    async def submit(value):
        identity.set(value)
        async def work():
            return identity.get()
        return await scheduler.submit(work)
    assert await asyncio.gather(submit('one'), submit('two')) == ['one', 'two']
    assert scheduler.stats()['avg_batch_size'] == 2


@pytest.mark.asyncio
async def test_upstream_trace_header():
    import json
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from app.config import BackendConfig
    from app.core.adapters import OpenAICompatAdapter
    seen = []
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers['Content-Length']))
            seen.append(self.headers.get('traceparent'))
            body = json.dumps({'choices': [{'message': {'content': 'ok'}}]}).encode()
            self.send_response(200)
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    provider = TracerProvider()
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    adapter = OpenAICompatAdapter(BackendConfig(name='test', base_url=f'http://127.0.0.1:{server.server_port}'))
    adapter.tracer_provider = provider
    try:
        with provider.get_tracer('test').start_as_current_span('parent') as parent:
            result = await adapter.generate(CompletionRequest(prompt='test'), 'm')
            assert result.text == 'ok'
            assert seen[0].split('-')[1] == f'{parent.get_span_context().trace_id:032x}'
        assert any(s.parent and s.parent.span_id == parent.get_span_context().span_id for s in exporter.get_finished_spans())
    finally:
        server.shutdown()
        server.server_close()
        worker.join()
        provider.shutdown()


def test_promote_body_query_validation(client):
    client.post('/v1/registry', json={'model_id': 'm', 'version': '1'})
    path = '/v1/registry/m/1/promote'
    assert client.post(path, json={'stage': 'production'}).json()['stage'] == 'production'
    assert client.post(path + '?stage=staging').json()['stage'] == 'staging'
    assert client.post(path).status_code == 422
    assert client.post(path, json={'stage': 'invalid'}).status_code == 422
    assert client.post(path + '?stage=dev', json={'stage': 'production'}).status_code == 422
    assert client.post('/v1/registry/m/unknown/promote', json={'stage': 'dev'}).status_code == 404


@pytest.mark.asyncio
async def test_stream_cache_and_batching():
    p = Platform(make_settings())
    req = CompletionRequest(prompt='repeat', stream=True)
    first = [chunk async for chunk in p.stream(req)]
    assert first
    assert p.batcher.total_requests == 1
    assert [chunk async for chunk in p.stream(req)] == first
    assert p.kv_cache.hits == 1
    assert p.batcher.total_requests == 1


@pytest.mark.asyncio
async def test_failed_and_closed_streams_not_cached():
    p = Platform(make_settings())
    async def failing(*args):
        yield 'partial'
        raise RuntimeError('upstream failed')
    p.adapters[0].stream = failing
    req = CompletionRequest(prompt='partial')
    with pytest.raises(RuntimeError):
        _ = [c async for c in p.stream(req)]
    assert p.kv_cache.stats()['size'] == 0
    stream = p.stream(req)
    assert await anext(stream) == 'partial'
    await stream.aclose()
    assert p.kv_cache.stats()['size'] == 0


@pytest.mark.asyncio
async def test_truncated_upstream_not_cached():
    import httpx
    from app.config import BackendConfig
    from app.core.adapters import OpenAICompatAdapter
    from app.errors import UpstreamUnavailableError
    p = Platform(make_settings())
    adapter = OpenAICompatAdapter(BackendConfig(name='primary', base_url='http://test'))
    adapter._client = lambda: httpx.AsyncClient(
        base_url='http://test', transport=httpx.MockTransport(lambda request: httpx.Response(
            200, text='data: {"choices":[{"delta":{"content":"partial"}}]}\n\n'
        ))
    )
    p.adapters[0].stream = adapter.stream
    with pytest.raises(UpstreamUnavailableError, match='before'):
        _ = [c async for c in p.stream(CompletionRequest(prompt='truncated'))]
    assert p.kv_cache.stats()['size'] == 0


@pytest.mark.asyncio
async def test_upstream_final_usage_event_has_empty_choices():
    import httpx
    from app.config import BackendConfig
    from app.core.adapters import OpenAICompatAdapter
    adapter = OpenAICompatAdapter(BackendConfig(name='primary', base_url='http://test'))
    body = 'data: {"choices":[{"delta":{"content":"ok"}}]}\n\n'
    body += 'data: {"choices":[],"usage":{"completion_tokens":1}}\n\n'
    body += 'data: [DONE]\n\n'
    adapter._client = lambda: httpx.AsyncClient(base_url='http://test',
        transport=httpx.MockTransport(lambda request: httpx.Response(200, text=body)))
    assert [c async for c in adapter.stream(CompletionRequest(prompt='hello'), 'qwen')] == ['ok']


@pytest.mark.asyncio
async def test_cancel_during_first_delta_closes_upstream():
    p = Platform(make_settings())
    entered = asyncio.Event()
    closed = asyncio.Event()
    async def slow(*args):
        try:
            entered.set()
            await asyncio.Event().wait()
            yield 'never'
        finally:
            closed.set()
    p.adapters[0].stream = slow
    stream = p.stream(CompletionRequest(prompt='cancel'))
    task = asyncio.create_task(anext(stream))
    await asyncio.wait_for(entered.wait(), 2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert closed.is_set()
    assert p.kv_cache.stats()['size'] == 0


def test_incoming_trace_context_and_metrics():
    provider = TracerProvider()
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace_id = '1234567890abcdef1234567890abcdef'
    with TestClient(create_app(make_settings(), tracer_provider=provider)) as client:
        assert client.get('/health', headers={'traceparent': f'00-{trace_id}-1234567890abcdef-01'}).status_code == 200
        assert client.get('/metrics').status_code == 200
    spans = exporter.get_finished_spans()
    assert any(s.context.trace_id == int(trace_id, 16) and s.parent.span_id == int('1234567890abcdef', 16) for s in spans if s.parent)
    provider.shutdown()


@pytest.mark.asyncio
async def test_stream_batch_does_not_wait_for_slowest_first_delta():
    from app.core.batching import BatchScheduler
    scheduler = BatchScheduler(window_ms=5, max_size=2)
    release = asyncio.Event()
    async def slow():
        await release.wait()
        yield 'slow'
    async def fast():
        yield 'fast'
    slow_stream = scheduler.submit_stream(slow())
    fast_stream = scheduler.submit_stream(fast())
    slow_task = asyncio.create_task(anext(slow_stream))
    assert await asyncio.wait_for(anext(fast_stream), 1) == 'fast'
    assert not slow_task.done()
    release.set()
    assert await slow_task == 'slow'
    await slow_stream.aclose()
    await fast_stream.aclose()
    assert scheduler.stats()['avg_batch_size'] == 2


def test_otlp_export_to_receiver(monkeypatch):
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest
    from app.core.tracing import make_tracer_provider
    received = []
    class Receiver(BaseHTTPRequestHandler):
        def do_POST(self):
            message = ExportTraceServiceRequest()
            message.ParseFromString(self.rfile.read(int(self.headers['Content-Length'])))
            received.append((self.path, message))
            self.send_response(200)
            self.end_headers()
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Receiver)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    monkeypatch.setenv('OTEL_EXPORTER_OTLP_TRACES_ENDPOINT', f'http://127.0.0.1:{server.server_port}/v1/traces')
    provider = make_tracer_provider()
    try:
        with provider.get_tracer('test').start_as_current_span('export-check'):
            pass
        assert provider.force_flush()
        assert received[0][0] == '/v1/traces'
        assert received[0][1].resource_spans[0].scope_spans[0].spans[0].name == 'export-check'
    finally:
        provider.shutdown()
        server.shutdown()
        server.server_close()
        worker.join()
