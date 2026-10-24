"""
Knowledge Service IPC handlers (``ks.*``).

Thin wrappers over knowledge.ks.service.KnowledgeService for the Knowledge
page's product-knowledge tabs. Long operations (imports, re-index) return a
job immediately; progress arrives as ``ks.jobProgress`` pushes and via
``ks.getJob`` polling.
"""
from typing import Any, Callable, Dict, Optional

from gui.ipc.registry import IPCHandlerRegistry
from gui.ipc.types import IPCRequest, IPCResponse, create_error_response, create_success_response
from utils.logger_helper import logger_helper as logger


def _svc():
    from knowledge.ks.service import get_service
    return get_service()


def _call(request: IPCRequest, code: str, fn: Callable[[], Any]) -> IPCResponse:
    try:
        return create_success_response(request, fn())
    except ValueError as e:  # validation problems the user can fix
        return create_error_response(request, 'INVALID_PARAMS', str(e))
    except FileNotFoundError as e:
        return create_error_response(request, 'FILE_NOT_FOUND', str(e))
    except Exception as e:
        logger.error(f"[KS] {code} failed: {e}", exc_info=True)
        return create_error_response(request, code, str(e))


def _p(params: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    return params or {}


def _require(params: Dict[str, Any], *keys: str) -> None:
    missing = [k for k in keys if not params.get(k)]
    if missing:
        raise ValueError(f"missing parameter(s): {', '.join(missing)}")


# ---- overview / stores ------------------------------------------------------------
@IPCHandlerRegistry.background_handler('ks.overview')
def handle_overview(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    return _call(request, 'KS_OVERVIEW_ERROR', lambda: _svc().overview())


@IPCHandlerRegistry.handler('ks.saveStore')
def handle_save_store(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    return _call(request, 'KS_SAVE_STORE_ERROR', lambda: _svc().save_store(_p(params)))


@IPCHandlerRegistry.handler('ks.deleteStore')
def handle_delete_store(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    def run():
        _require(_p(params), 'id')
        _svc().delete_store(params['id'])
        return {'deleted': params['id']}
    return _call(request, 'KS_DELETE_STORE_ERROR', run)


@IPCHandlerRegistry.handler('ks.updateTenant')
def handle_update_tenant(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    def run():
        svc = _svc()
        return svc.store.update_tenant(svc.tenant_id(), name=_p(params).get('name'))
    return _call(request, 'KS_UPDATE_TENANT_ERROR', run)


# ---- products -----------------------------------------------------------------------
@IPCHandlerRegistry.background_handler('ks.listProducts')
def handle_list_products(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    p = _p(params)
    return _call(request, 'KS_LIST_PRODUCTS_ERROR', lambda: _svc().list_products(
        q=p.get('q', ''), category=p.get('category', ''), store_id=p.get('store_id', ''),
        offset=int(p.get('offset', 0)), limit=min(int(p.get('limit', 50)), 200)))


@IPCHandlerRegistry.background_handler('ks.getProduct')
def handle_get_product(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    def run():
        _require(_p(params), 'id')
        prod = _svc().get_product(params['id'])
        if not prod:
            raise ValueError('product not found')
        return prod
    return _call(request, 'KS_GET_PRODUCT_ERROR', run)


@IPCHandlerRegistry.background_handler('ks.saveProduct')
def handle_save_product(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    def run():
        data = dict(_p(params).get('product') or {})
        doc_path = _p(params).get('attach_path')
        prod = _svc().save_product(data)
        if doc_path:
            _svc().attach_document(prod['id'], doc_path)
        return _svc().get_product(prod['id'])
    return _call(request, 'KS_SAVE_PRODUCT_ERROR', run)


@IPCHandlerRegistry.handler('ks.deleteProduct')
def handle_delete_product(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    def run():
        _require(_p(params), 'id')
        _svc().delete_product(params['id'])
        return {'deleted': params['id']}
    return _call(request, 'KS_DELETE_PRODUCT_ERROR', run)


# ---- catalog import -------------------------------------------------------------------
@IPCHandlerRegistry.background_handler('ks.previewCatalog')
def handle_preview_catalog(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    def run():
        _require(_p(params), 'path')
        return _svc().preview_catalog(params['path'])
    return _call(request, 'KS_PREVIEW_CATALOG_ERROR', run)


@IPCHandlerRegistry.background_handler('ks.recheckCatalog')
def handle_recheck_catalog(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    def run():
        _require(_p(params), 'path', 'mapping')
        return _svc().recheck_catalog(params['path'], params['mapping'])
    return _call(request, 'KS_RECHECK_CATALOG_ERROR', run)


@IPCHandlerRegistry.handler('ks.writeCatalogTemplate')
def handle_write_catalog_template(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Write the fill-in catalog template into the chosen folder (never
    overwrites: an existing file gets a (2), (3)... suffix)."""
    def run():
        import os
        from knowledge.ks.catalog_import import write_template
        _require(_p(params), 'dir')
        folder = params['dir']
        if not os.path.isdir(folder):
            raise FileNotFoundError(folder)
        base = params.get('filename') or '商品资料导入模板'
        path, n = os.path.join(folder, f'{base}.xlsx'), 2
        while os.path.exists(path):
            path, n = os.path.join(folder, f'{base} ({n}).xlsx'), n + 1
        return {'path': write_template(path)}
    return _call(request, 'KS_WRITE_TEMPLATE_ERROR', run)


@IPCHandlerRegistry.handler('ks.importCatalog')
def handle_import_catalog(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    def run():
        p = _p(params)
        _require(p, 'path', 'mapping')
        result = _svc().import_catalog(p['path'], p['mapping'], default_store_id=p.get('default_store_id', ''))
        if p.get('pending_id'):
            # A staged file (agent-fetched) is imported now: off the review list.
            # The import job reads the file later, so the copy stays on disk.
            from knowledge.ks.pending_imports import PendingImports
            PendingImports(_svc().data_dir).remove(p['pending_id'], delete_file=False)
        return result
    return _call(request, 'KS_IMPORT_CATALOG_ERROR', run)


@IPCHandlerRegistry.handler('ks.listPendingImports')
def handle_list_pending_imports(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Catalog files agents fetched (e.g. a store's product export), awaiting review."""
    return _call(request, 'KS_PENDING_IMPORTS_ERROR', lambda: {'items': _svc().pending_imports()})


@IPCHandlerRegistry.handler('ks.dismissPendingImport')
def handle_dismiss_pending_import(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    def run():
        _require(_p(params), 'id')
        return {'dismissed': _svc().dismiss_pending_import(params['id'])}
    return _call(request, 'KS_PENDING_IMPORTS_ERROR', run)


# ---- product documents ------------------------------------------------------------------
@IPCHandlerRegistry.background_handler('ks.draftFromDocument')
def handle_draft_from_document(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    def run():
        _require(_p(params), 'path')
        return _svc().draft_from_document(params['path'])
    return _call(request, 'KS_DRAFT_ERROR', run)


@IPCHandlerRegistry.handler('ks.ingestProductFiles')
def handle_ingest_product_files(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    def run():
        p = _p(params)
        _require(p, 'paths')
        return _svc().ingest_product_files(list(p['paths']), store_id=p.get('store_id', ''))
    return _call(request, 'KS_INGEST_FILES_ERROR', run)


@IPCHandlerRegistry.background_handler('ks.attachDocument')
def handle_attach_document(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    def run():
        _require(_p(params), 'product_id', 'path')
        return _svc().attach_document(params['product_id'], params['path'])
    return _call(request, 'KS_ATTACH_DOCUMENT_ERROR', run)


@IPCHandlerRegistry.handler('ks.deleteDocument')
def handle_delete_document(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    def run():
        _require(_p(params), 'id')
        _svc().delete_document(params['id'])
        return {'deleted': params['id']}
    return _call(request, 'KS_DELETE_DOCUMENT_ERROR', run)


# ---- policies ------------------------------------------------------------------------------
@IPCHandlerRegistry.background_handler('ks.getPolicies')
def handle_get_policies(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    return _call(request, 'KS_GET_POLICIES_ERROR', lambda: _svc().policies_view())


@IPCHandlerRegistry.background_handler('ks.savePolicy')
def handle_save_policy(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    def run():
        p = _p(params)
        _require(p, 'topic', 'text')
        return _svc().save_policy(p['topic'], p['text'], store_id=p.get('store_id') or None, title=p.get('title', ''))
    return _call(request, 'KS_SAVE_POLICY_ERROR', run)


@IPCHandlerRegistry.handler('ks.deletePolicy')
def handle_delete_policy(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    def run():
        _require(_p(params), 'id')
        _svc().delete_policy(params['id'])
        return {'deleted': params['id']}
    return _call(request, 'KS_DELETE_POLICY_ERROR', run)


# ---- buyer profiles (用户画像) ----------------------------------------------------------------
@IPCHandlerRegistry.background_handler('ks.listProfiles')
def handle_list_profiles(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    def run():
        _require(_p(params), 'store_id')
        return {'items': _svc().list_profiles(params['store_id'])}
    return _call(request, 'KS_LIST_PROFILES_ERROR', run)


@IPCHandlerRegistry.handler('ks.saveProfile')
def handle_save_profile(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    def run():
        p = _p(params)
        _require(p, 'store_id', 'customer_id')
        return _svc().set_profile_fields(p['store_id'], p['customer_id'], p.get('recipient', ''), p.get('fields') or {})
    return _call(request, 'KS_SAVE_PROFILE_ERROR', run)


@IPCHandlerRegistry.handler('ks.deleteProfile')
def handle_delete_profile(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    def run():
        p = _p(params)
        _require(p, 'store_id', 'customer_id')
        return {'deleted': _svc().delete_profile(p['store_id'], p['customer_id'], p.get('recipient', ''))}
    return _call(request, 'KS_DELETE_PROFILE_ERROR', run)


# ---- retrieval test -------------------------------------------------------------------------
@IPCHandlerRegistry.background_handler('ks.search')
def handle_search(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    def run():
        p = _p(params)
        _require(p, 'query')
        return _svc().search(p['query'], store_ref=p.get('store_id', ''),
                             platform_item_id=p.get('platform_item_id', ''), product_id=p.get('product_id', ''))
    return _call(request, 'KS_SEARCH_ERROR', run)


# ---- jobs / maintenance -----------------------------------------------------------------------
@IPCHandlerRegistry.handler('ks.getJob')
def handle_get_job(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    def run():
        _require(_p(params), 'id')
        job = _svc().get_job(params['id'])
        if not job:
            raise ValueError('job not found')
        return job
    return _call(request, 'KS_GET_JOB_ERROR', run)


@IPCHandlerRegistry.handler('ks.listJobs')
def handle_list_jobs(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    return _call(request, 'KS_LIST_JOBS_ERROR', lambda: _svc().list_jobs(limit=int(_p(params).get('limit', 30))))


@IPCHandlerRegistry.handler('ks.cancelJob')
def handle_cancel_job(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    def run():
        _require(_p(params), 'id')
        _svc().cancel_job(params['id'])
        return {'cancelling': params['id']}
    return _call(request, 'KS_CANCEL_JOB_ERROR', run)


@IPCHandlerRegistry.handler('ks.reindex')
def handle_reindex(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    return _call(request, 'KS_REINDEX_ERROR', lambda: _svc().reindex())


@IPCHandlerRegistry.handler('ks.listAudit')
def handle_list_audit(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    return _call(request, 'KS_AUDIT_ERROR', lambda: _svc().store.list_audit(int(_p(params).get('limit', 100))))


# ---- connections to private / public KS servers --------------------------------------------
def _router():
    from knowledge.ks.service import get_router
    return get_router()


def _conn(cid: str):
    c = next((c for c in _router().connections.list() if c['id'] == cid), None)
    if not c:
        raise ValueError('connection not found')
    return c


@IPCHandlerRegistry.handler('ks.listConnections')
def handle_list_connections(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    def run():
        cs = _router().connections
        return [{**c, 'signed_in': bool(cs.token(c['id'])) if c['auth'] == 'local' else True} for c in cs.list()]
    return _call(request, 'KS_CONNECTIONS_ERROR', run)


@IPCHandlerRegistry.handler('ks.saveConnection')
def handle_save_connection(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    return _call(request, 'KS_SAVE_CONNECTION_ERROR', lambda: _router().connections.save(_p(params)))


@IPCHandlerRegistry.handler('ks.deleteConnection')
def handle_delete_connection(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    def run():
        _require(_p(params), 'id')
        _router().connections.delete(params['id'])
        return {'deleted': params['id']}
    return _call(request, 'KS_DELETE_CONNECTION_ERROR', run)


@IPCHandlerRegistry.background_handler('ks.loginConnection')
def handle_login_connection(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    def run():
        p = _p(params)
        _require(p, 'id', 'email', 'password')
        router = _router()
        c = _conn(p['id'])
        client = router.client_factory(c)
        router.connections.set_token(c['id'], client.local_login(p['email'], p['password']))
        return {'signed_in': True}
    return _call(request, 'KS_LOGIN_CONNECTION_ERROR', run)


@IPCHandlerRegistry.background_handler('ks.testConnection')
def handle_test_connection(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Reachability, plane, identity and tenant membership, step by step for the GUI."""
    def run():
        import time as _t
        router = _router()
        c = _conn(_p(params).get('id', ''))
        client = router.client_factory(c)
        steps = []
        t0 = _t.perf_counter()
        try:
            h = client.health()
            steps.append({'step': 'reach', 'ok': True, 'detail': f"plane={h.get('plane')} embedder={h.get('embedder')}",
                          'ms': round((_t.perf_counter() - t0) * 1000)})
        except Exception as e:
            steps.append({'step': 'reach', 'ok': False, 'detail': str(e)})
            return {'ok': False, 'steps': steps}
        if h.get('plane') != c['plane']:
            steps.append({'step': 'plane', 'ok': False, 'detail': f"server says {h.get('plane')}, saved as {c['plane']}"})
        try:
            me = client.me()
            tenants = me.get('tenants', [])
            steps.append({'step': 'identity', 'ok': True,
                          'detail': me['principal'].get('email') or me['principal'].get('user_id')})
            match = [t for t in tenants if t['id'] == c['tenant_id']]
            steps.append({'step': 'tenant', 'ok': bool(match),
                          'detail': (f"{match[0]['name']} ({match[0]['role']})" if match
                                     else 'not a member of the saved tenant'),
                          'tenants': tenants})
        except Exception as e:
            steps.append({'step': 'identity', 'ok': False, 'detail': str(e)})
        return {'ok': all(s['ok'] for s in steps), 'steps': steps}
    return _call(request, 'KS_TEST_CONNECTION_ERROR', run)


@IPCHandlerRegistry.background_handler('ks.routerSearch')
def handle_router_search(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    def run():
        p = _p(params)
        _require(p, 'query')
        return _router().search(p['query'], store=p.get('store_id', ''), platform_item_id=p.get('platform_item_id', ''),
                                product_id=p.get('product_id', ''))
    return _call(request, 'KS_ROUTER_SEARCH_ERROR', run)


# ---- access administration (this computer or a connected server) --------------------------
def _admin_target(params: Dict[str, Any]):
    """The local service, or RemoteAdmin for params['connection_id']."""
    cid = params.get('connection_id')
    if not cid:
        return _svc()
    from knowledge.ks.planes import RemoteAdmin
    return RemoteAdmin(_router().client_factory(_conn(cid)))


_ACCESS_OPS = {
    'view': lambda t, p: t.access_view(),
    'saveMember': lambda t, p: t.save_member(p.get('email', ''), p.get('role', 'viewer'), p.get('status'),
                                             p.get('member_id'), p.get('display_name', '')),
    'removeMember': lambda t, p: t.remove_member(p['member_id']),
    'saveGroup': lambda t, p: t.save_group(p['name'], p.get('member_ids') or [], p.get('description', ''),
                                           p.get('group_id')),
    'deleteGroup': lambda t, p: t.delete_group(p['group_id']),
    'setGrant': lambda t, p: t.set_grant(p['kb_id'], p['principal_type'], p['principal_id'],
                                         p.get('permission', 'read')),
    'removeGrant': lambda t, p: t.remove_grant(p['grant_id']),
    'updateKb': lambda t, p: t.update_kb(p['kb_id'], **{k: p[k] for k in ('name', 'description', 'plane', 'sensitivity')
                                                         if k in p}),
    'audit': lambda t, p: t.list_audit(limit=int(p.get('limit', 100))),
}


@IPCHandlerRegistry.background_handler('ks.access')
def handle_access(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    def run():
        p = _p(params)
        op = _ACCESS_OPS.get(p.get('op', ''))
        if op is None:
            raise ValueError(f"unknown access operation {p.get('op')}")
        out = op(_admin_target(p), p)
        return {'ok': True} if out is None else out
    return _call(request, 'KS_ACCESS_ERROR', run)


# ---- link to the app's own stores (agent DB) ---------------------------------------------
def _app_stores():
    from app_context import AppContext
    mw = AppContext.get_main_window()
    svc = getattr(getattr(mw, 'ec_db_mgr', None), 'store_service', None)
    if svc is None:
        return []
    return [{'store_id': s.get('store_id'), 'name': s.get('name') or s.get('store_id'), 'platform': s.get('platform') or ''}
            for s in svc.list_stores()]


@IPCHandlerRegistry.handler('ks.listAppStores')
def handle_list_app_stores(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    return _call(request, 'KS_APP_STORES_ERROR', _app_stores)


@IPCHandlerRegistry.handler('ks.syncAppStores')
def handle_sync_app_stores(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Create a knowledge store for every app store not linked yet."""
    def run():
        svc = _svc()
        linked = {s['ecan_store_id'] for s in svc.store.list_stores(svc.tenant_id()) if s.get('ecan_store_id')}
        created = []
        for s in _app_stores():
            if s['store_id'] and s['store_id'] not in linked:
                created.append(svc.save_store({'name': s['name'], 'platform': s['platform'], 'ecan_store_id': s['store_id']}))
        return {'created': created}
    return _call(request, 'KS_SYNC_APP_STORES_ERROR', run)


# ---- LAN sharing: commander serves knowledge to platoon machines ---------------------------
def _lan():
    from knowledge.ks.service import get_lan
    return get_lan()


@IPCHandlerRegistry.background_handler('ks.lanStatus')
def handle_lan_status(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    from knowledge.ks.service import lan_sharing_status
    return _call(request, 'KS_LAN_STATUS_ERROR', lan_sharing_status)


@IPCHandlerRegistry.background_handler('ks.lanSetSharing')
def handle_lan_set_sharing(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    def run():
        from knowledge.ks.service import apply_lan_sharing
        p = _p(params)
        _lan()['access'].set_config(enabled=p.get('enabled'), port=p.get('port'))
        return apply_lan_sharing()
    return _call(request, 'KS_LAN_SET_SHARING_ERROR', run)


@IPCHandlerRegistry.handler('ks.lanNewCode')
def handle_lan_new_code(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    return _call(request, 'KS_LAN_CODE_ERROR', lambda: _lan()['access'].new_code())


@IPCHandlerRegistry.handler('ks.lanRevoke')
def handle_lan_revoke(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    def run():
        _require(_p(params), 'id')
        _lan()['access'].revoke(params['id'])
        return {'revoked': params['id']}
    return _call(request, 'KS_LAN_REVOKE_ERROR', run)


@IPCHandlerRegistry.background_handler('ks.lanDiscover')
def handle_lan_discover(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    from knowledge.ks.lan import discover_commanders
    return _call(request, 'KS_LAN_DISCOVER_ERROR', discover_commanders)


@IPCHandlerRegistry.background_handler('ks.lanPair')
def handle_lan_pair(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    def run():
        import socket
        p = _p(params)
        _require(p, 'url', 'code')
        try:
            return _lan()['source'].pair(p['url'], p['code'], p.get('device_name') or socket.gethostname(),
                                         p.get('commander', ''))
        except PermissionError as e:
            raise ValueError(str(e))
    return _call(request, 'KS_LAN_PAIR_ERROR', run)


@IPCHandlerRegistry.handler('ks.lanSetSource')
def handle_lan_set_source(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    def run():
        p = _p(params)
        if p.get('forget'):
            _lan()['source'].forget()
            return _lan()['source'].get()
        return _lan()['source'].set_mode(p.get('mode', 'local'))
    return _call(request, 'KS_LAN_SOURCE_ERROR', run)


@IPCHandlerRegistry.background_handler('ks.lanTestSource')
def handle_lan_test_source(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Can this platoon reach the commander's gateway with its device token?"""
    def run():
        import time as _t
        import httpx
        src = _lan()['source']
        if not src.url():
            raise ValueError('not paired with a commander')
        t0 = _t.perf_counter()
        with httpx.Client(timeout=5) as c:
            r = c.get(f"{src.url()}/v1/me", headers={'Authorization': f'Bearer {src.token()}'})
        ms = round((_t.perf_counter() - t0) * 1000)
        if r.status_code == 401:
            return {'ok': False, 'ms': ms, 'detail': 'the commander no longer accepts this machine; pair again'}
        r.raise_for_status()
        return {'ok': True, 'ms': ms, 'detail': r.json()['tenants'][0]['name']}
    return _call(request, 'KS_LAN_TEST_ERROR', run)


# ---- product-knowledge embedding model ---------------------------------------------------
@IPCHandlerRegistry.handler('ks.getEmbedder')
def handle_get_embedder(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    def run():
        from knowledge.ks.service import embedder_config
        cfg = embedder_config()
        cfg['active_id'] = _svc().embedder.id
        return cfg
    return _call(request, 'KS_GET_EMBEDDER_ERROR', run)


@IPCHandlerRegistry.background_handler('ks.testEmbedder')
def handle_test_embedder(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Embed two related and one unrelated sentence; report dimension, latency, separation."""
    def run():
        import time as _t
        from knowledge.ks.embedding import OpenAICompatibleEmbedder, embed_query
        from knowledge.ks.service import _embed_key
        p = _p(params)
        _require(p, 'base_url', 'model')
        key = p.get('api_key') if p.get('api_key') is not None else _embed_key()
        e = OpenAICompatibleEmbedder(p['base_url'], p['model'], key or '', verify_tls=p.get('verify_tls', True))
        t0 = _t.perf_counter()
        docs = e.embed(['会缩水吗\n首次洗涤可能轻微缩水约1-2%', '下单后48小时内发货，默认中通快递'])
        q = embed_query(e, '洗完会变小吗')
        ms = round((_t.perf_counter() - t0) * 1000)
        related, unrelated = float(docs[0] @ q), float(docs[1] @ q)
        return {'dim': int(docs.shape[1]), 'ms': ms, 'related': round(related, 3), 'unrelated': round(unrelated, 3),
                'separates': related > unrelated + 0.1, 'instruction': bool(e.query_instruction)}
    return _call(request, 'KS_TEST_EMBEDDER_ERROR', run)


@IPCHandlerRegistry.handler('ks.setEmbedder')
def handle_set_embedder(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    def run():
        from knowledge.ks.service import save_embedder_config
        p = _p(params)
        return save_embedder_config(p.get('mode', 'app'), p.get('base_url', ''), p.get('model', ''),
                                    p.get('api_key'), p.get('verify_tls', True))
    return _call(request, 'KS_SET_EMBEDDER_ERROR', run)
