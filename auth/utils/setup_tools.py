#!/usr/bin/env python3
"""
Setup Tools for Cognito Configuration
Consolidated setup utilities for AWS Cognito configuration.
"""

import boto3
from botocore.exceptions import ClientError
from auth.auth_config import AuthConfig


def setup_cognito_domain(domain_name: str = "ecan-auth") -> bool:
    """
    Setup Cognito User Pool domain for Hosted UI.
    
    Args:
        domain_name: Domain name to create
        
    Returns:
        True if successful, False otherwise
    """
    try:
        user_pool_id = AuthConfig.COGNITO.USER_POOL_ID
        region = AuthConfig.COGNITO.REGION
        
        cognito_idp = boto3.client('cognito-idp', region_name=region)
        
        print(f"🔧 Setting up Cognito domain: {domain_name}")
        print(f"   User Pool ID: {user_pool_id}")
        
        # Create domain
        try:
            response = cognito_idp.create_user_pool_domain(
                Domain=domain_name,
                UserPoolId=user_pool_id
            )
            print(f"✅ Domain created: https://{domain_name}.auth.{region}.amazoncognito.com")
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'InvalidParameterException':
                if 'already exists' in str(e):
                    print(f"✅ Domain already exists: https://{domain_name}.auth.{region}.amazoncognito.com")
                else:
                    print(f"❌ Domain creation failed: {e}")
                    return False
            else:
                print(f"❌ Domain creation failed: {e}")
                return False
        
        return True
        
    except Exception as e:
        print(f"❌ Setup failed: {e}")
        return False


def check_app_client_config() -> bool:
    """
    Check and display app client configuration.
    
    Returns:
        True if configuration is correct, False otherwise
    """
    try:
        user_pool_id = AuthConfig.COGNITO.USER_POOL_ID
        client_id = AuthConfig.COGNITO.CLIENT_ID
        region = AuthConfig.COGNITO.REGION
        
        cognito_idp = boto3.client('cognito-idp', region_name=region)
        
        print(f"\n🔍 Checking app client configuration...")
        
        # Get app client details
        response = cognito_idp.describe_user_pool_client(
            UserPoolId=user_pool_id,
            ClientId=client_id
        )
        
        client_config = response['UserPoolClient']
        
        print(f"   Client ID: {client_id}")
        print(f"   Client Name: {client_config.get('ClientName', 'N/A')}")
        
        # Check callback URLs
        callback_urls = client_config.get('CallbackURLs', [])
        print(f"   Callback URLs: {callback_urls}")
        
        # Check OAuth settings
        supported_flows = client_config.get('SupportedIdentityProviders', [])
        print(f"   Supported Identity Providers: {supported_flows}")
        
        allowed_flows = client_config.get('AllowedOAuthFlows', [])
        print(f"   Allowed OAuth Flows: {allowed_flows}")
        
        allowed_scopes = client_config.get('AllowedOAuthScopes', [])
        print(f"   Allowed OAuth Scopes: {allowed_scopes}")
        
        # Check if configuration is correct for local callback
        issues = []
        
        if 'code' not in allowed_flows:
            issues.append("Missing 'code' in AllowedOAuthFlows")
        
        if not any('localhost' in url for url in callback_urls):
            issues.append("No localhost callback URL configured")
        
        required_scopes = ['openid', 'email', 'profile']
        missing_scopes = [scope for scope in required_scopes if scope not in allowed_scopes]
        if missing_scopes:
            issues.append(f"Missing scopes: {missing_scopes}")
        
        if 'Google' not in supported_flows:
            issues.append("Google identity provider not configured")
        
        if issues:
            print(f"\n❌ Configuration issues found:")
            for issue in issues:
                print(f"   - {issue}")
            print(f"\n🔧 To fix these issues:")
            print(f"   1. Go to AWS Console → Cognito → User pools → {user_pool_id}")
            print(f"   2. App integration → App clients → {client_id} → Edit")
            print(f"   3. Update the configuration as needed")
        else:
            print(f"\n✅ App client configuration looks good!")
        
        return len(issues) == 0
        
    except Exception as e:
        print(f"❌ Failed to check app client: {e}")
        return False
