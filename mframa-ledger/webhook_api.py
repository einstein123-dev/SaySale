"""Authenticated generic webhook intake; every extracted record goes to human review."""
import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from starlette.responses import JSONResponse

import ai_parser
import store

logger = logging.getLogger(__name__)


class InboundEvent(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    event_id: str = Field(min_length=1, max_length=200)
    source_channel: str = Field(min_length=1, max_length=50)
    text: str = Field(min_length=1, max_length=5000)


def process_one_event(api_key, model):
    event = store.claim_webhook_event()
    if not event:
        return False
    try:
        store.authorize_webhook_ai(event)
        shop = store.webhook_shop_context(event['shop_id'])
        if not shop:
            raise ValueError('Shop not found.')
        drafts = ai_parser.parse_multi_transaction(event['source_text'], api_key, model, currency=shop['currency'])
        if not drafts:
            drafts = [{'type': None, 'currency': shop['currency'], 'missing_fields': ['type'],
                       'clarification_question': 'Please review and enter the transaction details.', 'confidence': 0.0}]
        store.finish_webhook_event(event['id'], drafts)
    except Exception as exc:
        logger.exception('Webhook event processing failed: %s', event['id'])
        store.fail_webhook_event(event['id'], exc)
    return True


@asynccontextmanager
async def lifespan(_app):
    store.init_db()
    stopping = asyncio.Event()

    async def worker():
        while not stopping.is_set():
            key, model = os.getenv('GEMINI_API_KEY'), os.getenv('GEMINI_MODEL')
            processed = False
            if key and model:
                try:
                    processed = await asyncio.to_thread(process_one_event, key, model)
                except Exception:
                    logger.exception('Webhook worker iteration failed; retrying.')
            if not processed:
                try:
                    await asyncio.wait_for(stopping.wait(), timeout=1.0)
                except asyncio.TimeoutError:
                    pass

    task = asyncio.create_task(worker())
    try:
        yield
    finally:
        stopping.set()
        await task


app = FastAPI(title='SaySale inbound webhook', version='1.0', lifespan=lifespan)


@app.middleware('http')
async def limit_webhook_body(request, call_next):
    if request.url.path.startswith('/webhooks/'):
        declared_length = request.headers.get('content-length')
        if declared_length and declared_length.isdigit() and int(declared_length) > 16_384:
            return JSONResponse(status_code=413, content={'detail': 'Webhook request body is too large.'})
        body = bytearray()
        more_body = True
        while more_body:
            message = await request.receive()
            body.extend(message.get('body', b''))
            if len(body) > 16_384:
                return JSONResponse(status_code=413, content={'detail': 'Webhook request body is too large.'})
            more_body = message.get('more_body', False)
        replayed = False

        async def replay_body():
            nonlocal replayed
            if replayed:
                return {'type': 'http.request', 'body': b'', 'more_body': False}
            replayed = True
            return {'type': 'http.request', 'body': bytes(body), 'more_body': False}

        request._receive = replay_body
    return await call_next(request)


@app.get('/health')
def health():
    return {'status': 'ok'}


@app.post('/webhooks/{shop_id}/transactions', status_code=202)
def receive_transaction(shop_id: str, event: InboundEvent, x_saysale_webhook_token: str = Header(default='')):
    try:
        result = store.accept_webhook_event(shop_id, x_saysale_webhook_token, event.event_id,
                                           event.source_channel, event.text)
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail='Invalid webhook credential.') from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception('Unable to persist inbound webhook event')
        raise HTTPException(status_code=503, detail='Event could not be queued; retry with the same event_id.') from exc
    return result
