"""T2: Proxy IP handling — uvicorn resolves request.client.host from trusted headers.
Source IP is read from request.client.host only; raw X-Forwarded-For is never parsed
directly so a client cannot poison webhook_events.source_ip via header injection.
The integration test test_source_ip_ignores_spoofed_x_forwarded_for in
tests/integration/test_webhook_endpoint.py covers the end-to-end behaviour.
"""
