"""
Azure Cost Monitor and Emergency Shutdown MCP Tools

This module provides MCP tools for:
1. azure_read_billing - Read detailed Azure billing information
2. azure_shutdown - Emergency shutdown of Azure services to prevent runaway costs

Targeted services:
- Virtual Machines (VMs)
- Azure Kubernetes Service (AKS)
- Azure Container Instances (ACI)
- Azure Machine Learning (compute instances, endpoints)
- Azure Functions
- Azure App Service
- Azure SQL Database
- Azure Cosmos DB
- Azure Storage
- Azure Event Hubs
- Azure Service Bus
- Azure API Management
- Azure Logic Apps
- Azure Data Factory
- Azure Synapse Analytics
- Azure Cognitive Services
"""

import os
import json
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
import mcp.types as types
from mcp.types import CallToolResult, TextContent
from utils.logger_helper import logger_helper as logger
from utils.logger_helper import get_traceback

try:
    from azure.identity import DefaultAzureCredential, ClientSecretCredential
    from azure.mgmt.compute import ComputeManagementClient
    from azure.mgmt.containerinstance import ContainerInstanceManagementClient
    from azure.mgmt.containerservice import ContainerServiceClient
    from azure.mgmt.web import WebSiteManagementClient
    from azure.mgmt.sql import SqlManagementClient
    from azure.mgmt.cosmosdb import CosmosDBManagementClient
    from azure.mgmt.storage import StorageManagementClient
    from azure.mgmt.eventhub import EventHubManagementClient
    from azure.mgmt.servicebus import ServiceBusManagementClient
    from azure.mgmt.apimanagement import ApiManagementClient
    from azure.mgmt.logic import LogicManagementClient
    from azure.mgmt.datafactory import DataFactoryManagementClient
    from azure.mgmt.machinelearningservices import AzureMachineLearningWorkspaces
    from azure.mgmt.resource import ResourceManagementClient, SubscriptionClient
    from azure.mgmt.costmanagement import CostManagementClient
    AZURE_SDK_AVAILABLE = True
except ImportError:
    AZURE_SDK_AVAILABLE = False
    logger.warning("[AZURE_TOOLS] Azure SDK not installed. Azure tools will not function.")


# ============================================================================
# Helper Functions
# ============================================================================

def get_azure_credential(tenant_id: str = None, client_id: str = None, client_secret: str = None):
    """Get Azure credential - either from service principal or default credential chain."""
    if not AZURE_SDK_AVAILABLE:
        return None
    try:
        if tenant_id and client_id and client_secret:
            return ClientSecretCredential(
                tenant_id=tenant_id,
                client_id=client_id,
                client_secret=client_secret
            )
        return DefaultAzureCredential()
    except Exception as e:
        logger.error(f"[AZURE_TOOLS] Failed to get Azure credential: {e}")
        return None


def get_subscriptions(credential) -> List[Dict[str, str]]:
    """Get all Azure subscriptions accessible with the credential."""
    try:
        sub_client = SubscriptionClient(credential)
        subscriptions = []
        for sub in sub_client.subscriptions.list():
            subscriptions.append({
                'subscription_id': sub.subscription_id,
                'display_name': sub.display_name,
                'state': sub.state
            })
        return subscriptions
    except Exception as e:
        logger.error(f"[AZURE_TOOLS] Failed to get subscriptions: {e}")
        return []


def get_resource_groups(credential, subscription_id: str) -> List[str]:
    """Get all resource groups in a subscription."""
    try:
        resource_client = ResourceManagementClient(credential, subscription_id)
        return [rg.name for rg in resource_client.resource_groups.list()]
    except Exception as e:
        logger.error(f"[AZURE_TOOLS] Failed to get resource groups: {e}")
        return []


# ============================================================================
# Billing Functions
# ============================================================================

def read_azure_cost_data(credential, subscription_id: str, days: int = 30) -> Dict[str, Any]:
    """Read cost data from Azure Cost Management."""
    try:
        cost_client = CostManagementClient(credential)
        
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=days)
        
        scope = f"/subscriptions/{subscription_id}"
        
        # Query cost by service
        query_result = cost_client.query.usage(
            scope=scope,
            parameters={
                "type": "ActualCost",
                "timeframe": "Custom",
                "timePeriod": {
                    "from": start_date.strftime('%Y-%m-%dT00:00:00Z'),
                    "to": end_date.strftime('%Y-%m-%dT23:59:59Z')
                },
                "dataset": {
                    "granularity": "Daily",
                    "aggregation": {
                        "totalCost": {
                            "name": "Cost",
                            "function": "Sum"
                        }
                    },
                    "grouping": [
                        {
                            "type": "Dimension",
                            "name": "ServiceName"
                        }
                    ]
                }
            }
        )
        
        # Parse results
        costs_by_service = {}
        daily_costs = []
        
        if query_result.rows:
            for row in query_result.rows:
                # Row format: [cost, date, service_name, currency]
                cost = float(row[0]) if row[0] else 0.0
                service = row[2] if len(row) > 2 else "Unknown"
                
                if service not in costs_by_service:
                    costs_by_service[service] = 0.0
                costs_by_service[service] += cost
        
        return {
            'success': True,
            'subscription_id': subscription_id,
            'period': f"{start_date} to {end_date}",
            'total_cost': sum(costs_by_service.values()),
            'costs_by_service': dict(sorted(costs_by_service.items(), key=lambda x: x[1], reverse=True)),
            'currency': 'USD'
        }
        
    except Exception as e:
        return {'success': False, 'error': str(e)}


def read_azure_budgets(credential, subscription_id: str) -> Dict[str, Any]:
    """Read Azure budgets."""
    try:
        cost_client = CostManagementClient(credential)
        scope = f"/subscriptions/{subscription_id}"
        
        budgets = cost_client.budgets.list(scope=scope)
        
        budget_list = []
        for budget in budgets:
            budget_list.append({
                'name': budget.name,
                'amount': float(budget.amount),
                'time_grain': budget.time_grain,
                'current_spend': float(budget.current_spend.amount) if budget.current_spend else 0,
            })
        
        return {'success': True, 'budgets': budget_list}
    except Exception as e:
        return {'success': False, 'error': str(e)}


# ============================================================================
# Shutdown Functions for Each Service
# ============================================================================

def shutdown_azure_vms(credential, subscription_id: str, resource_groups: List[str] = None, 
                       dry_run: bool = False) -> Dict[str, Any]:
    """Stop/deallocate all Azure VMs."""
    results = {'stopped': [], 'errors': []}
    
    try:
        compute_client = ComputeManagementClient(credential, subscription_id)
        
        if resource_groups:
            vms = []
            for rg in resource_groups:
                vms.extend(list(compute_client.virtual_machines.list(rg)))
        else:
            vms = list(compute_client.virtual_machines.list_all())
        
        for vm in vms:
            # Extract resource group from VM ID
            rg_name = vm.id.split('/')[4]
            vm_name = vm.name
            
            # Get power state
            instance_view = compute_client.virtual_machines.instance_view(rg_name, vm_name)
            power_state = None
            for status in instance_view.statuses:
                if status.code.startswith('PowerState/'):
                    power_state = status.code.split('/')[-1]
                    break
            
            if power_state == 'running':
                if dry_run:
                    results['stopped'].append({
                        'subscription': subscription_id,
                        'resource_group': rg_name,
                        'service': 'Virtual Machine',
                        'resource': vm_name,
                        'action': 'would_deallocate',
                        'dry_run': True
                    })
                else:
                    # Deallocate (stop and release compute resources)
                    compute_client.virtual_machines.begin_deallocate(rg_name, vm_name)
                    results['stopped'].append({
                        'subscription': subscription_id,
                        'resource_group': rg_name,
                        'service': 'Virtual Machine',
                        'resource': vm_name,
                        'action': 'deallocating'
                    })
                    logger.info(f"[AZURE_TOOLS] Deallocating VM: {vm_name} in {rg_name}")
                    
    except Exception as e:
        results['errors'].append({'service': 'Virtual Machines', 'error': str(e)})
    
    return results


def shutdown_azure_aks(credential, subscription_id: str, resource_groups: List[str] = None,
                       dry_run: bool = False) -> Dict[str, Any]:
    """Stop AKS clusters."""
    results = {'stopped': [], 'errors': []}
    
    try:
        aks_client = ContainerServiceClient(credential, subscription_id)
        
        if resource_groups:
            clusters = []
            for rg in resource_groups:
                clusters.extend(list(aks_client.managed_clusters.list_by_resource_group(rg)))
        else:
            clusters = list(aks_client.managed_clusters.list())
        
        for cluster in clusters:
            rg_name = cluster.id.split('/')[4]
            cluster_name = cluster.name
            
            if cluster.power_state and cluster.power_state.code == 'Running':
                if dry_run:
                    results['stopped'].append({
                        'subscription': subscription_id,
                        'resource_group': rg_name,
                        'service': 'AKS Cluster',
                        'resource': cluster_name,
                        'action': 'would_stop',
                        'dry_run': True
                    })
                else:
                    aks_client.managed_clusters.begin_stop(rg_name, cluster_name)
                    results['stopped'].append({
                        'subscription': subscription_id,
                        'resource_group': rg_name,
                        'service': 'AKS Cluster',
                        'resource': cluster_name,
                        'action': 'stopping'
                    })
                    logger.info(f"[AZURE_TOOLS] Stopping AKS cluster: {cluster_name}")
                    
    except Exception as e:
        results['errors'].append({'service': 'AKS', 'error': str(e)})
    
    return results


def shutdown_azure_container_instances(credential, subscription_id: str, resource_groups: List[str] = None,
                                        dry_run: bool = False) -> Dict[str, Any]:
    """Stop Azure Container Instances."""
    results = {'stopped': [], 'errors': []}
    
    try:
        aci_client = ContainerInstanceManagementClient(credential, subscription_id)
        
        if resource_groups:
            container_groups = []
            for rg in resource_groups:
                container_groups.extend(list(aci_client.container_groups.list_by_resource_group(rg)))
        else:
            container_groups = list(aci_client.container_groups.list())
        
        for cg in container_groups:
            rg_name = cg.id.split('/')[4]
            cg_name = cg.name
            
            if dry_run:
                results['stopped'].append({
                    'subscription': subscription_id,
                    'resource_group': rg_name,
                    'service': 'Container Instance',
                    'resource': cg_name,
                    'action': 'would_stop',
                    'dry_run': True
                })
            else:
                aci_client.container_groups.stop(rg_name, cg_name)
                results['stopped'].append({
                    'subscription': subscription_id,
                    'resource_group': rg_name,
                    'service': 'Container Instance',
                    'resource': cg_name,
                    'action': 'stopped'
                })
                logger.info(f"[AZURE_TOOLS] Stopped container instance: {cg_name}")
                
    except Exception as e:
        results['errors'].append({'service': 'Container Instances', 'error': str(e)})
    
    return results


def shutdown_azure_app_services(credential, subscription_id: str, resource_groups: List[str] = None,
                                 dry_run: bool = False) -> Dict[str, Any]:
    """Stop Azure App Services (Web Apps, Function Apps)."""
    results = {'stopped': [], 'errors': []}
    
    try:
        web_client = WebSiteManagementClient(credential, subscription_id)
        
        if resource_groups:
            apps = []
            for rg in resource_groups:
                apps.extend(list(web_client.web_apps.list_by_resource_group(rg)))
        else:
            apps = list(web_client.web_apps.list())
        
        for app in apps:
            rg_name = app.id.split('/')[4]
            app_name = app.name
            
            if app.state == 'Running':
                if dry_run:
                    results['stopped'].append({
                        'subscription': subscription_id,
                        'resource_group': rg_name,
                        'service': 'App Service',
                        'resource': app_name,
                        'kind': app.kind,
                        'action': 'would_stop',
                        'dry_run': True
                    })
                else:
                    web_client.web_apps.stop(rg_name, app_name)
                    results['stopped'].append({
                        'subscription': subscription_id,
                        'resource_group': rg_name,
                        'service': 'App Service',
                        'resource': app_name,
                        'kind': app.kind,
                        'action': 'stopped'
                    })
                    logger.info(f"[AZURE_TOOLS] Stopped App Service: {app_name}")
                    
    except Exception as e:
        results['errors'].append({'service': 'App Services', 'error': str(e)})
    
    return results


def shutdown_azure_sql(credential, subscription_id: str, resource_groups: List[str] = None,
                       dry_run: bool = False) -> Dict[str, Any]:
    """Pause Azure SQL databases (only works for Data Warehouse/Synapse)."""
    results = {'stopped': [], 'errors': []}
    
    try:
        sql_client = SqlManagementClient(credential, subscription_id)
        
        # List all SQL servers
        if resource_groups:
            servers = []
            for rg in resource_groups:
                servers.extend(list(sql_client.servers.list_by_resource_group(rg)))
        else:
            servers = list(sql_client.servers.list())
        
        for server in servers:
            rg_name = server.id.split('/')[4]
            server_name = server.name
            
            # List databases in server
            databases = sql_client.databases.list_by_server(rg_name, server_name)
            
            for db in databases:
                if db.name == 'master':
                    continue
                    
                # Note: Only Data Warehouse SKUs can be paused
                if db.sku and 'DW' in (db.sku.name or ''):
                    if dry_run:
                        results['stopped'].append({
                            'subscription': subscription_id,
                            'resource_group': rg_name,
                            'service': 'SQL Data Warehouse',
                            'resource': f"{server_name}/{db.name}",
                            'action': 'would_pause',
                            'dry_run': True
                        })
                    else:
                        sql_client.databases.begin_pause(rg_name, server_name, db.name)
                        results['stopped'].append({
                            'subscription': subscription_id,
                            'resource_group': rg_name,
                            'service': 'SQL Data Warehouse',
                            'resource': f"{server_name}/{db.name}",
                            'action': 'pausing'
                        })
                        logger.info(f"[AZURE_TOOLS] Pausing SQL DW: {server_name}/{db.name}")
                else:
                    # Regular SQL DBs can't be paused, note them
                    if dry_run:
                        results['stopped'].append({
                            'subscription': subscription_id,
                            'resource_group': rg_name,
                            'service': 'SQL Database',
                            'resource': f"{server_name}/{db.name}",
                            'action': 'cannot_pause (not DW SKU)',
                            'dry_run': True
                        })
                        
    except Exception as e:
        results['errors'].append({'service': 'SQL', 'error': str(e)})
    
    return results


def shutdown_azure_cosmosdb(credential, subscription_id: str, resource_groups: List[str] = None,
                            dry_run: bool = False) -> Dict[str, Any]:
    """Reduce Cosmos DB throughput to minimum."""
    results = {'stopped': [], 'errors': []}
    
    try:
        cosmos_client = CosmosDBManagementClient(credential, subscription_id)
        
        if resource_groups:
            accounts = []
            for rg in resource_groups:
                accounts.extend(list(cosmos_client.database_accounts.list_by_resource_group(rg)))
        else:
            accounts = list(cosmos_client.database_accounts.list())
        
        for account in accounts:
            rg_name = account.id.split('/')[4]
            account_name = account.name
            
            if dry_run:
                results['stopped'].append({
                    'subscription': subscription_id,
                    'resource_group': rg_name,
                    'service': 'Cosmos DB',
                    'resource': account_name,
                    'action': 'would_reduce_throughput',
                    'dry_run': True,
                    'note': 'Cannot fully stop Cosmos DB, would reduce throughput to minimum'
                })
            else:
                # Note: Cosmos DB can't be stopped, but throughput can be reduced
                # This requires iterating through databases and containers
                results['stopped'].append({
                    'subscription': subscription_id,
                    'resource_group': rg_name,
                    'service': 'Cosmos DB',
                    'resource': account_name,
                    'action': 'noted (manual throughput reduction recommended)',
                    'note': 'Cosmos DB cannot be stopped. Reduce throughput manually.'
                })
                logger.info(f"[AZURE_TOOLS] Cosmos DB {account_name} noted for manual throughput reduction")
                
    except Exception as e:
        results['errors'].append({'service': 'Cosmos DB', 'error': str(e)})
    
    return results


def shutdown_azure_ml(credential, subscription_id: str, resource_groups: List[str] = None,
                      dry_run: bool = False) -> Dict[str, Any]:
    """Stop Azure ML compute instances and delete online endpoints."""
    results = {'stopped': [], 'errors': []}
    
    try:
        ml_client = AzureMachineLearningWorkspaces(credential, subscription_id)
        
        # List workspaces
        if resource_groups:
            workspaces = []
            for rg in resource_groups:
                workspaces.extend(list(ml_client.workspaces.list_by_resource_group(rg)))
        else:
            workspaces = list(ml_client.workspaces.list_by_subscription())
        
        for ws in workspaces:
            rg_name = ws.id.split('/')[4]
            ws_name = ws.name
            
            # List compute instances
            try:
                computes = ml_client.compute.list(rg_name, ws_name)
                for compute in computes:
                    if compute.properties and hasattr(compute.properties, 'compute_type'):
                        if compute.properties.compute_type == 'ComputeInstance':
                            if dry_run:
                                results['stopped'].append({
                                    'subscription': subscription_id,
                                    'resource_group': rg_name,
                                    'service': 'ML Compute Instance',
                                    'resource': f"{ws_name}/{compute.name}",
                                    'action': 'would_stop',
                                    'dry_run': True
                                })
                            else:
                                ml_client.compute.begin_stop(rg_name, ws_name, compute.name)
                                results['stopped'].append({
                                    'subscription': subscription_id,
                                    'resource_group': rg_name,
                                    'service': 'ML Compute Instance',
                                    'resource': f"{ws_name}/{compute.name}",
                                    'action': 'stopping'
                                })
                                logger.info(f"[AZURE_TOOLS] Stopping ML compute: {ws_name}/{compute.name}")
            except Exception as ce:
                logger.debug(f"[AZURE_TOOLS] Error listing ML computes: {ce}")
                
    except Exception as e:
        results['errors'].append({'service': 'Azure ML', 'error': str(e)})
    
    return results


def shutdown_azure_event_hubs(credential, subscription_id: str, resource_groups: List[str] = None,
                               dry_run: bool = False) -> Dict[str, Any]:
    """Disable Event Hubs (can't fully stop, but can disable)."""
    results = {'stopped': [], 'errors': []}
    
    try:
        eh_client = EventHubManagementClient(credential, subscription_id)
        
        if resource_groups:
            namespaces = []
            for rg in resource_groups:
                namespaces.extend(list(eh_client.namespaces.list_by_resource_group(rg)))
        else:
            namespaces = list(eh_client.namespaces.list())
        
        for ns in namespaces:
            rg_name = ns.id.split('/')[4]
            ns_name = ns.name
            
            if dry_run:
                results['stopped'].append({
                    'subscription': subscription_id,
                    'resource_group': rg_name,
                    'service': 'Event Hub Namespace',
                    'resource': ns_name,
                    'action': 'would_disable_auto_inflate',
                    'dry_run': True
                })
            else:
                # Disable auto-inflate to prevent scaling
                eh_client.namespaces.update(
                    rg_name, ns_name,
                    {'is_auto_inflate_enabled': False, 'maximum_throughput_units': 0}
                )
                results['stopped'].append({
                    'subscription': subscription_id,
                    'resource_group': rg_name,
                    'service': 'Event Hub Namespace',
                    'resource': ns_name,
                    'action': 'auto_inflate_disabled'
                })
                logger.info(f"[AZURE_TOOLS] Disabled auto-inflate for Event Hub: {ns_name}")
                
    except Exception as e:
        results['errors'].append({'service': 'Event Hubs', 'error': str(e)})
    
    return results


def shutdown_azure_service_bus(credential, subscription_id: str, resource_groups: List[str] = None,
                                dry_run: bool = False) -> Dict[str, Any]:
    """Note Service Bus namespaces (can't be stopped)."""
    results = {'stopped': [], 'errors': []}
    
    try:
        sb_client = ServiceBusManagementClient(credential, subscription_id)
        
        if resource_groups:
            namespaces = []
            for rg in resource_groups:
                namespaces.extend(list(sb_client.namespaces.list_by_resource_group(rg)))
        else:
            namespaces = list(sb_client.namespaces.list())
        
        for ns in namespaces:
            rg_name = ns.id.split('/')[4]
            ns_name = ns.name
            
            results['stopped'].append({
                'subscription': subscription_id,
                'resource_group': rg_name,
                'service': 'Service Bus',
                'resource': ns_name,
                'action': 'noted (cannot be stopped)',
                'dry_run': dry_run,
                'note': 'Service Bus cannot be stopped. Consider deleting if not needed.'
            })
            
    except Exception as e:
        results['errors'].append({'service': 'Service Bus', 'error': str(e)})
    
    return results


def shutdown_azure_logic_apps(credential, subscription_id: str, resource_groups: List[str] = None,
                               dry_run: bool = False) -> Dict[str, Any]:
    """Disable Azure Logic Apps."""
    results = {'stopped': [], 'errors': []}
    
    try:
        logic_client = LogicManagementClient(credential, subscription_id)
        
        if resource_groups:
            workflows = []
            for rg in resource_groups:
                workflows.extend(list(logic_client.workflows.list_by_resource_group(rg)))
        else:
            workflows = list(logic_client.workflows.list_by_subscription())
        
        for workflow in workflows:
            rg_name = workflow.id.split('/')[4]
            workflow_name = workflow.name
            
            if workflow.state == 'Enabled':
                if dry_run:
                    results['stopped'].append({
                        'subscription': subscription_id,
                        'resource_group': rg_name,
                        'service': 'Logic App',
                        'resource': workflow_name,
                        'action': 'would_disable',
                        'dry_run': True
                    })
                else:
                    logic_client.workflows.disable(rg_name, workflow_name)
                    results['stopped'].append({
                        'subscription': subscription_id,
                        'resource_group': rg_name,
                        'service': 'Logic App',
                        'resource': workflow_name,
                        'action': 'disabled'
                    })
                    logger.info(f"[AZURE_TOOLS] Disabled Logic App: {workflow_name}")
                    
    except Exception as e:
        results['errors'].append({'service': 'Logic Apps', 'error': str(e)})
    
    return results


def shutdown_azure_data_factory(credential, subscription_id: str, resource_groups: List[str] = None,
                                 dry_run: bool = False) -> Dict[str, Any]:
    """Stop Azure Data Factory triggers."""
    results = {'stopped': [], 'errors': []}
    
    try:
        adf_client = DataFactoryManagementClient(credential, subscription_id)
        
        if resource_groups:
            factories = []
            for rg in resource_groups:
                factories.extend(list(adf_client.factories.list_by_resource_group(rg)))
        else:
            factories = list(adf_client.factories.list())
        
        for factory in factories:
            rg_name = factory.id.split('/')[4]
            factory_name = factory.name
            
            # Stop all triggers
            try:
                triggers = adf_client.triggers.list_by_factory(rg_name, factory_name)
                for trigger in triggers:
                    if trigger.properties and trigger.properties.runtime_state == 'Started':
                        if dry_run:
                            results['stopped'].append({
                                'subscription': subscription_id,
                                'resource_group': rg_name,
                                'service': 'Data Factory Trigger',
                                'resource': f"{factory_name}/{trigger.name}",
                                'action': 'would_stop',
                                'dry_run': True
                            })
                        else:
                            adf_client.triggers.begin_stop(rg_name, factory_name, trigger.name)
                            results['stopped'].append({
                                'subscription': subscription_id,
                                'resource_group': rg_name,
                                'service': 'Data Factory Trigger',
                                'resource': f"{factory_name}/{trigger.name}",
                                'action': 'stopping'
                            })
                            logger.info(f"[AZURE_TOOLS] Stopping ADF trigger: {factory_name}/{trigger.name}")
            except Exception as te:
                logger.debug(f"[AZURE_TOOLS] Error stopping triggers: {te}")
                
    except Exception as e:
        results['errors'].append({'service': 'Data Factory', 'error': str(e)})
    
    return results


def shutdown_azure_api_management(credential, subscription_id: str, resource_groups: List[str] = None,
                                   dry_run: bool = False) -> Dict[str, Any]:
    """Note API Management services (expensive but can't be easily stopped)."""
    results = {'stopped': [], 'errors': []}
    
    try:
        apim_client = ApiManagementClient(credential, subscription_id)
        
        if resource_groups:
            services = []
            for rg in resource_groups:
                services.extend(list(apim_client.api_management_service.list_by_resource_group(rg)))
        else:
            services = list(apim_client.api_management_service.list())
        
        for service in services:
            rg_name = service.id.split('/')[4]
            service_name = service.name
            
            results['stopped'].append({
                'subscription': subscription_id,
                'resource_group': rg_name,
                'service': 'API Management',
                'resource': service_name,
                'sku': service.sku.name if service.sku else 'Unknown',
                'action': 'noted (cannot be stopped)',
                'dry_run': dry_run,
                'note': 'APIM cannot be stopped. Consider downgrading SKU or deleting.'
            })
            
    except Exception as e:
        results['errors'].append({'service': 'API Management', 'error': str(e)})
    
    return results


# ============================================================================
# MCP Tool Functions
# ============================================================================

async def azure_read_billing(mainwin, args) -> List[TextContent]:
    """MCP tool to read Azure billing information."""
    try:
        if not AZURE_SDK_AVAILABLE:
            msg = "ERROR: Azure SDK not installed. Install with: pip install azure-identity azure-mgmt-costmanagement azure-mgmt-resource"
            logger.error(f"[MCP][AZURE_READ_BILLING]: {msg}")
            result = TextContent(type="text", text=msg)
            result.meta = {"success": False, "error": "azure_sdk_not_installed"}
            return [result]
        
        input_data = args.get("input", {})
        days = input_data.get("days", 30)
        subscription_id = input_data.get("subscription_id", None)
        tenant_id = input_data.get("tenant_id", None)
        client_id = input_data.get("client_id", None)
        client_secret = input_data.get("client_secret", None)
        
        logger.info(f"[MCP][AZURE_READ_BILLING]: Reading billing for last {days} days")
        
        credential = get_azure_credential(tenant_id, client_id, client_secret)
        if not credential:
            msg = "ERROR: Failed to get Azure credential. Check authentication."
            result = TextContent(type="text", text=msg)
            result.meta = {"success": False, "error": "credential_failed"}
            return [result]
        
        # Get subscriptions if not specified
        all_billing = {}
        if subscription_id:
            subscriptions = [{'subscription_id': subscription_id, 'display_name': 'Specified'}]
        else:
            subscriptions = get_subscriptions(credential)
        
        for sub in subscriptions:
            sub_id = sub['subscription_id']
            cost_data = read_azure_cost_data(credential, sub_id, days=days)
            budget_data = read_azure_budgets(credential, sub_id)
            
            all_billing[sub_id] = {
                'display_name': sub['display_name'],
                'cost_data': cost_data,
                'budgets': budget_data
            }
        
        # Compile summary
        total_cost = sum(
            b['cost_data'].get('total_cost', 0) 
            for b in all_billing.values() 
            if b['cost_data'].get('success')
        )
        
        msg = f"Azure Billing Summary ({days} days):\n"
        msg += f"  Total Cost: ${total_cost:.2f} USD\n"
        msg += f"  Subscriptions: {len(subscriptions)}\n"
        
        for sub_id, data in all_billing.items():
            if data['cost_data'].get('success'):
                sub_cost = data['cost_data'].get('total_cost', 0)
                msg += f"\n  {data['display_name']} ({sub_id[:8]}...): ${sub_cost:.2f}\n"
                top_services = list(data['cost_data'].get('costs_by_service', {}).items())[:3]
                for svc, cost in top_services:
                    msg += f"    - {svc}: ${cost:.2f}\n"
        
        result = TextContent(type="text", text=msg)
        result.meta = {"success": True, "billing_info": all_billing}
        
        logger.info(f"[MCP][AZURE_READ_BILLING]: Completed")
        return [result]
        
    except Exception as e:
        err_trace = get_traceback(e, "ErrorAzureReadBilling")
        logger.error(err_trace)
        result = TextContent(type="text", text=err_trace)
        result.meta = {"success": False}
        return [result]


async def azure_shutdown(mainwin, args) -> List[TextContent]:
    """MCP tool to emergency shutdown Azure services."""
    try:
        if not AZURE_SDK_AVAILABLE:
            msg = "ERROR: Azure SDK not installed. Install required packages."
            logger.error(f"[MCP][AZURE_SHUTDOWN]: {msg}")
            result = TextContent(type="text", text=msg)
            result.meta = {"success": False, "error": "azure_sdk_not_installed"}
            return [result]
        
        input_data = args.get("input", {})
        services = input_data.get("services", [])
        subscription_id = input_data.get("subscription_id", None)
        resource_groups = input_data.get("resource_groups", None)
        dry_run = input_data.get("dry_run", True)
        tenant_id = input_data.get("tenant_id", None)
        client_id = input_data.get("client_id", None)
        client_secret = input_data.get("client_secret", None)
        
        ALL_SERVICES = [
            'vms', 'aks', 'aci', 'app_services', 'sql', 'cosmosdb',
            'ml', 'event_hubs', 'service_bus', 'logic_apps', 
            'data_factory', 'api_management'
        ]
        
        if not services or services == ['all']:
            services = ALL_SERVICES
        
        logger.info(f"[MCP][AZURE_SHUTDOWN]: {'DRY RUN - ' if dry_run else ''}Shutting down: {services}")
        
        credential = get_azure_credential(tenant_id, client_id, client_secret)
        if not credential:
            msg = "ERROR: Failed to get Azure credential."
            result = TextContent(type="text", text=msg)
            result.meta = {"success": False, "error": "credential_failed"}
            return [result]
        
        # Get subscriptions
        if subscription_id:
            subscriptions = [subscription_id]
        else:
            subs = get_subscriptions(credential)
            subscriptions = [s['subscription_id'] for s in subs]
        
        all_results = {
            'dry_run': dry_run,
            'services_targeted': services,
            'subscriptions': subscriptions,
            'results': {}
        }
        
        service_handlers = {
            'vms': shutdown_azure_vms,
            'aks': shutdown_azure_aks,
            'aci': shutdown_azure_container_instances,
            'app_services': shutdown_azure_app_services,
            'sql': shutdown_azure_sql,
            'cosmosdb': shutdown_azure_cosmosdb,
            'ml': shutdown_azure_ml,
            'event_hubs': shutdown_azure_event_hubs,
            'service_bus': shutdown_azure_service_bus,
            'logic_apps': shutdown_azure_logic_apps,
            'data_factory': shutdown_azure_data_factory,
            'api_management': shutdown_azure_api_management,
        }
        
        for sub_id in subscriptions:
            all_results['results'][sub_id] = {}
            
            for service in services:
                service_lower = service.lower().replace('-', '_').replace(' ', '_')
                if service_lower in service_handlers:
                    handler = service_handlers[service_lower]
                    all_results['results'][sub_id][service_lower] = handler(
                        credential, sub_id, resource_groups, dry_run=dry_run
                    )
        
        # Compile summary
        total_stopped = 0
        total_errors = 0
        for sub_results in all_results['results'].values():
            for svc_result in sub_results.values():
                if isinstance(svc_result, dict):
                    total_stopped += len(svc_result.get('stopped', []))
                    total_errors += len(svc_result.get('errors', []))
        
        if dry_run:
            msg = f"🔍 DRY RUN - Azure Emergency Shutdown Preview:\n"
            msg += f"  Would affect {total_stopped} resources\n"
            msg += f"  Subscriptions: {len(subscriptions)}\n"
            msg += f"  ⚠️ Run with dry_run=false to execute\n"
        else:
            msg = f"🚨 Azure Emergency Shutdown Executed:\n"
            msg += f"  Stopped/Disabled: {total_stopped} resources\n"
            msg += f"  Errors: {total_errors}\n"
        
        result = TextContent(type="text", text=msg)
        result.meta = {
            "success": True,
            "dry_run": dry_run,
            "total_stopped": total_stopped,
            "total_errors": total_errors,
            "details": all_results
        }
        
        logger.info(f"[MCP][AZURE_SHUTDOWN]: Completed - {msg}")
        return [result]
        
    except Exception as e:
        err_trace = get_traceback(e, "ErrorAzureShutdown")
        logger.error(err_trace)
        result = TextContent(type="text", text=err_trace)
        result.meta = {"success": False}
        return [result]


# ============================================================================
# Schema Functions
# ============================================================================

def add_azure_read_billing_tool_schema(tool_schemas):
    """Add schema for azure_read_billing tool."""
    tool_schema = types.Tool(_meta={"run_in_cloud": False},
        name="azure_read_billing",
        description="<category>Azure</category><sub-category>Cost Management</sub-category>Read detailed Azure billing information including costs by service and budget status. Requires Azure credentials.",
        inputSchema={
            "type": "object",
            "required": ["input"],
            "properties": {
                "input": {
                    "type": "object",
                    "required": [],
                    "properties": {
                        "days": {
                            "type": "integer",
                            "description": "Number of days to look back for billing data (default: 30)",
                            "default": 30
                        },
                        "subscription_id": {
                            "type": "string",
                            "description": "Azure subscription ID (optional, queries all accessible subscriptions if not specified)"
                        },
                        "tenant_id": {
                            "type": "string",
                            "description": "Azure AD tenant ID for service principal auth (optional)"
                        },
                        "client_id": {
                            "type": "string",
                            "description": "Azure AD client/app ID for service principal auth (optional)"
                        },
                        "client_secret": {
                            "type": "string",
                            "description": "Azure AD client secret for service principal auth (optional)"
                        }
                    }
                }
            }
        }
    )
    tool_schemas.append(tool_schema)


def add_azure_shutdown_tool_schema(tool_schemas):
    """Add schema for azure_shutdown tool."""
    tool_schema = types.Tool(_meta={"run_in_cloud": False},
        name="azure_shutdown",
        description="""<category>Azure</category><sub-category>Cost Management</sub-category>Emergency shutdown of Azure services to prevent runaway costs.

SUPPORTED SERVICES:
- vms: Deallocate Virtual Machines
- aks: Stop AKS clusters
- aci: Stop Container Instances
- app_services: Stop App Services (Web Apps, Functions)
- sql: Pause SQL Data Warehouses
- cosmosdb: Note Cosmos DB (manual throughput reduction)
- ml: Stop ML compute instances
- event_hubs: Disable auto-inflate
- service_bus: Note Service Bus namespaces
- logic_apps: Disable Logic Apps
- data_factory: Stop Data Factory triggers
- api_management: Note APIM services

⚠️ CAUTION: This tool can cause service disruption. Use dry_run=true first!""",
        inputSchema={
            "type": "object",
            "required": ["input"],
            "properties": {
                "input": {
                    "type": "object",
                    "required": [],
                    "properties": {
                        "services": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of services to shutdown. Use ['all'] for all services."
                        },
                        "subscription_id": {
                            "type": "string",
                            "description": "Azure subscription ID (optional, targets all if not specified)"
                        },
                        "resource_groups": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of resource groups to target (optional, targets all if not specified)"
                        },
                        "dry_run": {
                            "type": "boolean",
                            "description": "If true, only simulates shutdown (default: true)",
                            "default": True
                        },
                        "tenant_id": {
                            "type": "string",
                            "description": "Azure AD tenant ID (optional)"
                        },
                        "client_id": {
                            "type": "string",
                            "description": "Azure AD client ID (optional)"
                        },
                        "client_secret": {
                            "type": "string",
                            "description": "Azure AD client secret (optional)"
                        }
                    }
                }
            }
        }
    )
    tool_schemas.append(tool_schema)
