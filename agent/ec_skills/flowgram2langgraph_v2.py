import json
import os
import re
from typing import Dict, List, Optional, Tuple
from agent.ec_skills.dev_defs import BreakpointManager

from utils.logger_helper import logger_helper as logger


def _v2_debug_workflow(tag: str, wf: dict, base_name: Optional[str] = None):
    try:
        nodes = wf.get('nodes', []) or []
        edges = wf.get('edges', []) or []
        info = {
            'tag': tag,
            'nodes': [{'id': n.get('id'), 'type': n.get('type')} for n in nodes],
            'edges': [{'s': e.get('sourceNodeID'), 't': e.get('targetNodeID'), 'sp': e.get('sourcePortID') } for e in edges],
            'node_count': len(nodes),
            'edge_count': len(edges),
        }
        logger.debug(f"[v2][wf] {json.dumps(info, ensure_ascii=False)}")
        # Also dump full JSON to file per step for inspection
        if base_name:
            out_js = f"{base_name}_v2_{tag}.json"
            try:
                with open(out_js, 'w', encoding='utf-8') as f:
                    json.dump({'nodes': nodes, 'edges': edges}, f, ensure_ascii=False, indent=2)
                logger.debug(f"[v2][wf] saved {out_js}")
            except Exception as _e:
                logger.debug(f"[v2][wf] save json failed: {_e}")
    except Exception:
        pass


def _v2_extract_next_sheet(data_obj: dict, sheet_map: Dict[str, dict]) -> Optional[str]:
    """Best-effort extraction of a next sheet name/id from a structural node's data.
    Tries common keys, then recursively scans for any value that matches a known sheet name/id.
    """
    try:
        if not isinstance(data_obj, dict):
            return None
        # Direct keys first (both hyphen/underscore and legacy variants)
        candidates = [
            data_obj.get('nextSheet'), data_obj.get('next_sheet'), data_obj.get('sheet'),
            data_obj.get('nextSheetId'), data_obj.get('next_sheet_id'), data_obj.get('sheetId'), data_obj.get('sheet_id'),
            data_obj.get('targetSheet'), data_obj.get('target_sheet'), data_obj.get('sheetName'), data_obj.get('sheet_name'),
        ]
        inner = data_obj.get('data') if isinstance(data_obj.get('data'), dict) else {}
        candidates += [
            inner.get('nextSheet'), inner.get('next_sheet'), inner.get('sheet'),
            inner.get('nextSheetId'), inner.get('next_sheet_id'), inner.get('sheetId'), inner.get('sheet_id'),
            inner.get('targetSheet'), inner.get('target_sheet'), inner.get('sheetName'), inner.get('sheet_name'),
        ]
        for c in candidates:
            if c and str(c) in sheet_map:
                return str(c)
        # Recursive scan for any value matching a sheet key
        def _scan(obj):
            if isinstance(obj, dict):
                for v in obj.values():
                    res = _scan(v)
                    if res:
                        return res
            elif isinstance(obj, list):
                for v in obj:
                    res = _scan(v)
                    if res:
                        return res
            else:
                sval = str(obj)
                if sval in sheet_map:
                    return sval
            return None
        return _scan(data_obj)
    except Exception:
        return None


def _v2_find_sheet_entry(wf: dict) -> Optional[str]:
    try:
        sheet_input_id = None
        for n in wf.get('nodes', []) or []:
            if n.get('type') == 'sheet-inputs':
                sheet_input_id = n.get('id')
                break
        if not sheet_input_id:
            return None
        for e in wf.get('edges', []) or []:
            if e.get('sourceNodeID') == sheet_input_id:
                return e.get('targetNodeID')
        return None
    except Exception:
        return None


def _v2_flatten_sheets(main_wf: dict, sheets: List[dict]) -> tuple[dict, Dict[str, str]]:
    """Return a new workflow with other sheets stitched into the main sheet.
    - For any edge to a 'sheet-call' or 'sheet-outputs' (with next sheet), redirect it to the entry node of that sheet.
    - Merge the secondary sheet nodes/edges (prefixed with sheetName__) into the main wf.
    - Remove structural sheet nodes from the main graph.
    - Log reconnections.
    """
    merged_nodes = list((main_wf.get('nodes') or []).copy())
    merged_edges = list((main_wf.get('edges') or []).copy())
    redirect_map: Dict[str, str] = {}

    # Build sheet map (by both name and id)
    sheet_map: Dict[str, dict] = {}
    for s in sheets:
        sname = str(s.get('name'))
        swf = s.get('workFlow') or {}
        if sname:
            sheet_map[sname] = swf
        sid = s.get('id') or None
        if sid:
            sheet_map[str(sid)] = swf

    # Helper to prefix ids for imported sheet nodes/edges
    def qid(sname: str, nid: str) -> str:
        return f"{sname}__{nid}"

    # Bring in all secondary sheets (except the first, which is main)
    for s in sheets[1:]:
        sname = str(s.get('name'))
        swf = s.get('workFlow') or {}
        # copy nodes
        for n in swf.get('nodes', []) or []:
            if n.get('type') in ('sheet-inputs', 'sheet_inputs', 'sheet-outputs', 'sheet_outputs', 'sheet-call', 'sheet_call', 'start'):
                continue
            nn = json.loads(json.dumps(n))
            nn['id'] = qid(sname, n.get('id'))
            merged_nodes.append(nn)
        # copy edges
        for e in swf.get('edges', []) or []:
            if not e: 
                continue
            # Skip edges originating from structural sheet-inputs or start
            src_id = e.get('sourceNodeID')
            tgt_id = e.get('targetNodeID')
            src_node = next((n for n in (swf.get('nodes') or []) if n.get('id') == src_id), {})
            tgt_node = next((n for n in (swf.get('nodes') or []) if n.get('id') == tgt_id), {})
            if src_node.get('type') in ('sheet-inputs','sheet_inputs','start'):
                continue
            if tgt_node.get('type') in ('sheet-inputs','sheet_inputs'):
                continue
            ee = json.loads(json.dumps(e))
            ee['sourceNodeID'] = qid(sname, src_id)
            ee['targetNodeID'] = qid(sname, tgt_id)
            merged_edges.append(ee)

    # Pre-compute a structural redirect map for ALL structural nodes we see now,
    # so edges created later (e.g., during loop conversion) can also be rewritten.
    # - sheet-call / sheet-outputs: use their configured next sheet entry
    # - sheet-inputs: use the entry point successor of their own sheet (main sheet)
    id_to_node = {n.get('id'): n for n in merged_nodes}
    struct_redirect_map: Dict[str, str] = {}
    for nid, n in list(id_to_node.items()):
        ntype = (n or {}).get('type')
        if ntype in ('sheet-call', 'sheet_call', 'sheet-outputs', 'sheet_outputs'):
            data = (n or {}).get('data') or {}
            # Robust extraction
            next_sheet = _v2_extract_next_sheet(data, sheet_map)
            if not next_sheet:
                continue
            swf = sheet_map.get(str(next_sheet))
            if not isinstance(swf, dict):
                continue
            entry = _v2_find_sheet_entry(swf)
            if not entry:
                continue
            struct_redirect_map[nid] = qid(str(next_sheet), entry)
        elif ntype in ('sheet-inputs','sheet_inputs'):
            # For edges pointing to a main sheet sheet-inputs, send to the first node after inputs
            entry = _v2_find_sheet_entry(main_wf)
            if entry:
                struct_redirect_map[nid] = entry

    # Merge into the shared redirect_map
    redirect_map.update(struct_redirect_map)

    # Redirect edges that currently target structural nodes, if we have a mapping
    new_edges = []
    for e in merged_edges:
        tgt = e.get('targetNodeID')
        if tgt in redirect_map:
            ee = json.loads(json.dumps(e))
            ee['targetNodeID'] = redirect_map[tgt]
            logger.debug(f"[v2][sheets] redirect edge {e.get('sourceNodeID')} -> {tgt} to {ee['targetNodeID']}")
            new_edges.append(ee)
        else:
            new_edges.append(e)

    merged_edges = new_edges

    # Final cleanup: any remaining edges pointing to structural nodes -> try redirect; otherwise KEEP
    struct_ids = {n.get('id') for n in merged_nodes if n.get('type') in ('sheet-call','sheet_call','sheet-outputs','sheet_outputs','sheet-inputs','sheet_inputs')}
    cleaned_edges = []
    for e in merged_edges:
        tgt = e.get('targetNodeID')
        if tgt in struct_ids:
            # Prefer pre-computed redirects if available
            if tgt in redirect_map:
                cleaned = json.loads(json.dumps(e))
                cleaned['targetNodeID'] = redirect_map[tgt]
                cleaned_edges.append(cleaned)
                continue
            # Otherwise, keep the edge as-is; a later pass (after loop conversion) may still rewrite it
            cleaned_edges.append(e)
            continue
        cleaned_edges.append(e)
    merged_edges = cleaned_edges

    # Remove structural sheet nodes from merged nodes
    cleaned_nodes = [n for n in merged_nodes if n.get('type') not in ('sheet-call','sheet_call','sheet-outputs','sheet_outputs','sheet-inputs','sheet_inputs', 'start')]
    stitched = {'nodes': cleaned_nodes, 'edges': merged_edges}
    _v2_debug_workflow('after_flatten_sheets', stitched)
    return stitched, redirect_map


def _v2_remove_groups(wf: dict) -> dict:
    cleaned_nodes = [n for n in (wf.get('nodes') or []) if n.get('type') != 'group']
    out = {'nodes': cleaned_nodes, 'edges': wf.get('edges') or []}
    _v2_debug_workflow('after_remove_groups', out)
    return out


def _v2_convert_conditions_schema_level(wf: dict) -> dict:
    """Optional schema-level conversion of condition nodes to edges.
    For now, keep condition nodes (original converter handles it). This is a hook.
    """
    _v2_debug_workflow('after_condition_convert_noop', wf)
    return wf


def _v2_convert_loops(wf: dict) -> dict:
    """Convert loop nodes by injecting an update_<loop>_condition code node and a check_<loop>_condition condition node,
    rewiring incoming/outgoing edges and flattening internal blocks. Removes block-start/block-end/loop shell.
    """
    nodes = list(wf.get('nodes') or [])
    edges = list(wf.get('edges') or [])

    id_to_node = {n.get('id'): n for n in nodes}
    # Build adjacency for inner detection
    def inner_first_last(loop_node: dict) -> tuple[set, set]:
        inner_nodes = set()
        preds = {}
        succs = {}
        for e in (loop_node.get('edges') or []):
            u = e.get('sourceNodeID'); v = e.get('targetNodeID')
            succs.setdefault(u, set()).add(v)
            preds.setdefault(v, set()).add(u)
            inner_nodes.add(u); inner_nodes.add(v)
        def is_passthru(nid: str):
            t = next((bn.get('type') for bn in (loop_node.get('blocks') or []) if bn.get('id') == nid), '')
            return t in ('block-start','block-end')
        candidates = {nid for nid in inner_nodes if not is_passthru(nid)}
        firsts = {nid for nid in candidates if len([p for p in preds.get(nid, set()) if not is_passthru(p)]) == 0}
        lasts = {nid for nid in candidates if len([s for s in succs.get(nid, set()) if not is_passthru(s)]) == 0}
        return firsts or candidates, lasts or candidates

    new_nodes = []
    new_edges = []

    # Helper to copy inner edges/nodes into outer graph (loop blocks)
    def copy_inner(loop_id: str, loop_node: dict):
        # Add inner nodes (excluding block-start/end)
        for bn in (loop_node.get('blocks') or []):
            if bn.get('type') in ('block-start','block-end'):
                continue
            nn = json.loads(json.dumps(bn))
            if not any(n.get('id') == nn.get('id') for n in new_nodes):
                new_nodes.append(nn)
        # Add inner edges directly
        for ie in (loop_node.get('edges') or []):
            su = ie.get('sourceNodeID'); tv = ie.get('targetNodeID')
            # skip edges touching passthru blocks
            if any(b.get('id') == su and b.get('type') in ('block-start','block-end') for b in (loop_node.get('blocks') or [])):
                continue
            if any(b.get('id') == tv and b.get('type') in ('block-start','block-end') for b in (loop_node.get('blocks') or [])):
                continue
            new_edges.append({'sourceNodeID': su, 'targetNodeID': tv})

    # Process each loop
    loop_ids = [n.get('id') for n in nodes if n.get('type') == 'loop']
    if not loop_ids:
        return wf

    # Build predecessor and successor edges for outer graph
    preds_out = {}
    succs_out = {}
    for e in edges:
        preds_out.setdefault(e.get('targetNodeID'), set()).add(e.get('sourceNodeID'))
        succs_out.setdefault(e.get('sourceNodeID'), set()).add(e.get('targetNodeID'))

    to_remove_node_ids = set()
    to_remove_edges = []

    for lid in loop_ids:
        lnode = id_to_node.get(lid)
        if not lnode:
            continue
        # determine internal entry/exit
        firsts, lasts = inner_first_last(lnode)
        # external predecessors and successors
        ext_preds = preds_out.get(lid, set())
        ext_succs = succs_out.get(lid, set())

        # inject update code node
        update_id = f"update_{lid}_condition"
        update_node = {
            'id': update_id,
            'type': 'code',
            'data': {
                'title': update_id,
                'script': {
                    'language': 'python',
                    'content': """
def main(state, *, runtime, store):
    # initialize or update loop condition variables here
    # TODO: implement per loop type (loopWhile/loopFor)
    # example:
    # state['condition'] = bool(state.get('loop', True))
    return {'result': 'ok'}
"""
                }
            }
        }
        # inject check condition node
        check_id = f"check_{lid}_condition"
        check_node = {
            'id': check_id,
            'type': 'condition',
            'data': {
                'title': check_id,
                'conditions': [
                    {'key': 'if_out', 'value': {'left': {'type': 'ref','content': ['start_0','condition']}, 'operator': 'is_true'}},
                    {'key': 'else_out', 'value': {'left': {'type': 'ref','content': ['start_0','condition']}, 'operator': 'is_false'}},
                ]
            }
        }
        new_nodes.extend([update_node, check_node])

        # external edges to loop -> update
        for p in ext_preds:
            to_remove_edges.append({'sourceNodeID': p, 'targetNodeID': lid})
            new_edges.append({'sourceNodeID': p, 'targetNodeID': update_id})
        # update -> check
        new_edges.append({'sourceNodeID': update_id, 'targetNodeID': check_id})
        # check if_true -> first inner(s)
        for f in firsts:
            new_edges.append({'sourceNodeID': check_id, 'targetNodeID': f, 'sourcePortID': 'if_out'})
        # check else -> external successor(s) of loop
        for s in ext_succs:
            to_remove_edges.append({'sourceNodeID': lid, 'targetNodeID': s})
            new_edges.append({'sourceNodeID': check_id, 'targetNodeID': s, 'sourcePortID': 'else_out'})
        # back-edge: last inner(s) -> update
        for la in lasts:
            new_edges.append({'sourceNodeID': la, 'targetNodeID': update_id})

        # copy inner graph into outer
        copy_inner(lid, lnode)

        # mark loop shell and passthrough blocks for removal
        to_remove_node_ids.add(lid)
        for bn in (lnode.get('blocks') or []):
            if bn.get('type') in ('block-start','block-end'):
                to_remove_node_ids.add(bn.get('id'))

    # Remove nodes
    nodes_out = [n for n in nodes if n.get('id') not in to_remove_node_ids]
    # Add injected nodes
    for n in new_nodes:
        if not any(x.get('id') == n.get('id') for x in nodes_out):
            nodes_out.append(n)

    # Remove loop touching edges and apply rewires
    def edge_key(e):
        return (e.get('sourceNodeID'), e.get('targetNodeID'), e.get('sourcePortID'))

    remove_keys = {edge_key(e) for e in to_remove_edges}
    edges_out = [e for e in edges if edge_key(e) not in remove_keys and e.get('sourceNodeID') not in to_remove_node_ids and e.get('targetNodeID') not in to_remove_node_ids]
    # Append new edges
    edges_out.extend(new_edges)

    # Defensive sweep: drop edges whose endpoints are no longer present (e.g., loop containers)
    valid_ids = {str(n.get('id')) for n in nodes_out}
    edges_out = [e for e in edges_out if str(e.get('sourceNodeID')) in valid_ids and str(e.get('targetNodeID')) in valid_ids]

    out = {'nodes': nodes_out, 'edges': edges_out}
    _v2_debug_workflow('after_convert_loops', out)
    return out


def _v2_build_mermaid(wf: dict) -> str:
    lines = ["flowchart TD"]
    nodes = wf.get('nodes', []) or []
    edges = wf.get('edges', []) or []
    # Identify structural ids to hide from diagram (defensive)
    struct_ids = {str(n.get('id')) for n in nodes if n.get('type') in ('sheet-call','sheet-outputs','sheet-inputs')}
    # Build safe id map
    safe_map = {}
    used = set()
    def _safe(n: str) -> str:
        s = re.sub(r'[^A-Za-z0-9_]', '_', n or '')
        if not re.match(r'^[A-Za-z_]', s):
            s = 'n_' + s
        # avoid empty
        if not s:
            s = 'n'
        base = s
        i = 1
        while s in used:
            s = f"{base}_{i}"
            i += 1
        used.add(s)
        return s
    for n in nodes:
        rid = str(n.get('id'))
        if rid not in safe_map:
            safe_map[rid] = _safe(rid)
    # Identify end nodes to render as END
    end_ids = {str(n.get('id')) for n in nodes if n.get('type') == 'end'}
    # Nodes
    for n in nodes:
        rid = str(n.get('id'))
        if rid in end_ids or rid in struct_ids:
            continue
        sid = safe_map[rid]
        lbl = rid.replace('"', '\\"')
        lines.append(f'{sid}["{lbl}"]')
    # Add END node if any end present
    if end_ids:
        lines.append('END["END"]')
    # Edges
    for e in edges:
        ur = str(e.get('sourceNodeID'))
        vr = str(e.get('targetNodeID'))
        # Skip edges that touch structural nodes (defensive)
        if ur in struct_ids or vr in struct_ids:
            continue
        # Also skip by id pattern if structural node ids were removed from nodes
        def _is_struct_id(x: str) -> bool:
            x = x or ''
            return bool(re.match(r"^(?:.*__)?sheet(?:[-_])(?:call|outputs|inputs)", x))
        if _is_struct_id(ur) or _is_struct_id(vr):
            continue
        u = safe_map.get(ur, _safe(ur))
        # Map edges to end to END
        if vr in end_ids:
            v = 'END'
        else:
            v = safe_map.get(vr, _safe(vr))
        sp = e.get('sourcePortID')
        if sp:
            sp_lbl = str(sp).replace('"','\"')
            lines.append(f'{u} --|{sp_lbl}|--> {v}')
        else:
            lines.append(f'{u} --> {v}')
    return "\n".join(lines)


def _v2_safe_base_name(flow: dict) -> str:
    try:
        name = str((flow or {}).get('skillName') or 'skill')
    except Exception:
        name = 'skill'
    return re.sub(r'[^A-Za-z0-9_\-]+', '_', name)


def _v2_save_mermaid(tag: str, wf: dict, base_name: str):
    try:
        mer = _v2_build_mermaid(wf)
        out_mmd = f"{base_name}_v2_{tag}.mmd"
        with open(out_mmd, 'w', encoding='utf-8') as f:
            f.write(mer)
        logger.debug(f"[v2][mmd] saved {out_mmd}")
    except Exception as e:
        logger.debug(f"[v2][mmd] save failed: {e}")


def flowgram2langgraph_v2(flow: dict, bundle_json: Optional[dict] = None, enable_subgraph: bool = False, bp_mgr: Optional[BreakpointManager] = None):
    """
    v2 layered converter (flat mode for now). Same input/output signature as v1.
    We preprocess schema (flatten sheets, remove groups), then delegate to v1.
    """
    # Prepare sheets list like v1
    sheets: List[dict] = []
    base = flow
    b = (bundle_json or base.get('bundle') or {})
    if isinstance(b, dict) and isinstance(b.get('sheets'), list):
        for s in b['sheets']:
            name = s.get('name') or s.get('id')
            doc = s.get('document') or {}
            if isinstance(doc, dict) and 'nodes' in doc and 'edges' in doc:
                sheets.append({'name': str(name), 'workFlow': doc})
    if not sheets:
        # Single sheet fallback
        sheets.append({'name': base.get('sheetName', 'main'), 'workFlow': base.get('workFlow', {})})

    base_name = _v2_safe_base_name(flow)

    # Preprocess each sheet individually: remove groups, convert loops
    processed_sheets: List[dict] = []
    for s in sheets:
        sname = str(s.get('name'))
        wf0 = s.get('workFlow') or {}
        _v2_debug_workflow(f'original_sheet_{sname}', wf0, base_name)
        _v2_save_mermaid(f'original_sheet_{sname}', wf0, base_name)
        wf1 = _v2_remove_groups(wf0)
        _v2_debug_workflow(f'after_remove_groups_{sname}', wf1, base_name)
        _v2_save_mermaid(f'after_remove_groups_{sname}', wf1, base_name)
        wf2 = _v2_convert_loops(wf1)
        _v2_debug_workflow(f'after_convert_loops_{sname}', wf2, base_name)
        _v2_save_mermaid(f'after_convert_loops_{sname}', wf2, base_name)
        processed_sheets.append({'name': sname, 'workFlow': wf2})

    main_wf = processed_sheets[0].get('workFlow') or {}

    # Prepare secondary sheet entries for fallback rewiring (based on processed sheets)
    secondary_entries_qid: Dict[str, str] = {}
    if len(processed_sheets) > 1:
        for s in processed_sheets[1:]:
            sname = str(s.get('name'))
            swf = s.get('workFlow') or {}
            entry = _v2_find_sheet_entry(swf)
            if entry:
                secondary_entries_qid[sname] = f"{sname}__{entry}"

    # Stitch sheets after per-sheet preprocessing
    stitched, redirect_map = _v2_flatten_sheets(main_wf, processed_sheets)
    _v2_debug_workflow('after_flatten_sheets', stitched, base_name)
    _v2_save_mermaid('after_flatten_sheets', stitched, base_name)
    # Re-apply redirect map for any edges that still target structural nodes (e.g., else branch to sheet-outputs)
    rewired = []
    for e in (stitched.get('edges') or []):
        tgt = e.get('targetNodeID')
        if isinstance(redirect_map, dict) and tgt in redirect_map:
            ne = json.loads(json.dumps(e))
            ne['targetNodeID'] = redirect_map[tgt]
            rewired.append(ne)
        else:
            # Fallback: if there's exactly one secondary sheet entry, rewire to that entry
            if len(secondary_entries_qid) == 1:
                only_entry = next(iter(secondary_entries_qid.values()))
                # If target looks like a structural id (not mapped), redirect to the only entry
                try:
                    tgt_str = str(tgt or '')
                except Exception:
                    tgt_str = ''
                if re.match(r"^(?:.*__)?sheet(?:[-_])(?:call|outputs|inputs)", tgt_str):
                    ne = json.loads(json.dumps(e))
                    ne['targetNodeID'] = only_entry
                    rewired.append(ne)
                    continue
            rewired.append(e)
    # Drop any edges that still target structural nodes by id or pattern
    struct_ids_final = {str(n.get('id')) for n in (stitched.get('nodes') or []) if n.get('type') in ('sheet-call','sheet_call','sheet-outputs','sheet_outputs','sheet-inputs','sheet_inputs')}
    def _is_struct_id_final(x: str) -> bool:
        try:
            x = str(x or '')
        except Exception:
            x = ''
        return bool(re.match(r"^(?:.*__)?sheet(?:[-_])(?:call|outputs|inputs)", x))
    rewired = [e for e in rewired if (str(e.get('targetNodeID')) not in struct_ids_final and not _is_struct_id_final(e.get('targetNodeID')))]

    # Always remove any residual structural nodes to ensure flattened graph has no virtual sheet nodes
    nodes_no_struct = [n for n in (stitched.get('nodes') or []) if n.get('type') not in ('sheet-call','sheet_call','sheet-outputs','sheet_outputs','sheet-inputs','sheet_inputs')]
    stitched = {'nodes': nodes_no_struct, 'edges': rewired}
    _v2_debug_workflow('after_convert_loops', stitched, base_name)
    _v2_save_mermaid('after_convert_loops', stitched, base_name)

    # 2) Remove groups
    stitched = _v2_remove_groups(stitched)

    # 3) Convert loops: iteratively rewrite loop containers to flat graphs (handles nested loops)
    def _has_loops(wf: dict) -> bool:
        try:
            return any((n or {}).get('type') == 'loop' for n in (wf.get('nodes') or []))
        except Exception:
            return False
    max_iters = 10
    iters = 0
    while _has_loops(stitched) and iters < max_iters:
        stitched = _v2_convert_loops(stitched)
        iters += 1
    if _has_loops(stitched):
        logger.debug('[v2] loop conversion reached iteration cap; residual loop nodes may remain')

    # 4) Convert conditions (deferred to v1 for now)
    stitched = _v2_convert_conditions_schema_level(stitched)

    # Delegate to v1 by re-wrapping as a single-sheet flow
    new_flow = {
        **{k: v for k, v in flow.items() if k not in ('workFlow', 'bundle')},
        'workFlow': stitched,
    }
    logger.debug('[v2] Delegating to v1 after preprocessing (flat mode)')
    from agent.ec_skills.flowgram2langgraph import flowgram2langgraph as v1
    return v1(new_flow, bundle_json=None, bp_mgr=bp_mgr)
