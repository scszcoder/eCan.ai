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


@IPCHandlerRegistry.handler('ks.importCatalog')
def handle_import_catalog(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    def run():
        p = _p(params)
        _require(p, 'path', 'mapping')
        return _svc().import_catalog(p['path'], p['mapping'], default_store_id=p.get('default_store_id', ''))
    return _call(request, 'KS_IMPORT_CATALOG_ERROR', run)


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
