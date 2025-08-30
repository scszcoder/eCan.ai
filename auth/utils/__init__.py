"""
Auth Utilities Package

This package provides utility functions for authentication operations.
"""

from .aws_diagnostics import AWSCognitoConfigDiagnostic
from .setup_tools import setup_cognito_domain

__all__ = [
    'AWSCognitoConfigDiagnostic',
    'setup_cognito_domain'
]
