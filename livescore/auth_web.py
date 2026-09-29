"""HTTP-Zugriffsschutz; fachliche APIs bleiben von Rollen unabhängig."""
import hmac
import secrets
from urllib.parse import urlsplit

from fastapi import Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse

from .auth import COOKIE, LOGIN_COOKIE, Login, PasswordChange


def error(code, status):
    return JSONResponse({'detail': code}, status_code=status)


def same_origin(connection):
    origin = connection.headers.get('origin')
    if not origin:
        return False
    parsed = urlsplit(origin)
    return parsed.scheme in ('http', 'https') and parsed.netloc == connection.headers.get('host') and not parsed.path


def install_auth(app, root):
    @app.middleware('http')
    async def access(request, call_next):
        auth = app.state.auth
        path = request.url.path.rstrip('/') or '/'
        public = (path in ('/login', '/api/auth/session')
                  or (request.method == 'GET' and path == '/api/v1/live')
                  or (path.startswith('/static/') and not path.endswith('.html')))
        session = auth.session(request.cookies.get(COOKIE)) if auth.config.enabled else None
        request.state.session = session
        if not auth.config.enabled or public:
            return await call_next(request)
        if not session:
            if request.method == 'GET' and not path.startswith('/api/'):
                return RedirectResponse('/login', status_code=303)
            return error('auth_required', 401)
        if request.method not in ('GET', 'HEAD', 'OPTIONS'):
            if (not hmac.compare_digest(request.headers.get('x-csrf-token', '').encode(), session.csrf.encode())
                    or (request.headers.get('origin') and not same_origin(request))):
                return error('csrf_invalid', 403)
        if auth.restricted(session) and path not in ('/users', '/api/auth/users', '/api/auth/password', '/logout'):
            if request.method == 'GET' and not path.startswith('/api/'):
                return RedirectResponse('/users', status_code=303)
            return error('password_required', 403)
        admin_only = (path in ('/users', '/docs', '/redoc', '/openapi.json', '/docs/oauth2-redirect', '/static/users.html')
                      or path.startswith('/api/auth/'))
        if admin_only and session.username != 'admin':
            return error('forbidden', 403)
        return await call_next(request)

    @app.get('/login', include_in_schema=False)
    async def login_page():
        return FileResponse(root / 'static/login.html')

    @app.get('/users', include_in_schema=False)
    async def users_page():
        return FileResponse(root / 'static/users.html')

    @app.get('/api/auth/session')
    async def session_info(request: Request):
        auth = app.state.auth
        info = auth.public(request.state.session)
        response = JSONResponse(info)
        if auth.config.enabled and not info['authenticated']:
            nonce = secrets.token_urlsafe(32)
            info['csrf_token'] = nonce
            response = JSONResponse(info)
            response.set_cookie(LOGIN_COOKIE, nonce, httponly=True, secure=auth.config.secure_cookie, samesite='strict', max_age=600)
        return response

    @app.post('/login')
    async def login(request: Request, command: Login):
        auth = app.state.auth
        if not auth.config.enabled:
            return JSONResponse({'redirect': '/'})
        csrf = request.headers.get('x-csrf-token', '')
        cookie = request.cookies.get(LOGIN_COOKIE, '')
        if not csrf or not cookie or not hmac.compare_digest(csrf.encode(), cookie.encode()) or (request.headers.get('origin') and not same_origin(request)):
            return error('csrf_invalid', 403)
        outcome, sid = await auth.login(command.username, command.password.get_secret_value())
        if outcome != 'ok':
            return error('login_limited' if outcome == 'limited' else 'login_invalid', 429 if outcome == 'limited' else 401)
        old = request.cookies.get(COOKIE)
        auth.sessions.pop(old, None)
        response = JSONResponse({'redirect': '/users' if auth.restricted(auth.session(sid)) else '/'})
        response.delete_cookie(LOGIN_COOKIE, secure=auth.config.secure_cookie, httponly=True, samesite='strict')
        response.set_cookie(COOKIE, sid, httponly=True, samesite='lax', secure=auth.config.secure_cookie, max_age=auth.config.session_hours*3600)
        return response

    @app.post('/logout')
    async def logout(request: Request):
        auth = app.state.auth
        auth.sessions.pop(request.cookies.get(COOKIE), None)
        response = JSONResponse({'redirect': '/login'})
        response.delete_cookie(COOKIE, secure=auth.config.secure_cookie, httponly=True, samesite='lax')
        return response

    @app.get('/api/auth/users')
    async def users():
        auth = app.state.auth
        return {'users': [{'username': name, 'role': user.role, 'default_password': user.default_password}
                          for name, user in auth.credentials.users.items()] if auth.config.enabled else []}

    @app.post('/api/auth/password')
    async def password(request: Request, command: PasswordChange):
        auth = app.state.auth
        if not auth.config.enabled:
            return error('auth_disabled', 403)
        failure = await auth.change_password(request.state.session, command)
        if failure:
            return error(failure, 401 if failure == 'auth_required' else 403 if failure == 'password_required' else 422)
        return {'reauthenticate': command.username == request.state.session.username}
