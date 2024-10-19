# import boto3

username = "abc.xyz@gmail.com"
password = "#Abc1234"

USER_POOL_ID = 'us-east-1_uUmKJUfB3'
# CLIENT_ID = '5400r8q5p9gfdhln2feqcpljsh'
# CLIENT_SECRET = ''
# CLIENT_ID = '46161uqkecob0c4netn36fuuaa'
# CLIENT_SECRET = ''
CLIENT_ID = '5bc4dq3ac6ga2f57hkbohsur3c'
CLIENT_SECRET = '1qohbck0k8n41ann5nrtc9fou999vnlnrrubgtdheo3l8kf814qc'

# auth_client = boto3.client("cognito-idp", region_name="us-east-1")

# cog = Cognito(USER_POOL_ID, CLIENT_ID, client_secret=CLIENT_SECRET, username="songc@yahoo.com")

# sign up
# response = auth_client.sign_up(
#     ClientId=os.getenv("COGNITO_USER_CLIENT_ID"),
#     Username=username,
#     Password=password,
#     UserAttributes=[{"Name": "email", "Value": username}],
# )

# Initiating the Authentication,
# response = auth_client.initiate_auth(
#     ClientId=os.getenv("COGNITO_USER_CLIENT_ID"),
#     AuthFlow="USER_PASSWORD_AUTH",
#     AuthParameters={"USERNAME": username, "PASSWORD": password},
# )

# From the JSON response you are accessing the AccessToken
# print(response)
# Getting the user details.
# access_token = response["AuthenticationResult"]["AccessToken"]

# response = client.get_user(AccessToken=access_token)
# print(response)