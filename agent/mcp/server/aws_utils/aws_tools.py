"""
AWS Cost Monitor and Emergency Shutdown MCP Tools

This module provides MCP tools for:
1. aws_read_billing - Read detailed AWS billing information
2. aws_shutdown - Emergency shutdown of AWS services to prevent runaway costs

Targeted services:
- EC2, SageMaker, SageMaker AutoScaling, ECS, EKS
- NAT Gateway, Data Transfer, S3, CloudWatch Logs
- Lambda, Athena, OpenSearch/Elasticsearch, RDS/Aurora
- Kinesis, Step Functions, SNS/SQS, API Gateway
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
    import boto3
    from botocore.exceptions import ClientError, NoCredentialsError
    BOTO3_AVAILABLE = True
except ImportError:
    BOTO3_AVAILABLE = False
    logger.warning("[AWS_TOOLS] boto3 not installed. AWS tools will not function.")


# ============================================================================
# Helper Functions
# ============================================================================

def get_boto3_session(region: str = None, profile: str = None) -> Optional[Any]:
    """Create a boto3 session with optional region and profile."""
    if not BOTO3_AVAILABLE:
        return None
    try:
        session_kwargs = {}
        if region:
            session_kwargs['region_name'] = region
        if profile:
            session_kwargs['profile_name'] = profile
        return boto3.Session(**session_kwargs)
    except Exception as e:
        logger.error(f"[AWS_TOOLS] Failed to create boto3 session: {e}")
        return None


def get_all_regions(session) -> List[str]:
    """Get all available AWS regions."""
    try:
        ec2 = session.client('ec2', region_name='us-east-1')
        regions = ec2.describe_regions()['Regions']
        return [r['RegionName'] for r in regions]
    except Exception as e:
        logger.error(f"[AWS_TOOLS] Failed to get regions: {e}")
        return ['us-east-1', 'us-west-2', 'eu-west-1', 'ap-northeast-1']


# ============================================================================
# Billing Functions
# ============================================================================

def read_cost_explorer_data(session, days: int = 30) -> Dict[str, Any]:
    """Read cost data from AWS Cost Explorer."""
    try:
        ce = session.client('ce', region_name='us-east-1')
        
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=days)
        
        # Get cost by service
        response = ce.get_cost_and_usage(
            TimePeriod={
                'Start': start_date.strftime('%Y-%m-%d'),
                'End': end_date.strftime('%Y-%m-%d')
            },
            Granularity='DAILY',
            Metrics=['UnblendedCost', 'UsageQuantity'],
            GroupBy=[
                {'Type': 'DIMENSION', 'Key': 'SERVICE'}
            ]
        )
        
        # Parse results
        costs_by_service = {}
        daily_costs = []
        
        for result in response.get('ResultsByTime', []):
            date = result['TimePeriod']['Start']
            daily_total = 0.0
            
            for group in result.get('Groups', []):
                service = group['Keys'][0]
                cost = float(group['Metrics']['UnblendedCost']['Amount'])
                daily_total += cost
                
                if service not in costs_by_service:
                    costs_by_service[service] = 0.0
                costs_by_service[service] += cost
            
            daily_costs.append({'date': date, 'cost': daily_total})
        
        # Get forecast if available
        forecast = None
        try:
            forecast_response = ce.get_cost_forecast(
                TimePeriod={
                    'Start': end_date.strftime('%Y-%m-%d'),
                    'End': (end_date + timedelta(days=30)).strftime('%Y-%m-%d')
                },
                Metric='UNBLENDED_COST',
                Granularity='MONTHLY'
            )
            forecast = float(forecast_response.get('Total', {}).get('Amount', 0))
        except Exception as fe:
            logger.debug(f"[AWS_TOOLS] Could not get forecast: {fe}")
        
        return {
            'success': True,
            'period': f"{start_date} to {end_date}",
            'total_cost': sum(costs_by_service.values()),
            'costs_by_service': dict(sorted(costs_by_service.items(), key=lambda x: x[1], reverse=True)),
            'daily_costs': daily_costs,
            'forecast_next_30_days': forecast,
            'currency': 'USD'
        }
        
    except ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code == 'AccessDeniedException':
            return {'success': False, 'error': 'Access denied. Cost Explorer requires ce:GetCostAndUsage permission.'}
        return {'success': False, 'error': str(e)}
    except Exception as e:
        return {'success': False, 'error': str(e)}


def read_budgets_data(session) -> Dict[str, Any]:
    """Read AWS Budgets data."""
    try:
        budgets = session.client('budgets', region_name='us-east-1')
        sts = session.client('sts')
        account_id = sts.get_caller_identity()['Account']
        
        response = budgets.describe_budgets(AccountId=account_id)
        
        budget_list = []
        for budget in response.get('Budgets', []):
            budget_list.append({
                'name': budget['BudgetName'],
                'type': budget['BudgetType'],
                'limit': float(budget['BudgetLimit']['Amount']),
                'actual_spend': float(budget.get('CalculatedSpend', {}).get('ActualSpend', {}).get('Amount', 0)),
                'forecasted_spend': float(budget.get('CalculatedSpend', {}).get('ForecastedSpend', {}).get('Amount', 0)),
            })
        
        return {'success': True, 'budgets': budget_list}
    except Exception as e:
        return {'success': False, 'error': str(e)}


# ============================================================================
# Shutdown Functions for Each Service
# ============================================================================

def shutdown_ec2_instances(session, regions: List[str], dry_run: bool = False) -> Dict[str, Any]:
    """Stop all running EC2 instances."""
    results = {'stopped': [], 'errors': []}
    
    for region in regions:
        try:
            ec2 = session.client('ec2', region_name=region)
            
            # Get all running instances
            response = ec2.describe_instances(
                Filters=[{'Name': 'instance-state-name', 'Values': ['running']}]
            )
            
            instance_ids = []
            for reservation in response['Reservations']:
                for instance in reservation['Instances']:
                    instance_ids.append(instance['InstanceId'])
            
            if instance_ids:
                if dry_run:
                    results['stopped'].append({
                        'region': region,
                        'service': 'EC2',
                        'instances': instance_ids,
                        'action': 'would_stop',
                        'dry_run': True
                    })
                else:
                    ec2.stop_instances(InstanceIds=instance_ids)
                    results['stopped'].append({
                        'region': region,
                        'service': 'EC2',
                        'instances': instance_ids,
                        'action': 'stopped'
                    })
                    logger.info(f"[AWS_TOOLS] Stopped EC2 instances in {region}: {instance_ids}")
                    
        except Exception as e:
            results['errors'].append({'region': region, 'service': 'EC2', 'error': str(e)})
    
    return results


def shutdown_sagemaker_endpoints(session, regions: List[str], dry_run: bool = False) -> Dict[str, Any]:
    """Delete all SageMaker endpoints."""
    results = {'stopped': [], 'errors': []}
    
    for region in regions:
        try:
            sm = session.client('sagemaker', region_name=region)
            
            # List all endpoints
            endpoints = sm.list_endpoints()['Endpoints']
            
            for endpoint in endpoints:
                endpoint_name = endpoint['EndpointName']
                if dry_run:
                    results['stopped'].append({
                        'region': region,
                        'service': 'SageMaker Endpoint',
                        'resource': endpoint_name,
                        'action': 'would_delete',
                        'dry_run': True
                    })
                else:
                    sm.delete_endpoint(EndpointName=endpoint_name)
                    results['stopped'].append({
                        'region': region,
                        'service': 'SageMaker Endpoint',
                        'resource': endpoint_name,
                        'action': 'deleted'
                    })
                    logger.info(f"[AWS_TOOLS] Deleted SageMaker endpoint in {region}: {endpoint_name}")
            
            # Also stop notebook instances
            notebooks = sm.list_notebook_instances()['NotebookInstances']
            for nb in notebooks:
                if nb['NotebookInstanceStatus'] in ['InService', 'Pending']:
                    nb_name = nb['NotebookInstanceName']
                    if dry_run:
                        results['stopped'].append({
                            'region': region,
                            'service': 'SageMaker Notebook',
                            'resource': nb_name,
                            'action': 'would_stop',
                            'dry_run': True
                        })
                    else:
                        sm.stop_notebook_instance(NotebookInstanceName=nb_name)
                        results['stopped'].append({
                            'region': region,
                            'service': 'SageMaker Notebook',
                            'resource': nb_name,
                            'action': 'stopped'
                        })
                        logger.info(f"[AWS_TOOLS] Stopped SageMaker notebook in {region}: {nb_name}")
                        
        except Exception as e:
            results['errors'].append({'region': region, 'service': 'SageMaker', 'error': str(e)})
    
    return results


def shutdown_sagemaker_autoscaling(session, regions: List[str], dry_run: bool = False) -> Dict[str, Any]:
    """Disable SageMaker autoscaling policies."""
    results = {'stopped': [], 'errors': []}
    
    for region in regions:
        try:
            aas = session.client('application-autoscaling', region_name=region)
            
            # Get SageMaker scalable targets
            paginator = aas.get_paginator('describe_scalable_targets')
            for page in paginator.paginate(ServiceNamespace='sagemaker'):
                for target in page['ScalableTargets']:
                    resource_id = target['ResourceId']
                    if dry_run:
                        results['stopped'].append({
                            'region': region,
                            'service': 'SageMaker AutoScaling',
                            'resource': resource_id,
                            'action': 'would_deregister',
                            'dry_run': True
                        })
                    else:
                        aas.deregister_scalable_target(
                            ServiceNamespace='sagemaker',
                            ResourceId=resource_id,
                            ScalableDimension=target['ScalableDimension']
                        )
                        results['stopped'].append({
                            'region': region,
                            'service': 'SageMaker AutoScaling',
                            'resource': resource_id,
                            'action': 'deregistered'
                        })
                        logger.info(f"[AWS_TOOLS] Deregistered SageMaker autoscaling in {region}: {resource_id}")
                        
        except Exception as e:
            results['errors'].append({'region': region, 'service': 'SageMaker AutoScaling', 'error': str(e)})
    
    return results


def shutdown_ecs_services(session, regions: List[str], dry_run: bool = False) -> Dict[str, Any]:
    """Scale down ECS services to 0."""
    results = {'stopped': [], 'errors': []}
    
    for region in regions:
        try:
            ecs = session.client('ecs', region_name=region)
            
            # List all clusters
            clusters = ecs.list_clusters()['clusterArns']
            
            for cluster_arn in clusters:
                # List services in cluster
                services = ecs.list_services(cluster=cluster_arn)['serviceArns']
                
                for service_arn in services:
                    service_name = service_arn.split('/')[-1]
                    if dry_run:
                        results['stopped'].append({
                            'region': region,
                            'service': 'ECS Service',
                            'resource': service_name,
                            'cluster': cluster_arn.split('/')[-1],
                            'action': 'would_scale_to_0',
                            'dry_run': True
                        })
                    else:
                        ecs.update_service(
                            cluster=cluster_arn,
                            service=service_arn,
                            desiredCount=0
                        )
                        results['stopped'].append({
                            'region': region,
                            'service': 'ECS Service',
                            'resource': service_name,
                            'cluster': cluster_arn.split('/')[-1],
                            'action': 'scaled_to_0'
                        })
                        logger.info(f"[AWS_TOOLS] Scaled ECS service to 0 in {region}: {service_name}")
                        
        except Exception as e:
            results['errors'].append({'region': region, 'service': 'ECS', 'error': str(e)})
    
    return results


def shutdown_eks_nodegroups(session, regions: List[str], dry_run: bool = False) -> Dict[str, Any]:
    """Scale down EKS node groups to 0."""
    results = {'stopped': [], 'errors': []}
    
    for region in regions:
        try:
            eks = session.client('eks', region_name=region)
            
            # List all clusters
            clusters = eks.list_clusters()['clusters']
            
            for cluster_name in clusters:
                # List node groups
                nodegroups = eks.list_nodegroups(clusterName=cluster_name)['nodegroups']
                
                for ng_name in nodegroups:
                    if dry_run:
                        results['stopped'].append({
                            'region': region,
                            'service': 'EKS NodeGroup',
                            'resource': ng_name,
                            'cluster': cluster_name,
                            'action': 'would_scale_to_0',
                            'dry_run': True
                        })
                    else:
                        eks.update_nodegroup_config(
                            clusterName=cluster_name,
                            nodegroupName=ng_name,
                            scalingConfig={
                                'minSize': 0,
                                'maxSize': 0,
                                'desiredSize': 0
                            }
                        )
                        results['stopped'].append({
                            'region': region,
                            'service': 'EKS NodeGroup',
                            'resource': ng_name,
                            'cluster': cluster_name,
                            'action': 'scaled_to_0'
                        })
                        logger.info(f"[AWS_TOOLS] Scaled EKS nodegroup to 0 in {region}: {ng_name}")
                        
        except Exception as e:
            results['errors'].append({'region': region, 'service': 'EKS', 'error': str(e)})
    
    return results


def shutdown_nat_gateways(session, regions: List[str], dry_run: bool = False) -> Dict[str, Any]:
    """Delete NAT Gateways (WARNING: This will break private subnet internet access)."""
    results = {'stopped': [], 'errors': []}
    
    for region in regions:
        try:
            ec2 = session.client('ec2', region_name=region)
            
            # List NAT gateways
            nat_gateways = ec2.describe_nat_gateways(
                Filters=[{'Name': 'state', 'Values': ['available']}]
            )['NatGateways']
            
            for nat in nat_gateways:
                nat_id = nat['NatGatewayId']
                if dry_run:
                    results['stopped'].append({
                        'region': region,
                        'service': 'NAT Gateway',
                        'resource': nat_id,
                        'action': 'would_delete',
                        'dry_run': True,
                        'warning': 'Deleting NAT Gateway will break private subnet internet access'
                    })
                else:
                    ec2.delete_nat_gateway(NatGatewayId=nat_id)
                    results['stopped'].append({
                        'region': region,
                        'service': 'NAT Gateway',
                        'resource': nat_id,
                        'action': 'deleted'
                    })
                    logger.info(f"[AWS_TOOLS] Deleted NAT Gateway in {region}: {nat_id}")
                    
        except Exception as e:
            results['errors'].append({'region': region, 'service': 'NAT Gateway', 'error': str(e)})
    
    return results


def shutdown_rds_instances(session, regions: List[str], dry_run: bool = False) -> Dict[str, Any]:
    """Stop RDS instances and Aurora clusters."""
    results = {'stopped': [], 'errors': []}
    
    for region in regions:
        try:
            rds = session.client('rds', region_name=region)
            
            # Stop RDS instances
            instances = rds.describe_db_instances()['DBInstances']
            for instance in instances:
                if instance['DBInstanceStatus'] == 'available':
                    db_id = instance['DBInstanceIdentifier']
                    if dry_run:
                        results['stopped'].append({
                            'region': region,
                            'service': 'RDS Instance',
                            'resource': db_id,
                            'action': 'would_stop',
                            'dry_run': True
                        })
                    else:
                        try:
                            rds.stop_db_instance(DBInstanceIdentifier=db_id)
                            results['stopped'].append({
                                'region': region,
                                'service': 'RDS Instance',
                                'resource': db_id,
                                'action': 'stopped'
                            })
                            logger.info(f"[AWS_TOOLS] Stopped RDS instance in {region}: {db_id}")
                        except ClientError as ce:
                            if 'is not in available state' not in str(ce):
                                raise
            
            # Stop Aurora clusters
            clusters = rds.describe_db_clusters()['DBClusters']
            for cluster in clusters:
                if cluster['Status'] == 'available':
                    cluster_id = cluster['DBClusterIdentifier']
                    if dry_run:
                        results['stopped'].append({
                            'region': region,
                            'service': 'Aurora Cluster',
                            'resource': cluster_id,
                            'action': 'would_stop',
                            'dry_run': True
                        })
                    else:
                        try:
                            rds.stop_db_cluster(DBClusterIdentifier=cluster_id)
                            results['stopped'].append({
                                'region': region,
                                'service': 'Aurora Cluster',
                                'resource': cluster_id,
                                'action': 'stopped'
                            })
                            logger.info(f"[AWS_TOOLS] Stopped Aurora cluster in {region}: {cluster_id}")
                        except ClientError as ce:
                            if 'is not in available state' not in str(ce):
                                raise
                                
        except Exception as e:
            results['errors'].append({'region': region, 'service': 'RDS/Aurora', 'error': str(e)})
    
    return results


def shutdown_lambda_functions(session, regions: List[str], dry_run: bool = False) -> Dict[str, Any]:
    """Disable Lambda functions by setting concurrency to 0."""
    results = {'stopped': [], 'errors': []}
    
    for region in regions:
        try:
            lambda_client = session.client('lambda', region_name=region)
            
            # List all functions
            paginator = lambda_client.get_paginator('list_functions')
            for page in paginator.paginate():
                for func in page['Functions']:
                    func_name = func['FunctionName']
                    if dry_run:
                        results['stopped'].append({
                            'region': region,
                            'service': 'Lambda',
                            'resource': func_name,
                            'action': 'would_set_concurrency_0',
                            'dry_run': True
                        })
                    else:
                        lambda_client.put_function_concurrency(
                            FunctionName=func_name,
                            ReservedConcurrentExecutions=0
                        )
                        results['stopped'].append({
                            'region': region,
                            'service': 'Lambda',
                            'resource': func_name,
                            'action': 'concurrency_set_to_0'
                        })
                        logger.info(f"[AWS_TOOLS] Set Lambda concurrency to 0 in {region}: {func_name}")
                        
        except Exception as e:
            results['errors'].append({'region': region, 'service': 'Lambda', 'error': str(e)})
    
    return results


def shutdown_opensearch_domains(session, regions: List[str], dry_run: bool = False) -> Dict[str, Any]:
    """Delete OpenSearch/Elasticsearch domains (WARNING: Data loss)."""
    results = {'stopped': [], 'errors': []}
    
    for region in regions:
        try:
            # Try OpenSearch first
            try:
                os_client = session.client('opensearch', region_name=region)
                domains = os_client.list_domain_names()['DomainNames']
                
                for domain in domains:
                    domain_name = domain['DomainName']
                    if dry_run:
                        results['stopped'].append({
                            'region': region,
                            'service': 'OpenSearch',
                            'resource': domain_name,
                            'action': 'would_delete',
                            'dry_run': True,
                            'warning': 'Deleting domain will cause data loss'
                        })
                    else:
                        os_client.delete_domain(DomainName=domain_name)
                        results['stopped'].append({
                            'region': region,
                            'service': 'OpenSearch',
                            'resource': domain_name,
                            'action': 'deleted'
                        })
                        logger.info(f"[AWS_TOOLS] Deleted OpenSearch domain in {region}: {domain_name}")
            except Exception:
                pass
            
            # Also try legacy Elasticsearch
            try:
                es_client = session.client('es', region_name=region)
                domains = es_client.list_domain_names()['DomainNames']
                
                for domain in domains:
                    domain_name = domain['DomainName']
                    if dry_run:
                        results['stopped'].append({
                            'region': region,
                            'service': 'Elasticsearch',
                            'resource': domain_name,
                            'action': 'would_delete',
                            'dry_run': True,
                            'warning': 'Deleting domain will cause data loss'
                        })
                    else:
                        es_client.delete_elasticsearch_domain(DomainName=domain_name)
                        results['stopped'].append({
                            'region': region,
                            'service': 'Elasticsearch',
                            'resource': domain_name,
                            'action': 'deleted'
                        })
                        logger.info(f"[AWS_TOOLS] Deleted Elasticsearch domain in {region}: {domain_name}")
            except Exception:
                pass
                
        except Exception as e:
            results['errors'].append({'region': region, 'service': 'OpenSearch/ES', 'error': str(e)})
    
    return results


def shutdown_kinesis_streams(session, regions: List[str], dry_run: bool = False) -> Dict[str, Any]:
    """Delete Kinesis Data Streams and Firehose delivery streams."""
    results = {'stopped': [], 'errors': []}
    
    for region in regions:
        try:
            # Kinesis Data Streams
            kinesis = session.client('kinesis', region_name=region)
            streams = kinesis.list_streams()['StreamNames']
            
            for stream_name in streams:
                if dry_run:
                    results['stopped'].append({
                        'region': region,
                        'service': 'Kinesis Data Stream',
                        'resource': stream_name,
                        'action': 'would_delete',
                        'dry_run': True
                    })
                else:
                    kinesis.delete_stream(StreamName=stream_name, EnforceConsumerDeletion=True)
                    results['stopped'].append({
                        'region': region,
                        'service': 'Kinesis Data Stream',
                        'resource': stream_name,
                        'action': 'deleted'
                    })
                    logger.info(f"[AWS_TOOLS] Deleted Kinesis stream in {region}: {stream_name}")
            
            # Kinesis Firehose
            firehose = session.client('firehose', region_name=region)
            delivery_streams = firehose.list_delivery_streams()['DeliveryStreamNames']
            
            for stream_name in delivery_streams:
                if dry_run:
                    results['stopped'].append({
                        'region': region,
                        'service': 'Kinesis Firehose',
                        'resource': stream_name,
                        'action': 'would_delete',
                        'dry_run': True
                    })
                else:
                    firehose.delete_delivery_stream(DeliveryStreamName=stream_name)
                    results['stopped'].append({
                        'region': region,
                        'service': 'Kinesis Firehose',
                        'resource': stream_name,
                        'action': 'deleted'
                    })
                    logger.info(f"[AWS_TOOLS] Deleted Firehose stream in {region}: {stream_name}")
                    
        except Exception as e:
            results['errors'].append({'region': region, 'service': 'Kinesis', 'error': str(e)})
    
    return results


def shutdown_step_functions(session, regions: List[str], dry_run: bool = False) -> Dict[str, Any]:
    """Stop running Step Functions executions and disable state machines."""
    results = {'stopped': [], 'errors': []}
    
    for region in regions:
        try:
            sfn = session.client('stepfunctions', region_name=region)
            
            # List state machines
            state_machines = sfn.list_state_machines()['stateMachines']
            
            for sm in state_machines:
                sm_arn = sm['stateMachineArn']
                sm_name = sm['name']
                
                # Stop all running executions
                try:
                    executions = sfn.list_executions(
                        stateMachineArn=sm_arn,
                        statusFilter='RUNNING'
                    )['executions']
                    
                    for execution in executions:
                        exec_arn = execution['executionArn']
                        if dry_run:
                            results['stopped'].append({
                                'region': region,
                                'service': 'Step Functions Execution',
                                'resource': exec_arn,
                                'action': 'would_stop',
                                'dry_run': True
                            })
                        else:
                            sfn.stop_execution(executionArn=exec_arn, cause='Emergency shutdown')
                            results['stopped'].append({
                                'region': region,
                                'service': 'Step Functions Execution',
                                'resource': exec_arn,
                                'action': 'stopped'
                            })
                            logger.info(f"[AWS_TOOLS] Stopped Step Function execution in {region}: {exec_arn}")
                except Exception:
                    pass
                
                # Delete state machine (optional - more aggressive)
                if not dry_run:
                    # Note: We don't delete state machines by default, just stop executions
                    pass
                    
        except Exception as e:
            results['errors'].append({'region': region, 'service': 'Step Functions', 'error': str(e)})
    
    return results


def shutdown_api_gateway(session, regions: List[str], dry_run: bool = False) -> Dict[str, Any]:
    """Disable API Gateway stages by setting throttling to 0."""
    results = {'stopped': [], 'errors': []}
    
    for region in regions:
        try:
            apigw = session.client('apigateway', region_name=region)
            
            # List REST APIs
            apis = apigw.get_rest_apis()['items']
            
            for api in apis:
                api_id = api['id']
                api_name = api['name']
                
                # Get stages
                try:
                    stages = apigw.get_stages(restApiId=api_id)['item']
                    
                    for stage in stages:
                        stage_name = stage['stageName']
                        if dry_run:
                            results['stopped'].append({
                                'region': region,
                                'service': 'API Gateway',
                                'resource': f"{api_name}/{stage_name}",
                                'action': 'would_throttle_to_0',
                                'dry_run': True
                            })
                        else:
                            # Set throttling to 0 to effectively disable
                            apigw.update_stage(
                                restApiId=api_id,
                                stageName=stage_name,
                                patchOperations=[
                                    {
                                        'op': 'replace',
                                        'path': '/*/*/throttling/rateLimit',
                                        'value': '0'
                                    },
                                    {
                                        'op': 'replace',
                                        'path': '/*/*/throttling/burstLimit',
                                        'value': '0'
                                    }
                                ]
                            )
                            results['stopped'].append({
                                'region': region,
                                'service': 'API Gateway',
                                'resource': f"{api_name}/{stage_name}",
                                'action': 'throttled_to_0'
                            })
                            logger.info(f"[AWS_TOOLS] Throttled API Gateway in {region}: {api_name}/{stage_name}")
                except Exception:
                    pass
                    
        except Exception as e:
            results['errors'].append({'region': region, 'service': 'API Gateway', 'error': str(e)})
    
    return results


def shutdown_sns_sqs(session, regions: List[str], dry_run: bool = False) -> Dict[str, Any]:
    """Purge SQS queues and set SNS delivery policies to block."""
    results = {'stopped': [], 'errors': []}
    
    for region in regions:
        try:
            # SQS - Purge queues
            sqs = session.client('sqs', region_name=region)
            queues = sqs.list_queues().get('QueueUrls', [])
            
            for queue_url in queues:
                queue_name = queue_url.split('/')[-1]
                if dry_run:
                    results['stopped'].append({
                        'region': region,
                        'service': 'SQS Queue',
                        'resource': queue_name,
                        'action': 'would_purge',
                        'dry_run': True
                    })
                else:
                    sqs.purge_queue(QueueUrl=queue_url)
                    results['stopped'].append({
                        'region': region,
                        'service': 'SQS Queue',
                        'resource': queue_name,
                        'action': 'purged'
                    })
                    logger.info(f"[AWS_TOOLS] Purged SQS queue in {region}: {queue_name}")
            
            # SNS - List topics (can't easily disable, just note them)
            sns = session.client('sns', region_name=region)
            topics = sns.list_topics().get('Topics', [])
            
            for topic in topics:
                topic_arn = topic['TopicArn']
                topic_name = topic_arn.split(':')[-1]
                if dry_run:
                    results['stopped'].append({
                        'region': region,
                        'service': 'SNS Topic',
                        'resource': topic_name,
                        'action': 'would_note (cannot easily disable)',
                        'dry_run': True
                    })
                    
        except Exception as e:
            results['errors'].append({'region': region, 'service': 'SNS/SQS', 'error': str(e)})
    
    return results


def shutdown_cloudwatch_logs(session, regions: List[str], dry_run: bool = False) -> Dict[str, Any]:
    """Set CloudWatch log group retention to minimum to reduce storage costs."""
    results = {'stopped': [], 'errors': []}
    
    for region in regions:
        try:
            logs = session.client('logs', region_name=region)
            
            # List log groups
            paginator = logs.get_paginator('describe_log_groups')
            for page in paginator.paginate():
                for log_group in page['logGroups']:
                    log_group_name = log_group['logGroupName']
                    current_retention = log_group.get('retentionInDays')
                    
                    # Only modify if retention is not already set to minimum (1 day)
                    if current_retention != 1:
                        if dry_run:
                            results['stopped'].append({
                                'region': region,
                                'service': 'CloudWatch Logs',
                                'resource': log_group_name,
                                'action': 'would_set_retention_1_day',
                                'dry_run': True
                            })
                        else:
                            logs.put_retention_policy(
                                logGroupName=log_group_name,
                                retentionInDays=1
                            )
                            results['stopped'].append({
                                'region': region,
                                'service': 'CloudWatch Logs',
                                'resource': log_group_name,
                                'action': 'retention_set_to_1_day'
                            })
                            logger.info(f"[AWS_TOOLS] Set log retention to 1 day in {region}: {log_group_name}")
                            
        except Exception as e:
            results['errors'].append({'region': region, 'service': 'CloudWatch Logs', 'error': str(e)})
    
    return results


def shutdown_s3_lifecycle(session, dry_run: bool = False) -> Dict[str, Any]:
    """Add aggressive lifecycle rules to S3 buckets to expire objects quickly."""
    results = {'stopped': [], 'errors': []}
    
    try:
        s3 = session.client('s3')
        buckets = s3.list_buckets()['Buckets']
        
        lifecycle_rule = {
            'Rules': [{
                'ID': 'EmergencyExpiration',
                'Status': 'Enabled',
                'Filter': {'Prefix': ''},
                'Expiration': {'Days': 1},
                'NoncurrentVersionExpiration': {'NoncurrentDays': 1},
                'AbortIncompleteMultipartUpload': {'DaysAfterInitiation': 1}
            }]
        }
        
        for bucket in buckets:
            bucket_name = bucket['Name']
            if dry_run:
                results['stopped'].append({
                    'service': 'S3 Bucket',
                    'resource': bucket_name,
                    'action': 'would_add_expiration_lifecycle',
                    'dry_run': True,
                    'warning': 'This will delete all objects after 1 day'
                })
            else:
                try:
                    s3.put_bucket_lifecycle_configuration(
                        Bucket=bucket_name,
                        LifecycleConfiguration=lifecycle_rule
                    )
                    results['stopped'].append({
                        'service': 'S3 Bucket',
                        'resource': bucket_name,
                        'action': 'lifecycle_expiration_added'
                    })
                    logger.info(f"[AWS_TOOLS] Added expiration lifecycle to S3 bucket: {bucket_name}")
                except ClientError as ce:
                    results['errors'].append({'service': 'S3', 'resource': bucket_name, 'error': str(ce)})
                    
    except Exception as e:
        results['errors'].append({'service': 'S3', 'error': str(e)})
    
    return results


# ============================================================================
# MCP Tool Functions
# ============================================================================

async def aws_read_billing(mainwin, args) -> List[TextContent]:
    """MCP tool to read AWS billing information."""
    try:
        if not BOTO3_AVAILABLE:
            msg = "ERROR: boto3 is not installed. Please install it with: pip install boto3"
            logger.error(f"[MCP][AWS_READ_BILLING]: {msg}")
            result = TextContent(type="text", text=msg)
            result.meta = {"success": False, "error": "boto3_not_installed"}
            return [result]
        
        input_data = args.get("input", {})
        days = input_data.get("days", 30)
        region = input_data.get("region", "us-east-1")
        profile = input_data.get("profile", None)
        
        logger.info(f"[MCP][AWS_READ_BILLING]: Reading billing for last {days} days")
        
        session = get_boto3_session(region=region, profile=profile)
        if not session:
            msg = "ERROR: Failed to create AWS session. Check credentials."
            result = TextContent(type="text", text=msg)
            result.meta = {"success": False, "error": "session_failed"}
            return [result]
        
        # Get cost data
        cost_data = read_cost_explorer_data(session, days=days)
        
        # Get budget data
        budget_data = read_budgets_data(session)
        
        # Compile results
        billing_info = {
            "cost_explorer": cost_data,
            "budgets": budget_data
        }
        
        if cost_data.get('success'):
            total = cost_data.get('total_cost', 0)
            forecast = cost_data.get('forecast_next_30_days')
            top_services = list(cost_data.get('costs_by_service', {}).items())[:5]
            
            msg = f"AWS Billing Summary ({days} days):\n"
            msg += f"  Total Cost: ${total:.2f} USD\n"
            if forecast:
                msg += f"  30-Day Forecast: ${forecast:.2f} USD\n"
            msg += f"  Top Services:\n"
            for svc, cost in top_services:
                msg += f"    - {svc}: ${cost:.2f}\n"
        else:
            msg = f"Failed to read billing: {cost_data.get('error', 'Unknown error')}"
        
        result = TextContent(type="text", text=msg)
        result.meta = {"success": cost_data.get('success', False), "billing_info": billing_info}
        
        logger.info(f"[MCP][AWS_READ_BILLING]: Completed - {msg[:100]}...")
        return [result]
        
    except Exception as e:
        err_trace = get_traceback(e, "ErrorAwsReadBilling")
        logger.error(err_trace)
        result = TextContent(type="text", text=err_trace)
        result.meta = {"success": False}
        return [result]


async def aws_shutdown(mainwin, args) -> List[TextContent]:
    """MCP tool to emergency shutdown AWS services."""
    try:
        if not BOTO3_AVAILABLE:
            msg = "ERROR: boto3 is not installed. Please install it with: pip install boto3"
            logger.error(f"[MCP][AWS_SHUTDOWN]: {msg}")
            result = TextContent(type="text", text=msg)
            result.meta = {"success": False, "error": "boto3_not_installed"}
            return [result]
        
        input_data = args.get("input", {})
        services = input_data.get("services", [])
        regions = input_data.get("regions", [])
        dry_run = input_data.get("dry_run", True)  # Default to dry_run for safety
        profile = input_data.get("profile", None)
        
        # All supported services
        ALL_SERVICES = [
            'ec2', 'sagemaker', 'sagemaker_autoscaling', 'ecs', 'eks',
            'nat_gateway', 's3', 'cloudwatch_logs', 'lambda', 'opensearch',
            'rds', 'kinesis', 'step_functions', 'sns_sqs', 'api_gateway'
        ]
        
        # If no services specified, target all
        if not services or services == ['all']:
            services = ALL_SERVICES
        
        logger.info(f"[MCP][AWS_SHUTDOWN]: {'DRY RUN - ' if dry_run else ''}Shutting down services: {services}")
        
        session = get_boto3_session(profile=profile)
        if not session:
            msg = "ERROR: Failed to create AWS session. Check credentials."
            result = TextContent(type="text", text=msg)
            result.meta = {"success": False, "error": "session_failed"}
            return [result]
        
        # Get regions if not specified
        if not regions:
            regions = get_all_regions(session)
        
        all_results = {
            'dry_run': dry_run,
            'services_targeted': services,
            'regions': regions,
            'results': {}
        }
        
        # Execute shutdown for each service
        service_handlers = {
            'ec2': shutdown_ec2_instances,
            'sagemaker': shutdown_sagemaker_endpoints,
            'sagemaker_autoscaling': shutdown_sagemaker_autoscaling,
            'ecs': shutdown_ecs_services,
            'eks': shutdown_eks_nodegroups,
            'nat_gateway': shutdown_nat_gateways,
            'rds': shutdown_rds_instances,
            'lambda': shutdown_lambda_functions,
            'opensearch': shutdown_opensearch_domains,
            'kinesis': shutdown_kinesis_streams,
            'step_functions': shutdown_step_functions,
            'api_gateway': shutdown_api_gateway,
            'sns_sqs': shutdown_sns_sqs,
            'cloudwatch_logs': shutdown_cloudwatch_logs,
        }
        
        for service in services:
            service_lower = service.lower().replace('-', '_').replace(' ', '_')
            if service_lower in service_handlers:
                handler = service_handlers[service_lower]
                if service_lower == 's3':
                    # S3 is global, doesn't need regions
                    all_results['results'][service_lower] = shutdown_s3_lifecycle(session, dry_run=dry_run)
                else:
                    all_results['results'][service_lower] = handler(session, regions, dry_run=dry_run)
            else:
                all_results['results'][service_lower] = {'error': f'Unknown service: {service}'}
        
        # S3 handled separately (global service)
        if 's3' in [s.lower() for s in services]:
            all_results['results']['s3'] = shutdown_s3_lifecycle(session, dry_run=dry_run)
        
        # Compile summary
        total_stopped = 0
        total_errors = 0
        for svc, result_data in all_results['results'].items():
            if isinstance(result_data, dict):
                total_stopped += len(result_data.get('stopped', []))
                total_errors += len(result_data.get('errors', []))
        
        if dry_run:
            msg = f"🔍 DRY RUN - AWS Emergency Shutdown Preview:\n"
            msg += f"  Would affect {total_stopped} resources across {len(services)} services\n"
            msg += f"  Regions: {len(regions)}\n"
            msg += f"  ⚠️ Run with dry_run=false to execute\n"
        else:
            msg = f"🚨 AWS Emergency Shutdown Executed:\n"
            msg += f"  Stopped/Disabled: {total_stopped} resources\n"
            msg += f"  Errors: {total_errors}\n"
            msg += f"  Services: {', '.join(services)}\n"
        
        result = TextContent(type="text", text=msg)
        result.meta = {
            "success": True,
            "dry_run": dry_run,
            "total_stopped": total_stopped,
            "total_errors": total_errors,
            "details": all_results
        }
        
        logger.info(f"[MCP][AWS_SHUTDOWN]: Completed - {msg}")
        return [result]
        
    except Exception as e:
        err_trace = get_traceback(e, "ErrorAwsShutdown")
        logger.error(err_trace)
        result = TextContent(type="text", text=err_trace)
        result.meta = {"success": False}
        return [result]


# ============================================================================
# Schema Functions
# ============================================================================

def add_aws_read_billing_tool_schema(tool_schemas):
    """Add schema for aws_read_billing tool."""
    tool_schema = types.Tool(
        name="aws_read_billing",
        description="<category>AWS</category><sub-category>Cost Management</sub-category>Read detailed AWS billing information including costs by service, daily breakdown, and budget status. Requires AWS credentials with Cost Explorer permissions.",
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
                        "region": {
                            "type": "string",
                            "description": "AWS region for Cost Explorer API (default: us-east-1)",
                            "default": "us-east-1"
                        },
                        "profile": {
                            "type": "string",
                            "description": "AWS profile name to use (optional, uses default if not specified)"
                        }
                    }
                }
            }
        }
    )
    tool_schemas.append(tool_schema)


def add_aws_shutdown_tool_schema(tool_schemas):
    """Add schema for aws_shutdown tool."""
    tool_schema = types.Tool(
        name="aws_shutdown",
        description="""<category>AWS</category><sub-category>Cost Management</sub-category>Emergency shutdown of AWS services to prevent runaway costs. 
        
SUPPORTED SERVICES:
- ec2: Stop all running EC2 instances
- sagemaker: Delete endpoints and stop notebooks
- sagemaker_autoscaling: Deregister autoscaling targets
- ecs: Scale services to 0
- eks: Scale node groups to 0
- nat_gateway: Delete NAT gateways (WARNING: breaks private subnet access)
- rds: Stop RDS instances and Aurora clusters
- lambda: Set function concurrency to 0
- opensearch: Delete OpenSearch/Elasticsearch domains (WARNING: data loss)
- kinesis: Delete Data Streams and Firehose
- step_functions: Stop running executions
- api_gateway: Throttle to 0
- sns_sqs: Purge SQS queues
- cloudwatch_logs: Set retention to 1 day
- s3: Add expiration lifecycle (WARNING: deletes objects after 1 day)

⚠️ CAUTION: This tool can cause service disruption and data loss. Use dry_run=true first!""",
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
                            "description": "List of services to shutdown. Use ['all'] for all services. Options: ec2, sagemaker, sagemaker_autoscaling, ecs, eks, nat_gateway, rds, lambda, opensearch, kinesis, step_functions, api_gateway, sns_sqs, cloudwatch_logs, s3"
                        },
                        "regions": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of AWS regions to target. If empty, targets all regions."
                        },
                        "dry_run": {
                            "type": "boolean",
                            "description": "If true, only simulates the shutdown without making changes (default: true for safety)",
                            "default": True
                        },
                        "profile": {
                            "type": "string",
                            "description": "AWS profile name to use (optional)"
                        }
                    }
                }
            }
        }
    )
    tool_schemas.append(tool_schema)
