#!/usr/bin/env python3
"""
AWS Cognito Configuration Diagnostics
Consolidated diagnostic tools for AWS Cognito Identity Pool and IAM role configuration.
"""

import json
import boto3
import yaml
import os
from typing import Dict, Any, Optional
from botocore.exceptions import ClientError


class AWSCognitoConfigDiagnostic:
    """Diagnose AWS Cognito Identity Pool and IAM role configuration."""
    
    def __init__(self, config_path: str = None):
        """Initialize diagnostic tool."""
        self.config_path = config_path or os.path.join(os.path.dirname(__file__), '..', 'auth_config.yml')
        self.config = self._load_config()
        self.region = self.config.get('COGNITO', {}).get('REGION', 'us-east-1')
        self.identity_pool_id = self.config.get('COGNITO', {}).get('IDENTITY_POOL_ID')
        
        if not self.identity_pool_id:
            raise ValueError("Identity Pool ID not found in auth_config.yml")
        
        # Initialize AWS clients
        try:
            self.cognito_identity = boto3.client('cognito-identity', region_name=self.region)
            self.iam = boto3.client('iam', region_name=self.region)
        except Exception as e:
            print(f"❌ Failed to initialize AWS clients: {e}")
            print("   Make sure AWS credentials are configured: aws configure")
            raise
    
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from YAML file."""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except Exception as e:
            print(f"❌ Failed to load config from {self.config_path}: {e}")
            raise
    
    def check_identity_pool(self) -> Dict[str, Any]:
        """Check Identity Pool configuration."""
        print("🔍 Checking Identity Pool configuration...")
        result = {'exists': False, 'config': None, 'error': None}
        
        try:
            pool_config = self.cognito_identity.describe_identity_pool(
                IdentityPoolId=self.identity_pool_id
            )
            result['exists'] = True
            result['config'] = pool_config
            
            print(f"✅ Identity Pool exists: {pool_config['IdentityPoolName']}")
            print(f"   Pool ID: {pool_config['IdentityPoolId']}")
            print(f"   Allow unauthenticated: {pool_config['AllowUnauthenticatedIdentities']}")
            
            # Check supported identity providers
            if 'SupportedLoginProviders' in pool_config:
                print(f"   Supported providers: {list(pool_config['SupportedLoginProviders'].keys())}")
            else:
                print("   No supported login providers configured")
            
        except ClientError as e:
            result['error'] = str(e)
            print(f"❌ Identity Pool check failed: {e}")
        
        return result
    
    def check_identity_pool_roles(self) -> Dict[str, Any]:
        """Check IAM roles assigned to Identity Pool."""
        print("\n🔍 Checking Identity Pool role assignments...")
        result = {'roles': {}, 'role_mappings': {}, 'error': None}
        
        try:
            roles_response = self.cognito_identity.get_identity_pool_roles(
                IdentityPoolId=self.identity_pool_id
            )
            
            result['roles'] = roles_response.get('Roles', {})
            result['role_mappings'] = roles_response.get('RoleMappings', {})
            
            print(f"   Identity Pool ID: {roles_response['IdentityPoolId']}")
            
            if result['roles']:
                print("   Assigned roles:")
                for role_type, role_arn in result['roles'].items():
                    print(f"     {role_type}: {role_arn}")
            else:
                print("   ❌ No roles assigned to Identity Pool!")
            
            if result['role_mappings']:
                print("   Role mappings:")
                for provider, mapping in result['role_mappings'].items():
                    print(f"     {provider}: {mapping}")
            else:
                print("   No role mappings configured")
                
        except ClientError as e:
            result['error'] = str(e)
            print(f"❌ Role assignment check failed: {e}")
        
        return result
    
    def run_complete_diagnosis(self) -> Dict[str, Any]:
        """Run complete diagnostic check."""
        print("=" * 70)
        print("🚀 AWS COGNITO IDENTITY POOL DIAGNOSTIC")
        print("=" * 70)
        print(f"Identity Pool ID: {self.identity_pool_id}")
        print(f"Region: {self.region}")
        print()
        
        diagnosis = {}
        
        # Step 1: Check Identity Pool
        diagnosis['identity_pool'] = self.check_identity_pool()
        
        if not diagnosis['identity_pool']['exists']:
            print("\n❌ Cannot proceed - Identity Pool does not exist or is not accessible")
            return diagnosis
        
        # Step 2: Check role assignments
        diagnosis['role_assignments'] = self.check_identity_pool_roles()
        
        # Summary
        print("\n" + "=" * 70)
        print("📋 DIAGNOSIS SUMMARY")
        print("=" * 70)
        
        issues = []
        
        if not diagnosis['identity_pool']['exists']:
            issues.append("Identity Pool does not exist")
        
        if not diagnosis['role_assignments']['roles']:
            issues.append("No IAM roles assigned to Identity Pool")
        
        if issues:
            print("❌ Issues found:")
            for i, issue in enumerate(issues, 1):
                print(f"   {i}. {issue}")
        else:
            print("✅ No issues found - configuration appears correct!")
        
        return diagnosis
