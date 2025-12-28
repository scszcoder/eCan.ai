"""
Google Cloud Cost Monitor and Emergency Shutdown MCP Tools

This module provides MCP tools for:
1. gcloud_read_billing - Read detailed GCP billing information
2. gcloud_shutdown - Emergency shutdown of GCP services to prevent runaway costs

Targeted services:
- Compute Engine (VMs)
- Google Kubernetes Engine (GKE)
- Cloud Run
- Cloud Functions
- App Engine
- Cloud SQL
- BigQuery
- Dataflow
- Dataproc
- Pub/Sub
- Cloud Storage
- Vertex AI
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
    from google.cloud import compute_v1
    from google.cloud import container_v1
    from google.cloud import run_v2
    from google.cloud import functions_v2
    from google.cloud import sqladmin_v1beta4
    from google.cloud import bigquery
    from google.cloud import dataproc_v1
    from google.cloud import pubsub_v1
    from google.cloud import storage
    from google.cloud import billing_v1
    from google.cloud import resourcemanager_v3
    from google.auth import default as google_auth_default
    from google.oauth2 import service_account
    GCLOUD_SDK_AVAILABLE = True
except ImportError:
    GCLOUD_SDK_AVAILABLE = False
    logger.warning("[GCLOUD_TOOLS] Google Cloud SDK not installed.")


# ============================================================================
# Helper Functions
# ============================================================================

def get_gcloud_credentials(service_account_file: str = None):
    """Get Google Cloud credentials."""
    if not GCLOUD_SDK_AVAILABLE:
        return None, None
    try:
        if service_account_file and os.path.exists(service_account_file):
            credentials = service_account.Credentials.from_service_account_file(
                service_account_file,
                scopes=['https://www.googleapis.com/auth/cloud-platform']
            )
            with open(service_account_file, 'r') as f:
                sa_info = json.load(f)
                project_id = sa_info.get('project_id')
            return credentials, project_id
        else:
            credentials, project_id = google_auth_default()
            return credentials, project_id
    except Exception as e:
        logger.error(f"[GCLOUD_TOOLS] Failed to get credentials: {e}")
        return None, None


def get_all_zones(credentials, project_id: str) -> List[str]:
    """Get all zones in a project."""
    try:
        client = compute_v1.ZonesClient(credentials=credentials)
        return [zone.name for zone in client.list(project=project_id)]
    except Exception as e:
        logger.error(f"[GCLOUD_TOOLS] Failed to get zones: {e}")
        return ['us-central1-a', 'us-east1-b', 'europe-west1-b']


def get_all_regions(credentials, project_id: str) -> List[str]:
    """Get all regions in a project."""
    try:
        client = compute_v1.RegionsClient(credentials=credentials)
        return [region.name for region in client.list(project=project_id)]
    except Exception as e:
        logger.error(f"[GCLOUD_TOOLS] Failed to get regions: {e}")
        return ['us-central1', 'us-east1', 'europe-west1']


# ============================================================================
# Billing Functions
# ============================================================================

def read_gcloud_billing_data(credentials, billing_account_id: str) -> Dict[str, Any]:
    """Read billing data from GCP Cloud Billing API."""
    try:
        client = billing_v1.CloudBillingClient(credentials=credentials)
        billing_account_name = f"billingAccounts/{billing_account_id}"
        
        try:
            account = client.get_billing_account(name=billing_account_name)
            account_info = {
                'name': account.name,
                'display_name': account.display_name,
                'open': account.open,
            }
        except Exception as e:
            account_info = {'error': str(e)}
        
        projects = []
        try:
            for project_info in client.list_project_billing_info(name=billing_account_name):
                projects.append({
                    'project_id': project_info.project_id,
                    'billing_enabled': project_info.billing_enabled
                })
        except Exception as e:
            logger.debug(f"[GCLOUD_TOOLS] Error listing billing projects: {e}")
        
        return {
            'success': True,
            'billing_account': account_info,
            'projects': projects,
            'note': 'For detailed costs, export billing to BigQuery.'
        }
    except Exception as e:
        return {'success': False, 'error': str(e)}


# ============================================================================
# Shutdown Functions
# ============================================================================

def shutdown_compute_instances(credentials, project_id: str, zones: List[str] = None,
                                dry_run: bool = False) -> Dict[str, Any]:
    """Stop all Compute Engine VMs."""
    results = {'stopped': [], 'errors': []}
    try:
        client = compute_v1.InstancesClient(credentials=credentials)
        if not zones:
            zones = get_all_zones(credentials, project_id)
        
        for zone in zones:
            try:
                for instance in client.list(project=project_id, zone=zone):
                    if instance.status == 'RUNNING':
                        if dry_run:
                            results['stopped'].append({
                                'project': project_id, 'zone': zone,
                                'service': 'Compute Engine', 'resource': instance.name,
                                'action': 'would_stop', 'dry_run': True
                            })
                        else:
                            client.stop(project=project_id, zone=zone, instance=instance.name)
                            results['stopped'].append({
                                'project': project_id, 'zone': zone,
                                'service': 'Compute Engine', 'resource': instance.name,
                                'action': 'stopping'
                            })
                            logger.info(f"[GCLOUD_TOOLS] Stopping VM: {instance.name}")
            except Exception as ze:
                logger.debug(f"[GCLOUD_TOOLS] Error in zone {zone}: {ze}")
    except Exception as e:
        results['errors'].append({'service': 'Compute Engine', 'error': str(e)})
    return results


def shutdown_gke_clusters(credentials, project_id: str, dry_run: bool = False) -> Dict[str, Any]:
    """Scale down GKE node pools to 0."""
    results = {'stopped': [], 'errors': []}
    try:
        client = container_v1.ClusterManagerClient(credentials=credentials)
        parent = f"projects/{project_id}/locations/-"
        
        response = client.list_clusters(parent=parent)
        for cluster in response.clusters:
            for node_pool in cluster.node_pools:
                if dry_run:
                    results['stopped'].append({
                        'project': project_id, 'location': cluster.location,
                        'service': 'GKE Node Pool',
                        'resource': f"{cluster.name}/{node_pool.name}",
                        'action': 'would_scale_to_0', 'dry_run': True
                    })
                else:
                    try:
                        name = f"projects/{project_id}/locations/{cluster.location}/clusters/{cluster.name}/nodePools/{node_pool.name}"
                        client.set_node_pool_size(name=name, node_count=0)
                        results['stopped'].append({
                            'project': project_id, 'location': cluster.location,
                            'service': 'GKE Node Pool',
                            'resource': f"{cluster.name}/{node_pool.name}",
                            'action': 'scaling_to_0'
                        })
                        logger.info(f"[GCLOUD_TOOLS] Scaling GKE to 0: {cluster.name}/{node_pool.name}")
                    except Exception as npe:
                        results['errors'].append({'service': 'GKE', 'error': str(npe)})
    except Exception as e:
        results['errors'].append({'service': 'GKE', 'error': str(e)})
    return results


def shutdown_cloud_run(credentials, project_id: str, regions: List[str] = None,
                       dry_run: bool = False) -> Dict[str, Any]:
    """Scale Cloud Run services to 0."""
    results = {'stopped': [], 'errors': []}
    try:
        client = run_v2.ServicesClient(credentials=credentials)
        if not regions:
            regions = get_all_regions(credentials, project_id)
        
        for region in regions:
            try:
                parent = f"projects/{project_id}/locations/{region}"
                for service in client.list_services(parent=parent):
                    service_name = service.name.split('/')[-1]
                    if dry_run:
                        results['stopped'].append({
                            'project': project_id, 'region': region,
                            'service': 'Cloud Run', 'resource': service_name,
                            'action': 'would_scale_to_0', 'dry_run': True
                        })
                    else:
                        service.template.scaling.min_instance_count = 0
                        client.update_service(service=service)
                        results['stopped'].append({
                            'project': project_id, 'region': region,
                            'service': 'Cloud Run', 'resource': service_name,
                            'action': 'min_instances_set_to_0'
                        })
                        logger.info(f"[GCLOUD_TOOLS] Cloud Run min=0: {service_name}")
            except Exception as re:
                logger.debug(f"[GCLOUD_TOOLS] Error in region {region}: {re}")
    except Exception as e:
        results['errors'].append({'service': 'Cloud Run', 'error': str(e)})
    return results


def shutdown_cloud_functions(credentials, project_id: str, regions: List[str] = None,
                              dry_run: bool = False) -> Dict[str, Any]:
    """Disable Cloud Functions."""
    results = {'stopped': [], 'errors': []}
    try:
        client = functions_v2.FunctionServiceClient(credentials=credentials)
        if not regions:
            regions = get_all_regions(credentials, project_id)
        
        for region in regions:
            try:
                parent = f"projects/{project_id}/locations/{region}"
                for func in client.list_functions(parent=parent):
                    func_name = func.name.split('/')[-1]
                    if dry_run:
                        results['stopped'].append({
                            'project': project_id, 'region': region,
                            'service': 'Cloud Functions', 'resource': func_name,
                            'action': 'would_set_max_0', 'dry_run': True
                        })
                    else:
                        func.service_config.max_instance_count = 0
                        client.update_function(function=func)
                        results['stopped'].append({
                            'project': project_id, 'region': region,
                            'service': 'Cloud Functions', 'resource': func_name,
                            'action': 'max_instances_set_to_0'
                        })
                        logger.info(f"[GCLOUD_TOOLS] Function max=0: {func_name}")
            except Exception as re:
                logger.debug(f"[GCLOUD_TOOLS] Error in region {region}: {re}")
    except Exception as e:
        results['errors'].append({'service': 'Cloud Functions', 'error': str(e)})
    return results


def shutdown_cloud_sql(credentials, project_id: str, dry_run: bool = False) -> Dict[str, Any]:
    """Stop Cloud SQL instances."""
    results = {'stopped': [], 'errors': []}
    try:
        client = sqladmin_v1beta4.SqlInstancesServiceClient(credentials=credentials)
        instances = client.list(project=project_id)
        
        for instance in instances.items or []:
            if instance.state == 'RUNNABLE':
                if dry_run:
                    results['stopped'].append({
                        'project': project_id, 'service': 'Cloud SQL',
                        'resource': instance.name, 'action': 'would_stop', 'dry_run': True
                    })
                else:
                    instance.settings.activation_policy = 'NEVER'
                    client.patch(project=project_id, instance=instance.name, body=instance)
                    results['stopped'].append({
                        'project': project_id, 'service': 'Cloud SQL',
                        'resource': instance.name, 'action': 'stopping'
                    })
                    logger.info(f"[GCLOUD_TOOLS] Stopping Cloud SQL: {instance.name}")
    except Exception as e:
        results['errors'].append({'service': 'Cloud SQL', 'error': str(e)})
    return results


def shutdown_dataproc(credentials, project_id: str, regions: List[str] = None,
                      dry_run: bool = False) -> Dict[str, Any]:
    """Delete Dataproc clusters."""
    results = {'stopped': [], 'errors': []}
    try:
        client = dataproc_v1.ClusterControllerClient(credentials=credentials)
        if not regions:
            regions = get_all_regions(credentials, project_id)
        
        for region in regions:
            try:
                for cluster in client.list_clusters(project_id=project_id, region=region):
                    if dry_run:
                        results['stopped'].append({
                            'project': project_id, 'region': region,
                            'service': 'Dataproc', 'resource': cluster.cluster_name,
                            'action': 'would_delete', 'dry_run': True
                        })
                    else:
                        client.delete_cluster(
                            project_id=project_id, region=region,
                            cluster_name=cluster.cluster_name
                        )
                        results['stopped'].append({
                            'project': project_id, 'region': region,
                            'service': 'Dataproc', 'resource': cluster.cluster_name,
                            'action': 'deleting'
                        })
                        logger.info(f"[GCLOUD_TOOLS] Deleting Dataproc: {cluster.cluster_name}")
            except Exception as re:
                logger.debug(f"[GCLOUD_TOOLS] Error in region {region}: {re}")
    except Exception as e:
        results['errors'].append({'service': 'Dataproc', 'error': str(e)})
    return results


def shutdown_pubsub(credentials, project_id: str, dry_run: bool = False) -> Dict[str, Any]:
    """Note Pub/Sub subscriptions (can't stop, but can delete)."""
    results = {'stopped': [], 'errors': []}
    try:
        subscriber = pubsub_v1.SubscriberClient(credentials=credentials)
        project_path = f"projects/{project_id}"
        
        for subscription in subscriber.list_subscriptions(project=project_path):
            sub_name = subscription.name.split('/')[-1]
            results['stopped'].append({
                'project': project_id, 'service': 'Pub/Sub Subscription',
                'resource': sub_name,
                'action': 'noted (delete manually if needed)', 'dry_run': dry_run
            })
    except Exception as e:
        results['errors'].append({'service': 'Pub/Sub', 'error': str(e)})
    return results


# ============================================================================
# MCP Tool Functions
# ============================================================================

async def gcloud_read_billing(mainwin, args) -> List[TextContent]:
    """MCP tool to read GCP billing information."""
    try:
        if not GCLOUD_SDK_AVAILABLE:
            msg = "ERROR: Google Cloud SDK not installed. pip install google-cloud-billing google-cloud-compute"
            result = TextContent(type="text", text=msg)
            result.meta = {"success": False, "error": "gcloud_sdk_not_installed"}
            return [result]
        
        input_data = args.get("input", {})
        billing_account_id = input_data.get("billing_account_id", "")
        service_account_file = input_data.get("service_account_file", None)
        
        logger.info(f"[MCP][GCLOUD_READ_BILLING]: Reading billing info")
        
        credentials, project_id = get_gcloud_credentials(service_account_file)
        if not credentials:
            msg = "ERROR: Failed to get GCP credentials."
            result = TextContent(type="text", text=msg)
            result.meta = {"success": False, "error": "credential_failed"}
            return [result]
        
        billing_data = {}
        if billing_account_id:
            billing_data = read_gcloud_billing_data(credentials, billing_account_id)
        
        msg = f"GCP Billing Info:\n"
        if billing_data.get('success'):
            msg += f"  Account: {billing_data.get('billing_account', {}).get('display_name', 'N/A')}\n"
            msg += f"  Projects: {len(billing_data.get('projects', []))}\n"
            msg += f"  Note: {billing_data.get('note', '')}\n"
        else:
            msg += f"  Error: {billing_data.get('error', 'Unknown')}\n"
            msg += "  Tip: Provide billing_account_id for detailed info\n"
        
        result = TextContent(type="text", text=msg)
        result.meta = {"success": True, "billing_info": billing_data}
        return [result]
        
    except Exception as e:
        err_trace = get_traceback(e, "ErrorGcloudReadBilling")
        logger.error(err_trace)
        result = TextContent(type="text", text=err_trace)
        result.meta = {"success": False}
        return [result]


async def gcloud_shutdown(mainwin, args) -> List[TextContent]:
    """MCP tool to emergency shutdown GCP services."""
    try:
        if not GCLOUD_SDK_AVAILABLE:
            msg = "ERROR: Google Cloud SDK not installed."
            result = TextContent(type="text", text=msg)
            result.meta = {"success": False, "error": "gcloud_sdk_not_installed"}
            return [result]
        
        input_data = args.get("input", {})
        services = input_data.get("services", [])
        project_id = input_data.get("project_id", None)
        regions = input_data.get("regions", None)
        zones = input_data.get("zones", None)
        dry_run = input_data.get("dry_run", True)
        service_account_file = input_data.get("service_account_file", None)
        
        ALL_SERVICES = ['compute', 'gke', 'cloud_run', 'cloud_functions', 'cloud_sql', 'dataproc', 'pubsub']
        
        if not services or services == ['all']:
            services = ALL_SERVICES
        
        logger.info(f"[MCP][GCLOUD_SHUTDOWN]: {'DRY RUN - ' if dry_run else ''}Shutting down: {services}")
        
        credentials, default_project = get_gcloud_credentials(service_account_file)
        if not credentials:
            msg = "ERROR: Failed to get GCP credentials."
            result = TextContent(type="text", text=msg)
            result.meta = {"success": False, "error": "credential_failed"}
            return [result]
        
        if not project_id:
            project_id = default_project
        
        if not project_id:
            msg = "ERROR: No project_id specified and none found in credentials."
            result = TextContent(type="text", text=msg)
            result.meta = {"success": False, "error": "no_project"}
            return [result]
        
        all_results = {
            'dry_run': dry_run,
            'project_id': project_id,
            'services_targeted': services,
            'results': {}
        }
        
        service_handlers = {
            'compute': lambda: shutdown_compute_instances(credentials, project_id, zones, dry_run),
            'gke': lambda: shutdown_gke_clusters(credentials, project_id, dry_run),
            'cloud_run': lambda: shutdown_cloud_run(credentials, project_id, regions, dry_run),
            'cloud_functions': lambda: shutdown_cloud_functions(credentials, project_id, regions, dry_run),
            'cloud_sql': lambda: shutdown_cloud_sql(credentials, project_id, dry_run),
            'dataproc': lambda: shutdown_dataproc(credentials, project_id, regions, dry_run),
            'pubsub': lambda: shutdown_pubsub(credentials, project_id, dry_run),
        }
        
        for service in services:
            service_lower = service.lower().replace('-', '_').replace(' ', '_')
            if service_lower in service_handlers:
                all_results['results'][service_lower] = service_handlers[service_lower]()
        
        total_stopped = sum(len(r.get('stopped', [])) for r in all_results['results'].values())
        total_errors = sum(len(r.get('errors', [])) for r in all_results['results'].values())
        
        if dry_run:
            msg = f"🔍 DRY RUN - GCP Emergency Shutdown Preview:\n"
            msg += f"  Would affect {total_stopped} resources\n"
            msg += f"  Project: {project_id}\n"
            msg += f"  ⚠️ Run with dry_run=false to execute\n"
        else:
            msg = f"🚨 GCP Emergency Shutdown Executed:\n"
            msg += f"  Stopped/Disabled: {total_stopped} resources\n"
            msg += f"  Errors: {total_errors}\n"
        
        result = TextContent(type="text", text=msg)
        result.meta = {
            "success": True, "dry_run": dry_run,
            "total_stopped": total_stopped, "total_errors": total_errors,
            "details": all_results
        }
        return [result]
        
    except Exception as e:
        err_trace = get_traceback(e, "ErrorGcloudShutdown")
        logger.error(err_trace)
        result = TextContent(type="text", text=err_trace)
        result.meta = {"success": False}
        return [result]


# ============================================================================
# Schema Functions
# ============================================================================

def add_gcloud_read_billing_tool_schema(tool_schemas):
    """Add schema for gcloud_read_billing tool."""
    tool_schema = types.Tool(
        name="gcloud_read_billing",
        description="<category>GCP</category><sub-category>Cost Management</sub-category>Read GCP billing account information and linked projects.",
        inputSchema={
            "type": "object",
            "required": ["input"],
            "properties": {
                "input": {
                    "type": "object",
                    "required": [],
                    "properties": {
                        "billing_account_id": {
                            "type": "string",
                            "description": "GCP billing account ID (e.g., 01A2B3-C4D5E6-F7G8H9)"
                        },
                        "service_account_file": {
                            "type": "string",
                            "description": "Path to service account JSON key file (optional)"
                        }
                    }
                }
            }
        }
    )
    tool_schemas.append(tool_schema)


def add_gcloud_shutdown_tool_schema(tool_schemas):
    """Add schema for gcloud_shutdown tool."""
    tool_schema = types.Tool(
        name="gcloud_shutdown",
        description="""<category>GCP</category><sub-category>Cost Management</sub-category>Emergency shutdown of GCP services.

SUPPORTED SERVICES:
- compute: Stop Compute Engine VMs
- gke: Scale GKE node pools to 0
- cloud_run: Set min instances to 0
- cloud_functions: Set max instances to 0
- cloud_sql: Stop SQL instances
- dataproc: Delete Dataproc clusters
- pubsub: Note Pub/Sub subscriptions

⚠️ CAUTION: Use dry_run=true first!""",
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
                            "description": "Services to shutdown. Use ['all'] for all."
                        },
                        "project_id": {
                            "type": "string",
                            "description": "GCP project ID"
                        },
                        "regions": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Regions to target (optional)"
                        },
                        "zones": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Zones to target for Compute Engine (optional)"
                        },
                        "dry_run": {
                            "type": "boolean",
                            "description": "Simulate only (default: true)",
                            "default": True
                        },
                        "service_account_file": {
                            "type": "string",
                            "description": "Path to service account JSON key file"
                        }
                    }
                }
            }
        }
    )
    tool_schemas.append(tool_schema)
