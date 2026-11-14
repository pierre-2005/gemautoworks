"""GEM Autoworks web app: public site, booking, customer accounts and the admin panel."""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from . import config
from .booking import money, nice_time
from .db import SIZES, SIZE_LABEL, connection, get_settings, migrate
from .mail import worker
from .security import csrf_token

logging.basicConfig(level=logging.INFO, format='%(levelname)s %(name)s: %(message)s')
STATIC = config.ROOT / 'static'

templates = Jinja2Templates(directory=str(config.ROOT / 'templates'))


def picture(base: str | None) -> dict:
    """'/static/img/work/altima-after' -> {'src', 'srcset', 'w', 'h'} from the built WebP widths.
    Works for uploads too ('/uploads/g12'). Anything else is passed through unchanged."""
    if not base:
        return {'src': '', 'srcset': ''}
    if base.startswith('/static/'):
        folder, stem = STATIC / Path(base[len('/static/'):]).parent, Path(base).name
        prefix = '/static/' + str(Path(base[len('/static/'):]).parent).replace('\\', '/')
    elif base.startswith('/uploads/'):
        folder, stem = config.UPLOAD_DIR, Path(base).name
        prefix = '/uploads'
    else:
        return {'src': base, 'srcset': ''}
    if '.' in stem:
        return {'src': base, 'srcset': ''}
    files = []
    for f in folder.glob(f'{stem}-*.webp'):
        tail = f.stem[len(stem) + 1:]
        if tail.isdigit():
            files.append((int(tail), f'{prefix}/{f.name}'))
    files.sort()
    if not files:
        return {'src': base, 'srcset': ''}
    return {'src': files[-1][1], 'srcset': ', '.join(f'{u} {w}w' for w, u in files), 'w': files[-1][0]}


def tel(phone: str) -> str:
    digits = ''.join(ch for ch in phone if ch.isdigit())
    if len(digits) == 10:
        digits = '1' + digits
    return f'tel:+{digits}'


templates.env.globals.update(picture=picture, money=money, tel=tel, SIZES=SIZES, SIZE_LABEL=SIZE_LABEL,
                             nice_time=nice_time, current_year=lambda: date.today().year)


def render(request: Request, name: str, status: int = 200, **ctx) -> HTMLResponse:
    with connection() as c:
        site = get_settings(c)
    from .routes.account import current_customer
    ctx.setdefault('customer', current_customer(request))
    return templates.TemplateResponse(request, name, {'site': site, 'csrf': csrf_token(request), 'path': request.url.path, **ctx},
                                      status_code=status)


@asynccontextmanager
async def lifespan(app: FastAPI):
    migrate()
    task = asyncio.create_task(worker())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


app = FastAPI(title='GEM Autoworks', docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=config.SECRET_KEY, session_cookie='gem_session', same_site='lax',
                   https_only=config.COOKIE_SECURE, max_age=30 * 24 * 3600)
app.mount('/static', StaticFiles(directory=STATIC), name='static')
app.mount('/uploads', StaticFiles(directory=config.UPLOAD_DIR), name='uploads')


@app.middleware('http')
async def headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault('X-Content-Type-Options', 'nosniff')
    response.headers.setdefault('X-Frame-Options', 'DENY')
    response.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
    response.headers.setdefault('Permissions-Policy', 'camera=(), microphone=(), geolocation=()')
    response.headers.setdefault('Content-Security-Policy',
                                "default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; "
                                "script-src 'self' 'unsafe-inline'; font-src 'self'; connect-src 'self'; frame-ancestors 'none'; "
                                "base-uri 'self'; form-action 'self'")
    path = request.url.path
    if path.startswith('/static/'):
        response.headers.setdefault('Cache-Control', 'public, max-age=604800')
    elif path.startswith(('/admin', '/account', '/booking')):
        response.headers['Cache-Control'] = 'no-store'
    return response


@app.exception_handler(HTTPException)
async def http_error(request: Request, exc: HTTPException):
    if request.url.path.startswith('/api/'):
        from fastapi.responses import JSONResponse
        return JSONResponse({'error': exc.detail}, status_code=exc.status_code)
    if exc.status_code in (301, 302, 303, 307) and exc.headers:
        return Response(status_code=exc.status_code, headers=exc.headers)
    titles = {404: 'We could not find that page', 400: 'Something in that form needs another look',
              403: 'You do not have access to that page', 429: 'Too many tries for now'}
    return render(request, 'public/error.html', status=exc.status_code, code=exc.status_code,
                  title=titles.get(exc.status_code, 'Something went wrong'), detail=exc.detail)


@app.get('/health')
def health():
    with connection() as c:
        c.execute('SELECT 1').fetchone()
    return {'ok': True}


@app.get('/robots.txt', response_class=PlainTextResponse)
def robots():
    lines = ['User-agent: *', 'Disallow: /admin', 'Disallow: /account', 'Disallow: /booking/']
    if config.PUBLIC_BASE_URL:
        lines.append(f'Sitemap: {config.PUBLIC_BASE_URL}/sitemap.xml')
    return '\n'.join(lines) + '\n'


@app.get('/sitemap.xml')
def sitemap():
    base = config.PUBLIC_BASE_URL or ''
    urls = ''.join(f'<url><loc>{base}{p}</loc></url>' for p in ('/', '/services', '/work', '/about', '/book', '/contact', '/reviews'))
    return Response(f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>',
                    media_type='application/xml')


from .routes import account, admin, public  # noqa: E402

app.include_router(public.router)
app.include_router(account.router)
app.include_router(admin.router)
