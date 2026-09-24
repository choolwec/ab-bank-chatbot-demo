"""HTTP Basic auth for every /admin/* route (ticket P8).

Unconfigured (ADMIN_USER/ADMIN_PASSWORD unset) -> 404, so the routes don't
exist as far as the internet can tell; wrong or missing credentials -> 401
with a Basic challenge. Constant-time comparison. Every admin route adds
`dependencies=[Depends(require_admin)]`; tests/test_admin.py checks all of them.
"""

import hmac

from fastapi import Depends, HTTPException
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from . import config

_basic = HTTPBasic(auto_error=False)


def require_admin(credentials: HTTPBasicCredentials | None = Depends(_basic)) -> None:
    expected = config.admin_credentials()
    if expected is None:
        raise HTTPException(status_code=404, detail="Not Found")
    ok = credentials is not None and (
        hmac.compare_digest(credentials.username.encode(), expected[0].encode())
        & hmac.compare_digest(credentials.password.encode(), expected[1].encode())
    )
    if not ok:
        raise HTTPException(
            status_code=401,
            detail="Unauthorized",
            headers={"WWW-Authenticate": 'Basic realm="admin"'},
        )
