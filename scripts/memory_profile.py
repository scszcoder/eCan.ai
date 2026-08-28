#!/usr/bin/env python3
"""
Memory Distribution Analyzer

使用方法:
    from scripts.memory_profile import analyze_memory
    
    # 分析内存分布
    analyze_memory()
    
    # 或导入到代码中
    from utils.memory_monitor import get_memory_monitor
    monitor = get_memory_monitor()
    monitor.dump_global_caches()  # 检查关键缓存
"""

import gc
import sys
import tracemalloc
import os
from collections import Counter
from typing import Dict, List, Any


def get_top_memory_allocations(top_n: int = 30) -> List[Dict]:
    """获取内存分配最多的代码位置"""
    if not tracemalloc.is_tracing():
        tracemalloc.start()
    
    snapshot = tracemalloc.take_snapshot()
    
    # 按内存大小排序
    top_stats = snapshot.statistics('lineno')
    
    results = []
    for stat in top_stats[:top_n]:
        results.append({
            'size_mb': stat.size / (1024 * 1024),
            'size_kb': stat.size / 1024,
            'count': stat.count,
            'location': str(stat.traceback)
        })
    
    return results


def get_object_type_distribution() -> List[Dict]:
    """获取内存中对象的类型分布"""
    gc.collect()
    objects = gc.get_objects()
    
    type_counter = Counter(type(obj).__name__ for obj in objects)
    total = len(objects)
    
    results = []
    for type_name, count in type_counter.most_common(50):
        size = 0
        try:
            for obj in objects:
                if type(obj).__name__ == type_name:
                    try:
                        size += sys.getsizeof(obj)
                    except:
                        pass
        except:
            pass
        
        results.append({
            'type': type_name,
            'count': count,
            'percentage': count / total * 100 if total > 0 else 0,
            'estimated_size_mb': size / (1024 * 1024)
        })
    
    return results


def get_global_variable_sizes() -> Dict[str, Dict]:
    """分析全局变量的大小"""
    sizes = {}
    
    # 分析主要模块
    modules_to_check = [
        'agent.ec_skills.build_node',
        'agent.ec_skills.browser_node.runner',
        'agent.ec_skills.browser_node.session',
        'agent.ec_skills.browser_node.build_helpers',
        'agent.mcp.server.chat_utils.chat_tools',
        'agent.ec_tasks.runner',
        'gui.MainGUI',
    ]
    
    for module_name in modules_to_check:
        try:
            parts = module_name.split('.')
            obj = __import__(module_name, fromlist=parts)
            
            module_vars = {}
            for name in dir(obj):
                if not name.startswith('__'):
                    try:
                        var = getattr(obj, name)
                        var_size = sys.getsizeof(var)
                        
                        # 对于容器类型，估算内容大小
                        if isinstance(var, (dict, list, set, tuple)):
                            try:
                                content_size = sum(sys.getsizeof(x) for x in var)
                                var_size = max(var_size, content_size)
                            except:
                                pass
                        
                        if var_size > 1024 * 100:  # > 100KB
                            module_vars[name] = {
                                'size_kb': var_size / 1024,
                                'type': type(var).__name__,
                                'len': len(var) if hasattr(var, '__len__') else None
                            }
                    except:
                        pass
            
            sizes[module_name] = module_vars
        except Exception as e:
            sizes[module_name] = {'error': str(e)}
    
    return sizes


def get_cache_sizes() -> Dict[str, Any]:
    """检查所有关键缓存的大小"""
    caches = {}
    
    # build_node.py 中的缓存
    try:
        from agent.ec_skills.build_node import (
            _PEND_GLOBAL_SENT,
            _first_invocation_done,
            _dispatch_state_by_agent,
            _dispatch_inflight,
            _last_known_agent_id_by_node,
            _cached_passive_agents,
        )
        caches['build_node._PEND_GLOBAL_SENT'] = len(_PEND_GLOBAL_SENT)
        caches['build_node._first_invocation_done'] = len(_first_invocation_done)
        caches['build_node._dispatch_state_by_agent'] = len(_dispatch_state_by_agent)
        caches['build_node._dispatch_inflight'] = len(_dispatch_inflight)
        caches['build_node._last_known_agent_id_by_node'] = len(_last_known_agent_id_by_node)
        caches['build_node._cached_passive_agents'] = len(_cached_passive_agents)
    except Exception as e:
        caches['build_node'] = {'error': str(e)}
    
    # chat_tools.py 中的缓存
    try:
        from agent.mcp.server.chat_utils.chat_tools import (
            _sender_dispatch_state,
            _send_chat_response_dedup,
            _qa_response_pending_lock,
        )
        caches['chat_tools._sender_dispatch_state'] = len(_sender_dispatch_state)
        caches['chat_tools._send_chat_response_dedup'] = len(_send_chat_response_dedup)
        caches['chat_tools._qa_response_pending_lock'] = len(_qa_response_pending_lock)
    except Exception as e:
        caches['chat_tools'] = {'error': str(e)}
    
    # build_helpers.py 中的缓存
    try:
        from agent.ec_skills.browser_node.build_helpers import (
            cached_bu_agents,
            cached_browser_sessions,
            _cached_bu_agents_insertion_order,
        )
        caches['build_helpers.cached_bu_agents'] = len(cached_bu_agents)
        caches['build_helpers.cached_browser_sessions'] = len(cached_browser_sessions)
        caches['build_helpers._cached_bu_agents_insertion_order'] = len(_cached_bu_agents_insertion_order)
    except Exception as e:
        caches['build_helpers'] = {'error': str(e)}
    
    # session.py 中的缓存
    try:
        from agent.ec_skills.browser_node.session import _cached_passive_agents as session_cached_passive
        caches['session._cached_passive_agents'] = len(session_cached_passive)
    except Exception as e:
        caches['session'] = {'error': str(e)}
    
    # event_monitor.py 中的缓存
    try:
        from agent.ec_skills.browser_use_extension.event_monitor import (
            _COLDSTART_SCAN_TASKS,
            _WS_DIRECT_DISPATCH_TASKS,
        )
        caches['event_monitor._COLDSTART_SCAN_TASKS'] = len(_COLDSTART_SCAN_TASKS)
        caches['event_monitor._WS_DIRECT_DISPATCH_TASKS'] = len(_WS_DIRECT_DISPATCH_TASKS)
    except Exception as e:
        caches['event_monitor'] = {'error': str(e)}
    
    return caches


def get_rss_and_memory_info() -> Dict:
    """获取进程的 RSS 和内存信息"""
    import psutil
    
    process = psutil.Process(os.getpid())
    mem_info = process.memory_info()
    
    return {
        'rss_mb': mem_info.rss / (1024 * 1024),
        'vms_mb': mem_info.vms / (1024 * 1024),
        'num_threads': process.num_threads(),
        'num_fds': process.num_fds() if hasattr(process, 'num_fds') else 'N/A',
    }


def analyze_memory():
    """执行完整的内存分析"""
    print("=" * 80)
    print("                    内存分布分析报告")
    print("=" * 80)
    
    # 1. 基础内存信息
    print("\n## 1. 进程基础信息")
    print("-" * 40)
    mem_info = get_rss_and_memory_info()
    for key, value in mem_info.items():
        print(f"  {key}: {value}")
    
    # 2. 缓存大小分析
    print("\n## 2. 关键缓存大小")
    print("-" * 40)
    caches = get_cache_sizes()
    total_cache_items = 0
    for name, size in sorted(caches.items(), key=lambda x: str(x[1]) if isinstance(x[1], (int, float)) else 0, reverse=True):
        if isinstance(size, int):
            total_cache_items += size
            # 高亮显示可能有问题的缓存
            if 'pending' in name.lower() and size > 1000:
                print(f"  ⚠️  {name}: {size} (可能过多!)")
            elif 'agent' in name.lower() and 'bu_agent' in name.lower() and size > 4:
                print(f"  ⚠️  {name}: {size} (可能过多! 每个约860MB)")
            else:
                print(f"  ✅ {name}: {size}")
        else:
            print(f"  ❌ {name}: {size}")
    print(f"\n  总缓存条目数: {total_cache_items}")
    
    # 3. 对象类型分布
    print("\n## 3. 对象类型分布 (Top 20)")
    print("-" * 40)
    obj_types = get_object_type_distribution()
    for i, obj in enumerate(obj_types[:20]):
        print(f"  {i+1:2d}. {obj['type']:30s} {obj['count']:>8d} 个 ({obj['percentage']:>5.1f}%)")
    
    # 4. 内存分配热点
    print("\n## 4. 内存分配热点 (Top 15)")
    print("-" * 40)
    allocations = get_top_memory_allocations(15)
    for i, alloc in enumerate(allocations):
        print(f"  {i+1:2d}. {alloc['size_kb']:>8.1f} KB x {alloc['count']:>6d} 位置: {alloc['location'][:60]}...")
    
    # 5. 全局变量分析
    print("\n## 5. 大型全局变量 (>100KB)")
    print("-" * 40)
    global_sizes = get_global_variable_sizes()
    for module, vars in global_sizes.items():
        large_vars = {k: v for k, v in vars.items() if isinstance(v, dict) and v.get('size_kb', 0) > 100}
        if large_vars:
            print(f"  模块: {module}")
            for name, info in sorted(large_vars.items(), key=lambda x: x[1].get('size_kb', 0), reverse=True):
                print(f"    - {name}: {info['size_kb']:.1f} KB ({info['type']}, len={info['len']})")
    
    # 6. 总结和建议
    print("\n" + "=" * 80)
    print("                    分析总结")
    print("=" * 80)
    
    # 检查潜在问题
    issues = []
    
    # 检查缓存大小
    if caches.get('build_node._PEND_GLOBAL_SENT', 0) > 1000:
        issues.append("⚠️  _PEND_GLOBAL_SENT 超过 1000 条，可能需要清理")
    
    if caches.get('build_helpers.cached_bu_agents', 0) > 4:
        issues.append(f"⚠️  cached_bu_agents 有 {caches['build_helpers.cached_bu_agents']} 个实例，每个约 860MB，总计约 {caches['build_helpers.cached_bu_agents'] * 860}MB!")
    
    if caches.get('event_monitor._COLDSTART_SCAN_TASKS', 0) > 10:
        issues.append(f"⚠️  _COLDSTART_SCAN_TASKS 有 {caches['event_monitor._COLDSTART_SCAN_TASKS']} 个任务，可能未正常清理")
    
    if caches.get('event_monitor._WS_DIRECT_DISPATCH_TASKS', 0) > 50:
        issues.append(f"⚠️  _WS_DIRECT_DISPATCH_TASKS 有 {caches['event_monitor._WS_DIRECT_DISPATCH_TASKS']} 个任务，可能未正常清理")
    
    # 检查对象数量
    dict_count = next((o for o in obj_types if o['type'] == 'dict'), None)
    if dict_count and dict_count['count'] > 100000:
        issues.append(f"⚠️  dict 对象过多 ({dict_count['count']}), 可能存在字典泄漏")
    
    if issues:
        print("\n发现的问题:")
        for issue in issues:
            print(f"  {issue}")
    else:
        print("\n✅ 未发现明显的内存泄漏问题")
    
    print(f"\n进程总内存: {mem_info['rss_mb']:.1f} MB")
    print("=" * 80)


if __name__ == '__main__':
    analyze_memory()
